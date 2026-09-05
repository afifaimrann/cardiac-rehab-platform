"""Six-minute walk test: screening, recording and history."""
from typing import Annotated, List, Optional

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import (
    AssignedPatient, ClinicianUser, CurrentUser, DbSession, OwnPatientProfile,
)
from app.models.assessment import WalkTest
from app.models.enums import FlagSource
from app.models.user import PatientProfile
from app.models.clinical import VitalsRecord
from app.schemas.assessment import (
    PrefillScreening, PrefillVitals, ScreeningRequest, ScreeningResponse,
    WalkTestChange, WalkTestCreate, WalkTestCreateResponse, WalkTestPrefill,
    WalkTestRead,
)
from app.schemas.clinical import RiskFlagRead
from app.services import walk_test as service
from app.services.flags import persist_flags

router = APIRouter(prefix="/walk-tests", tags=["walk test"])

Limit = Annotated[int, Query(ge=1, le=50)]


@router.post(
    "/screening",
    response_model=ScreeningResponse,
    summary="Check contraindications before a six-minute walk test",
)
async def screen_for_walk_test(payload: ScreeningRequest, _: CurrentUser) -> ScreeningResponse:
    """Run the protocol's contraindication check.

    Separate from recording a result, and meant to be called first: a test with
    an absolute contraindication should never be started, and finding that out
    afterwards is not useful.
    """
    result = service.screen(**payload.model_dump())
    return ScreeningResponse(
        cleared=result.cleared,
        absolute_blocks=result.absolute_blocks,
        relative_cautions=result.relative_cautions,
        summary=result.summary,
    )


async def _previous_test(db, patient_id: str, exclude_id: Optional[str] = None) -> Optional[WalkTest]:
    stmt = select(WalkTest).where(WalkTest.patient_id == patient_id)
    if exclude_id:
        stmt = stmt.where(WalkTest.id != exclude_id)
    stmt = stmt.order_by(WalkTest.performed_at.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _record(
    db, profile: PatientProfile, payload: WalkTestCreate, conducted_by_id: Optional[str],
) -> WalkTestCreateResponse:
    previous = await _previous_test(db, profile.id)

    data = payload.model_dump(exclude={"weight_kg"}, exclude_none=True)
    test = WalkTest(patient_id=profile.id, conducted_by_id=conducted_by_id, **data)

    predicted, percent, below = service.interpret(test, profile, payload.weight_kg)
    test.predicted_distance_m = predicted
    test.percent_predicted = percent
    test.below_lower_limit = below

    db.add(test)
    await db.flush()

    flags = await persist_flags(
        db, profile, FlagSource.WALK_TEST, test.id, service.evaluate(test, previous)
    )
    await db.commit()
    await db.refresh(test)

    change = service.change_since(test, previous)
    return WalkTestCreateResponse(
        walk_test=WalkTestRead.model_validate(test),
        change=WalkTestChange(**change) if change else None,
        flags_raised=[RiskFlagRead.model_validate(f) for f in flags],
    )


async def _latest_vitals(db, patient_id: str) -> Optional[VitalsRecord]:
    stmt = (
        select(VitalsRecord).where(VitalsRecord.patient_id == patient_id)
        .order_by(VitalsRecord.recorded_at.desc()).limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _latest_weight(db, patient_id: str) -> Optional[VitalsRecord]:
    """The most recent record that actually carries a weight.

    Separate from the latest vitals because weight is usually logged less often
    than blood pressure, and the newest record is frequently the one without it.
    """
    stmt = (
        select(VitalsRecord)
        .where(VitalsRecord.patient_id == patient_id, VitalsRecord.weight_kg.is_not(None))
        .order_by(VitalsRecord.recorded_at.desc()).limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _prefill(db, profile: PatientProfile) -> WalkTestPrefill:
    vitals = await _latest_vitals(db, profile.id)
    weight_record = await _latest_weight(db, profile.id)
    previous = await _previous_test(db, profile.id)

    weight = weight_record.weight_kg if weight_record else None

    screening = None
    if previous is not None and previous.screen_acs_within_30_days is not None:
        screening = PrefillScreening(
            answered_at=previous.performed_at,
            acs_within_30_days=bool(previous.screen_acs_within_30_days),
            unstable_angina=bool(previous.screen_unstable_angina),
            syncope_history=bool(previous.screen_syncope_history),
            acute_respiratory_failure=bool(previous.screen_acute_respiratory_failure),
        )

    return WalkTestPrefill(
        vitals=PrefillVitals(
            recorded_at=vitals.recorded_at,
            heart_rate=vitals.heart_rate,
            systolic=vitals.systolic,
            diastolic=vitals.diastolic,
            spo2=vitals.spo2,
            weight_kg=vitals.weight_kg,
            stale=service.vitals_are_stale(vitals.recorded_at),
        ) if vitals else None,
        weight_kg=weight,
        weight_recorded_at=weight_record.recorded_at if weight_record else None,
        height_cm=profile.height_cm,
        sex_at_birth=profile.sex_at_birth,
        age=service.age_from(profile.date_of_birth),
        course_length_m=previous.course_length_m if previous else 30.0,
        missing_for_prediction=service.prediction_inputs_missing(profile, weight),
        previous_screening=screening,
        previous_distance_m=previous.distance_m if previous else None,
        previous_performed_at=previous.performed_at if previous else None,
    )


@router.get(
    "/prefill", response_model=WalkTestPrefill,
    summary="Values already on record, to start a test from",
)
async def prefill_own(profile: OwnPatientProfile, db: DbSession) -> WalkTestPrefill:
    """Everything the record already knows about this patient.

    The test is long enough without retyping a resting heart rate that was
    measured ten minutes ago and a height that has not changed since enrolment.
    Every value comes back with the time it was recorded so the person running
    the test confirms a reading rather than inheriting one blindly.
    """
    return await _prefill(db, profile)


@router.get(
    "/patients/{patient_id}/prefill", response_model=WalkTestPrefill, tags=["clinician"],
    summary="Values already on record for an assigned patient",
)
async def prefill_for_patient(patient: AssignedPatient, db: DbSession) -> WalkTestPrefill:
    return await _prefill(db, patient)


@router.post(
    "", response_model=WalkTestCreateResponse, status_code=status.HTTP_201_CREATED,
    summary="Record your own six-minute walk test",
)
async def create_own(
    payload: WalkTestCreate, profile: OwnPatientProfile, db: DbSession
) -> WalkTestCreateResponse:
    return await _record(db, profile, payload, conducted_by_id=None)


@router.get("", response_model=List[WalkTestRead], summary="Your own test history")
async def list_own(profile: OwnPatientProfile, db: DbSession, limit: Limit = 20) -> List[WalkTest]:
    result = await db.execute(
        select(WalkTest).where(WalkTest.patient_id == profile.id)
        .order_by(WalkTest.performed_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


@router.post(
    "/patients/{patient_id}", response_model=WalkTestCreateResponse,
    status_code=status.HTTP_201_CREATED, tags=["clinician"],
    summary="Record a supervised test for an assigned patient",
)
async def create_for_patient(
    payload: WalkTestCreate, patient: AssignedPatient, clinician: ClinicianUser, db: DbSession
) -> WalkTestCreateResponse:
    return await _record(db, patient, payload, conducted_by_id=clinician.id)


@router.get(
    "/patients/{patient_id}", response_model=List[WalkTestRead], tags=["clinician"],
    summary="Test history for an assigned patient",
)
async def list_for_patient(
    patient: AssignedPatient, db: DbSession, limit: Limit = 20
) -> List[WalkTest]:
    result = await db.execute(
        select(WalkTest).where(WalkTest.patient_id == patient.id)
        .order_by(WalkTest.performed_at.desc()).limit(limit)
    )
    return list(result.scalars().all())

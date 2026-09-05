"""Patient-logged vitals and symptoms.

Every route here is scoped to the authenticated patient's own profile through
the OwnPatientProfile dependency, so no handler ever accepts a patient id from
the client -- the commonest way these APIs leak other people's records.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Query, status
from sqlalchemy import and_, or_, select

from app.api.deps import DbSession, OwnPatientProfile
from app.core.pagination import decode_cursor, next_cursor_for
from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
from app.models.enums import FlagSource
from app.schemas.clinical import (
    RiskFlagRead, SymptomCreate, SymptomCreateResponse, SymptomRead,
    VitalsCreate, VitalsCreateResponse, VitalsRead,
)
from app.schemas.common import CursorPage
from app.services.flags import persist_flags
from app.services.risk_rules import evaluate_symptom, evaluate_vitals

router = APIRouter(prefix="/vitals", tags=["vitals"])
symptom_router = APIRouter(prefix="/symptoms", tags=["symptoms"])
flag_router = APIRouter(prefix="/flags", tags=["vitals"])

PageLimit = Annotated[int, Query(ge=1, le=100, description="Rows per page.")]
Cursor = Annotated[Optional[str], Query(description="next_cursor from the previous page.")]


@router.post(
    "",
    response_model=VitalsCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a vitals reading",
)
async def create_vitals(
    payload: VitalsCreate, profile: OwnPatientProfile, db: DbSession
) -> VitalsCreateResponse:
    """Store a reading and evaluate it against the risk rules in one transaction."""
    record = VitalsRecord(patient_id=profile.id, **payload.model_dump(exclude_none=True))
    db.add(record)
    await db.flush()  # assign the id the flags will reference

    results = evaluate_vitals(record, profile)
    flags = await persist_flags(db, profile, FlagSource.VITALS, record.id, results)

    await db.commit()
    await db.refresh(record)
    return VitalsCreateResponse(
        vitals=VitalsRead.model_validate(record),
        flags_raised=[RiskFlagRead.model_validate(f) for f in flags],
    )


@router.get("", response_model=CursorPage[VitalsRead], summary="List own vitals, newest first")
async def list_vitals(
    profile: OwnPatientProfile, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[VitalsRead]:
    stmt = select(VitalsRecord).where(VitalsRecord.patient_id == profile.id)

    if cursor:
        ts, row_id = decode_cursor(cursor)
        # Strictly "older than the last row seen", with the id breaking ties.
        stmt = stmt.where(
            or_(
                VitalsRecord.recorded_at < ts,
                and_(VitalsRecord.recorded_at == ts, VitalsRecord.id < row_id),
            )
        )

    stmt = stmt.order_by(VitalsRecord.recorded_at.desc(), VitalsRecord.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return CursorPage[VitalsRead](
        items=[VitalsRead.model_validate(r) for r in rows],
        next_cursor=next_cursor_for(rows, limit, "recorded_at"),
    )


@symptom_router.post(
    "",
    response_model=SymptomCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report a symptom",
)
async def create_symptom(
    payload: SymptomCreate, profile: OwnPatientProfile, db: DbSession
) -> SymptomCreateResponse:
    report = SymptomReport(patient_id=profile.id, **payload.model_dump(exclude_none=True))
    db.add(report)
    await db.flush()

    results = evaluate_symptom(report, profile)
    flags = await persist_flags(db, profile, FlagSource.SYMPTOM, report.id, results)

    await db.commit()
    await db.refresh(report)
    return SymptomCreateResponse(
        symptom=SymptomRead.model_validate(report),
        flags_raised=[RiskFlagRead.model_validate(f) for f in flags],
    )


@symptom_router.get(
    "", response_model=CursorPage[SymptomRead], summary="List own symptoms, newest first"
)
async def list_symptoms(
    profile: OwnPatientProfile, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[SymptomRead]:
    stmt = select(SymptomReport).where(SymptomReport.patient_id == profile.id)
    if cursor:
        ts, row_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                SymptomReport.recorded_at < ts,
                and_(SymptomReport.recorded_at == ts, SymptomReport.id < row_id),
            )
        )
    stmt = stmt.order_by(SymptomReport.recorded_at.desc(), SymptomReport.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return CursorPage[SymptomRead](
        items=[SymptomRead.model_validate(r) for r in rows],
        next_cursor=next_cursor_for(rows, limit, "recorded_at"),
    )


@flag_router.get(
    "",
    response_model=CursorPage[RiskFlagRead],
    summary="Flags raised on your own records",
)
async def list_own_flags(
    profile: OwnPatientProfile, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[RiskFlagRead]:
    """A patient can see what was flagged on their own data.

    Withholding this would be odd: the flag was raised by their reading, they
    were already told at the time, and the clinician-facing queue is separate.
    """
    stmt = select(RiskFlag).where(RiskFlag.patient_id == profile.id)
    if cursor:
        ts, row_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(RiskFlag.created_at < ts, and_(RiskFlag.created_at == ts, RiskFlag.id < row_id))
        )
    stmt = stmt.order_by(RiskFlag.created_at.desc(), RiskFlag.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return CursorPage[RiskFlagRead](
        items=[RiskFlagRead.model_validate(r) for r in rows],
        next_cursor=next_cursor_for(rows, limit, "created_at"),
    )

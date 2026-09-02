"""Clinician caseload, adherence overview and the risk-flag queue."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select

from app.api.deps import AdminUser, AssignedPatient, ClinicianUser, DbSession
from app.core.pagination import decode_cursor, next_cursor_for
from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
from app.models.enums import FlagStatus, Severity, UserRole
from app.models.program import ExercisePlan, ExerciseSession
from app.models.user import PatientProfile, User
from app.schemas.clinical import FlagResolve, RiskFlagRead, SymptomRead, VitalsRead
from app.schemas.clinician import Caseload, CaseloadRow, PatientAssign
from app.schemas.common import CursorPage
from app.schemas.user import PatientProfileRead

router = APIRouter(prefix="/clinician", tags=["clinician"])

Window = Annotated[int, Query(ge=7, le=365, description="Adherence window in days.")]
PageLimit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[Optional[str], Query()]

_SEVERITY_ORDER = {Severity.MILD: 0, Severity.MODERATE: 1, Severity.SEVERE: 2}


@router.get("/caseload", response_model=Caseload, summary="Assigned patients with status")
async def read_caseload(
    clinician: ClinicianUser, db: DbSession, window_days: Window = 28
) -> Caseload:
    """The roster in a fixed number of queries.

    Deliberately five aggregate queries rather than one per patient: the obvious
    implementation issues a query per row and degrades linearly with caseload
    size. Cost here is constant in the number of patients.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    # 1. The caseload itself. An admin sees every patient.
    stmt = select(PatientProfile, User).join(User, PatientProfile.user_id == User.id)
    if clinician.role is not UserRole.ADMIN:
        stmt = stmt.where(PatientProfile.clinician_id == clinician.id)
    rows = list((await db.execute(stmt)).all())
    if not rows:
        return Caseload(window_days=window_days, patients=[])

    ids = [profile.id for profile, _ in rows]

    # 2. Open flags per patient.
    flag_rows = (await db.execute(
        select(RiskFlag.patient_id, RiskFlag.severity, func.count(RiskFlag.id))
        .where(RiskFlag.patient_id.in_(ids), RiskFlag.status == FlagStatus.OPEN)
        .group_by(RiskFlag.patient_id, RiskFlag.severity)
    )).all()
    open_counts: dict[str, int] = {}
    worst: dict[str, Severity] = {}
    for pid, severity, count in flag_rows:
        open_counts[pid] = open_counts.get(pid, 0) + count
        if pid not in worst or _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[worst[pid]]:
            worst[pid] = severity

    # 3. Completed sessions in the window.
    session_rows = (await db.execute(
        select(ExerciseSession.patient_id, func.count(ExerciseSession.id))
        .where(
            ExerciseSession.patient_id.in_(ids),
            ExerciseSession.completed.is_(True),
            ExerciseSession.performed_at >= since,
        )
        .group_by(ExerciseSession.patient_id)
    )).all()
    sessions_done = {pid: count for pid, count in session_rows}

    # 4. Active plans, for the adherence denominator.
    plan_rows = (await db.execute(
        select(ExercisePlan).where(
            ExercisePlan.patient_id.in_(ids), ExercisePlan.is_active.is_(True)
        )
    )).scalars().all()
    plans = {p.patient_id: p for p in plan_rows}

    # 5. Most recent vitals timestamp.
    vitals_rows = (await db.execute(
        select(VitalsRecord.patient_id, func.max(VitalsRecord.recorded_at))
        .where(VitalsRecord.patient_id.in_(ids))
        .group_by(VitalsRecord.patient_id)
    )).all()
    last_vitals = {pid: ts for pid, ts in vitals_rows}

    weeks = window_days / 7.0
    patients: List[CaseloadRow] = []
    for profile, user in rows:
        plan = plans.get(profile.id)
        done = sessions_done.get(profile.id, 0)
        expected = plan.sessions_per_week * weeks if plan else 0
        patients.append(
            CaseloadRow(
                patient_id=profile.id,
                full_name=user.full_name,
                email=user.email,
                primary_condition=profile.primary_condition,
                open_flags=open_counts.get(profile.id, 0),
                highest_open_severity=worst.get(profile.id),
                last_vitals_at=last_vitals.get(profile.id),
                sessions_completed=done,
                adherence_pct=round(done / expected * 100.0, 1) if expected else None,
            )
        )

    # Most urgent first: severity, then flag count, then worst adherence.
    patients.sort(
        key=lambda p: (
            -_SEVERITY_ORDER.get(p.highest_open_severity, -1),
            -p.open_flags,
            p.adherence_pct if p.adherence_pct is not None else 999,
        )
    )
    return Caseload(window_days=window_days, patients=patients)


@router.get(
    "/flags", response_model=CursorPage[RiskFlagRead], summary="Risk-flag queue, newest first"
)
async def list_flags(
    clinician: ClinicianUser,
    db: DbSession,
    flag_status: Annotated[FlagStatus, Query(alias="status")] = FlagStatus.OPEN,
    limit: PageLimit = 20,
    cursor: Cursor = None,
) -> CursorPage[RiskFlagRead]:
    stmt = select(RiskFlag).where(RiskFlag.status == flag_status)
    if clinician.role is not UserRole.ADMIN:
        # Restrict to the caller's own caseload at the query level rather than
        # filtering after the fact.
        stmt = stmt.where(
            RiskFlag.patient_id.in_(
                select(PatientProfile.id).where(PatientProfile.clinician_id == clinician.id)
            )
        )
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


@router.patch(
    "/flags/{flag_id}", response_model=RiskFlagRead, summary="Acknowledge or resolve a flag"
)
async def resolve_flag(
    flag_id: str, payload: FlagResolve, clinician: ClinicianUser, db: DbSession
) -> RiskFlag:
    flag = await db.get(RiskFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")

    if clinician.role is not UserRole.ADMIN:
        profile = await db.get(PatientProfile, flag.patient_id)
        if profile is None or profile.clinician_id != clinician.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")

    if payload.status is FlagStatus.OPEN:
        raise HTTPException(
            status_code=422,  # Starlette renamed this constant; the code is stable.
            detail="A flag cannot be reopened through this endpoint.",
        )

    flag.status = payload.status
    flag.resolution_note = payload.resolution_note
    flag.resolved_by_id = clinician.id
    flag.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(flag)
    return flag


@router.get(
    "/patients/{patient_id}",
    response_model=PatientProfileRead,
    summary="Profile of an assigned patient",
)
async def read_patient(patient: AssignedPatient) -> PatientProfile:
    return patient


@router.get(
    "/patients/{patient_id}/vitals",
    response_model=CursorPage[VitalsRead],
    summary="Vitals for an assigned patient",
)
async def read_patient_vitals(
    patient: AssignedPatient, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[VitalsRead]:
    stmt = select(VitalsRecord).where(VitalsRecord.patient_id == patient.id)
    if cursor:
        ts, row_id = decode_cursor(cursor)
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


@router.get(
    "/patients/{patient_id}/symptoms",
    response_model=CursorPage[SymptomRead],
    summary="Symptoms for an assigned patient",
)
async def read_patient_symptoms(
    patient: AssignedPatient, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[SymptomRead]:
    stmt = select(SymptomReport).where(SymptomReport.patient_id == patient.id)
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


@router.patch(
    "/patients/{patient_id}/assignment",
    response_model=PatientProfileRead,
    summary="Assign a patient to a clinician (admin only)",
)
async def assign_patient(
    patient_id: str, payload: PatientAssign, _: AdminUser, db: DbSession
) -> PatientProfile:
    profile = await db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if payload.clinician_id is not None:
        clinician = await db.get(User, payload.clinician_id)
        if clinician is None or clinician.role not in (UserRole.CLINICIAN, UserRole.ADMIN):
            raise HTTPException(
                status_code=422,  # Starlette renamed this constant; the code is stable.
                detail="clinician_id must reference a clinician account",
            )

    profile.clinician_id = payload.clinician_id
    await db.commit()
    await db.refresh(profile)
    return profile

"""Exercise plans (clinician-prescribed) and sessions (patient-logged)."""
from typing import Annotated, List, Optional

from fastapi import APIRouter, Query, status
from sqlalchemy import and_, or_, select, update

from app.api.deps import AssignedPatient, ClinicianUser, DbSession, OwnPatientProfile
from app.core.pagination import decode_cursor, next_cursor_for
from app.models.enums import FlagSource
from app.models.program import ExercisePlan, ExerciseSession
from app.schemas.clinical import RiskFlagRead
from app.schemas.common import CursorPage
from app.schemas.program import (
    AdherenceSummary, PlanCreate, PlanRead, SessionCreate, SessionCreateResponse, SessionRead,
)
from app.services.adherence import compute_adherence, get_active_plan
from app.services.flags import persist_flags
from app.services.risk_rules import evaluate_session

router = APIRouter(tags=["program"])

PageLimit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[Optional[str], Query(description="next_cursor from the previous page.")]
Window = Annotated[int, Query(ge=7, le=365, description="Rolling window in days.")]


# --------------------------------------------------------------------------
# Patient-facing
# --------------------------------------------------------------------------

@router.get("/plans/active", response_model=Optional[PlanRead], summary="Own active plan")
async def read_active_plan(profile: OwnPatientProfile, db: DbSession):
    return await get_active_plan(db, profile.id)


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log an exercise session",
)
async def log_session(
    payload: SessionCreate, profile: OwnPatientProfile, db: DbSession
) -> SessionCreateResponse:
    """Attach the session to whichever plan is active at the time of logging."""
    plan = await get_active_plan(db, profile.id)
    session = ExerciseSession(
        patient_id=profile.id,
        plan_id=plan.id if plan else None,
        **payload.model_dump(exclude_none=True),
    )
    db.add(session)
    await db.flush()

    flags = await persist_flags(
        db, profile, FlagSource.SESSION, session.id, evaluate_session(session, profile)
    )
    await db.commit()
    await db.refresh(session)
    return SessionCreateResponse(
        session=SessionRead.model_validate(session),
        flags_raised=[RiskFlagRead.model_validate(f) for f in flags],
    )


@router.get(
    "/sessions", response_model=CursorPage[SessionRead], summary="List own sessions, newest first"
)
async def list_sessions(
    profile: OwnPatientProfile, db: DbSession, limit: PageLimit = 20, cursor: Cursor = None
) -> CursorPage[SessionRead]:
    stmt = select(ExerciseSession).where(ExerciseSession.patient_id == profile.id)
    if cursor:
        ts, row_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                ExerciseSession.performed_at < ts,
                and_(ExerciseSession.performed_at == ts, ExerciseSession.id < row_id),
            )
        )
    stmt = stmt.order_by(
        ExerciseSession.performed_at.desc(), ExerciseSession.id.desc()
    ).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return CursorPage[SessionRead](
        items=[SessionRead.model_validate(r) for r in rows],
        next_cursor=next_cursor_for(rows, limit, "performed_at"),
    )


@router.get("/adherence", response_model=AdherenceSummary, summary="Own adherence summary")
async def read_own_adherence(
    profile: OwnPatientProfile, db: DbSession, window_days: Window = 28
) -> AdherenceSummary:
    return await compute_adherence(db, profile.id, window_days)


# --------------------------------------------------------------------------
# Clinician-facing
# --------------------------------------------------------------------------

@router.post(
    "/patients/{patient_id}/plans",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
    tags=["clinician"],
    summary="Prescribe a plan for an assigned patient",
)
async def prescribe_plan(
    payload: PlanCreate, patient: AssignedPatient, clinician: ClinicianUser, db: DbSession
) -> ExercisePlan:
    """Prescribing supersedes any existing plan rather than editing it.

    Old plans are deactivated, not deleted, so a session logged last month can
    still be read against the plan that was in force when it happened.
    """
    await db.execute(
        update(ExercisePlan)
        .where(ExercisePlan.patient_id == patient.id, ExercisePlan.is_active.is_(True))
        .values(is_active=False)
    )
    plan = ExercisePlan(
        patient_id=patient.id, prescribed_by_id=clinician.id, **payload.model_dump()
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.get(
    "/patients/{patient_id}/plans",
    response_model=List[PlanRead],
    tags=["clinician"],
    summary="Plan history for an assigned patient",
)
async def list_patient_plans(patient: AssignedPatient, db: DbSession) -> List[ExercisePlan]:
    result = await db.execute(
        select(ExercisePlan)
        .where(ExercisePlan.patient_id == patient.id)
        .order_by(ExercisePlan.created_at.desc())
    )
    return list(result.scalars().all())

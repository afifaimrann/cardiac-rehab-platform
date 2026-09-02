"""Adherence calculation.

Adherence is completed sessions against the active plan's weekly target,
prorated over the requested window. Sessions logged as not completed are
excluded from the numerator but still stored -- an abandoned session is
clinically meaningful and raises its own flag.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.program import ExercisePlan, ExerciseSession
from app.schemas.program import AdherenceSummary


async def get_active_plan(db: AsyncSession, patient_id: str) -> Optional[ExercisePlan]:
    result = await db.execute(
        select(ExercisePlan)
        .where(ExercisePlan.patient_id == patient_id, ExercisePlan.is_active.is_(True))
        .order_by(ExercisePlan.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def compute_adherence(
    db: AsyncSession, patient_id: str, window_days: int = 28
) -> AdherenceSummary:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    plan = await get_active_plan(db, patient_id)

    # One aggregate query rather than loading rows: adherence never needs the
    # individual sessions, only their count and total minutes.
    result = await db.execute(
        select(
            func.count(ExerciseSession.id),
            func.coalesce(func.sum(ExerciseSession.duration_minutes), 0),
        ).where(
            ExerciseSession.patient_id == patient_id,
            ExerciseSession.completed.is_(True),
            ExerciseSession.performed_at >= since,
        )
    )
    completed_count, completed_minutes = result.one()

    if plan is None:
        return AdherenceSummary(
            patient_id=patient_id,
            plan_id=None,
            window_days=window_days,
            sessions_expected=0.0,
            sessions_completed=completed_count,
            minutes_expected=0.0,
            minutes_completed=int(completed_minutes),
            adherence_pct=None,
        )

    weeks = window_days / 7.0
    sessions_expected = plan.sessions_per_week * weeks
    minutes_expected = sessions_expected * plan.minutes_per_session
    pct = (completed_count / sessions_expected * 100.0) if sessions_expected else None

    return AdherenceSummary(
        patient_id=patient_id,
        plan_id=plan.id,
        window_days=window_days,
        sessions_expected=round(sessions_expected, 2),
        sessions_completed=completed_count,
        minutes_expected=round(minutes_expected, 2),
        minutes_completed=int(completed_minutes),
        adherence_pct=round(pct, 1) if pct is not None else None,
    )

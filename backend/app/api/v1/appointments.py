"""Booking, cancelling and running consultations.

A patient books themselves: the rota is published by their clinician, this
module turns it into open slots, and the patient takes one. Nothing here
requires a clinician to answer a message first, which is the point -- the
back-and-forth of arranging a time is the part that does not need a person.
"""
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import (
    AssignedPatient, ClinicianUser, CurrentUser, DbSession, OwnPatientProfile,
)
from app.models.care import Appointment, AvailabilityRule
from app.models.enums import AppointmentMode, AppointmentStatus, UserRole
from app.models.user import PatientProfile, User
from app.schemas.care import (
    AppointmentBook, AppointmentCancel, AppointmentRead, AppointmentUpdate,
    AvailabilityRuleCreate, AvailabilityRuleRead, SlotRead,
)
from app.services import scheduling
from app.services.meetings import MeetingProviderUnavailable, create_room

router = APIRouter(prefix="/appointments", tags=["appointments"])

Horizon = Annotated[int, Query(ge=1, le=scheduling.MAX_HORIZON_DAYS)]

# Statuses that still occupy a time in the diary. A cancelled appointment does
# not, and its slot must become bookable again.
LIVE_STATUSES = (AppointmentStatus.SCHEDULED, AppointmentStatus.COMPLETED)


async def _read(db, appointment: Appointment) -> AppointmentRead:
    """Attach the names both sides need, which neither row carries."""
    clinician = await db.get(User, appointment.clinician_id)
    profile = await db.get(PatientProfile, appointment.patient_id)
    patient_user = await db.get(User, profile.user_id) if profile else None

    payload = AppointmentRead.model_validate(appointment)
    payload.clinician_name = clinician.full_name if clinician else None
    payload.patient_name = patient_user.full_name if patient_user else None
    return payload


async def _live_slot_keys(db, clinician_id: str) -> List[str]:
    result = await db.execute(
        select(Appointment.slot_key).where(
            Appointment.clinician_id == clinician_id,
            Appointment.slot_key.is_not(None),
            Appointment.status.in_(LIVE_STATUSES),
        )
    )
    return [k for k in result.scalars().all() if k]


async def _rules_for(db, clinician_id: str) -> List[AvailabilityRule]:
    result = await db.execute(
        select(AvailabilityRule).where(
            AvailabilityRule.clinician_id == clinician_id,
            AvailabilityRule.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------- patient ---
@router.get(
    "/slots", response_model=List[SlotRead],
    summary="Times you can book with your clinician",
)
async def open_slots(
    profile: OwnPatientProfile, db: DbSession, days: Horizon = 14,
) -> List[SlotRead]:
    """Open slots from the assigned clinician's rota, soonest first.

    Returns an empty list rather than an error when no clinician is assigned or
    none has published a rota: "nothing available yet" is a state a patient
    should see calmly, not an error page.
    """
    if not profile.clinician_id:
        return []

    rules = await _rules_for(db, profile.clinician_id)
    if not rules:
        return []

    clinician = await db.get(User, profile.clinician_id)
    slots = scheduling.generate_slots(
        rules, days=days, taken_keys=await _live_slot_keys(db, profile.clinician_id)
    )
    return [
        SlotRead(
            starts_at=s.starts_at, ends_at=s.ends_at, mode=s.mode, location=s.location,
            clinician_id=s.clinician_id,
            clinician_name=clinician.full_name if clinician else None,
        )
        for s in slots
    ]


@router.post(
    "", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED,
    summary="Book one of the open slots",
)
async def book(
    payload: AppointmentBook, profile: OwnPatientProfile, db: DbSession
) -> AppointmentRead:
    if not profile.clinician_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You do not have a clinician assigned yet, so there is nothing to book.",
        )

    rules = await _rules_for(db, profile.clinician_id)
    slots = scheduling.generate_slots(
        rules, days=scheduling.MAX_HORIZON_DAYS,
        taken_keys=await _live_slot_keys(db, profile.clinician_id),
    )
    slot = scheduling.find_slot(slots, payload.starts_at)
    if slot is None:
        # Deliberately one message for "never offered" and "just taken": the
        # patient's next action is the same either way, and distinguishing them
        # would leak which times another patient booked.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time is no longer available. Please choose another slot.",
        )

    mode = payload.mode or slot.mode
    if mode is not slot.mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"That slot is {slot.mode.value.replace('_', ' ')} only.",
        )

    appointment = Appointment(
        patient_id=profile.id,
        clinician_id=slot.clinician_id,
        slot_key=slot.key,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        mode=mode,
        location=slot.location,
        reason=payload.reason,
        status=AppointmentStatus.SCHEDULED,
    )

    if mode is AppointmentMode.ONLINE:
        try:
            meeting = create_room()
        except MeetingProviderUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        appointment.meeting_provider = meeting.provider
        appointment.meeting_room = meeting.room
        appointment.meeting_url = meeting.url

    db.add(appointment)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Two patients posting the same slot in the same instant: the unique
        # index on slot_key decides, and the loser is told the same thing as
        # anyone else who was too late.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That time was taken a moment ago. Please choose another slot.",
        ) from exc

    await db.refresh(appointment)
    return await _read(db, appointment)


@router.get("", response_model=List[AppointmentRead], summary="Your appointments")
async def list_own(
    profile: OwnPatientProfile, db: DbSession,
    upcoming_only: bool = Query(default=False),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> List[AppointmentRead]:
    stmt = select(Appointment).where(Appointment.patient_id == profile.id)
    if upcoming_only:
        stmt = stmt.where(
            Appointment.starts_at >= datetime.now(timezone.utc),
            Appointment.status == AppointmentStatus.SCHEDULED,
        ).order_by(Appointment.starts_at.asc())
    else:
        stmt = stmt.order_by(Appointment.starts_at.desc())

    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [await _read(db, a) for a in rows]


@router.post(
    "/{appointment_id}/cancel", response_model=AppointmentRead,
    summary="Cancel an appointment",
)
async def cancel(
    appointment_id: str, payload: AppointmentCancel, user: CurrentUser, db: DbSession
) -> AppointmentRead:
    """Cancel, as either side.

    Ownership is checked here rather than by a dependency because both a
    patient and their clinician may cancel the same row, and the two arrive by
    different routes through the data.
    """
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    allowed = False
    if user.role is UserRole.PATIENT:
        profile = (await db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user.id)
        )).scalar_one_or_none()
        allowed = profile is not None and appointment.patient_id == profile.id
    else:
        allowed = user.role is UserRole.ADMIN or appointment.clinician_id == user.id

    if not allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.status is not AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This appointment is already {appointment.status.value}.",
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_by_id = user.id
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancellation_reason = payload.reason
    # Releasing the key is what makes the time bookable again; the unique index
    # ignores NULLs.
    appointment.slot_key = None
    # The room dies with the booking. Leaving a live URL on a cancelled
    # appointment means a link in someone's calendar still opens a call.
    appointment.meeting_url = None
    appointment.meeting_room = None

    await db.commit()
    await db.refresh(appointment)
    return await _read(db, appointment)


# -------------------------------------------------------------- clinician ---
@router.get(
    "/availability", response_model=List[AvailabilityRuleRead], tags=["clinician"],
    summary="Your published weekly rota",
)
async def list_availability(
    clinician: ClinicianUser, db: DbSession
) -> List[AvailabilityRule]:
    return await _rules_for(db, clinician.id)


@router.post(
    "/availability", response_model=AvailabilityRuleRead,
    status_code=status.HTTP_201_CREATED, tags=["clinician"],
    summary="Publish a weekly availability window",
)
async def add_availability(
    payload: AvailabilityRuleCreate, clinician: ClinicianUser, db: DbSession
) -> AvailabilityRule:
    rule = AvailabilityRule(clinician_id=clinician.id, **payload.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete(
    "/availability/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["clinician"],
    summary="Withdraw an availability window",
)
async def remove_availability(
    rule_id: str, clinician: ClinicianUser, db: DbSession
) -> None:
    rule = await db.get(AvailabilityRule, rule_id)
    if rule is None or rule.clinician_id != clinician.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    # Deactivated, not deleted: appointments already booked under this rule
    # must remain explicable.
    rule.is_active = False
    await db.commit()


@router.get(
    "/clinic", response_model=List[AppointmentRead], tags=["clinician"],
    summary="Your diary",
)
async def clinic_diary(
    clinician: ClinicianUser, db: DbSession,
    upcoming_only: bool = Query(default=True),
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> List[AppointmentRead]:
    stmt = select(Appointment).where(Appointment.clinician_id == clinician.id)
    if upcoming_only:
        stmt = stmt.where(
            Appointment.starts_at >= datetime.now(timezone.utc),
            Appointment.status == AppointmentStatus.SCHEDULED,
        ).order_by(Appointment.starts_at.asc())
    else:
        stmt = stmt.order_by(Appointment.starts_at.desc())

    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [await _read(db, a) for a in rows]


@router.patch(
    "/{appointment_id}", response_model=AppointmentRead, tags=["clinician"],
    summary="Record the outcome of a consultation",
)
async def update_appointment(
    appointment_id: str, payload: AppointmentUpdate, clinician: ClinicianUser, db: DbSession
) -> AppointmentRead:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None or (
        clinician.role is not UserRole.ADMIN and appointment.clinician_id != clinician.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    data = payload.model_dump(exclude_none=True)
    if data.get("status") is AppointmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancel through /appointments/{id}/cancel so the slot is released.",
        )
    for field, value in data.items():
        setattr(appointment, field, value)

    await db.commit()
    await db.refresh(appointment)
    return await _read(db, appointment)


@router.get(
    "/patients/{patient_id}", response_model=List[AppointmentRead], tags=["clinician"],
    summary="Appointment history for an assigned patient",
)
async def list_for_patient(
    patient: AssignedPatient, db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> List[AppointmentRead]:
    rows = (await db.execute(
        select(Appointment).where(Appointment.patient_id == patient.id)
        .order_by(Appointment.starts_at.desc()).limit(limit)
    )).scalars().all()
    return [await _read(db, a) for a in rows]

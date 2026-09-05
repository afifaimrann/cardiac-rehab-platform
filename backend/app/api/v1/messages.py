"""Direct messages between a patient and their care team.

Deliberately separate from the AI chat. A patient asking the assistant a
question and a patient writing to their nurse are different acts with different
expectations, and merging them into one inbox would mean either a human reading
every question or a model answering something meant for a person.
"""
from datetime import datetime, timezone
from typing import Annotated, List, Optional, Sequence

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, update

from app.api.deps import AssignedPatient, ClinicianUser, DbSession, OwnPatientProfile
from app.models.care import DirectMessage
from app.models.user import PatientProfile, User
from app.schemas.care import DirectMessageRead, MessageSend, MessageThread

router = APIRouter(prefix="/messages", tags=["messages"])

Limit = Annotated[int, Query(ge=1, le=200)]


async def _hydrate(db, rows: Sequence[DirectMessage]) -> List[DirectMessageRead]:
    """Attach sender names in one query rather than one per message."""
    sender_ids = {m.sender_id for m in rows}
    senders = {}
    if sender_ids:
        result = await db.execute(select(User).where(User.id.in_(sender_ids)))
        senders = {u.id: u for u in result.scalars().all()}

    out = []
    for m in rows:
        payload = DirectMessageRead.model_validate(m)
        sender = senders.get(m.sender_id)
        payload.sender_name = sender.full_name if sender else None
        payload.sender_role = sender.role.value if sender else None
        out.append(payload)
    return out


async def _thread(
    db, profile: PatientProfile, *, reader_id: str, viewer_is_patient: bool, limit: int
) -> MessageThread:
    rows = list((await db.execute(
        select(DirectMessage).where(DirectMessage.patient_id == profile.id)
        .order_by(DirectMessage.sent_at.desc()).limit(limit)
    )).scalars().all())
    rows.reverse()  # oldest first, the order a conversation is read in

    unread = [m for m in rows if m.sender_id != reader_id and m.read_at is None]

    # Whom the reader is talking to: the patient sees their clinician, the
    # clinician sees the patient.
    counterparty: Optional[User] = None
    other_id = profile.clinician_id if viewer_is_patient else profile.user_id
    if other_id:
        counterparty = await db.get(User, other_id)

    thread = MessageThread(
        messages=await _hydrate(db, rows),
        unread_count=len(unread),
        counterparty_name=counterparty.full_name if counterparty else None,
    )

    # Opening the thread marks the other side's messages read. Done after the
    # payload is built so the caller sees which ones were unread when they
    # arrived, rather than a thread that is always fully read.
    if unread:
        await db.execute(
            update(DirectMessage)
            .where(DirectMessage.id.in_([m.id for m in unread]))
            .values(read_at=datetime.now(timezone.utc))
        )
        await db.commit()

    return thread


# ---------------------------------------------------------------- patient ---
@router.get("", response_model=MessageThread, summary="Your thread with your care team")
async def own_thread(
    profile: OwnPatientProfile, db: DbSession, limit: Limit = 100
) -> MessageThread:
    user = await db.get(User, profile.user_id)
    return await _thread(
        db, profile, reader_id=user.id, viewer_is_patient=True, limit=limit
    )


@router.post(
    "", response_model=DirectMessageRead, status_code=status.HTTP_201_CREATED,
    summary="Write to your care team",
)
async def send_as_patient(
    payload: MessageSend, profile: OwnPatientProfile, db: DbSession
) -> DirectMessageRead:
    if not profile.clinician_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You do not have a clinician assigned yet. Use the assistant, or "
            "call the number on your discharge letter if it is urgent.",
        )
    message = DirectMessage(patient_id=profile.id, sender_id=profile.user_id, body=payload.body)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return (await _hydrate(db, [message]))[0]


@router.get("/unread", summary="Unread count for the badge")
async def own_unread(profile: OwnPatientProfile, db: DbSession) -> dict:
    rows = (await db.execute(
        select(DirectMessage).where(
            DirectMessage.patient_id == profile.id,
            DirectMessage.sender_id != profile.user_id,
            DirectMessage.read_at.is_(None),
        )
    )).scalars().all()
    return {"unread_count": len(rows)}


# -------------------------------------------------------------- clinician ---
@router.get(
    "/patients/{patient_id}", response_model=MessageThread, tags=["clinician"],
    summary="Thread with an assigned patient",
)
async def patient_thread(
    patient: AssignedPatient, clinician: ClinicianUser, db: DbSession, limit: Limit = 100
) -> MessageThread:
    return await _thread(
        db, patient, reader_id=clinician.id, viewer_is_patient=False, limit=limit
    )


@router.post(
    "/patients/{patient_id}", response_model=DirectMessageRead,
    status_code=status.HTTP_201_CREATED, tags=["clinician"],
    summary="Reply to an assigned patient",
)
async def send_as_clinician(
    payload: MessageSend, patient: AssignedPatient, clinician: ClinicianUser, db: DbSession
) -> DirectMessageRead:
    message = DirectMessage(patient_id=patient.id, sender_id=clinician.id, body=payload.body)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return (await _hydrate(db, [message]))[0]

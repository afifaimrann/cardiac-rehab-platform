"""The clinician's assistant, scoped to one assigned patient."""
from typing import Annotated, List

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, select

from app.api.deps import AssignedPatient, ClinicianUser, DbSession
from app.models.care import ClinicianAssistantMessage
from app.schemas.care import AssistantAnswer, AssistantAsk, AssistantTurn
from app.services import clinician_assistant

router = APIRouter(prefix="/assistant", tags=["clinician"])

Limit = Annotated[int, Query(ge=1, le=100)]


async def _history(db, clinician_id: str, patient_id: str, limit: int) -> List[ClinicianAssistantMessage]:
    rows = list((await db.execute(
        select(ClinicianAssistantMessage).where(
            ClinicianAssistantMessage.clinician_id == clinician_id,
            ClinicianAssistantMessage.patient_id == patient_id,
        ).order_by(ClinicianAssistantMessage.created_at.desc()).limit(limit)
    )).scalars().all())
    rows.reverse()
    return rows


@router.get(
    "/patients/{patient_id}", response_model=List[AssistantTurn],
    summary="Your assistant thread about this patient",
)
async def thread(
    patient: AssignedPatient, clinician: ClinicianUser, db: DbSession, limit: Limit = 50
) -> List[ClinicianAssistantMessage]:
    return await _history(db, clinician.id, patient.id, limit)


@router.post(
    "/patients/{patient_id}", response_model=AssistantAnswer,
    status_code=status.HTTP_200_OK,
    summary="Ask the assistant about this patient",
)
async def ask(
    payload: AssistantAsk, patient: AssignedPatient, clinician: ClinicianUser, db: DbSession
) -> AssistantAnswer:
    """Ask a question answered from this patient's record.

    `patient` arrives through the AssignedPatient dependency, so the record the
    assistant can read has already been authorised for this clinician. The
    model selects tools; it never selects a patient.
    """
    prior = await _history(db, clinician.id, patient.id, clinician_assistant.HISTORY_TURNS)
    history = [{"role": m.role, "content": m.content} for m in prior]

    reply = await clinician_assistant.ask(payload.question, db, patient, history=history)

    db.add(ClinicianAssistantMessage(
        clinician_id=clinician.id, patient_id=patient.id,
        role="user", content=payload.question,
    ))
    db.add(ClinicianAssistantMessage(
        clinician_id=clinician.id, patient_id=patient.id,
        role="assistant", content=reply.answer,
        tools_used=", ".join(dict.fromkeys(reply.tools_used))[:300] or None,
    ))
    await db.commit()

    return AssistantAnswer(
        answer=reply.answer,
        tools_used=list(dict.fromkeys(reply.tools_used)),
        generated=reply.generated,
    )


@router.delete(
    "/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear your assistant thread about this patient",
)
async def clear(
    patient: AssignedPatient, clinician: ClinicianUser, db: DbSession
) -> None:
    await db.execute(
        delete(ClinicianAssistantMessage).where(
            ClinicianAssistantMessage.clinician_id == clinician.id,
            ClinicianAssistantMessage.patient_id == patient.id,
        )
    )
    await db.commit()

"""Patient question answering, by text or by voice."""
from typing import Annotated, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, or_, select

from app.api.deps import DbSession, OwnPatientProfile
from app.core.pagination import decode_cursor, next_cursor_for
from app.models.chat import Conversation, Message
from app.models.enums import FlagSource, MessageRole, Severity
from app.models.user import PatientProfile
from app.schemas.chat import (
    AskRequest, AskResponse, ConversationCreate, ConversationRead, MessageRead,
)
from app.schemas.clinical import RiskFlagRead
from app.schemas.common import CursorPage
from app.services.chat import HISTORY_TURNS, answer_question
from app.services.flags import persist_flags
from app.services.risk_rules import RuleResult
from app.services.transcription import (
    ALLOWED_CONTENT_TYPES, MAX_AUDIO_BYTES, TranscriptionUnavailable, transcribe,
)

router = APIRouter(prefix="/conversations", tags=["chat"])

PageLimit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[Optional[str], Query()]


async def _owned_conversation(
    conversation_id: str, profile: PatientProfile, db
) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    # 404 rather than 403 for someone else's conversation: the id must not be
    # usable to discover that a conversation exists.
    if conversation is None or conversation.patient_id != profile.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conversation


@router.post(
    "", response_model=ConversationRead, status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
async def create_conversation(
    payload: ConversationCreate, profile: OwnPatientProfile, db: DbSession
) -> Conversation:
    conversation = Conversation(patient_id=profile.id, title=payload.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=List[ConversationRead], summary="List own conversations")
async def list_conversations(profile: OwnPatientProfile, db: DbSession) -> List[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.patient_id == profile.id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/{conversation_id}/messages",
    response_model=CursorPage[MessageRead],
    summary="Message history, newest first",
)
async def list_messages(
    conversation_id: str, profile: OwnPatientProfile, db: DbSession,
    limit: PageLimit = 50, cursor: Cursor = None,
) -> CursorPage[MessageRead]:
    await _owned_conversation(conversation_id, profile, db)

    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if cursor:
        ts, row_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(Message.created_at < ts, and_(Message.created_at == ts, Message.id < row_id))
        )
    stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return CursorPage[MessageRead](
        items=[MessageRead.model_validate(r) for r in rows],
        next_cursor=next_cursor_for(rows, limit, "created_at"),
    )


async def _handle_question(
    conversation: Conversation, question_text: str, profile: PatientProfile, db,
    audio_filename: Optional[str] = None,
) -> AskResponse:
    """Store the question, answer it, store the answer, flag if needed."""
    question = Message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=question_text,
        transcribed_from_audio=audio_filename,
    )
    db.add(question)
    await db.flush()

    # Recent turns, oldest first, excluding the question just stored.
    previous = (await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.id != question.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(HISTORY_TURNS)
    )).scalars().all()
    history = [
        {"role": m.role.value, "content": m.content}
        for m in reversed(list(previous))
    ]

    result = await answer_question(question_text, db=db, history=history)

    answer = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=result.content,
        citations=result.citations or None,
    )
    db.add(answer)
    await db.flush()

    # A question the guardrail intercepted goes to the care team as a flag: the
    # patient has told us about a symptom, and that must not stop at a chatbot.
    flags = []
    if result.is_emergency:
        flags = await persist_flags(
            db, profile, FlagSource.CHAT, question.id,
            [RuleResult(
                "CHAT_EMERGENCY_LANGUAGE",
                Severity.SEVERE,
                f'Patient described urgent symptoms to the assistant: "{question_text[:180]}"',
            )],
        )

    # Name the conversation after its first question, for the sidebar.
    if conversation.title is None:
        conversation.title = question_text[:80]

    await db.commit()
    await db.refresh(question)
    await db.refresh(answer)

    return AskResponse(
        question=MessageRead.model_validate(question),
        answer=MessageRead.model_validate(answer),
        citations=result.citations,
        is_emergency=result.is_emergency,
        generated=result.generated,
        retrieval_mode=result.retrieval_mode,
        flags_raised=[RiskFlagRead.model_validate(f) for f in flags],
        transcript=question_text if audio_filename else None,
    )


@router.post(
    "/{conversation_id}/ask",
    response_model=AskResponse,
    summary="Ask a question as text",
)
async def ask(
    conversation_id: str, payload: AskRequest, profile: OwnPatientProfile, db: DbSession
) -> AskResponse:
    conversation = await _owned_conversation(conversation_id, profile, db)
    return await _handle_question(conversation, payload.question.strip(), profile, db)


@router.post(
    "/{conversation_id}/ask-audio",
    response_model=AskResponse,
    summary="Ask a question as an audio clip",
    responses={503: {"description": "Speech-to-text is not configured on this server"}},
)
async def ask_audio(
    conversation_id: str,
    profile: OwnPatientProfile,
    db: DbSession,
    audio: Annotated[UploadFile, File(description="Recorded question (webm, ogg, wav, m4a, mp3)")],
) -> AskResponse:
    conversation = await _owned_conversation(conversation_id, profile, db)

    if audio.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type {audio.content_type!r}. "
                   f"Accepted: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="The audio file is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio must be under {MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )

    try:
        transcript = await transcribe(data, audio.filename or "question.webm")
    except TranscriptionUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT") else 422,
            detail="Could not make out any speech in that recording. Please try again.",
        )

    return await _handle_question(
        conversation, transcript, profile, db, audio_filename=audio.filename
    )

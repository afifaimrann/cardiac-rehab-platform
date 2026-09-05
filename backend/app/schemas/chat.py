"""Conversation and message payloads."""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole
from app.schemas.clinical import RiskFlagRead


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    title: Optional[str] = None
    created_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: MessageRole
    content: str
    citations: Optional[Any] = None
    transcribed_from_audio: Optional[str] = None
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AskResponse(BaseModel):
    """Both sides of the exchange, plus what the answer was built from."""

    question: MessageRead
    answer: MessageRead
    citations: List[dict] = []
    is_emergency: bool = Field(
        default=False,
        description="True when the safety guardrail intercepted the question.",
    )
    generated: bool = Field(
        default=False,
        description="True if a language model wrote the answer; false if it was extracted verbatim.",
    )
    retrieval_mode: str = Field(
        default="lexical",
        description="Which retrieval path produced the citations: lexical, dense or hybrid.",
    )
    flags_raised: List[RiskFlagRead] = []
    transcript: Optional[str] = Field(
        default=None, description="Set when the question arrived as audio."
    )

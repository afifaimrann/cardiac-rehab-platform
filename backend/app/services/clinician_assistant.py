"""An assistant a clinician can ask about one patient's record.

Different in kind from the patient-facing chat. That one answers from a
guidance corpus and must never touch the record; this one answers *from* the
record, for a reader who can judge what it says. So the shape is inverted: a
tool layer that reads the database, and a model whose job is to summarise and
compare rather than to advise.

SECURITY -- how a patient's record stays inside their own record
    Every tool below is bound to a single PatientProfile at construction, in
    `RecordTools.__init__`, from a profile the route already resolved through
    the `AssignedPatient` dependency. The model chooses *which* tool to call
    and with what date range; it can never choose *whose* record to read,
    because no tool takes a patient identifier. A prompt-injected instruction
    to "look up the patient in bed four" has nothing to call.

With no API key the module still answers, by rendering the same tool output as
a deterministic briefing. That keeps the feature demonstrable offline and means
an outage degrades the answer rather than removing it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.assessment import WalkTest
from app.models.care import Appointment
from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
from app.models.enums import FlagStatus
from app.models.program import ExercisePlan, ExerciseSession
from app.models.user import PatientProfile, User
from app.services import walk_test as walk_service

logger = logging.getLogger("cardiac.assistant")

MAX_TOOL_ROUNDS = 4          # enough to look up, compare, then answer
REQUEST_TIMEOUT_SECONDS = 40.0
MAX_ATTEMPTS = 2
DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 365
MAX_ROWS = 60                # a whole record does not belong in one prompt
HISTORY_TURNS = 8

SYSTEM_PROMPT = """You are a clinical assistant for a cardiac rehabilitation \
service. You are speaking to the clinician responsible for this patient, not to \
the patient.

You have read-only tools over this one patient's record. Use them before \
answering anything factual. Never answer a question about numbers, dates or \
trends from memory or from an earlier turn -- call a tool and read the values.

HOW TO ANSWER
- Lead with the answer. A clinician reading between appointments wants the \
finding first and the working after it.
- Quote real numbers with their dates. "SpO2 nadir 86% on 3 Sep" not "oxygen \
saturation was somewhat low recently".
- Say plainly when the record does not contain something. An absence is a \
finding: "no vitals logged since 21 Aug" is useful.
- Note contradictions between sources rather than smoothing them over.
- Be concise. Prose for a short answer, a short list when there are genuinely \
separate items. No headings unless the answer is long.

WHAT YOU ARE NOT
- You do not diagnose, prescribe, or decide. You summarise the record and point \
at what looks worth the clinician's attention; the judgement is theirs.
- You do not invent a value that is not in the record, or estimate one. If a \
tool returns nothing, say so.
- You are not talking to the patient, so do not write reassurance or advice \
aimed at them. If asked to draft a message for the patient, say that it is a \
draft for the clinician to check and send.
"""

BRIEFING_HEADER = (
    "No language model is configured, so this is the record itself rather than "
    "an answer to your question."
)


def _window(days: Optional[int]) -> datetime:
    days = max(1, min(days or DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class RecordTools:
    """Read-only lookups over exactly one patient's record.

    No method takes a patient id. That is the whole security model: the
    identifier is captured once, from an authorised profile, and the model
    never gets to supply one.
    """

    def __init__(self, db: AsyncSession, profile: PatientProfile) -> None:
        self._db = db
        self._profile = profile

    async def profile_summary(self) -> dict:
        user = await self._db.get(User, self._profile.user_id)
        clinician = (
            await self._db.get(User, self._profile.clinician_id)
            if self._profile.clinician_id else None
        )
        return {
            "name": user.full_name if user else None,
            "age": walk_service.age_from(self._profile.date_of_birth),
            "primary_condition": self._profile.primary_condition,
            "language": self._profile.language,
            "resting_hr_baseline": self._profile.resting_hr_baseline,
            "target_hr_max": self._profile.target_hr_max,
            "height_cm": self._profile.height_cm,
            "sex_at_birth": (
                self._profile.sex_at_birth.value if self._profile.sex_at_birth else None
            ),
            "assigned_clinician": clinician.full_name if clinician else None,
        }

    async def vitals(self, days: Optional[int] = None) -> dict:
        since = _window(days)
        rows = (await self._db.execute(
            select(VitalsRecord)
            .where(VitalsRecord.patient_id == self._profile.id,
                   VitalsRecord.recorded_at >= since)
            .order_by(VitalsRecord.recorded_at.desc()).limit(MAX_ROWS)
        )).scalars().all()
        return {
            "since": _iso(since),
            "count": len(rows),
            "readings": [
                {
                    "recorded_at": _iso(r.recorded_at), "systolic": r.systolic,
                    "diastolic": r.diastolic, "heart_rate": r.heart_rate,
                    "spo2": r.spo2, "weight_kg": r.weight_kg,
                }
                for r in rows
            ],
        }

    async def symptoms(self, days: Optional[int] = None) -> dict:
        since = _window(days)
        rows = (await self._db.execute(
            select(SymptomReport)
            .where(SymptomReport.patient_id == self._profile.id,
                   SymptomReport.recorded_at >= since)
            .order_by(SymptomReport.recorded_at.desc()).limit(MAX_ROWS)
        )).scalars().all()
        return {
            "since": _iso(since), "count": len(rows),
            "reports": [
                {"recorded_at": _iso(r.recorded_at), "description": r.description,
                 "severity": r.severity.value}
                for r in rows
            ],
        }

    async def risk_flags(self, open_only: bool = True) -> dict:
        stmt = select(RiskFlag).where(RiskFlag.patient_id == self._profile.id)
        if open_only:
            stmt = stmt.where(RiskFlag.status == FlagStatus.OPEN)
        rows = (await self._db.execute(
            stmt.order_by(RiskFlag.created_at.desc()).limit(MAX_ROWS)
        )).scalars().all()
        return {
            "open_only": open_only, "count": len(rows),
            "flags": [
                {"raised_at": _iso(f.created_at), "rule": f.rule_code,
                 "severity": f.severity.value, "status": f.status.value,
                 "message": f.message}
                for f in rows
            ],
        }

    async def walk_tests(self) -> dict:
        rows = (await self._db.execute(
            select(WalkTest).where(WalkTest.patient_id == self._profile.id)
            .order_by(WalkTest.performed_at.desc()).limit(12)
        )).scalars().all()
        return {
            "count": len(rows),
            "mcid_metres": walk_service.MCID_METRES,
            "tests": [
                {
                    "performed_at": _iso(t.performed_at), "distance_m": t.distance_m,
                    "percent_predicted": t.percent_predicted,
                    "below_lower_limit": t.below_lower_limit,
                    "lowest_spo2": t.lowest_spo2, "rest_count": t.rest_count,
                    "post_borg_dyspnoea": t.post_borg_dyspnoea,
                    "status": t.status.value, "stop_reason": t.stop_reason,
                    "symptoms": t.symptoms,
                }
                for t in rows
            ],
        }

    async def exercise_adherence(self, days: Optional[int] = None) -> dict:
        since = _window(days)
        plan = (await self._db.execute(
            select(ExercisePlan).where(ExercisePlan.patient_id == self._profile.id,
                                       ExercisePlan.is_active.is_(True))
            .order_by(ExercisePlan.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        sessions = (await self._db.execute(
            select(ExerciseSession)
            .where(ExerciseSession.patient_id == self._profile.id,
                   ExerciseSession.performed_at >= since)
            .order_by(ExerciseSession.performed_at.desc()).limit(MAX_ROWS)
        )).scalars().all()

        weeks = max((datetime.now(timezone.utc) - since).days / 7.0, 1.0)
        completed = [s for s in sessions if s.completed]
        return {
            "since": _iso(since),
            "plan": None if plan is None else {
                "title": plan.title, "sessions_per_week": plan.sessions_per_week,
                "minutes_per_session": plan.minutes_per_session,
                "target_exertion_max": plan.target_exertion_max,
            },
            "sessions_logged": len(sessions),
            "sessions_completed": len(completed),
            "sessions_per_week_actual": round(len(completed) / weeks, 1),
            "recent": [
                {"performed_at": _iso(s.performed_at), "activity": s.activity,
                 "duration_minutes": s.duration_minutes,
                 "perceived_exertion": s.perceived_exertion, "completed": s.completed}
                for s in sessions[:15]
            ],
        }

    async def appointments(self) -> dict:
        rows = (await self._db.execute(
            select(Appointment).where(Appointment.patient_id == self._profile.id)
            .order_by(Appointment.starts_at.desc()).limit(20)
        )).scalars().all()
        return {
            "count": len(rows),
            "appointments": [
                {"starts_at": _iso(a.starts_at), "mode": a.mode.value,
                 "status": a.status.value, "reason": a.reason,
                 "notes": a.clinician_notes}
                for a in rows
            ],
        }


# The schema the model sees. Descriptions are written for it, not for a human
# reader: they say when to reach for a tool, which is what it has to decide.
TOOL_SPECS: List[dict] = [
    {
        "name": "get_profile",
        "description": "Who the patient is: age, primary condition, baselines, "
                       "language, assigned clinician. Call this first when the "
                       "question needs any context about the person.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_vitals",
        "description": "Logged blood pressure, heart rate, SpO2 and weight, newest "
                       "first. Use for any question about readings or trends.",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer",
                                    "description": "How far back to look. Default 30."}},
        },
    },
    {
        "name": "get_symptoms",
        "description": "Patient-reported symptoms with severity and date.",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer"}},
        },
    },
    {
        "name": "get_risk_flags",
        "description": "Concerns raised automatically from this patient's data. "
                       "Open flags by default; pass open_only=false for history.",
        "parameters": {
            "type": "object",
            "properties": {"open_only": {"type": "boolean"}},
        },
    },
    {
        "name": "get_walk_tests",
        "description": "Six-minute walk test results with percent predicted and "
                       "desaturation. Use for functional capacity or progress.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_exercise_adherence",
        "description": "The prescribed plan and what the patient actually logged, "
                       "with sessions per week achieved.",
        "parameters": {
            "type": "object",
            "properties": {"days": {"type": "integer"}},
        },
    },
    {
        "name": "get_appointments",
        "description": "Past and upcoming consultations, including cancellations "
                       "and no-shows.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _dispatch(tools: RecordTools) -> Dict[str, Callable[..., Any]]:
    return {
        "get_profile": tools.profile_summary,
        "get_vitals": tools.vitals,
        "get_symptoms": tools.symptoms,
        "get_risk_flags": tools.risk_flags,
        "get_walk_tests": tools.walk_tests,
        "get_exercise_adherence": tools.exercise_adherence,
        "get_appointments": tools.appointments,
    }


@dataclass
class AssistantReply:
    answer: str
    tools_used: List[str] = field(default_factory=list)
    generated: bool = False


async def _briefing(tools: RecordTools) -> AssistantReply:
    """The offline path: the record, rendered, with nothing inferred."""
    profile = await tools.profile_summary()
    vitals = await tools.vitals()
    flags = await tools.risk_flags()
    walks = await tools.walk_tests()
    adherence = await tools.exercise_adherence()

    lines = [BRIEFING_HEADER, ""]
    lines.append(
        f"**{profile['name'] or 'Patient'}** — "
        f"{profile['primary_condition'] or 'condition not recorded'}"
        + (f", age {profile['age']}" if profile["age"] else "")
    )

    if vitals["count"]:
        latest = vitals["readings"][0]
        lines.append(
            f"- Last reading {latest['recorded_at'][:10]}: "
            f"BP {latest['systolic'] or '–'}/{latest['diastolic'] or '–'}, "
            f"HR {latest['heart_rate'] or '–'}, SpO₂ {latest['spo2'] or '–'}%"
            f" ({vitals['count']} readings in 30 days)"
        )
    else:
        lines.append("- No vitals logged in the last 30 days.")

    if walks["count"]:
        newest = walks["tests"][0]
        pct = newest["percent_predicted"]
        lines.append(
            f"- Six-minute walk {newest['performed_at'][:10]}: "
            f"{newest['distance_m']:.0f} m"
            + (f" ({pct:.0f}% predicted)" if pct else "")
        )
    else:
        lines.append("- No six-minute walk test on record.")

    plan = adherence["plan"]
    lines.append(
        f"- Exercise: {adherence['sessions_per_week_actual']} sessions/week logged"
        + (f" against {plan['sessions_per_week']} prescribed" if plan else ", no active plan")
    )

    if flags["count"]:
        lines.append(f"- {flags['count']} open flag(s):")
        lines.extend(f"    · {f['severity']}: {f['message']}" for f in flags["flags"][:5])
    else:
        lines.append("- No open risk flags.")

    return AssistantReply(
        answer="\n".join(lines),
        tools_used=["get_profile", "get_vitals", "get_risk_flags",
                    "get_walk_tests", "get_exercise_adherence"],
        generated=False,
    )


async def ask(
    question: str,
    db: AsyncSession,
    profile: PatientProfile,
    history: Optional[List[dict]] = None,
) -> AssistantReply:
    """Answer a clinician's question about `profile`, reading only that record."""
    tools = RecordTools(db, profile)
    if not settings.llm_enabled:
        return await _briefing(tools)

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)
    dispatch = _dispatch(tools)
    schema = [{"type": "function", "function": spec} for spec in TOOL_SPECS]

    messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend((history or [])[-HISTORY_TURNS:])
    messages.append({"role": "user", "content": question})

    used: List[str] = []

    for _round in range(MAX_TOOL_ROUNDS):
        response = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await client.chat.completions.create(
                    model=settings.CLINICIAN_ASSISTANT_MODEL,
                    messages=messages,
                    tools=schema,
                    temperature=0.1,
                    max_tokens=700,
                )
                break
            except Exception as exc:  # noqa: BLE001 - any failure falls back
                if attempt == MAX_ATTEMPTS:
                    logger.warning("Assistant call failed: %s", exc)
                    return await _briefing(tools)
                await asyncio.sleep(0.5 * attempt)

        choice = response.choices[0].message
        calls = choice.tool_calls or []
        if not calls:
            answer = (choice.content or "").strip()
            if not answer:
                return await _briefing(tools)
            return AssistantReply(answer=answer, tools_used=used, generated=True)

        messages.append({
            "role": "assistant",
            "content": choice.content,
            "tool_calls": [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in calls
            ],
        })

        for call in calls:
            name = call.function.name
            handler = dispatch.get(name)
            if handler is None:
                # The model asked for something that does not exist. Say so
                # rather than failing the turn: it will usually recover.
                payload = {"error": f"No such tool: {name}"}
            else:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    payload = await handler(**args)
                    used.append(name)
                except TypeError as exc:
                    payload = {"error": f"Bad arguments for {name}: {exc}"}
            messages.append({
                "role": "tool", "tool_call_id": call.id, "name": name,
                "content": json.dumps(payload, default=str),
            })

    # Out of rounds. Rather than return the model's half-finished reasoning,
    # give the clinician the record.
    logger.info("Assistant exhausted %d tool rounds", MAX_TOOL_ROUNDS)
    return await _briefing(tools)

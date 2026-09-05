"""Grounded question answering over the guidance corpus.

Pipeline: guardrail -> retrieve -> generate. The guardrail runs first and can
end the turn on its own; nothing describing a symptom in progress reaches the
model.

Generation is optional. With no API key configured the service answers
extractively from the retrieved passages and says so. That keeps the whole
feature demonstrable offline, and means an outage degrades the answer rather
than removing it.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import guardrails
from app.services.dense import DenseRetriever
from app.services.fusion import reciprocal_rank_fusion
from app.services.knowledge import Passage
from app.services.language import Script, detect_script
from app.services.reranking import get_reranker, rerank
from app.services.retrieval import MIN_SCORE_RATIO, Hit, retriever

logger = logging.getLogger("cardiac.chat")

MAX_ATTEMPTS = 3
BASE_BACKOFF_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 20.0
MIN_RELEVANCE_SCORE = 1.0
# Prior turns passed to the model. Six is three exchanges: enough to resolve a
# follow-up, short enough that the prompt stays small and cheap.
HISTORY_TURNS = 6

SYSTEM_PROMPT = """You are a cardiac rehabilitation assistant supporting a patient \
between clinic appointments.

The person has had a cardiac event. They may be frightened, tired, or unsure \
whether what they are feeling is normal. Talk to them the way a good \
rehabilitation nurse would: acknowledge what they said, then help. Warm, \
practical, unhurried, never preachy.

BE GENUINELY USEFUL
- Give concrete, practical guidance they can act on today. "Walk for ten \
minutes after breakfast and see how you feel" beats "regular exercise is \
recommended".
- If the passages cover part of the question, answer that part rather than \
refusing the whole thing. Say briefly what you cannot cover.
- Anticipate the obvious next worry and address it in a line.
- Use a short list when there are genuine steps; otherwise write prose.
- Usually four to six sentences. Longer only if they asked something detailed.

STAY GROUNDED
- Every factual and clinical claim comes from the numbered passages. Cite them \
inline as [1], [2].
- General everyday encouragement (pacing yourself, keeping a routine, writing \
questions down for your next appointment, telling your team what you noticed) \
does not need a citation and is welcome.

NEVER
- Diagnose, or say how serious a symptom is.
- Suggest starting, stopping or changing any medication or dose.
- Suggest herbal remedies, supplements, or home treatments. Cardiac patients \
are typically on anticoagulants, antiplatelets or statins, and common remedies \
interact with them: garlic, ginger, turmeric and ginkgo affect bleeding, \
liquorice raises blood pressure, grapefruit interacts with statins. If asked, \
say plainly that anything they take -- including herbal or over-the-counter \
products -- should be checked with their doctor or pharmacist first, because of \
interactions with heart medication.
- Reassure someone that a symptom is nothing. If something they describe sounds \
like it needs review, say so and tell them who to contact.

CONTEXT
The conversation so far is provided. Use it to understand follow-up questions, \
but base every factual claim on the passages, never on earlier turns.
"""

# The corpus is English; the patient may not be. The passages stay in English
# and the answer is written in the patient's language, which is the whole point
# of a multilingual retriever.
BENGALI_INSTRUCTION = """
The patient wrote in Bangla (Bengali). The reference passages are in English.

- Write your entire answer in Bangla, in plain everyday language a patient would
  use, not formal or literary Bangla.
- Keep clinical terms the patient will recognise; where an English term is more
  familiar than its Bangla translation, keep the English word.
- Do not translate the citation markers: keep them as [1], [2].
- Do not apologise for the language or mention that the sources are in English.
"""

NO_CONTEXT_RESPONSE_BN = (
    "প্রোগ্রাম হ্যান্ডবুকে এ বিষয়ে কিছু পাইনি, তাই অনুমান করে বলতে চাই না। "
    "আপনার রিহ্যাবিলিটেশন টিম এটার সঠিক উত্তর দিতে পারবেন — পরের "
    "অ্যাপয়েন্টমেন্টের জন্য লিখে রাখুন, বা জরুরি হলে তাঁদের ফোন করুন।"
)

EXTRACTIVE_PREFIX_BN = (
    "প্রোগ্রাম হ্যান্ডবুকে যা লেখা আছে তা নিচে দেওয়া হলো (ইংরেজিতে, কারণ "
    "উত্তর লেখার ভাষা-মডেল এই সার্ভারে চালু নেই):"
)

NO_CONTEXT_RESPONSE = (
    "I don't have guidance on that in the programme handbook, so I'd rather not "
    "guess. Your rehabilitation team can answer this properly — it's worth "
    "writing down for your next appointment, or calling them if it can't wait."
)

EXTRACTIVE_PREFIX = (
    "Here's what the programme handbook says (shown directly, as the assistant's "
    "language model is not configured):"
)


@dataclass
class Answer:
    content: str
    citations: List[dict] = field(default_factory=list)
    is_emergency: bool = False
    matched_rules: List[str] = field(default_factory=list)
    generated: bool = False
    retrieval_mode: str = "lexical"


_dense = DenseRetriever()


async def retrieve(question: str, db: Optional[AsyncSession], k: int) -> tuple[List[Hit], str]:
    """Lexical, dense, or both fused, depending on what is available.

    Availability is checked at call time rather than at import: a deployment
    without an embedding backend, or before the corpus is ingested, must still
    answer rather than fail.
    """
    bengali = detect_script(question) in (Script.BENGALI, Script.MIXED)
    reranking = get_reranker() is not None

    # Retrieve a wider candidate set when a reranker will narrow it: recall
    # matters more than precision at this stage, precision is the reranker's job.
    fetch_k = settings.RERANK_CANDIDATES if reranking else max(k, 5)

    # A Bengali query shares no tokens with an English corpus, so BM25 returns
    # noise at best. Fusing that noise would only dilute good dense results, so
    # the lexical arm is skipped rather than fused.
    lexical = [] if bengali else retriever.search(question, k=fetch_k)

    if bengali and (db is None or not _dense.available):
        # Nothing can answer a Bengali question without a multilingual encoder.
        return [], "unavailable"

    if settings.RETRIEVAL_MODE == "lexical" or db is None or not _dense.available:
        floor = lexical[0].score * MIN_SCORE_RATIO if lexical else 0.0
        return [h for h in lexical if h.score >= floor][:k], "lexical"

    dense = await _dense.search(db, question, k=fetch_k)
    if not reranking:
        # Without a reranker the bi-encoder cosine is all there is, so weak
        # neighbours are dropped here. Nearest is not the same as relevant.
        dense = [h for h in dense if h.score >= settings.MIN_DENSE_SIMILARITY]

    if not dense:
        if bengali:
            return [], "no-match"
        floor = lexical[0].score * MIN_SCORE_RATIO if lexical else 0.0
        return [h for h in lexical if h.score >= floor][:k], "lexical"

    if settings.RETRIEVAL_MODE == "dense" or not lexical:
        candidates, mode = dense, "dense"
    else:
        fused = reciprocal_rank_fusion(lexical, dense, k=fetch_k)
        candidates, mode = [f.hit for f in fused], "hybrid"

    if not reranking:
        return candidates[:k], mode

    reranked, ran = rerank(question, candidates, k=fetch_k)
    if not ran:
        return candidates[:k], mode

    # The reranker's scale is its own, so its own threshold applies. This is the
    # cut that a bi-encoder cosine could not make cleanly across two languages.
    kept = [h for h in reranked if h.score >= settings.MIN_RERANK_SCORE][:k]
    return kept, f"{mode}+rerank"


def _citation(hit: Hit, index: int) -> dict:
    return {
        "index": index,
        "id": hit.passage.id,
        "title": hit.passage.title,
        "source": hit.passage.source,
        "score": hit.score,
    }


def _format_context(hits: List[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] {h.passage.title} ({h.passage.source})\n{h.passage.text}"
        for i, h in enumerate(hits, start=1)
    )


def _extractive_answer(hits: List[Hit], prefix: str = EXTRACTIVE_PREFIX) -> str:
    body = "\n\n".join(
        f"**{h.passage.title}** [{i}]\n{h.passage.text}" for i, h in enumerate(hits, start=1)
    )
    return f"{prefix}\n\n{body}"


async def _generate(
    question: str,
    hits: List[Hit],
    bengali: bool = False,
    history: Optional[List[dict]] = None,
) -> Optional[str]:
    """Call the language model, retrying transient failures with backoff.

    Returns None when every attempt fails, so the caller can fall back to the
    extractive answer instead of surfacing an error to a patient.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=REQUEST_TIMEOUT_SECONDS)
    system_prompt = SYSTEM_PROMPT + (BENGALI_INSTRUCTION if bengali else "")
    user_prompt = f"Passages:\n{_format_context(hits)}\n\nPatient question: {question}"

    # Prior turns give the model enough to resolve a follow-up, without letting
    # earlier answers become a source of fact -- the passages are the only
    # grounding, and history is capped so the prompt cannot grow without bound.
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_prompt})

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.CHAT_MODEL,
                messages=messages,
                temperature=0.2,
                max_tokens=350,
            )
            return (response.choices[0].message.content or "").strip() or None
        except Exception as exc:  # noqa: BLE001 - any failure falls back
            if attempt == MAX_ATTEMPTS:
                logger.warning("Generation failed after %d attempts: %s", attempt, exc)
                return None
            delay = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.info("Generation attempt %d failed (%s); retrying in %.1fs", attempt, exc, delay)
            await asyncio.sleep(delay)
    return None


async def answer_question(
    question: str,
    db: Optional[AsyncSession] = None,
    k: int = 3,
    history: Optional[List[dict]] = None,
) -> Answer:
    verdict = guardrails.check(question)
    if verdict.is_emergency:
        logger.info("Emergency guardrail triggered")
        return Answer(
            # The guardrail already chose the language; use its response rather
            # than the English constant, or a Bangla speaker gets escalation
            # advice they may not be able to read.
            content=verdict.response or guardrails.EMERGENCY_RESPONSE,
            is_emergency=True,
            matched_rules=verdict.matched,
        )

    bengali = detect_script(question) in (Script.BENGALI, Script.MIXED)

    hits, mode = await retrieve(question, db, k)
    if mode == "lexical":
        hits = [h for h in hits if h.score >= MIN_RELEVANCE_SCORE]
    if not hits:
        return Answer(
            content=NO_CONTEXT_RESPONSE_BN if bengali else NO_CONTEXT_RESPONSE,
            retrieval_mode=mode,
        )

    citations = [_citation(h, i) for i, h in enumerate(hits, start=1)]

    if settings.llm_enabled:
        generated = await _generate(question, hits, bengali=bengali, history=history)
        if generated:
            return Answer(
                content=generated, citations=citations, generated=True, retrieval_mode=mode
            )

    # Extractive fallback cannot translate. Say so in Bangla rather than
    # returning English text with no explanation.
    prefix = EXTRACTIVE_PREFIX_BN if bengali else EXTRACTIVE_PREFIX
    return Answer(
        content=_extractive_answer(hits, prefix=prefix), citations=citations,
        retrieval_mode=mode,
    )

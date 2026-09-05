# The two assistants

One answers a patient from a guidance corpus and must never touch the record.
The other answers a clinician *from* the record. Different jobs, opposite shapes.

[← back to the README](../README.md)

---


---

## The clinician's assistant

Inverted from the patient-facing assistant. That one answers from a guidance
corpus and must never touch the record; this one answers *from* the record, for
a reader who can judge what it says. So it is a tool layer over the database
with a model on top, and the prompt tells it to lead with the finding, quote
real numbers with their dates, and treat an absence as a finding
("no vitals logged since 21 Aug").

**How a patient's record stays inside their own record.** Every tool is bound
to one `PatientProfile` at construction, from a profile the route already
resolved through the `AssignedPatient` dependency. No tool takes a patient
identifier — the model chooses *which* lookup and over what date range, never
*whose*. A prompt-injected instruction sitting in a symptom note has nothing to
call. There is a test asserting no tool ever grows a patient-selector
parameter, because that is the change that would silently turn this feature
into an authorisation bypass.

There are two ways in, because a clinician who wants to ask about someone
should not have to remember whose record to open first: **Ask about a patient**
in the rail opens a patient picker beside the panel, and every caseload row has
an **Ask** button that jumps straight to that patient. Inside a record it is
also a tab. Switching patient remounts the panel on that patient's own thread —
context bleeding between two patients' records is the one failure mode of this
feature that would be genuinely dangerous.

The answer shows which parts of the record it read. That line is not
decoration: an assistant summarising a record is only useful if the reader can
tell whether it looked at the thing they care about, and "answered without
reading the walk tests" is otherwise invisible.

With no API key configured it still answers, rendering the same tool output as
a deterministic briefing — which is also the state the whole test suite runs in.

---

## The assistant

Patients can ask questions about their recovery, by typing or by voice. Answers
are grounded in the guidance corpus in `services/knowledge.py` and cite the
passages they were built from.

The pipeline is **guardrail → retrieve → generate**, and each stage can end the
turn on its own.

### Safety comes first, literally

The guardrail runs *before* retrieval and before the model sees anything. A
question describing symptoms in progress — chest pain, breathlessness, fainting
— is never answered with handbook advice. It gets fixed escalation text, and it
raises a `CHAT_EMERGENCY_LANGUAGE` flag at severity `severe` so the care team
sees that the patient reported a symptom. An assistant must not be the reason
someone waits.

The matcher is deliberately over-inclusive: a false positive costs one
unnecessary reassurance, a false negative costs far more. It does distinguish
teaching questions from live symptoms — *"What should I do if I get chest pain
during exercise?"* is answered normally, and there is a test asserting exactly
that.

### Multilingual retrieval

Patients ask in Bangla; the corpus is English. BGE-M3 embeds both into one space,
so a Bangla question retrieves the English passage that answers it and the model
writes the reply back in Bangla. No translation step, no parallel corpus.

Measured on a calibration set (`python -m scripts.retrieval_debug`):

| Question | Retrieved | Cosine |
|---|---|---|
| কাজে ফিরে যেতে পারব কবে? | Returning to work | 0.694 |
| ধূমপান ছাড়তে চাই | Quitting Smoking | 0.657 |
| আমার রক্তচাপ কত হওয়া উচিত? | Blood pressure in rehabilitation | 0.645 |
| *What is the capital of Mongolia?* | *(nothing above threshold)* | 0.290 |
| *how do I fix a bicycle puncture* | *(nothing above threshold)* | 0.480 |

Script detection routes the query: Bangla text shares no tokens with an English
corpus, so BM25 is skipped rather than fused, and code-switched input
("আমার chest pain হচ্ছে") counts as Bangla because that is how people type.

`MIN_DENSE_SIMILARITY` is 0.50, taken from that run rather than guessed:
relevant queries scored 0.500-0.694 and the strongest irrelevant one reached
0.480. That margin is narrow, and the threshold is set to refuse rather than to
answer when in doubt.

### Reranking: implemented, and switched off

A cross-encoder reranking stage (`services/reranking.py`) is written, tested and
wired in, and it is **disabled by default**.

On the development machine, `bge-reranker-v2-m3` scored an exact-match pair
("Can I drive after my heart attack?" against the passage on driving
restrictions) at **0.002**, where a working cross-encoder gives >0.9.

Finding the cause took three wrong guesses, and the sequence is the useful part:

| Hypothesis | Test | Result |
|---|---|---|
| sentence-transformers' generic wrapper | score through plain transformers instead | identical output — not the wrapper |
| transformers 5.x incompatibility | downgrade to 4.57 | identical output — not the version |
| wrong loader for this checkpoint | score through BAAI's own FlagEmbedding | identical output — not the loader |

| corrupt or truncated download | delete the cache and refetch 2.27 GB | identical output — not the file |

Four hypotheses, four eliminations, cause still unknown.

The fourth deserves a note, because the reasoning that motivated it was wrong.
Inspecting the checkpoint showed `classifier.dense.weight` at std 0.0201 against
the config's `initializer_range: 0.02`, which looked like an untrained head. It
is not evidence of that: a head fine-tuned at a small learning rate stays close
to its initialisation distribution, so a working model looks the same. The
refetch disproved the theory, and `scripts/check_checkpoint.py` now says plainly
that weight statistics cannot distinguish the two.

What remains true is the structural observation: byte-identical scores across
three independent loaders point at a shared input rather than three coincident
bugs. That reasoning was sound; the specific conclusion drawn from it was not.

Two habits earned their keep here. `scripts/rerank_sanity.py` scores pairs whose
answer is not in doubt, so "the model loaded and returned numbers" is never
mistaken for "the model works". And the calibration script reports the *margin*
between relevant and irrelevant queries rather than just a suggested threshold —
which is what caught an earlier bug in this same stage, where sigmoid was applied
to values that had already been through one, mapping every score into
[0.5, 0.73]. Nothing errored, ordering still changed, the numbers looked
plausible, and the only visible symptom was a margin of +0.004.

### Lexical retrieval is BM25, written here rather than imported

For a corpus this size that is the right tool: no model, no vector store, no API
key, microseconds per query, and inspectable scores — when a wrong passage comes
back you can see which term caused it.

Two refinements, both from observed failures rather than guesswork:

- **A light stemmer.** The first version ranked *"how hard should I be
  exercising?"* against the wrong passage because `exercising` and `exercise`
  were different terms. Same cause for `eat`/`eating` and `sex`/`sexual`.
- **Query-side synonym expansion.** Stemming cannot bridge `anxious` → `mood` or
  `cigarettes` → `smoking`. Expansion is applied to queries only, never to
  documents, so the corpus statistics stay honest.

`Retriever` is a Protocol, so a dense/embedding retriever can be dropped in
without touching the chat service. That swap earns its complexity when
paraphrase-heavy questions start missing — a patient asking about *"the pill
that makes me tired"* will not match *"beta blocker"* on terms alone.

Retrieval quality is a test, not a claim: `tests/test_retrieval.py` asserts the
correct top-1 passage for 18 real questions, so a tokenizer or corpus change
cannot silently regress it.

### Generation is optional

With no `OPENAI_API_KEY`, answers are extractive — the retrieved passages
verbatim, labelled as such. With a key, a language model writes the answer under
a prompt that restricts it to the supplied passages, forbids diagnosis and
medication advice, and requires inline citations. Generation failures retry
three times with exponential backoff and then fall back to the extractive
answer, so an outage degrades the answer rather than removing the feature.

The `generated` field in the response says which path produced the answer.

### Voice

Audio is transcribed with Whisper, then follows the identical text path — the
transport is separate from the reasoning, so typing and speaking cannot diverge
in behaviour. Without a key the endpoint returns `503` with an explanation, and
the UI hides the microphone rather than offering a button that fails.

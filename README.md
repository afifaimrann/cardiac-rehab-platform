# Cardiac Rehab Platform

A remote cardiac rehabilitation service. Patients log vital signs, symptoms and
exercise sessions, record six-minute walk tests, book video or in-person
consultations from their clinician's rota, and message their care team; a rule
engine evaluates every submission and raises flags for clinician review;
clinicians work a caseload prioritised by clinical urgency, run a diary, and
question an assistant that reads one patient's record.

Built as a single-developer project: FastAPI + PostgreSQL on the back end,
React + TypeScript on the front, with an emphasis on the parts that are usually
skipped — authorisation boundaries, pagination that does not lose rows,
reversible migrations, and tests that assert the boundaries hold.

> **Not a medical device.** The thresholds in the risk engine are illustrative
> and this system has not been clinically validated.

![CI](https://github.com/afifaimrann/cardiac-rehab-platform/actions/workflows/ci.yml/badge.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![React 18](https://img.shields.io/badge/react-18-149eca)
![Tests](https://img.shields.io/badge/tests-347%20passing-2b6340)
![Licence](https://img.shields.io/badge/licence-MIT-lightgrey)

---

|  |  |
|---|---|
| ![Patient overview](docs/screenshots/patient-overview.png) | ![Six-minute walk test](docs/screenshots/walk-test.png) |
| **The patient's record.** What is next, what was flagged, and the trend behind it. | **The six-minute walk test.** The timer captures rests and the oxygen nadir so they are not typed from memory afterwards. |
| ![Clinician caseload](docs/screenshots/caseload.png) | ![The clinician's assistant](docs/screenshots/assistant.png) |
| **The caseload**, ordered by clinical urgency, with a review queue of flags raised automatically. | **The assistant**, answering from one patient's record and showing which parts of it were read. |

---

## Contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [API](#api)
- [Authorisation model](#authorisation-model)
- [The risk engine](#the-risk-engine)
- [The six-minute walk test](#the-six-minute-walk-test)
- [Scheduling and video consultations](#scheduling-and-video-consultations)
- [The clinician's assistant](#the-clinicians-assistant)
- [Profile photographs](#profile-photographs)
- [The assistant](#the-assistant)
- [Testing](#testing)
- [Design decisions](#design-decisions)

---

## Quick start

### With Docker (Postgres, migrations, both apps)

```bash
docker compose up --build
```

- App — <http://localhost:8080>
- API docs — <http://localhost:8000/docs>

### Locally, without Docker

```bash
# --- backend ---
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # then set JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # generate one

alembic upgrade head          # create the schema
python -m scripts.seed_demo   # optional: demo accounts and 28 days of history
uvicorn app.main:app --reload

# --- frontend (second terminal) ---
cd frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

### Demo accounts

Seeded by `scripts/seed_demo.py`. All use the password `demo-password-123`.

| Account | Role | What you see |
|---|---|---|
| `dr.chowdhury@example.com` | clinician | Caseload of 3 patients, live flag queue |
| `rina@example.com` | patient | 28 days of readings, 92% adherence |
| `kamal@example.com` | patient | Moderate adherence, a heart-rate flag |
| `nadia@example.com` | patient | Poor adherence — how the dashboard surfaces drop-off |
| `admin@example.com` | admin | Everything, plus patient assignment |

The seed is deterministic and idempotent: re-running it will not duplicate data.

---

## Architecture

```
┌─────────────────┐        ┌──────────────────────────────────┐       ┌────────────┐
│  React SPA      │        │  FastAPI                         │       │ PostgreSQL │
│  Vite + TS      │  REST  │                                  │  SQL  │            │
│                 │───────▶│  routers ─▶ dependencies         │──────▶│  9 tables  │
│  patient view   │  JWT   │              (authn / authz)     │ async │            │
│  clinician view │◀───────│           ─▶ services            │       │            │
└─────────────────┘        │              (risk, adherence)   │       └────────────┘
                           │           ─▶ SQLAlchemy 2.0      │
                           └──────────────────────────────────┘
```

Request path: **router → dependency (who are you, what may you see) → service
(business rules) → ORM**. Authorisation lives in dependencies, not in handler
bodies, so every route declares its access requirements in its signature and a
route that forgets to authorise is visibly missing one.

```
backend/app/
├── api/
│   ├── deps.py            # authentication, roles, record ownership
│   └── v1/                # auth, vitals, program, clinician routers
├── core/                  # settings, JWT + password hashing, pagination
├── db/                    # declarative base, async session factory
├── models/                # SQLAlchemy models
├── schemas/               # Pydantic request/response models
└── services/              # risk rules, flag persistence, adherence
```

---

## API

23 endpoints, versioned under `/api/v1`. The OpenAPI schema is generated from
the route signatures — Swagger UI at `/docs`, ReDoc at `/redoc`.

### Authentication

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/register` | Patient self-registration; creates the clinical profile atomically |
| `POST` | `/auth/login` | Returns an access + refresh pair |
| `POST` | `/auth/refresh` | Refresh tokens only — an access token here is rejected |
| `POST` | `/auth/clinicians` | Admin only: provision a clinician |
| `GET` | `/auth/me` | Current user and profile |

### Patient

| Method | Path | Notes |
|---|---|---|
| `POST` | `/vitals` | Log a reading; returns any flags it raised inline |
| `GET` | `/vitals` | Own readings, newest first, cursor-paginated |
| `POST` | `/symptoms` | Report a symptom |
| `GET` | `/symptoms` | Own symptom history |
| `POST` | `/sessions` | Log an exercise session |
| `GET` | `/sessions` | Own session history |
| `GET` | `/plans/active` | The plan currently prescribed |
| `GET` | `/adherence` | Adherence over a rolling window |
| `POST` | `/conversations` | Start a conversation with the assistant |
| `GET` | `/conversations` | Own conversations |
| `GET` | `/conversations/{id}/messages` | Message history, cursor-paginated |
| `POST` | `/conversations/{id}/ask` | Ask a question as text |
| `POST` | `/conversations/{id}/ask-audio` | Ask a question as an audio clip |
| `GET` | `/walk-tests/prefill` | Values already on record, to start a test from |
| `POST` | `/walk-tests/screening` | Contraindication check, before a test starts |
| `POST` | `/walk-tests` | Record a test; returns change vs previous and any flags |
| `GET` | `/walk-tests` | Own test history |
| `GET` | `/appointments/slots` | Bookable times from the assigned clinician's rota |
| `POST` | `/appointments` | Book a slot; creates the video room |
| `GET` | `/appointments` | Own appointments |
| `POST` | `/appointments/{id}/cancel` | Cancel and release the slot |
| `GET` | `/messages` | Thread with the care team; marks the other side read |
| `POST` | `/messages` | Write to the care team |
| `GET` | `/messages/unread` | Unread count, for the badge |
| `PATCH` | `/me/profile` | Edit your own details |
| `POST` | `/me/avatar` | Upload a profile photograph |
| `DELETE` | `/me/avatar` | Remove it |

None of these accept a patient id. The record acted on is always derived from
the token, which removes the commonest way this class of API leaks data.

### Clinician

| Method | Path | Notes |
|---|---|---|
| `GET` | `/clinician/caseload` | Assigned patients with flags, adherence, last contact |
| `GET` | `/clinician/flags` | Review queue, scoped to the caseload |
| `PATCH` | `/clinician/flags/{id}` | Acknowledge or resolve, with an audit trail |
| `GET` | `/clinician/patients/{id}` | Profile of an assigned patient |
| `GET` | `/clinician/patients/{id}/vitals` | Their readings |
| `GET` | `/clinician/patients/{id}/symptoms` | Their symptom reports |
| `POST` | `/patients/{id}/plans` | Prescribe a plan (supersedes the previous one) |
| `GET` | `/patients/{id}/plans` | Plan history |
| `PATCH` | `/clinician/patients/{id}/assignment` | Admin only: assign to a clinician |
| `GET`/`POST`/`DELETE` | `/appointments/availability` | Publish and withdraw weekly rota windows |
| `GET` | `/appointments/clinic` | The diary |
| `PATCH` | `/appointments/{id}` | Record an outcome (seen, missed, notes) |
| `GET`/`POST` | `/messages/patients/{id}` | Read and reply to a patient's thread |
| `GET`/`POST`/`DELETE` | `/assistant/patients/{id}` | Ask the assistant about one patient |
| `GET` | `/walk-tests/patients/{id}` | Their walk test history |
| `POST` | `/walk-tests/patients/{id}` | Record a supervised test |

### Pagination

List endpoints are cursor-paginated, not offset-paginated. Clinical logs are
append-heavy and read newest-first, where an offset shifts under the reader and
silently duplicates or skips rows. The cursor encodes the last row's timestamp
**and** its id, making the ordering total so ties cannot swallow a row.

```http
GET /api/v1/vitals?limit=20
→ { "items": [...], "next_cursor": "MjAyNi0wOS0wMlQxMDoxNTowMHwzZjJi..." }

GET /api/v1/vitals?limit=20&cursor=MjAyNi0wOS0wMlQxMDoxNTowMHwzZjJi...
→ { "items": [...], "next_cursor": null }        # last page
```

---

## Authorisation model

Three roles, enforced by dependency:

| | Patient | Clinician | Admin |
|---|---|---|---|
| Own clinical records | read/write | — | — |
| Assigned patients | — | read | read (all) |
| Prescribe plans | — | assigned only | any |
| Resolve flags | — | assigned only | any |
| Provision clinicians | — | — | yes |
| Assign patients | — | — | yes |

Two decisions worth calling out:

**A clinician requesting a patient outside their caseload gets `404`, not
`403`.** A 403 confirms the record exists, which turns an id into an oracle for
enumerating a patient list. The 404 path is tested explicitly.

**Roles cannot be self-granted.** Registration ignores any `role` in the body
and always creates a patient; clinician accounts come from an admin-only
endpoint. There is a test that posts `"role": "admin"` and asserts the result is
still a patient.

---

## The risk engine

Rules, not a model — a rehabilitation programme needs decisions a clinician can
read, audit and overrule, and every flag traces to a named threshold stored with
the flag. Tuning the thresholds later does not rewrite the history of flags
already raised.

| Rule | Trigger | Severity |
|---|---|---|
| `BP_HYPERTENSIVE_CRISIS` | ≥180/120 mmHg | severe |
| `BP_HIGH` | ≥160/100 mmHg | moderate |
| `BP_LOW` | systolic ≤90 mmHg | moderate |
| `HR_ABOVE_TARGET` | above the patient's prescribed ceiling | moderate / severe |
| `HR_LOW` | <45 bpm | moderate |
| `SPO2_LOW` / `SPO2_BORDERLINE` | <90% / <94% | severe / mild |
| `SYMPTOM_RED_FLAG` | cardiac red-flag keywords | moderate / severe |
| `SYMPTOM_SEVERE` | patient rates a symptom severe | moderate |
| `EXERTION_HIGH` | Borg RPE ≥17 | moderate |
| `SESSION_ABANDONED` | session logged incomplete | mild |

Two details that matter in use:

- **Thresholds are personalised where a baseline exists.** A heart rate of 115
  is unremarkable by default but flags for a patient whose prescribed ceiling is
  110.
- **Overlapping rules are suppressed.** A 190/125 reading raises one crisis flag,
  not a crisis flag *and* a high-BP flag. A queue that double-reports trains
  clinicians to ignore it.

Adding a rule means adding one function to the relevant tuple. Nothing else
changes.

---

## The six-minute walk test

The 6MWT is the standard submaximal measure of functional capacity in cardiac
rehabilitation: distance walked on a flat course in six minutes, with heart
rate, oxygen saturation and perceived exertion before and after. `screen()`
separates absolute contraindications (which block the test) from relative ones
(which require supervision), because collapsing the two would either forbid
safe tests or permit unsafe ones. Predicted distance uses the Enright &
Sherrill equations and returns `None` rather than a guess when height, weight,
age or sex is missing — a percentage of a predicted distance computed from an
assumed height is a number that looks clinical and means nothing.

### Cutting the manual input

The first version of this screen asked for roughly fifteen numbers, four
checkboxes and four Borg ratings across four stages, then asked for the rests
and the lowest SpO₂ from memory once the patient had sat down. Almost none of
that had to be typed:

| Was typed | Now |
|---|---|
| Resting HR, systolic, diastolic at screening | Offered from the last reading, with its age, if it is under 90 minutes old |
| The same three again as baseline | Carried through from the screening — it was the same measurement asked twice |
| Rests taken, seconds rested | A **Patient resting** button on the timer |
| Lowest SpO₂ during the walk | The minimum of the readings logged during the walk |
| SpO₂ at the end | The last reading logged, unless overridden |
| Four contraindication checkboxes | One line summarising the last test's answers, expandable if anything changed |
| Weight | From the most recent reading that carried one |
| Two baseline Borg ratings | Collapsed behind a link; optional by protocol |

What is left is what is genuinely new on the day: baseline SpO₂, post-walk heart
rate and SpO₂, and the two post-walk Borg ratings.

Two decisions in there are deliberately conservative. A reading older than
`VITALS_STALE_AFTER` (90 minutes) is shown but **not** pre-filled, because a
resting heart rate carried over from yesterday is not a pre-test observation and
must not clear a patient with one tap. And a previous test with no stored
screening answers offers nothing back rather than defaulting to all-false —
inventing "no contraindications" from an absence would clear a patient nobody
screened.

---

## Scheduling and video consultations

The clinician publishes a weekly rota; patients book themselves. There is no
request-and-approve step, because the back-and-forth of arranging a time is
precisely the part that does not need a person.

**The rota is rules, not rows.** `AvailabilityRule` stores "Tuesdays, 09:00 to
13:00, thirty-minute slots, video". Slots are generated on read by
`services/scheduling.py`. A clinic publishing twelve weeks of half-hour slots
would otherwise write four hundred rows that mostly go unused, and every rota
change would have to rewrite them.

**Double-booking is prevented in the database.** Two patients can post the same
slot in the same millisecond, so a check in the handler is not enough.
Appointments carry a `slot_key` (`clinician:20260908T0400`) under a unique
constraint; cancelling sets it to `NULL`, and NULLs do not collide under a
unique index on either SQLite or Postgres — so a cancelled time becomes bookable
again without needing a partial index.

**Timezones are converted in one place.** The rota is authored in clinic-local
wall-clock time and stored as a naive `time` against a weekday;
`CLINIC_TIMEZONE_OFFSET_MINUTES` converts. A scheduling bug that puts a
consultation six hours out is invisible in tests written in the same wrong
timezone as the code, so the tests assert on clinic-local time explicitly.

**Video rooms are Jitsi, and the room name is random.** Jitsi needs no account
or credentials, so booking produces a link that actually opens a call. The room
name comes from `secrets`, never from the appointment id, the patient, or the
date: a Jitsi room is created by whoever visits its URL first, and anyone who
knows the name can walk into the consultation. Cancelling clears the URL, so a
stale calendar invite cannot open a live room. Zoom and Google Meet sit behind
the same `create_room()` interface but need per-clinic OAuth credentials;
rather than fake a plausible-looking Zoom URL that dials nowhere, the service
raises and the API says the provider is not configured.

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

## Profile photographs

An upload is the one place the application accepts an arbitrary binary from an
unprivileged user and writes it to disk, so nothing is stored as received. The
image is decoded, verified, centre-cropped, resized and re-encoded, and only
the result is written:

- a file claiming to be a PNG that is actually a script does not survive a
  decode, so nothing executable reaches the media directory;
- re-encoding drops every metadata block, including the EXIF GPS tags that
  would otherwise publish the patient's home address alongside their face;
- a decompression bomb is refused by Pillow's own limit before allocation;
- the stored name is a random token, so a user cannot choose a path, an
  extension, or another patient's filename.

Avatars are then served without a bearer token, addressed by a 128-bit random
filename. The trade-off, stated plainly: an `<img>` tag cannot send an
`Authorization` header, so the alternatives are fetching every photograph as a
blob in JavaScript or a capability URL. The URL is unguessable and never
enumerable, but anyone it is forwarded to can see the photograph. A deployment
needing stricter control wants short-lived signed URLs, not a longer filename.


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


---

## Testing

```bash
cd backend && pytest
# 347 passed, 1 xfailed in ~118s
```

Each test runs against a fresh in-memory SQLite database on a shared
connection, so the suite needs no database server and tests cannot leak state
into one another.

Coverage is aimed at the boundaries rather than at a percentage:

- **Token handling** — an access token rejected at the refresh endpoint and a
  refresh token rejected as a bearer credential (token-type confusion).
- **Privilege escalation** — registration cannot grant a role.
- **Tenant isolation** — a second patient sees none of the first patient's rows;
  an unrelated clinician gets 404 on both the profile and its sub-resources.
- **Pagination integrity** — 15 rows across 4 pages asserts no duplicates and no
  skips, and a malformed cursor is a 400 rather than a 500.
- **Risk rules** — parameterised unit tests per threshold, plus the suppression
  and personalisation behaviours, run without a database or HTTP layer.
- **Account enumeration** — an unknown email and a wrong password return the
  same status.
- **Assistant safety** — emergency phrasings are intercepted and flagged;
  hypothetical questions are not; unanswerable questions refuse rather than
  guess; another patient cannot read or post to a conversation.
- **Retrieval quality** — top-1 passage asserted for 18 real patient questions.

---

## Design decisions

**Cursor pagination over offset.** Offsets shift under a reader when rows are
inserted concurrently, so a clinician scrolling a log can see a row twice or
miss one. The cursor is `(timestamp, id)` base64-encoded, which keeps the sort
total.

**Flags stored with their message and rule code, not a reference to live rule
logic.** A flag raised in March still reads correctly after the thresholds are
retuned in June.

**Plans superseded, never edited.** Prescribing deactivates the previous plan
and inserts a new one, so a session logged last month can still be compared
against the plan in force when it happened. Adherence would otherwise be
retroactively rewritten by a prescription change.

**String UUID primary keys.** Portable across SQLite and Postgres and safe in
URLs; sequential integers leak record counts and invite enumeration.

**Enums stored as strings.** The same models run on SQLite in development and
Postgres in production, and adding a value never needs an `ALTER TYPE`.

**The caseload is five aggregate queries, not one per patient.** The obvious
implementation issues a query per row and degrades linearly with caseload size;
this one is constant.

**The signing key refuses to be a placeholder in production.** `get_settings()`
raises at import if `ENVIRONMENT` is production and `JWT_SECRET_KEY` is still
the development default. A signing key committed to a public repository does not
make a deployment insecure later; every access token it has ever issued is
already forgeable.

**bcrypt used directly rather than through passlib.** passlib 1.7.4 is
unmaintained and warns against bcrypt ≥4. The cost factor is explicit, and
passwords beyond bcrypt's 72-byte limit are rejected rather than silently
truncated.

**A column type, not a fix at each call site, for UTC.** `DateTime(timezone=True)`
is a promise SQLite does not keep: Postgres returns an aware datetime, SQLite
returns a naive one. The difference is invisible in Python and appears in the
browser, which parses a timestamp with no offset as *local* time — a
consultation stored at 04:00 UTC displayed as 04:00 in Dhaka and 05:00 in
London. It was found by reading a booked appointment as 04:00 AM next to the
open slots for the same rota at 09:00 AM. Patching each serialiser would have
left the next model to reintroduce it, so `UtcDateTime` normalises both
directions in the type itself, and a regression test asserts every timestamp
leaves the API with an offset.

**Charting split into a lazily loaded chunk.** recharts is the single largest
dependency and only the patient view renders a chart; clinicians never download
it. The main bundle is ~50 kB, the chart chunk loads on demand.

---

## Status

Feature-complete for what it set out to do: authentication and roles, vitals and
symptoms with automatic flagging, exercise plans and session logging, adherence,
six-minute walk tests, self-service booking with video consultations,
patient–clinician messaging, editable profiles with photographs, the grounded
patient assistant with its safety guardrail and voice input, the clinician's
record assistant, both dashboards, migrations, Docker, CI, and 347 tests.

Known limitations, stated plainly:

- Cross-encoder reranking is implemented but disabled; the cause of its scoring
  behaviour on this machine is unresolved. See above.
- The dense threshold rests on a 12-query calibration set. That is enough to set
  a defensible number and not enough to call it validated.
- The corpus is 21 hand-written programme passages plus ~92 MedlinePlus topics.
  It answers rehabilitation questions well and anything outside cardiac
  rehabilitation not at all, by design.
- The Bengali emergency phrasings in `services/guardrails.py` are marked
  `PENDING NATIVE-SPEAKER REVIEW`. They are tested against twelve constructed
  cases; they have not been read by a Bangla-speaking clinician, which is what
  they need before anyone relies on them.
- Refresh tokens are stateless and cannot be revoked before expiry. A token
  denylist is the usual next step.
- There is no rate limiting on the auth endpoints yet.
- Zoom and Google Meet are recognised but cannot create meetings without
  per-clinic OAuth credentials; Jitsi is the working provider.
- The unread-message badge polls once a minute rather than using a socket.
- Avatars are served by capability URL rather than a signed, expiring one.

---

## Repository layout

```
backend/
  app/
    api/v1/       route modules, one per resource
    core/         config, security, pagination
    db/           session, declarative base, column types
    models/       SQLAlchemy models
    schemas/      Pydantic request and response models
    services/     the logic worth testing on its own
  alembic/        migrations
  corpus/         MedlinePlus health topics (public domain)
  scripts/        seed, corpus fetch, retrieval debugging
  tests/          347 tests
frontend/
  src/
    components/   presentational primitives and shared pieces
    pages/        one file per screen
    lib/          typed API client, types, utilities
docs/screenshots/
```

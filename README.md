# Cardiac Rehab Platform

A remote cardiac rehabilitation service. Patients log vital signs, symptoms and
exercise sessions; a rule engine evaluates every submission and raises flags for
clinician review; clinicians work a caseload prioritised by clinical urgency.

Built as a single-developer project: FastAPI + PostgreSQL on the back end,
React + TypeScript on the front, with an emphasis on the parts that are usually
skipped — authorisation boundaries, pagination that does not lose rows,
reversible migrations, and tests that assert the boundaries hold.

> **Not a medical device.** The thresholds in the risk engine are illustrative
> and this system has not been clinically validated.

---

## Contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [API](#api)
- [Authorisation model](#authorisation-model)
- [The risk engine](#the-risk-engine)
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

19 endpoints, versioned under `/api/v1`. The OpenAPI schema is generated from
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

## Testing

```bash
cd backend && pytest
# 77 passed in ~28s
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

**bcrypt used directly rather than through passlib.** passlib 1.7.4 is
unmaintained and warns against bcrypt ≥4. The cost factor is explicit, and
passwords beyond bcrypt's 72-byte limit are rejected rather than silently
truncated.

**Charting split into a lazily loaded chunk.** recharts is the single largest
dependency and only the patient view renders a chart; clinicians never download
it. The main bundle is ~50 kB, the chart chunk loads on demand.

---

## Status

Working: authentication and roles, vitals and symptoms with automatic flagging,
exercise plans and session logging, adherence, the clinician caseload and review
queue, both dashboards, migrations, Docker, and the test suite.

Not yet built: the voice Q&A module (transcription plus retrieval over
rehabilitation guidance) — the data model for conversations and messages is in
place, the endpoints are not.

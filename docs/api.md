# API reference

Every endpoint, and the rules that decide who may call it.

[← back to the README](../README.md)

---


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

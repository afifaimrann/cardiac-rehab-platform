# Design decisions

Choices that are not obvious from the code, and why they were made.

[← back to the README](../README.md)

---


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

**One accent, and it is the opposite of the alarm colour.** Blue for every
action, red reserved for clinical severity. They sit opposite each other on the
wheel, so a button and a flag can never be mistaken for the same kind of thing —
which matters more here than in most software, because the flags are the point.
Severity is the only saturated colour in the system; everything else is a cool
near-neutral, so a flag is always the most vivid thing on screen.

The ground is a cool white rather than a warm one. Warm paper looks handsome in
isolation and slightly jaundiced next to a chart, which is what this interface
is actually read beside.

**Charting split into a lazily loaded chunk.** recharts is the single largest
dependency and only the patient view renders a chart; clinicians never download
it. The main bundle is ~50 kB, the chart chunk loads on demand.

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

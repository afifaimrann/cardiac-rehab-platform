"""Timestamps must leave the API as aware UTC, on any database.

This is the regression test for a bug that was invisible in Python and only
appeared in a browser: SQLite ignores `timezone=True` and returns naive
datetimes, FastAPI then serialises them with no offset, and JavaScript parses
an offset-less timestamp as *local* time. A consultation stored at 04:00 UTC
displayed at 04:00 in Dhaka and 05:00 in London.
"""
from datetime import datetime, timedelta, timezone

from app.models.clinical import VitalsRecord


def _is_aware_utc(value: str) -> bool:
    parsed = datetime.fromisoformat(value)
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


async def test_the_orm_returns_aware_datetimes(session_factory):
    async with session_factory() as db:
        from app.models.user import PatientProfile, User
        from app.core.security import hash_password

        user = User(email="tz@test.com", hashed_password=hash_password("x" * 12),
                    full_name="TZ", role="patient")
        db.add(user)
        await db.flush()
        profile = PatientProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
        db.add(VitalsRecord(patient_id=profile.id, systolic=120, diastolic=80))
        await db.commit()
        record_id = (await db.execute(
            __import__("sqlalchemy").select(VitalsRecord.id)
        )).scalar_one()

    async with session_factory() as db:
        record = await db.get(VitalsRecord, record_id)
        assert record.recorded_at.tzinfo is not None
        assert record.created_at.tzinfo is not None


async def test_a_naive_datetime_is_stored_and_returned_as_utc(session_factory):
    """A naive value written by older code must not change meaning."""
    from app.models.user import PatientProfile, User
    from app.core.security import hash_password
    import sqlalchemy

    naive = datetime(2026, 9, 8, 4, 0, 0)
    async with session_factory() as db:
        user = User(email="tz2@test.com", hashed_password=hash_password("x" * 12),
                    full_name="TZ2", role="patient")
        db.add(user)
        await db.flush()
        profile = PatientProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
        db.add(VitalsRecord(patient_id=profile.id, recorded_at=naive, systolic=118))
        await db.commit()
        record_id = (await db.execute(sqlalchemy.select(VitalsRecord.id))).scalar_one()

    async with session_factory() as db:
        record = await db.get(VitalsRecord, record_id)
        assert record.recorded_at == naive.replace(tzinfo=timezone.utc)


async def test_vitals_serialise_with_an_offset(client, patient):
    await client.post("/api/v1/vitals", json={"systolic": 124, "diastolic": 80},
                      headers=patient["headers"])
    body = (await client.get("/api/v1/vitals", headers=patient["headers"])).json()
    assert _is_aware_utc(body["items"][0]["recorded_at"])


async def test_appointments_serialise_with_an_offset(client, clinician, assigned_patient):
    for d in range(7):
        await client.post(
            "/api/v1/appointments/availability",
            json={"weekday": d, "start_time": "09:00:00", "end_time": "17:00:00"},
            headers=clinician["headers"],
        )
    slots = (await client.get("/api/v1/appointments/slots",
                              headers=assigned_patient["headers"])).json()
    assert _is_aware_utc(slots[0]["starts_at"]), "generated slots"

    booked = (await client.post(
        "/api/v1/appointments", json={"starts_at": slots[0]["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()
    # The one that actually round-tripped through the database.
    assert _is_aware_utc(booked["starts_at"]), "a stored appointment"
    assert _is_aware_utc(booked["ends_at"])

    listed = (await client.get("/api/v1/appointments",
                               headers=assigned_patient["headers"])).json()
    assert _is_aware_utc(listed[0]["starts_at"])
    # And the instant is unchanged by the round trip.
    assert datetime.fromisoformat(listed[0]["starts_at"]) == \
        datetime.fromisoformat(slots[0]["starts_at"])


async def test_messages_serialise_with_an_offset(client, clinician, assigned_patient):
    await client.post("/api/v1/messages", json={"body": "hello"},
                      headers=assigned_patient["headers"])
    thread = (await client.get("/api/v1/messages",
                               headers=assigned_patient["headers"])).json()
    assert _is_aware_utc(thread["messages"][0]["sent_at"])


async def test_walk_tests_serialise_with_an_offset(client, patient):
    await client.post("/api/v1/walk-tests", json={"laps": 10},
                      headers=patient["headers"])
    tests = (await client.get("/api/v1/walk-tests", headers=patient["headers"])).json()
    assert _is_aware_utc(tests[0]["performed_at"])

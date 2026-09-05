"""Booking, double-booking, cancellation and access control."""
from datetime import datetime, timedelta, timezone

from app.core.config import settings


async def publish_rota(client, clinician, *, mode="online", location=None, weekday=None):
    """Open every weekday, so a slot always exists inside the notice window."""
    created = []
    days = range(7) if weekday is None else [weekday]
    for wd in days:
        r = await client.post(
            "/api/v1/appointments/availability",
            json={
                "weekday": wd, "start_time": "09:00:00", "end_time": "17:00:00",
                "slot_minutes": 30, "mode": mode, "location": location,
            },
            headers=clinician["headers"],
        )
        assert r.status_code == 201, r.text
        created.append(r.json())
    return created


async def first_slot(client, patient):
    slots = (await client.get("/api/v1/appointments/slots", headers=patient["headers"])).json()
    assert slots, "expected the rota to offer at least one slot"
    return slots[0]


# --- publishing a rota -----------------------------------------------------
async def test_patient_cannot_publish_a_rota(client, patient):
    r = await client.post(
        "/api/v1/appointments/availability",
        json={"weekday": 0, "start_time": "09:00:00", "end_time": "12:00:00"},
        headers=patient["headers"],
    )
    assert r.status_code == 403


async def test_in_person_rota_requires_a_location(client, clinician):
    r = await client.post(
        "/api/v1/appointments/availability",
        json={"weekday": 0, "start_time": "09:00:00", "end_time": "12:00:00",
              "mode": "in_person"},
        headers=clinician["headers"],
    )
    assert r.status_code == 422


async def test_end_before_start_is_rejected(client, clinician):
    r = await client.post(
        "/api/v1/appointments/availability",
        json={"weekday": 0, "start_time": "12:00:00", "end_time": "09:00:00"},
        headers=clinician["headers"],
    )
    assert r.status_code == 422


async def test_withdrawn_rule_stops_offering_slots(client, clinician, assigned_patient):
    rules = await publish_rota(client, clinician)
    for rule in rules:
        r = await client.delete(
            f"/api/v1/appointments/availability/{rule['id']}", headers=clinician["headers"]
        )
        assert r.status_code == 204
    slots = (await client.get(
        "/api/v1/appointments/slots", headers=assigned_patient["headers"]
    )).json()
    assert slots == []


# --- what a patient can see ------------------------------------------------
async def test_unassigned_patient_sees_no_slots(client, patient, clinician):
    await publish_rota(client, clinician)
    r = await client.get("/api/v1/appointments/slots", headers=patient["headers"])
    assert r.status_code == 200
    assert r.json() == []


async def test_unassigned_patient_cannot_book(client, patient):
    r = await client.post(
        "/api/v1/appointments",
        json={"starts_at": datetime.now(timezone.utc).isoformat()},
        headers=patient["headers"],
    )
    assert r.status_code == 409


async def test_slots_carry_the_clinician_name(client, clinician, assigned_patient):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    assert slot["clinician_name"] == "Dr Test"


# --- booking ---------------------------------------------------------------
async def test_booking_an_online_slot_creates_a_meeting_room(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)

    r = await client.post(
        "/api/v1/appointments",
        json={"starts_at": slot["starts_at"], "reason": "breathless on stairs"},
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["status"] == "scheduled"
    assert booking["meeting_provider"] == "jitsi"
    assert booking["meeting_url"].startswith(settings.JITSI_BASE_URL)
    assert booking["clinician_name"] == "Dr Test"


async def test_meeting_rooms_are_not_derived_from_patient_data(
    client, clinician, assigned_patient
):
    """A guessable room name lets a stranger walk into the consultation."""
    await publish_rota(client, clinician)
    slots = (await client.get(
        "/api/v1/appointments/slots", headers=assigned_patient["headers"]
    )).json()

    urls = []
    for slot in slots[:2]:
        r = await client.post(
            "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
            headers=assigned_patient["headers"],
        )
        urls.append(r.json()["meeting_url"])

    assert urls[0] != urls[1]
    room = urls[0].rsplit("/", 1)[-1]
    assert len(room) > 30
    for leak in (assigned_patient["profile_id"], assigned_patient["user_id"], "Test"):
        assert leak.lower() not in room.lower()


async def test_in_person_booking_has_no_meeting_url(client, clinician, assigned_patient):
    await publish_rota(client, clinician, mode="in_person", location="Clinic B, 2nd floor")
    slot = await first_slot(client, assigned_patient)

    r = await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["mode"] == "in_person"
    assert booking["meeting_url"] is None
    assert booking["location"] == "Clinic B, 2nd floor"


async def test_cannot_request_a_mode_the_slot_does_not_offer(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician, mode="in_person", location="Clinic B")
    slot = await first_slot(client, assigned_patient)
    r = await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"], "mode": "online"},
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 400


async def test_a_time_the_rota_never_offered_is_refused(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician)
    at_3am = (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=3, minute=17, second=0, microsecond=0
    )
    r = await client.post(
        "/api/v1/appointments", json={"starts_at": at_3am.isoformat()},
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 409


async def test_booked_slot_disappears_and_cannot_be_taken_twice(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)

    first = await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )
    assert first.status_code == 201

    remaining = (await client.get(
        "/api/v1/appointments/slots", headers=assigned_patient["headers"]
    )).json()
    assert slot["starts_at"] not in [s["starts_at"] for s in remaining]

    second = await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )
    assert second.status_code == 409


# --- cancellation ----------------------------------------------------------
async def test_cancelling_releases_the_slot_and_kills_the_room(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    r = await client.post(
        f"/api/v1/appointments/{booking['id']}/cancel",
        json={"reason": "work"}, headers=assigned_patient["headers"],
    )
    assert r.status_code == 200
    cancelled = r.json()
    assert cancelled["status"] == "cancelled"
    # A live link on a cancelled appointment still opens a call for anyone
    # holding the calendar invite.
    assert cancelled["meeting_url"] is None

    again = (await client.get(
        "/api/v1/appointments/slots", headers=assigned_patient["headers"]
    )).json()
    assert slot["starts_at"] in [s["starts_at"] for s in again]


async def test_clinician_can_cancel_their_own_appointment(
    client, clinician, assigned_patient
):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    r = await client.post(
        f"/api/v1/appointments/{booking['id']}/cancel", json={},
        headers=clinician["headers"],
    )
    assert r.status_code == 200


async def test_a_stranger_cannot_cancel_and_is_told_nothing(
    client, session_factory, clinician, assigned_patient
):
    from tests.conftest import _make_user, auth_headers
    from app.models import UserRole

    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    await _make_user(session_factory, "other@test.com", UserRole.PATIENT, "Other")
    intruder = await auth_headers(client, "other@test.com")

    r = await client.post(
        f"/api/v1/appointments/{booking['id']}/cancel", json={}, headers=intruder
    )
    # 404, not 403: the response must not confirm the appointment exists.
    assert r.status_code == 404


async def test_cancelling_twice_is_refused(client, clinician, assigned_patient):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    await client.post(f"/api/v1/appointments/{booking['id']}/cancel", json={},
                      headers=assigned_patient["headers"])
    r = await client.post(f"/api/v1/appointments/{booking['id']}/cancel", json={},
                          headers=assigned_patient["headers"])
    assert r.status_code == 409


# --- the clinician side ----------------------------------------------------
async def test_diary_shows_the_booking(client, clinician, assigned_patient):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    await client.post("/api/v1/appointments", json={"starts_at": slot["starts_at"]},
                      headers=assigned_patient["headers"])

    diary = (await client.get("/api/v1/appointments/clinic",
                              headers=clinician["headers"])).json()
    assert len(diary) == 1
    assert diary[0]["patient_name"] == "Test Patient"


async def test_clinician_records_an_outcome(client, clinician, assigned_patient):
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    r = await client.patch(
        f"/api/v1/appointments/{booking['id']}",
        json={"status": "completed", "clinician_notes": "Tolerating the plan well."},
        headers=clinician["headers"],
    )
    assert r.status_code == 200
    assert r.json()["clinician_notes"] == "Tolerating the plan well."


async def test_patch_cannot_be_used_to_cancel(client, clinician, assigned_patient):
    """Cancelling through PATCH would leave slot_key set and the time unbookable."""
    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    r = await client.patch(
        f"/api/v1/appointments/{booking['id']}", json={"status": "cancelled"},
        headers=clinician["headers"],
    )
    assert r.status_code == 400


async def test_clinician_cannot_touch_another_clinicians_appointment(
    client, session_factory, clinician, assigned_patient
):
    from tests.conftest import _make_user, auth_headers
    from app.models import UserRole

    await publish_rota(client, clinician)
    slot = await first_slot(client, assigned_patient)
    booking = (await client.post(
        "/api/v1/appointments", json={"starts_at": slot["starts_at"]},
        headers=assigned_patient["headers"],
    )).json()

    await _make_user(session_factory, "doc2@test.com", UserRole.CLINICIAN, "Dr Two")
    other = await auth_headers(client, "doc2@test.com")

    r = await client.patch(f"/api/v1/appointments/{booking['id']}",
                           json={"clinician_notes": "snooping"}, headers=other)
    assert r.status_code == 404


async def test_clinician_cannot_read_an_unassigned_patients_appointments(
    client, session_factory, clinician, assigned_patient
):
    from tests.conftest import _make_user, auth_headers
    from app.models import UserRole

    await _make_user(session_factory, "doc2@test.com", UserRole.CLINICIAN, "Dr Two")
    other = await auth_headers(client, "doc2@test.com")

    r = await client.get(
        f"/api/v1/appointments/patients/{assigned_patient['profile_id']}", headers=other
    )
    assert r.status_code == 404

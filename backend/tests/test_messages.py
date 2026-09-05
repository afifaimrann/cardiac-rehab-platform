"""The patient-to-care-team thread."""
from app.models import UserRole
from tests.conftest import _make_user, auth_headers


async def test_patient_without_a_clinician_cannot_send(client, patient):
    r = await client.post("/api/v1/messages", json={"body": "hello"},
                          headers=patient["headers"])
    assert r.status_code == 409


async def test_empty_message_is_rejected(client, assigned_patient):
    r = await client.post("/api/v1/messages", json={"body": ""},
                          headers=assigned_patient["headers"])
    assert r.status_code == 422


async def test_round_trip(client, clinician, assigned_patient):
    sent = await client.post(
        "/api/v1/messages", json={"body": "My ankles are swollen this week."},
        headers=assigned_patient["headers"],
    )
    assert sent.status_code == 201
    assert sent.json()["sender_role"] == "patient"

    thread = (await client.get(
        f"/api/v1/messages/patients/{assigned_patient['profile_id']}",
        headers=clinician["headers"],
    )).json()
    assert thread["unread_count"] == 1
    assert thread["counterparty_name"] == "Test Patient"
    assert thread["messages"][0]["body"] == "My ankles are swollen this week."

    reply = await client.post(
        f"/api/v1/messages/patients/{assigned_patient['profile_id']}",
        json={"body": "Weigh yourself each morning and send me the numbers."},
        headers=clinician["headers"],
    )
    assert reply.status_code == 201

    patient_view = (await client.get(
        "/api/v1/messages", headers=assigned_patient["headers"]
    )).json()
    assert patient_view["counterparty_name"] == "Dr Test"
    assert [m["body"] for m in patient_view["messages"]] == [
        "My ankles are swollen this week.",
        "Weigh yourself each morning and send me the numbers.",
    ]


async def test_messages_are_ordered_oldest_first(client, clinician, assigned_patient):
    for i in range(4):
        await client.post("/api/v1/messages", json={"body": f"note {i}"},
                          headers=assigned_patient["headers"])
    thread = (await client.get("/api/v1/messages",
                               headers=assigned_patient["headers"])).json()
    assert [m["body"] for m in thread["messages"]] == [f"note {i}" for i in range(4)]


async def test_own_messages_never_count_as_unread(client, assigned_patient):
    await client.post("/api/v1/messages", json={"body": "hello"},
                      headers=assigned_patient["headers"])
    unread = (await client.get("/api/v1/messages/unread",
                               headers=assigned_patient["headers"])).json()
    assert unread["unread_count"] == 0


async def test_opening_the_thread_marks_the_other_side_read(
    client, clinician, assigned_patient
):
    await client.post(
        f"/api/v1/messages/patients/{assigned_patient['profile_id']}",
        json={"body": "Please book a review."}, headers=clinician["headers"],
    )

    before = (await client.get("/api/v1/messages/unread",
                               headers=assigned_patient["headers"])).json()
    assert before["unread_count"] == 1

    # The thread reports what was unread on arrival, then clears it.
    opened = (await client.get("/api/v1/messages",
                               headers=assigned_patient["headers"])).json()
    assert opened["unread_count"] == 1

    after = (await client.get("/api/v1/messages/unread",
                              headers=assigned_patient["headers"])).json()
    assert after["unread_count"] == 0


async def test_another_clinician_cannot_read_the_thread(
    client, session_factory, clinician, assigned_patient
):
    await client.post("/api/v1/messages", json={"body": "private"},
                      headers=assigned_patient["headers"])
    await _make_user(session_factory, "doc2@test.com", UserRole.CLINICIAN, "Dr Two")
    other = await auth_headers(client, "doc2@test.com")

    r = await client.get(
        f"/api/v1/messages/patients/{assigned_patient['profile_id']}", headers=other
    )
    assert r.status_code == 404


async def test_another_patient_sees_their_own_empty_thread(
    client, session_factory, clinician, assigned_patient
):
    """A patient endpoint takes no id, so there is nothing to tamper with."""
    await client.post("/api/v1/messages", json={"body": "private"},
                      headers=assigned_patient["headers"])
    await _make_user(session_factory, "other@test.com", UserRole.PATIENT, "Other")
    other = await auth_headers(client, "other@test.com")

    thread = (await client.get("/api/v1/messages", headers=other)).json()
    assert thread["messages"] == []


async def test_clinician_has_no_patient_thread_of_their_own(client, clinician):
    r = await client.get("/api/v1/messages", headers=clinician["headers"])
    assert r.status_code == 403

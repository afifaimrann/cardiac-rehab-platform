"""Question answering: grounding, the safety guardrail, and ownership."""
import pytest


async def _conversation(client, patient):
    r = await client.post("/api/v1/conversations", json={}, headers=patient["headers"])
    assert r.status_code == 201
    return r.json()["id"]


async def test_answer_is_grounded_and_cited(client, patient):
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "How hard should I be exercising?"},
        headers=patient["headers"],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["citations"], "an answerable question must cite its sources"
    assert body["citations"][0]["title"] == "How hard should I exercise?"
    assert body["is_emergency"] is False
    # Without an API key the answer is extractive, drawn verbatim from the corpus.
    assert body["generated"] is False
    assert "Borg" in body["answer"]["content"]


async def test_unanswerable_question_refuses_rather_than_guessing(client, patient):
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "What is the capital of Mongolia?"},
        headers=patient["headers"],
    )
    body = r.json()
    assert body["citations"] == []
    assert "rehabilitation team" in body["answer"]["content"]


@pytest.mark.parametrize(
    "question",
    [
        "I'm having chest pain right now",
        "chest tightness and a cold sweat",
        "I can't breathe properly",
        "I fainted this morning",
    ],
)
async def test_emergency_language_is_intercepted(client, patient, question):
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask", json={"question": question}, headers=patient["headers"]
    )
    body = r.json()
    assert body["is_emergency"] is True
    assert "emergency number" in body["answer"]["content"]
    # The answer must not be dressed up with handbook citations.
    assert body["citations"] == []


async def test_emergency_raises_a_flag_for_the_care_team(client, patient, clinician, admin):
    await client.patch(
        f"/api/v1/clinician/patients/{patient['profile_id']}/assignment",
        json={"clinician_id": clinician["user_id"]},
        headers=admin["headers"],
    )
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "I'm having chest pain right now"},
        headers=patient["headers"],
    )
    assert [f["rule_code"] for f in r.json()["flags_raised"]] == ["CHAT_EMERGENCY_LANGUAGE"]

    queue = (await client.get("/api/v1/clinician/flags", headers=clinician["headers"])).json()
    assert any(f["rule_code"] == "CHAT_EMERGENCY_LANGUAGE" for f in queue["items"])
    assert any(f["severity"] == "severe" for f in queue["items"])


async def test_hypothetical_question_is_not_treated_as_an_emergency(client, patient):
    """'What should I do if...' is a teaching question, not a symptom report."""
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "What should I do if I get chest pain during exercise?"},
        headers=patient["headers"],
    )
    body = r.json()
    assert body["is_emergency"] is False
    assert body["citations"], "it should still answer from the handbook"


async def test_history_records_both_turns(client, patient):
    cid = await _conversation(client, patient)
    await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "Can I drive after my heart attack?"},
        headers=patient["headers"],
    )
    msgs = (
        await client.get(f"/api/v1/conversations/{cid}/messages", headers=patient["headers"])
    ).json()["items"]
    assert len(msgs) == 2
    assert {m["role"] for m in msgs} == {"user", "assistant"}


async def test_conversation_is_titled_from_the_first_question(client, patient):
    cid = await _conversation(client, patient)
    await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "Can I drive after my heart attack?"},
        headers=patient["headers"],
    )
    convos = (await client.get("/api/v1/conversations", headers=patient["headers"])).json()
    assert convos[0]["title"] == "Can I drive after my heart attack?"


async def test_another_patient_cannot_read_or_post_to_a_conversation(client, patient):
    cid = await _conversation(client, patient)

    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "nosy@test.com", "password": "a-long-enough-password", "full_name": "Nosy"},
    )
    headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert (
        await client.get(f"/api/v1/conversations/{cid}/messages", headers=headers)
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/conversations/{cid}/ask", json={"question": "hello"}, headers=headers
        )
    ).status_code == 404


async def test_clinician_cannot_use_the_patient_chat(client, clinician):
    r = await client.post("/api/v1/conversations", json={}, headers=clinician["headers"])
    assert r.status_code == 403


async def test_empty_question_is_rejected(client, patient):
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask", json={"question": ""}, headers=patient["headers"]
    )
    assert r.status_code == 422


async def test_audio_endpoint_reports_unavailable_without_a_key(client, patient):
    """No API key configured: say so clearly rather than failing obscurely."""
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask-audio",
        files={"audio": ("q.webm", b"fake-audio-bytes", "audio/webm")},
        headers=patient["headers"],
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


async def test_audio_rejects_an_unsupported_content_type(client, patient):
    cid = await _conversation(client, patient)
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask-audio",
        files={"audio": ("q.txt", b"not audio", "text/plain")},
        headers=patient["headers"],
    )
    assert r.status_code == 415

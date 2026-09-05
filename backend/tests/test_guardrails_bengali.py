# -*- coding: utf-8 -*-
"""Emergency detection in Bengali and transliterated Bengali.

A missed emergency here is the most serious failure this system can have, so
these cases are asserted explicitly rather than left to the English patterns.
"""
import pytest

from app.services.guardrails import EMERGENCY_RESPONSE_BN, check

LIVE_SYMPTOMS_BN = [
    "বুকে ব্যথা হচ্ছে",
    "আমার বুকে ব্যাথা করছে",
    "বুকে চাপ লাগছে",
    "শ্বাসকষ্ট হচ্ছে",
    "শ্বাস নিতে পারছি না",
    "মাথা ঘুরছে",
    "আমি অজ্ঞান হয়ে গিয়েছিলাম",
    "ঠান্ডা ঘাম হচ্ছে",
    "বাম হাতে ব্যথা হচ্ছে",
    "বুক ধড়ফড় করছে",
]

LIVE_SYMPTOMS_TRANSLITERATED = [
    "buke betha hocche",
    "amar buke byatha korche",
    "shwash kosto hocche",
    "matha ghurche",
    "thanda gham hocche",
]

CODE_SWITCHED = [
    "আমার chest pain হচ্ছে",
    "chest e betha hocche",
]


@pytest.mark.parametrize("question", LIVE_SYMPTOMS_BN)
def test_bengali_symptoms_are_intercepted(question):
    verdict = check(question)
    assert verdict.is_emergency, f"missed: {question}"
    assert verdict.response == EMERGENCY_RESPONSE_BN


@pytest.mark.parametrize("question", LIVE_SYMPTOMS_TRANSLITERATED)
def test_transliterated_symptoms_are_intercepted(question):
    assert check(question).is_emergency, f"missed: {question}"


@pytest.mark.parametrize("question", CODE_SWITCHED)
def test_code_switched_symptoms_are_intercepted(question):
    assert check(question).is_emergency, f"missed: {question}"


def test_escalation_is_returned_in_the_patients_language():
    """Advice nobody can read is not advice."""
    assert check("বুকে ব্যথা হচ্ছে").response == EMERGENCY_RESPONSE_BN
    assert "জরুরি নম্বরে ফোন করুন" in EMERGENCY_RESPONSE_BN

    english = check("I'm having chest pain right now")
    assert english.response != EMERGENCY_RESPONSE_BN
    assert "emergency number" in english.response


@pytest.mark.parametrize(
    "question",
    [
        "ব্যায়াম করার সময় বুকে ব্যথা হলে কি করব",   # hypothetical
        "বুকে ব্যথা কেন হয়",                        # explanatory
    ],
)
def test_hypothetical_bengali_questions_are_answered_normally(question):
    assert not check(question).is_emergency


def test_present_tense_overrides_the_hypothetical_marker():
    """'হচ্ছে' means it is happening now, whatever else the sentence contains."""
    assert check("বুকে ব্যথা হচ্ছে, এখন কি করব").is_emergency


@pytest.mark.parametrize(
    "question",
    [
        "আমি কি হাঁটতে পারব",
        "কতটুকু ব্যায়াম করা উচিত",
        "ওষুধ খেতে ভুলে গেছি",
    ],
)
def test_ordinary_bengali_questions_are_not_flagged(question):
    assert not check(question).is_emergency


async def test_bengali_emergency_answer_is_returned_in_bengali(client, patient):
    """Regression: the service once returned the English constant regardless of
    the language the guardrail had already chosen."""
    conversation = await client.post(
        "/api/v1/conversations", json={}, headers=patient["headers"]
    )
    cid = conversation.json()["id"]
    r = await client.post(
        f"/api/v1/conversations/{cid}/ask",
        json={"question": "বুকে ব্যথা হচ্ছে"},
        headers=patient["headers"],
    )
    body = r.json()
    assert body["is_emergency"] is True
    assert "জরুরি নম্বরে ফোন করুন" in body["answer"]["content"]
    assert "emergency number" not in body["answer"]["content"]
    assert [f["rule_code"] for f in body["flags_raised"]] == ["CHAT_EMERGENCY_LANGUAGE"]


@pytest.mark.parametrize(
    "question",
    [
        "আমার আজকে বুকে অনেক ব্যথা করছে",
        "বুকে খুব ব্যথা",
        "বুকে প্রচণ্ড ব্যথা হচ্ছে",
        "আমার বুকে সকাল থেকে ব্যথা",
        "buke onek betha hocche",
        "I have a lot of chest pain today",
        "really bad chest pain right now",
    ],
)
def test_words_between_body_part_and_symptom_still_trigger(question):
    """Regression: patterns originally required 'বুকে' adjacent to 'ব্যথা', so a
    real patient message -- "আমার আজকে বুকে অনেক ব্যথা করছে" -- was answered from
    the handbook with citations and raised no flag. Bangla routinely puts
    intensifiers and time words between the two."""
    assert check(question).is_emergency, f"missed: {question}"

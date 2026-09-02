"""Vitals and symptom endpoints: validation, flagging, pagination, isolation."""
import pytest


async def test_logging_vitals_returns_flags_inline(client, patient):
    r = await client.post(
        "/api/v1/vitals", json={"systolic": 190, "diastolic": 125}, headers=patient["headers"]
    )
    assert r.status_code == 201
    body = r.json()
    assert body["vitals"]["systolic"] == 190
    assert [f["rule_code"] for f in body["flags_raised"]] == ["BP_HYPERTENSIVE_CRISIS"]


async def test_normal_reading_raises_no_flags(client, patient):
    r = await client.post(
        "/api/v1/vitals",
        json={"systolic": 118, "diastolic": 76, "heart_rate": 68, "spo2": 98},
        headers=patient["headers"],
    )
    assert r.json()["flags_raised"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"note": "no measurements at all"},
        {"systolic": 110, "diastolic": 130},   # diastolic above systolic
        {"heart_rate": 900},                   # out of range
        {"spo2": 140},
        {"weight_kg": -5},
    ],
)
async def test_invalid_readings_are_rejected(client, patient, payload):
    r = await client.post("/api/v1/vitals", json=payload, headers=patient["headers"])
    assert r.status_code == 422


async def test_vitals_require_authentication(client):
    assert (await client.post("/api/v1/vitals", json={"heart_rate": 70})).status_code in (401, 403)
    assert (await client.get("/api/v1/vitals")).status_code in (401, 403)


async def test_clinician_cannot_use_patient_routes(client, clinician):
    """Role separation: these endpoints act on 'my own' record, which a clinician lacks."""
    r = await client.post("/api/v1/vitals", json={"heart_rate": 70}, headers=clinician["headers"])
    assert r.status_code == 403


async def test_pagination_does_not_repeat_or_skip_rows(client, patient):
    for hr in range(60, 75):
        await client.post("/api/v1/vitals", json={"heart_rate": hr}, headers=patient["headers"])

    seen, cursor, pages = [], None, 0
    while True:
        url = f"/api/v1/vitals?limit=4{f'&cursor={cursor}' if cursor else ''}"
        body = (await client.get(url, headers=patient["headers"])).json()
        seen.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        pages += 1
        if not cursor or pages > 10:
            break

    assert len(seen) == 15
    assert len(set(seen)) == 15          # no duplicates across pages
    assert pages == 4                     # 4 + 4 + 4 + 3


async def test_pages_are_ordered_newest_first(client, patient):
    for hr in (60, 61, 62):
        await client.post("/api/v1/vitals", json={"heart_rate": hr}, headers=patient["headers"])
    items = (await client.get("/api/v1/vitals", headers=patient["headers"])).json()["items"]
    timestamps = [i["recorded_at"] for i in items]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_malformed_cursor_is_a_client_error(client, patient):
    r = await client.get("/api/v1/vitals?cursor=!!!not-base64!!!", headers=patient["headers"])
    assert r.status_code == 400


async def test_patients_cannot_see_each_other(client, patient):
    await client.post("/api/v1/vitals", json={"heart_rate": 70}, headers=patient["headers"])

    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "other@test.com", "password": "a-long-enough-password", "full_name": "Other"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    body = (await client.get("/api/v1/vitals", headers=other_headers)).json()
    assert body["items"] == []


async def test_symptom_red_flag_is_raised(client, patient):
    r = await client.post(
        "/api/v1/symptoms",
        json={"description": "Chest pain climbing stairs", "severity": "moderate"},
        headers=patient["headers"],
    )
    assert r.status_code == 201
    assert [f["rule_code"] for f in r.json()["flags_raised"]] == ["SYMPTOM_RED_FLAG"]


async def test_empty_symptom_is_rejected(client, patient):
    r = await client.post(
        "/api/v1/symptoms", json={"description": "", "severity": "mild"}, headers=patient["headers"]
    )
    assert r.status_code == 422

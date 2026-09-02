"""Plans, session logging and adherence."""
from datetime import date


PLAN = {
    "title": "Phase II walking",
    "starts_on": str(date.today()),
    "sessions_per_week": 3,
    "minutes_per_session": 30,
    "target_exertion_max": 14,
}


async def _prescribe(client, clinician, patient, **overrides):
    return await client.post(
        f"/api/v1/patients/{patient['profile_id']}/plans",
        json={**PLAN, **overrides},
        headers=clinician["headers"],
    )


async def test_clinician_prescribes_and_patient_sees_the_plan(client, assigned_patient, clinician):
    r = await _prescribe(client, clinician, assigned_patient)
    assert r.status_code == 201

    active = await client.get("/api/v1/plans/active", headers=assigned_patient["headers"])
    assert active.status_code == 200
    assert active.json()["title"] == "Phase II walking"


async def test_prescribing_supersedes_the_previous_plan(client, assigned_patient, clinician):
    await _prescribe(client, clinician, assigned_patient)
    await _prescribe(client, clinician, assigned_patient, title="Phase III")

    plans = (
        await client.get(
            f"/api/v1/patients/{assigned_patient['profile_id']}/plans",
            headers=clinician["headers"],
        )
    ).json()
    assert len(plans) == 2
    assert sum(p["is_active"] for p in plans) == 1        # exactly one active
    assert plans[0]["title"] == "Phase III"


async def test_plan_dates_are_validated(client, assigned_patient, clinician):
    r = await _prescribe(client, clinician, assigned_patient, ends_on="2020-01-01")
    assert r.status_code == 422


async def test_patient_cannot_prescribe_to_themselves(client, assigned_patient):
    r = await client.post(
        f"/api/v1/patients/{assigned_patient['profile_id']}/plans",
        json=PLAN,
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 403


async def test_session_attaches_to_the_active_plan(client, assigned_patient, clinician):
    plan = (await _prescribe(client, clinician, assigned_patient)).json()
    r = await client.post(
        "/api/v1/sessions",
        json={"activity": "Treadmill walk", "duration_minutes": 30, "perceived_exertion": 12},
        headers=assigned_patient["headers"],
    )
    assert r.status_code == 201
    assert r.json()["session"]["plan_id"] == plan["id"]
    assert r.json()["flags_raised"] == []


async def test_high_exertion_session_raises_a_flag(client, assigned_patient):
    r = await client.post(
        "/api/v1/sessions",
        json={"activity": "Cycle", "duration_minutes": 20, "perceived_exertion": 18},
        headers=assigned_patient["headers"],
    )
    assert [f["rule_code"] for f in r.json()["flags_raised"]] == ["EXERTION_HIGH"]


async def test_abandoned_session_raises_a_flag(client, assigned_patient):
    r = await client.post(
        "/api/v1/sessions",
        json={"activity": "Walk", "duration_minutes": 5, "completed": False},
        headers=assigned_patient["headers"],
    )
    assert "SESSION_ABANDONED" in [f["rule_code"] for f in r.json()["flags_raised"]]


async def test_adherence_is_null_without_a_plan(client, patient):
    body = (await client.get("/api/v1/adherence", headers=patient["headers"])).json()
    assert body["adherence_pct"] is None
    assert body["sessions_expected"] == 0


async def test_adherence_counts_only_completed_sessions(client, assigned_patient, clinician):
    await _prescribe(client, clinician, assigned_patient)
    for completed in (True, True, False):
        await client.post(
            "/api/v1/sessions",
            json={"activity": "Walk", "duration_minutes": 30, "completed": completed},
            headers=assigned_patient["headers"],
        )

    body = (
        await client.get("/api/v1/adherence?window_days=7", headers=assigned_patient["headers"])
    ).json()
    assert body["sessions_completed"] == 2
    assert body["sessions_expected"] == 3.0        # 3/week over a 7-day window
    assert body["adherence_pct"] == 66.7

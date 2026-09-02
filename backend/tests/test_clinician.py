"""Caseload, the flag queue and the boundaries around them."""


async def test_caseload_lists_only_assigned_patients(client, assigned_patient, clinician):
    body = (await client.get("/api/v1/clinician/caseload", headers=clinician["headers"])).json()
    assert len(body["patients"]) == 1
    assert body["patients"][0]["patient_id"] == assigned_patient["profile_id"]


async def test_unassigned_patients_are_invisible(client, patient, clinician):
    """The patient exists but is not assigned, so this caseload is empty."""
    body = (await client.get("/api/v1/clinician/caseload", headers=clinician["headers"])).json()
    assert body["patients"] == []


async def test_caseload_counts_open_flags(client, assigned_patient, clinician):
    await client.post(
        "/api/v1/vitals", json={"systolic": 190, "diastolic": 125}, headers=assigned_patient["headers"]
    )
    row = (await client.get("/api/v1/clinician/caseload", headers=clinician["headers"])).json()[
        "patients"
    ][0]
    assert row["open_flags"] == 1
    assert row["highest_open_severity"] == "severe"


async def test_patients_cannot_read_the_caseload(client, patient):
    assert (
        await client.get("/api/v1/clinician/caseload", headers=patient["headers"])
    ).status_code == 403


async def test_unrelated_clinician_gets_404_not_403(client, assigned_patient, admin):
    """404 rather than 403: the API must not confirm records outside the caseload."""
    r = await client.post(
        "/api/v1/auth/clinicians",
        json={"email": "other.doc@test.com", "password": "a-long-enough-password", "full_name": "Other"},
        headers=admin["headers"],
    )
    assert r.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "other.doc@test.com", "password": "a-long-enough-password"},
    )
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}

    pid = assigned_patient["profile_id"]
    assert (await client.get(f"/api/v1/clinician/patients/{pid}", headers=other)).status_code == 404
    assert (
        await client.get(f"/api/v1/clinician/patients/{pid}/vitals", headers=other)
    ).status_code == 404


async def test_flag_queue_is_scoped_to_the_caseload(client, assigned_patient, clinician, admin):
    await client.post(
        "/api/v1/vitals", json={"systolic": 190, "diastolic": 125}, headers=assigned_patient["headers"]
    )
    mine = (await client.get("/api/v1/clinician/flags", headers=clinician["headers"])).json()
    assert len(mine["items"]) == 1

    login = await client.post(
        "/api/v1/auth/clinicians",
        json={"email": "doc3@test.com", "password": "a-long-enough-password", "full_name": "Doc 3"},
        headers=admin["headers"],
    )
    assert login.status_code == 201
    tokens = await client.post(
        "/api/v1/auth/login", json={"email": "doc3@test.com", "password": "a-long-enough-password"}
    )
    other = {"Authorization": f"Bearer {tokens.json()['access_token']}"}
    assert (await client.get("/api/v1/clinician/flags", headers=other)).json()["items"] == []


async def test_resolving_a_flag_records_who_and_when(client, assigned_patient, clinician):
    await client.post(
        "/api/v1/vitals", json={"systolic": 190, "diastolic": 125}, headers=assigned_patient["headers"]
    )
    flag = (await client.get("/api/v1/clinician/flags", headers=clinician["headers"])).json()[
        "items"
    ][0]

    r = await client.patch(
        f"/api/v1/clinician/flags/{flag['id']}",
        json={"status": "resolved", "resolution_note": "Called patient."},
        headers=clinician["headers"],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["resolved_at"] is not None

    # It leaves the open queue.
    assert (await client.get("/api/v1/clinician/flags", headers=clinician["headers"])).json()[
        "items"
    ] == []


async def test_a_flag_cannot_be_reopened_here(client, assigned_patient, clinician):
    await client.post(
        "/api/v1/vitals", json={"systolic": 190, "diastolic": 125}, headers=assigned_patient["headers"]
    )
    flag = (await client.get("/api/v1/clinician/flags", headers=clinician["headers"])).json()[
        "items"
    ][0]
    r = await client.patch(
        f"/api/v1/clinician/flags/{flag['id']}", json={"status": "open"}, headers=clinician["headers"]
    )
    assert r.status_code == 422


async def test_missing_flag_is_404(client, clinician):
    r = await client.patch(
        "/api/v1/clinician/flags/does-not-exist",
        json={"status": "resolved"},
        headers=clinician["headers"],
    )
    assert r.status_code == 404


async def test_only_admin_assigns_patients(client, patient, clinician):
    r = await client.patch(
        f"/api/v1/clinician/patients/{patient['profile_id']}/assignment",
        json={"clinician_id": clinician["user_id"]},
        headers=clinician["headers"],
    )
    assert r.status_code == 403


async def test_assignment_rejects_a_non_clinician(client, patient, admin):
    r = await client.patch(
        f"/api/v1/clinician/patients/{patient['profile_id']}/assignment",
        json={"clinician_id": patient["user_id"]},
        headers=admin["headers"],
    )
    assert r.status_code == 422

"""Authentication, token handling and account provisioning."""
import pytest

from tests.conftest import TEST_PASSWORD

REGISTRATION = {
    "email": "new@test.com",
    "password": "a-long-enough-password",
    "full_name": "New Patient",
}


async def test_register_returns_tokens_and_creates_profile(client):
    r = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "patient"
    # The clinical profile must exist immediately, not on first write.
    assert me.json()["patient_profile"] is not None


async def test_duplicate_email_is_rejected(client):
    await client.post("/api/v1/auth/register", json=REGISTRATION)
    r = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert r.status_code == 409


async def test_registration_cannot_grant_a_role(client):
    """Passing a role in the body must not escalate privilege."""
    r = await client.post("/api/v1/auth/register", json={**REGISTRATION, "role": "admin"})
    assert r.status_code == 201
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert me.json()["user"]["role"] == "patient"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "a-long-enough-password", "full_name": "X"},
        {"email": "ok@test.com", "password": "short", "full_name": "X"},
        {"email": "ok@test.com", "password": "a-long-enough-password", "full_name": ""},
    ],
)
async def test_registration_validation(client, payload):
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 422


async def test_login_rejects_wrong_password(client, patient):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "patient@test.com", "password": "wrong-password"}
    )
    assert r.status_code == 401


async def test_login_rejects_unknown_email(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@test.com", "password": TEST_PASSWORD}
    )
    # Same status and shape as a wrong password: no account enumeration.
    assert r.status_code == 401


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer garbage", "Basic abc"])
async def test_protected_route_rejects_bad_credentials(client, header):
    headers = {"Authorization": header} if header is not None else {}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code in (401, 403)


async def test_refresh_returns_new_tokens(client, patient):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "patient@test.com", "password": TEST_PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert r.json()["access_token"]


async def test_access_token_is_rejected_at_refresh(client, patient):
    """Token type confusion: an access token must not mint new credentials."""
    access = patient["headers"]["Authorization"].removeprefix("Bearer ")
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


async def test_refresh_token_is_rejected_as_access_token(client, patient):
    login = await client.post(
        "/api/v1/auth/login", json={"email": "patient@test.com", "password": TEST_PASSWORD}
    )
    refresh = login.json()["refresh_token"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


async def test_only_admin_can_provision_clinicians(client, patient, clinician, admin):
    body = {"email": "doc2@test.com", "password": "a-long-enough-password", "full_name": "Doc Two"}

    assert (await client.post("/api/v1/auth/clinicians", json=body)).status_code in (401, 403)
    assert (
        await client.post("/api/v1/auth/clinicians", json=body, headers=patient["headers"])
    ).status_code == 403
    assert (
        await client.post("/api/v1/auth/clinicians", json=body, headers=clinician["headers"])
    ).status_code == 403

    r = await client.post("/api/v1/auth/clinicians", json=body, headers=admin["headers"])
    assert r.status_code == 201
    assert r.json()["role"] == "clinician"

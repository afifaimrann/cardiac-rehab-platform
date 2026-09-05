"""Test fixtures.

Each test gets a fresh in-memory database on a single shared connection
(StaticPool), so tests are isolated from one another and from any local
cardiac.db, and the suite needs no database server to run.
"""
from typing import AsyncGenerator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import pytest

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import PatientProfile, User, UserRole
from app.core.security import hash_password

TEST_PASSWORD = "test-password-123"


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    """Force the offline path for every test.

    pydantic-settings reads .env, so a developer with a real OPENAI_API_KEY
    would otherwise run the suite against the live API: slow, billable, and
    non-deterministic. Tests assert the extractive and guardrail behaviour,
    which must hold with no key present.
    """
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "RERANK_ENABLED", False, raising=False)


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[httpx.AsyncClient, None]:
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Account helpers
# --------------------------------------------------------------------------

async def _make_user(session_factory, email: str, role: UserRole, name: str = "Test User"):
    async with session_factory() as db:
        user = User(
            email=email,
            hashed_password=hash_password(TEST_PASSWORD),
            full_name=name,
            role=role,
        )
        db.add(user)
        await db.flush()
        profile = None
        if role is UserRole.PATIENT:
            profile = PatientProfile(user_id=user.id)
            db.add(profile)
            await db.flush()
        await db.commit()
        return user.id, (profile.id if profile else None)


async def auth_headers(client: httpx.AsyncClient, email: str, password: str = TEST_PASSWORD):
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def patient(client, session_factory):
    """A registered patient plus their auth headers and profile id."""
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "patient@test.com", "password": TEST_PASSWORD, "full_name": "Test Patient"},
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    return {"headers": headers, "profile_id": me["patient_profile"]["id"], "user_id": me["user"]["id"]}


@pytest_asyncio.fixture
async def clinician(client, session_factory):
    user_id, _ = await _make_user(session_factory, "doc@test.com", UserRole.CLINICIAN, "Dr Test")
    return {"headers": await auth_headers(client, "doc@test.com"), "user_id": user_id}


@pytest_asyncio.fixture
async def admin(client, session_factory):
    user_id, _ = await _make_user(session_factory, "admin@test.com", UserRole.ADMIN, "Admin")
    return {"headers": await auth_headers(client, "admin@test.com"), "user_id": user_id}


@pytest_asyncio.fixture
async def assigned_patient(client, session_factory, patient, clinician, admin):
    """A patient assigned to the `clinician` fixture."""
    r = await client.patch(
        f"/api/v1/clinician/patients/{patient['profile_id']}/assignment",
        json={"clinician_id": clinician["user_id"]},
        headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    return patient

"""Application entrypoint.

The OpenAPI description here is the contract the frontend and any external
consumer read, so it is written for them rather than as an afterthought.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    appointments, assessment, assistant, auth, chat, clinician, messages, profile,
    program, vitals,
)
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  -- register mappers before create_all

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger("cardiac")

DESCRIPTION = """
REST API for a remote cardiac rehabilitation programme.

**Patients** log vitals, symptoms and exercise sessions, record six-minute walk
tests, book consultations from their clinician's rota, message their care team,
and ask questions about their recovery. **Clinicians** review an assigned
caseload, prescribe exercise plans, work a queue of risk flags raised
automatically from patient data, run a clinic diary, and question an assistant
that reads one patient's record.

### Authentication
All endpoints except `/health` and `/auth/*` require a bearer access token:
`Authorization: Bearer <access_token>`. Tokens are obtained from
`POST /auth/login` and renewed with `POST /auth/refresh`.

### Authorisation
Patients can only ever read and write their own records. Clinicians can only
read patients assigned to them; requests for anyone else return `404` rather
than `403`, so the API never confirms the existence of records outside the
caller's caseload.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Registration, login, token refresh."},
    {"name": "vitals", "description": "Patient-logged vital signs."},
    {"name": "symptoms", "description": "Patient-reported symptoms."},
    {"name": "program", "description": "Exercise plans and logged sessions."},
    {"name": "chat", "description": "Voice and text Q&A about recovery."},
    {"name": "clinician", "description": "Caseload, adherence and the risk-flag queue."},
    {"name": "walk test", "description": "Six-minute walk test screening, recording and history."},
    {"name": "appointments", "description": "Clinician rota, patient self-booking, and video consultations."},
    {"name": "messages", "description": "Direct messages between a patient and their care team."},
    {"name": "profile", "description": "Your own account details and profile photograph."},
    {"name": "system", "description": "Health and readiness."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is owned by Alembic in every environment, development
    # included. An earlier version called create_all() here as a convenience;
    # it creates missing tables but never alters existing ones, so adding a
    # column left the database half-migrated with Alembic unaware. Checking and
    # refusing to guess is better than a convenience that corrupts state.
    await verify_schema()
    await warn_if_corpus_empty()
    yield
    await engine.dispose()
    logger.info("Database connections closed")


async def verify_schema() -> None:
    """Fail fast with an actionable message if migrations have not been run."""
    from sqlalchemy import inspect

    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))

    expected = set(Base.metadata.tables)
    missing = expected - tables

    if not tables:
        raise RuntimeError(
            "The database is empty. Run `alembic upgrade head` before starting the API."
        )
    if missing:
        raise RuntimeError(
            f"Schema is out of date; missing table(s): {', '.join(sorted(missing))}. "
            "Run `alembic upgrade head`."
        )
    logger.info("Schema verified: %d tables", len(expected))


async def warn_if_corpus_empty() -> None:
    """Say so loudly when there is nothing to retrieve.

    An empty corpus is not a crash: the API starts, every endpoint works, and
    the assistant answers "I don't have guidance on that" to everything. That is
    a far worse failure than a stack trace, because it looks like a bad model
    rather than a missing setup step -- and dropping the database drops the
    corpus with it, so it happens exactly when someone is resetting their data.
    """
    from sqlalchemy import func, select

    from app.models.knowledge import KnowledgePassage

    async with engine.connect() as conn:
        count = await conn.scalar(select(func.count()).select_from(KnowledgePassage))

    if not count:
        logger.warning(
            "Knowledge corpus is EMPTY -- the assistant will answer every question "
            "with 'I don't have guidance on that'. Run: python -m scripts.embed_corpus"
        )
    else:
        logger.info("Knowledge corpus: %d passages", count)


app = FastAPI(
    title=settings.APP_NAME,
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(vitals.router, prefix=settings.API_V1_PREFIX)
app.include_router(vitals.symptom_router, prefix=settings.API_V1_PREFIX)
app.include_router(vitals.flag_router, prefix=settings.API_V1_PREFIX)
app.include_router(program.router, prefix=settings.API_V1_PREFIX)
app.include_router(clinician.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(assessment.router, prefix=settings.API_V1_PREFIX)
app.include_router(appointments.router, prefix=settings.API_V1_PREFIX)
app.include_router(messages.router, prefix=settings.API_V1_PREFIX)
app.include_router(assistant.router, prefix=settings.API_V1_PREFIX)
app.include_router(profile.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}

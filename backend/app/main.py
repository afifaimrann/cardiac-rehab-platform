"""Application entrypoint.

The OpenAPI description here is the contract the frontend and any external
consumer read, so it is written for them rather than as an afterthought.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, clinician, program, vitals
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

**Patients** log vitals, symptoms and exercise sessions, and ask questions about
their recovery. **Clinicians** review an assigned caseload, prescribe exercise
plans, and work a queue of risk flags raised automatically from patient data.

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
    {"name": "system", "description": "Health and readiness."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Development convenience only. Production schema changes go through Alembic.
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Schema ensured (development mode)")
    yield
    await engine.dispose()
    logger.info("Database connections closed")


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
app.include_router(program.router, prefix=settings.API_V1_PREFIX)
app.include_router(clinician.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}

"""Reusable FastAPI dependencies: authentication, roles and record ownership.

Authorisation is expressed as dependencies rather than checks inside handlers so
that every route states its access requirements in its signature -- a route that
forgets to authorise is visibly missing a dependency, instead of silently open.
"""
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenType, decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import PatientProfile, User

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    payload = decode_token(credentials.credentials, TokenType.ACCESS)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("sub")
    if not user_id:
        raise CREDENTIALS_EXCEPTION

    user = await db.get(User, user_id)
    # Re-check the user on every request: a token issued before deactivation
    # must stop working immediately, not at its natural expiry.
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


class RequireRole:
    """Dependency factory: allow only the listed roles."""

    def __init__(self, *roles: UserRole) -> None:
        self.roles = set(roles)

    async def __call__(self, user: CurrentUser) -> User:
        if user.role not in self.roles:
            # 403, not 404: the caller is authenticated but not permitted.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint requires one of: "
                + ", ".join(sorted(r.value for r in self.roles)),
            )
        return user


require_patient = RequireRole(UserRole.PATIENT)
require_clinician = RequireRole(UserRole.CLINICIAN, UserRole.ADMIN)
require_admin = RequireRole(UserRole.ADMIN)

PatientUser = Annotated[User, Depends(require_patient)]
ClinicianUser = Annotated[User, Depends(require_clinician)]
AdminUser = Annotated[User, Depends(require_admin)]


async def get_own_patient_profile(user: PatientUser, db: DbSession) -> PatientProfile:
    """The profile belonging to the authenticated patient."""
    result = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient profile not found"
        )
    return profile


OwnPatientProfile = Annotated[PatientProfile, Depends(get_own_patient_profile)]


async def get_patient_for_clinician(
    patient_id: Annotated[str, Path(description="Patient profile id")],
    user: ClinicianUser,
    db: DbSession,
) -> PatientProfile:
    """A patient the authenticated clinician is allowed to see.

    A clinician may only read patients assigned to them; an admin may read any.
    An unassigned patient returns 404 rather than 403 so that the endpoint does
    not confirm the existence of records outside the caller's caseload.
    """
    profile = await db.get(PatientProfile, patient_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if user.role is not UserRole.ADMIN and profile.clinician_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return profile


AssignedPatient = Annotated[PatientProfile, Depends(get_patient_for_clinician)]

"""Registration, login, token refresh and identity."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, AdminUser
from app.core.config import settings
from app.core.security import (
    TokenType, create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from app.models.enums import UserRole
from app.models.user import PatientProfile, User
from app.schemas.user import (
    ClinicianCreate, MeResponse, RefreshRequest, TokenPair, UserLogin,
    UserRead, UserRegister,
)

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _create_user(db, payload, role: UserRole) -> User:
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    return user


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a patient account",
    responses={409: {"description": "Email already registered"}},
)
async def register(payload: UserRegister, db: DbSession) -> TokenPair:
    """Create a patient account and its clinical profile in one transaction.

    Self-registration always creates a patient. Clinician accounts are
    provisioned by an admin so that privilege can never be self-granted.
    """
    user = await _create_user(db, payload, UserRole.PATIENT)
    db.add(PatientProfile(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return _token_pair(user)


@router.post(
    "/clinicians",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a clinician account (admin only)",
)
async def create_clinician(payload: ClinicianCreate, db: DbSession, _: AdminUser) -> User:
    user = await _create_user(db, payload, UserRole.CLINICIAN)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair, summary="Exchange credentials for tokens")
async def login(payload: UserLogin, db: DbSession) -> TokenPair:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # Verify against a dummy hash when the user is missing so that response time
    # does not reveal whether an email is registered.
    if user is None:
        verify_password(payload.password, hash_password("dummy-password-for-timing"))
        raise INVALID_CREDENTIALS
    if not verify_password(payload.password, user.hashed_password):
        raise INVALID_CREDENTIALS
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token")
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    claims = decode_token(payload.refresh_token, TokenType.REFRESH)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )
    user = await db.get(User, claims.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )
    return _token_pair(user)


@router.get("/me", response_model=MeResponse, summary="Current user and profile")
async def read_me(user: CurrentUser, db: DbSession) -> MeResponse:
    profile = None
    if user.role is UserRole.PATIENT:
        result = await db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user.id)
        )
        profile = result.scalar_one_or_none()
    return MeResponse(user=user, patient_profile=profile)

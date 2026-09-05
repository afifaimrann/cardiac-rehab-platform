"""Editing your own account: details and profile photograph.

Everything here acts on the authenticated user's own record. There is no
patient identifier in any path, which is what makes "can a patient edit someone
else's profile?" a question with no code to inspect.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.enums import UserRole
from app.models.user import PatientProfile, User
from app.schemas.user import MeResponse, PatientProfileUpdate, PatientProfileRead, UserRead
from app.services import avatars

router = APIRouter(tags=["profile"])

# --- avatar URLs -------------------------------------------------------------
# Avatars are served without a bearer token, addressed by a 128-bit random
# filename. The trade-off, stated plainly: an <img> tag cannot send an
# Authorization header, so the alternatives are fetching every photograph as a
# blob in JavaScript, or a capability URL. A capability URL is unguessable and
# never enumerable -- there is no listing endpoint and the directory is not
# served -- but anyone the URL is forwarded to can see the photograph. For a
# deployment needing stricter control, the fix is a short-lived signed URL
# rather than a longer filename.
AVATAR_PATH = "/media/avatars"
# The path the browser uses, which includes the API prefix the router is
# mounted under. Kept as one expression so the two can never drift.
AVATAR_URL_PREFIX = f"{settings.API_V1_PREFIX}{AVATAR_PATH}"


def _avatar_url(user: User) -> Optional[str]:
    return f"{AVATAR_URL_PREFIX}/{user.avatar_filename}" if user.avatar_filename else None


def _me(user: User, profile: Optional[PatientProfile]) -> MeResponse:
    payload = UserRead.model_validate(user)
    payload.avatar_url = _avatar_url(user)
    return MeResponse(
        user=payload,
        patient_profile=PatientProfileRead.model_validate(profile) if profile else None,
    )


async def _own_profile(db, user: User) -> Optional[PatientProfile]:
    if user.role is not UserRole.PATIENT:
        return None
    return (await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )).scalar_one_or_none()


@router.patch("/me/profile", response_model=MeResponse, summary="Update your own details")
async def update_own_profile(
    payload: PatientProfileUpdate, user: CurrentUser, db: DbSession
) -> MeResponse:
    data = payload.model_dump(exclude_unset=True)

    # full_name lives on the account, not the clinical profile, so a clinician
    # can rename themselves through the same endpoint a patient uses.
    name = data.pop("full_name", None)
    if name is not None:
        user.full_name = name

    profile = await _own_profile(db, user)
    if data:
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only patients have a clinical profile to update.",
            )
        for field, value in data.items():
            setattr(profile, field, value)

    await db.commit()
    await db.refresh(user)
    if profile is not None:
        await db.refresh(profile)
    return _me(user, profile)


@router.post(
    "/me/avatar", response_model=MeResponse, summary="Upload a profile photograph"
)
async def upload_avatar(
    user: CurrentUser, db: DbSession, file: Annotated[UploadFile, File()]
) -> MeResponse:
    """Replace the profile photograph.

    The uploaded bytes are decoded, cropped, re-encoded and only then written;
    the file that arrives is never the file that is stored. See
    app/services/avatars.py for why.
    """
    raw = await file.read()
    try:
        filename = avatars.store(raw, previous=user.avatar_filename)
    except avatars.AvatarRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user.avatar_filename = filename
    await db.commit()
    await db.refresh(user)
    return _me(user, await _own_profile(db, user))


@router.delete("/me/avatar", response_model=MeResponse, summary="Remove your photograph")
async def delete_avatar(user: CurrentUser, db: DbSession) -> MeResponse:
    if user.avatar_filename:
        avatars.remove(user.avatar_filename)
        user.avatar_filename = None
        await db.commit()
        await db.refresh(user)
    return _me(user, await _own_profile(db, user))


@router.get(
    f"{AVATAR_PATH}/{{filename}}",
    summary="Fetch a stored profile photograph",
    response_class=FileResponse,
)
async def read_avatar(filename: str) -> Response:
    path = avatars.path_for(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    # Cached hard: the filename changes whenever the image does, so a stale
    # cache entry is impossible by construction.
    return FileResponse(
        path, media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )

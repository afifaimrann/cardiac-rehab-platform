"""Storing a profile photograph safely.

An uploaded image is never stored as received. It is decoded, verified, resized
and re-encoded, and only the result is written to disk. That single decision
handles most of what makes image upload risky:

  - A file claiming to be a PNG that is actually a script does not survive a
    decode, so nothing executable ever reaches the media directory.
  - Re-encoding drops every metadata block, including the EXIF GPS tags that
    would otherwise publish the patient's home address alongside their face.
  - A "decompression bomb" -- a small file that expands to gigabytes -- is
    rejected by Pillow's own limit before allocation.

The stored name is a random token, not the uploaded filename, so a user cannot
choose a path, an extension, or another patient's filename.
"""
from __future__ import annotations

import io
import secrets
from pathlib import Path
from typing import Optional

from app.core.config import settings

ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
STORED_FORMAT = "JPEG"
STORED_SUFFIX = ".jpg"
JPEG_QUALITY = 88


class AvatarRejected(ValueError):
    """The upload is not an image this service will store."""


def media_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / "avatars"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _square(image, edge: int):
    """Centre-crop to a square, then resize.

    Cropping rather than squashing: a stretched face is worse than a cropped
    one, and every avatar in the interface is round.
    """
    from PIL import Image

    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    return image.resize((edge, edge), Image.LANCZOS)


def store(data: bytes, *, previous: Optional[str] = None) -> str:
    """Validate, normalise and write an avatar. Returns the stored filename."""
    from PIL import Image, UnidentifiedImageError

    if not data:
        raise AvatarRejected("The uploaded file is empty.")
    if len(data) > settings.MAX_AVATAR_BYTES:
        limit_mb = settings.MAX_AVATAR_BYTES / (1024 * 1024)
        raise AvatarRejected(f"Images must be smaller than {limit_mb:.0f} MB.")

    try:
        # Opened twice on purpose: verify() checks the file is what it claims
        # and then leaves the object unusable, so the real decode needs a fresh
        # handle. Skipping verify() would mean malformed data reaching resize.
        Image.open(io.BytesIO(data)).verify()
        image = Image.open(io.BytesIO(data))
    except UnidentifiedImageError as exc:
        raise AvatarRejected("That file is not an image we can read.") from exc
    except Image.DecompressionBombError as exc:
        raise AvatarRejected("That image is too large to process.") from exc
    except Exception as exc:  # noqa: BLE001 - a corrupt image is a user error
        raise AvatarRejected("That image could not be read.") from exc

    if image.format not in ACCEPTED_FORMATS:
        raise AvatarRejected("Please upload a JPEG, PNG or WebP image.")

    # Flatten transparency onto white rather than onto black, which is what an
    # RGBA-to-RGB conversion does by default and which turns a cut-out portrait
    # into a silhouette.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        from PIL import Image as _Image

        background = _Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    else:
        image = image.convert("RGB")

    image = _square(image, settings.AVATAR_EDGE_PX)

    filename = f"{secrets.token_hex(16)}{STORED_SUFFIX}"
    path = media_root() / filename
    image.save(path, STORED_FORMAT, quality=JPEG_QUALITY, optimize=True)

    if previous:
        remove(previous)
    return filename


def remove(filename: str) -> None:
    """Delete a stored avatar, ignoring anything that is not one.

    The name is rebuilt from its basename before use: a stored value should
    never contain a path, and if one ever does, it must not escape the media
    directory.
    """
    if not filename:
        return
    safe = Path(filename).name
    try:
        (media_root() / safe).unlink(missing_ok=True)
    except OSError:  # pragma: no cover - a failed cleanup must not fail a request
        pass


def path_for(filename: Optional[str]) -> Optional[Path]:
    if not filename:
        return None
    candidate = media_root() / Path(filename).name
    return candidate if candidate.is_file() else None

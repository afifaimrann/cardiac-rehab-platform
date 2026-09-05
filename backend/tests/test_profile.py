"""Editing your own details, and the avatar pipeline.

The avatar tests are mostly about what the service refuses. An image upload is
the one place a web application accepts an arbitrary binary from an unprivileged
user and writes it to disk, so the interesting cases are the malicious ones.
"""
import io

import pytest
from PIL import Image

from app.core.config import settings
from app.services import avatars


@pytest.fixture(autouse=True)
def isolated_media(tmp_path, monkeypatch):
    """Never write test avatars into the repository."""
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"), raising=False)


def png_bytes(size=(800, 600), colour=(200, 40, 40), mode="RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, colour).save(buf, "PNG")
    return buf.getvalue()


# --- profile editing -------------------------------------------------------
async def test_patient_updates_the_fields_the_walk_test_needs(client, patient):
    r = await client.patch(
        "/api/v1/me/profile",
        json={"full_name": "Afifa I", "height_cm": 162.5, "sex_at_birth": "female",
              "date_of_birth": "1968-04-11", "language": "bn"},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["full_name"] == "Afifa I"
    assert body["patient_profile"]["height_cm"] == 162.5
    assert body["patient_profile"]["sex_at_birth"] == "female"
    assert body["patient_profile"]["language"] == "bn"


async def test_a_partial_update_leaves_other_fields_alone(client, patient):
    await client.patch("/api/v1/me/profile", json={"height_cm": 170},
                       headers=patient["headers"])
    r = await client.patch("/api/v1/me/profile", json={"language": "bn"},
                           headers=patient["headers"])
    assert r.json()["patient_profile"]["height_cm"] == 170


async def test_a_patient_cannot_reassign_their_own_clinician(
    client, patient, clinician
):
    """clinician_id is not a profile field; sending it must change nothing."""
    r = await client.patch(
        "/api/v1/me/profile", json={"clinician_id": clinician["user_id"]},
        headers=patient["headers"],
    )
    assert r.status_code == 200
    assert r.json()["patient_profile"]["clinician_id"] is None


async def test_implausible_height_is_rejected(client, patient):
    r = await client.patch("/api/v1/me/profile", json={"height_cm": 12},
                           headers=patient["headers"])
    assert r.status_code == 422


async def test_a_clinician_can_rename_themselves(client, clinician):
    r = await client.patch("/api/v1/me/profile", json={"full_name": "Dr A Rahman"},
                           headers=clinician["headers"])
    assert r.status_code == 200
    assert r.json()["user"]["full_name"] == "Dr A Rahman"
    assert r.json()["patient_profile"] is None


async def test_a_clinician_has_no_clinical_profile_to_edit(client, clinician):
    r = await client.patch("/api/v1/me/profile", json={"height_cm": 180},
                           headers=clinician["headers"])
    assert r.status_code == 400


async def test_profile_edit_needs_authentication(client):
    r = await client.patch("/api/v1/me/profile", json={"full_name": "nobody"})
    assert r.status_code == 401


# --- avatars: the service ---------------------------------------------------
def test_upload_is_re_encoded_not_stored_as_received():
    name = avatars.store(png_bytes())
    stored = avatars.path_for(name)
    with Image.open(stored) as img:
        assert img.format == "JPEG"           # a PNG went in
        assert img.size == (settings.AVATAR_EDGE_PX, settings.AVATAR_EDGE_PX)


def test_exif_is_not_carried_into_storage():
    """EXIF on a phone photo carries GPS: the patient's home address."""
    buf = io.BytesIO()
    img = Image.new("RGB", (400, 400), (10, 10, 10))
    exif = img.getexif()
    exif[271] = "TestMake"   # Make
    exif[34853] = {}         # GPSInfo pointer
    img.save(buf, "JPEG", exif=exif)

    stored = avatars.path_for(avatars.store(buf.getvalue()))
    with Image.open(stored) as out:
        assert not dict(out.getexif())


def test_a_non_image_is_refused():
    with pytest.raises(avatars.AvatarRejected):
        avatars.store(b"#!/bin/sh\nrm -rf /\n")


def test_an_empty_file_is_refused():
    with pytest.raises(avatars.AvatarRejected):
        avatars.store(b"")


def test_an_oversized_file_is_refused(monkeypatch):
    monkeypatch.setattr(settings, "MAX_AVATAR_BYTES", 100, raising=False)
    with pytest.raises(avatars.AvatarRejected):
        avatars.store(png_bytes())


def test_a_gif_is_refused_even_though_pillow_reads_it():
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), (1, 2, 3)).save(buf, "GIF")
    with pytest.raises(avatars.AvatarRejected):
        avatars.store(buf.getvalue())


def test_stored_names_are_random_not_chosen():
    a, b = avatars.store(png_bytes()), avatars.store(png_bytes())
    assert a != b
    assert a.endswith(".jpg") and len(a) > 20


def test_a_wide_image_is_cropped_square_not_squashed():
    stored = avatars.path_for(avatars.store(png_bytes(size=(1200, 300))))
    with Image.open(stored) as img:
        assert img.width == img.height


def test_transparency_flattens_onto_white_not_black():
    buf = io.BytesIO()
    Image.new("RGBA", (200, 200), (255, 0, 0, 0)).save(buf, "PNG")
    stored = avatars.path_for(avatars.store(buf.getvalue()))
    with Image.open(stored) as img:
        assert img.getpixel((100, 100)) > (200, 200, 200)


def test_replacing_an_avatar_deletes_the_old_file():
    first = avatars.store(png_bytes())
    second = avatars.store(png_bytes(), previous=first)
    assert avatars.path_for(first) is None
    assert avatars.path_for(second) is not None


def test_a_traversal_path_cannot_escape_the_media_directory(tmp_path):
    victim = tmp_path / "secret.txt"
    victim.write_text("do not delete")
    avatars.remove(f"../../{victim.name}")
    assert victim.exists()
    assert avatars.path_for("../../../etc/passwd") is None


# --- avatars: the endpoints -------------------------------------------------
async def test_upload_fetch_and_delete(client, patient):
    r = await client.post(
        "/api/v1/me/avatar",
        files={"file": ("me.png", png_bytes(), "image/png")},
        headers=patient["headers"],
    )
    assert r.status_code == 200, r.text
    url = r.json()["user"]["avatar_url"]
    assert url and url.startswith("/api/v1/media/avatars/")

    fetched = await client.get(url)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/jpeg"

    gone = await client.delete("/api/v1/me/avatar", headers=patient["headers"])
    assert gone.json()["user"]["avatar_url"] is None
    assert (await client.get(url)).status_code == 404


async def test_uploading_a_document_is_refused_with_a_readable_message(client, patient):
    r = await client.post(
        "/api/v1/me/avatar",
        files={"file": ("cv.pdf", b"%PDF-1.4 not an image", "application/pdf")},
        headers=patient["headers"],
    )
    assert r.status_code == 422
    assert "image" in r.json()["detail"].lower()


async def test_a_missing_avatar_is_a_404_not_a_server_error(client):
    r = await client.get("/api/v1/media/avatars/deadbeef.jpg")
    assert r.status_code == 404

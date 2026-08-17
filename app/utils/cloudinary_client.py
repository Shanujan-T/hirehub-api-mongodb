import logging
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import Error as CloudinaryError
from flask import current_app, url_for


logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


def _configure_cloudinary():
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def _read_file_storage(file_storage) -> bytes:
    file_storage.stream.seek(0)
    data = file_storage.read()
    file_storage.stream.seek(0)
    return data


def _local_uploads_enabled() -> bool:
    """Disk fallback is explicit and limited to a non-Railway debug server."""
    return (
        current_app.debug
        and os.getenv("LOCAL_UPLOADS_ENABLED", "0") == "1"
        and not os.getenv("RAILWAY_ENVIRONMENT")
    )


def _save_local_image(file_storage, folder: str) -> str:
    safe_folder = "/".join(
        part
        for part in folder.replace("\\", "/").split("/")
        if part and part not in {".", ".."}
    )
    extension = Path(file_storage.filename).suffix.lower()
    relative_path = Path(safe_folder) / f"{uuid4().hex}{extension}"
    destination = Path(current_app.instance_path) / "uploads" / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_read_file_storage(file_storage))
    logger.warning("Cloud storage unavailable; saved development image to %s", destination)
    return url_for("uploaded_file", filename=relative_path.as_posix(), _external=True)


def validate_image_file(file_storage):
    if not file_storage or not file_storage.filename:
        return "No image file provided."

    extension = Path(file_storage.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return "Only JPG, PNG, and WEBP images are allowed."

    content_type = (file_storage.content_type or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return "Only JPG, PNG, and WEBP images are allowed."

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size <= 0:
        return "Uploaded file is empty."
    if size > MAX_FILE_SIZE_BYTES:
        return "Image must be 5MB or smaller."

    return None


def upload_image(file_storage, folder: str) -> str:
    error = validate_image_file(file_storage)
    if error:
        raise ValueError(error)

    if not os.getenv("CLOUDINARY_CLOUD_NAME"):
        if _local_uploads_enabled():
            return _save_local_image(file_storage, folder)
        raise RuntimeError("Cloudinary is not configured.")

    _configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            _read_file_storage(file_storage),
            folder=folder,
            resource_type="image",
        )
    except CloudinaryError as exc:
        logger.exception("Cloudinary avatar/image upload failed")
        if _local_uploads_enabled():
            return _save_local_image(file_storage, folder)
        raise RuntimeError(
            "Image storage rejected the upload. Check Cloudinary asset-create permissions."
        ) from exc

    return result["secure_url"]


def _cloudinary_public_id(image_url: str) -> str | None:
    parsed = urlparse(image_url)
    if parsed.hostname != "res.cloudinary.com":
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    try:
        upload_index = parts.index("upload")
    except ValueError:
        return None
    asset_parts = parts[upload_index + 1 :]
    version_index = next(
        (index for index, part in enumerate(asset_parts) if part.startswith("v") and part[1:].isdigit()),
        None,
    )
    if version_index is not None:
        asset_parts = asset_parts[version_index + 1 :]
    if not asset_parts:
        return None
    public_id = "/".join(asset_parts)
    return public_id.rsplit(".", 1)[0]


def delete_image(image_url: str | None) -> None:
    if not image_url:
        return

    parsed = urlparse(image_url)
    if parsed.path.startswith("/uploads/"):
        relative_path = Path(unquote(parsed.path.removeprefix("/uploads/")))
        upload_root = (Path(current_app.instance_path) / "uploads").resolve()
        target = (upload_root / relative_path).resolve()
        if not target.is_relative_to(upload_root):
            raise RuntimeError("Refusing to delete an image outside the upload directory.")
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            logger.exception("Failed to delete local image %s", target)
            raise RuntimeError("Failed to remove the stored profile picture.") from exc
        return

    public_id = _cloudinary_public_id(image_url)
    if public_id:
        _configure_cloudinary()
        try:
            result = cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
        except CloudinaryError as exc:
            logger.exception("Cloudinary image deletion failed for public_id=%s", public_id)
            raise RuntimeError(
                "Image storage rejected the deletion. Check Cloudinary asset-delete permissions."
            ) from exc
        if result.get("result") not in {"ok", "not found"}:
            logger.error("Unexpected Cloudinary deletion result for public_id=%s: %s", public_id, result)
            raise RuntimeError("Failed to remove the stored profile picture.")
        return

    logger.info("Avatar URL is not managed by HireHub storage; clearing the database reference only.")

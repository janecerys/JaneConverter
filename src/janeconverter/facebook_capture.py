"""Validate and save photo renditions discovered in an isolated Facebook guest page."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import urllib.parse
from typing import Any, Callable, Optional

import requests
from PIL import Image

from .extractor import sanitize_filename
from .image_format import convert_image_format


MAX_PHOTOS = 500
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_ALBUM_BYTES = 2 * 1024 * 1024 * 1024
PHOTO_ID_RE = re.compile(r"^[0-9]{5,30}$")
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 5


def _public_photo_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 16_384:
        raise ValueError("Facebook returned an invalid photo link.")
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or not (host.endswith(".fbcdn.net") or host == "fbcdn.net" or host.endswith(".fbsbx.com") or host == "fbsbx.com")
    ):
        raise ValueError("Facebook returned a photo link outside its public media CDN.")
    return value


def _get_public_photo(session: requests.Session, url: str) -> requests.Response:
    """Follow only redirects that stay on Facebook's public media CDN."""
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        response = session.get(
            current_url,
            headers={"Referer": "https://www.facebook.com/"},
            stream=True,
            timeout=(10, 35),
            allow_redirects=False,
        )
        if response.status_code not in REDIRECT_STATUSES:
            return response
        location = response.headers.get("Location")
        response.close()
        if not location or redirect_count == MAX_REDIRECTS:
            raise RuntimeError("Facebook returned too many or invalid photo redirects.")
        try:
            current_url = _public_photo_url(urllib.parse.urljoin(current_url, location))
        except ValueError as error:
            raise RuntimeError("Facebook redirected a photo outside its public media CDN.") from error
    raise RuntimeError("Facebook returned too many photo redirects.")


def download_facebook_photo_manifest(
    manifest: Any,
    output_dir: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    abort_event: Optional[Any] = None,
    target_format: Optional[str] = None,
    quality: str = "best",
) -> dict[str, Any]:
    """Download every unique, guest-visible photo in a validated browser manifest."""
    if not isinstance(manifest, dict):
        raise ValueError("The Facebook photo list is missing or invalid.")
    raw_photos = manifest.get("photos")
    if not isinstance(raw_photos, list) or len(raw_photos) < 2:
        raise RuntimeError("This public Facebook post does not contain multiple downloadable photos.")
    if len(raw_photos) > MAX_PHOTOS:
        raise RuntimeError(f"This Facebook post exposes more than {MAX_PHOTOS} photos; nothing was downloaded.")

    photos: dict[str, dict[str, Any]] = {}
    for item in raw_photos:
        if not isinstance(item, dict):
            raise ValueError("Facebook returned an invalid photo entry.")
        photo_id = item.get("id")
        if not isinstance(photo_id, str) or not PHOTO_ID_RE.fullmatch(photo_id):
            raise ValueError("Facebook returned an invalid photo identifier.")
        photo = {
            "url": _public_photo_url(item.get("url")),
            "width": max(0, min(int(item.get("width", 0)), 20_000)),
        }
        existing = photos.get(photo_id)
        if existing is None or photo["width"] > existing["width"]:
            photos[photo_id] = photo

    if len(photos) < 2:
        raise RuntimeError("Facebook exposed fewer than two unique photos.")

    raw_title = manifest.get("title")
    title = sanitize_filename(raw_title if isinstance(raw_title, str) else "")
    if title == "media_file":
        title = "Facebook Post"
    parent = os.path.abspath(output_dir)
    os.makedirs(parent, exist_ok=True)
    target_dir = os.path.join(parent, title)
    suffix = 2
    while os.path.lexists(target_dir):
        target_dir = os.path.join(parent, f"{title} ({suffix})")
        suffix += 1

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    })
    staging_dir = tempfile.mkdtemp(prefix=".facebook-album-", dir=parent)
    total_bytes = 0

    def report(progress: float, message: str) -> None:
        if progress_callback:
            progress_callback(progress, message)

    try:
        for index, photo in enumerate(photos.values(), start=1):
            if abort_event and abort_event.is_set():
                raise KeyboardInterrupt("Facebook photo download aborted by user.")
            report(0.05 + 0.9 * ((index - 1) / len(photos)), f"Downloading Facebook photo {index} of {len(photos)}...")
            with _get_public_photo(session, photo["url"]) as response:
                response.raise_for_status()
                _public_photo_url(response.url)
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                extension = IMAGE_EXTENSIONS.get(content_type)
                if not extension:
                    raise RuntimeError(f"Facebook returned an unsupported image type for photo {index}.")
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_IMAGE_BYTES:
                    raise RuntimeError(f"Facebook photo {index} is larger than the 100 MB per-image limit.")

                image_path = os.path.join(staging_dir, f"{title}_{index:03d}{extension}")
                image_bytes = 0
                with open(image_path, "wb") as image_file:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        image_bytes += len(chunk)
                        total_bytes += len(chunk)
                        if image_bytes > MAX_IMAGE_BYTES:
                            raise RuntimeError(f"Facebook photo {index} is larger than the 100 MB per-image limit.")
                        if total_bytes > MAX_ALBUM_BYTES:
                            raise RuntimeError("The Facebook album exceeds the 2 GB total download limit.")
                        image_file.write(chunk)
                with Image.open(image_path) as image:
                    image.verify()
                convert_image_format(image_path, target_format, quality)

        os.replace(staging_dir, target_dir)
    except requests.RequestException as error:
        raise RuntimeError("Could not download a Facebook photo. The album may have changed or the link may have expired.") from error
    except (OSError, ValueError) as error:
        raise RuntimeError("Could not save or validate one of the Facebook photos.") from error
    finally:
        session.close()
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)

    report(1.0, f"Saved all {len(photos)} Facebook photos.")
    return {
        "title": title,
        "folder_path": os.path.abspath(target_dir),
        "photo_count": len(photos),
        "total_bytes": total_bytes,
    }

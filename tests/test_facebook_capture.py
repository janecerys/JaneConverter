from __future__ import annotations

import io

import pytest
from PIL import Image

from janeconverter import facebook_capture


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), color=(35, 90, 160))
    stream = io.BytesIO()
    image.save(stream, format="JPEG")
    return stream.getvalue()


class _Response:
    def __init__(self, url: str, body: bytes, content_type: str = "image/jpeg"):
        self.url = url
        self.body = body
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def close(self):
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]


class _Session:
    def __init__(self, response_type: str = "image/jpeg"):
        self.headers = {}
        self.response_type = response_type
        self.requested = []

    def get(self, url: str, **_kwargs):
        self.requested.append(url)
        return _Response(url, _jpeg_bytes(), self.response_type)

    def close(self):
        return None


class _RedirectResponse(_Response):
    def __init__(self, url: str, location: str):
        super().__init__(url, b"")
        self.headers = {"Location": location}
        self.status_code = 302


class _RedirectSession(_Session):
    def get(self, url: str, **_kwargs):
        self.requested.append(url)
        return _RedirectResponse(url, "https://example.com/redirected-photo.jpg")


def _manifest():
    return {
        "title": "Public album",
        "photos": [
            {"id": "123456", "url": "https://scontent-1.xx.fbcdn.net/low.jpg", "width": 480},
            {"id": "123456", "url": "https://scontent-1.xx.fbcdn.net/high.jpg", "width": 1080},
            {"id": "234567", "url": "https://scontent-2.xx.fbcdn.net/second.jpg", "width": 960},
        ],
    }


def test_manifest_download_deduplicates_and_keeps_largest_rendition(tmp_path, monkeypatch):
    session = _Session()
    monkeypatch.setattr(facebook_capture.requests, "Session", lambda: session)
    reports = []

    result = facebook_capture.download_facebook_photo_manifest(
        _manifest(),
        str(tmp_path),
        progress_callback=lambda progress, message: reports.append((progress, message)),
    )

    album_dir = tmp_path / "Public album"
    assert result["photo_count"] == 2
    assert session.requested == [
        "https://scontent-1.xx.fbcdn.net/high.jpg",
        "https://scontent-2.xx.fbcdn.net/second.jpg",
    ]
    saved = sorted(album_dir.glob("*.jpg"))
    assert len(saved) == 2
    with Image.open(saved[0]) as image:
        assert image.size == (8, 8)
    assert reports[-1][0] == 1.0
    assert not list(tmp_path.glob(".facebook-album-*"))


def test_manifest_converts_photo_to_selected_png(tmp_path, monkeypatch):
    monkeypatch.setattr(facebook_capture.requests, "Session", _Session)

    facebook_capture.download_facebook_photo_manifest(
        _manifest(),
        str(tmp_path),
        target_format="png",
    )

    saved = sorted((tmp_path / "Public album").glob("*"))
    assert len(saved) == 2
    assert all(path.suffix == ".png" for path in saved)
    with Image.open(saved[0]) as image:
        assert image.format == "PNG"


@pytest.mark.parametrize(
    "url",
    [
        "http://scontent.xx.fbcdn.net/photo.jpg",
        "https://example.com/photo.jpg",
        "https://user@example.xx.fbcdn.net/photo.jpg",
    ],
)
def test_manifest_rejects_non_public_or_non_cdn_urls(tmp_path, url):
    manifest = {
        "title": "Invalid album",
        "photos": [
            {"id": "123456", "url": url, "width": 960},
            {"id": "234567", "url": "https://scontent.xx.fbcdn.net/second.jpg", "width": 960},
        ],
    }

    with pytest.raises(ValueError, match="public media CDN"):
        facebook_capture.download_facebook_photo_manifest(manifest, str(tmp_path))


def test_manifest_never_follows_redirects_outside_facebook_cdn(tmp_path, monkeypatch):
    session = _RedirectSession()
    monkeypatch.setattr(facebook_capture.requests, "Session", lambda: session)

    with pytest.raises(RuntimeError, match="redirected a photo outside"):
        facebook_capture.download_facebook_photo_manifest(_manifest(), str(tmp_path))

    assert session.requested == ["https://scontent-1.xx.fbcdn.net/high.jpg"]


def test_failed_image_validation_removes_staging_without_partial_album(tmp_path, monkeypatch):
    session = _Session(response_type="text/html")
    monkeypatch.setattr(facebook_capture.requests, "Session", lambda: session)

    with pytest.raises(RuntimeError, match="unsupported image type"):
        facebook_capture.download_facebook_photo_manifest(_manifest(), str(tmp_path))

    assert not list(tmp_path.glob(".facebook-album-*"))
    assert not (tmp_path / "Public album").exists()

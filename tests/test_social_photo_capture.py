from __future__ import annotations

import io

from PIL import Image

from janeconverter import cli, social_photo_capture


def _webp_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), color=(35, 90, 160))
    stream = io.BytesIO()
    image.save(stream, format="WEBP")
    return stream.getvalue()


class _Response:
    def __init__(self, url: str, body: bytes, content_type: str = "image/webp"):
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
    def __init__(self):
        self.headers = {}

    def get(self, url: str, **_kwargs):
        return _Response(url, _webp_bytes())

    def close(self):
        return None


def _manifest():
    return {
        "platform": "instagram",
        "title": "Public post",
        "photos": [
            {"id": "photo_1", "url": "https://scontent.cdninstagram.com/photo.webp", "width": 1080},
        ],
    }


def test_selected_png_format_converts_webp_social_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(social_photo_capture.requests, "Session", _Session)

    result = social_photo_capture.download_social_photo_manifest(
        _manifest(),
        str(tmp_path),
        target_format="png",
    )

    saved = list((tmp_path / "Public post").glob("*"))
    assert result["photo_count"] == 1
    assert [path.suffix for path in saved] == [".png"]
    with Image.open(saved[0]) as image:
        assert image.format == "PNG"
        assert image.size == (8, 8)


def test_source_format_keeps_original_webp_social_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(social_photo_capture.requests, "Session", _Session)

    social_photo_capture.download_social_photo_manifest(
        _manifest(),
        str(tmp_path),
        target_format="source",
    )

    saved = list((tmp_path / "Public post").glob("*"))
    assert [path.suffix for path in saved] == [".webp"]
    with Image.open(saved[0]) as image:
        assert image.format == "WEBP"


def test_conversion_passes_selected_image_format_to_social_downloader(tmp_path, monkeypatch):
    received = {}

    def download(_manifest, output_dir, **kwargs):
        received.update(kwargs)
        received["output_dir"] = output_dir
        return {"photo_count": 1, "folder_path": str(tmp_path / "export")}

    monkeypatch.setattr(cli, "download_social_photo_manifest", download)

    result = cli.process_conversion(
        source="https://www.instagram.com/p/public-post/",
        output_dir=str(tmp_path),
        target_format="png",
        bitrate="best",
        social_photo_manifest=_manifest(),
    )

    assert received["target_format"] == "png"
    assert received["quality"] == "best"
    assert result == str(tmp_path / "export")

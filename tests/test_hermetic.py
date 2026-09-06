"""
Hermetic tests: network and subprocess behavior is mocked.
Covers Spotify metadata parsing, playlist extraction, filename sanitization,
CLI validation, disk-space checks, and hardware encoder argument construction.
"""

import os
import sys
import argparse

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import engine.extractor as extractor
from engine.extractor import sanitize_filename, resolve_spotify_metadata, fetch_playlist_entries
from engine.converter import build_ffmpeg_args, VAAPI_ENCODER_ARGS
from engine.version import __version__
from run_converter import validate_cli_args, ensure_free_disk_space
from conftest import FakeResponse, make_spotify_track_embed_html, make_spotify_entity


# ---------------------------------------------------------------------------
# Spotify metadata parsing (network mocked)
# ---------------------------------------------------------------------------

def test_resolve_spotify_metadata_parses_embed_payload(monkeypatch):
    entity = make_spotify_entity()
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "/embed/track/" in url:
            return FakeResponse(200, text=make_spotify_track_embed_html(entity))
        # OpenGraph page scrape and oEmbed fallback
        return FakeResponse(200, text='<meta property="og:description" content="project//aspyr · The Heavenly Demon · Song · 2026">')

    monkeypatch.setattr(extractor.requests, "get", fake_get)
    data = resolve_spotify_metadata("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")

    assert data["title"] == "Hyperpop Anthem"
    assert data["artist"] == "project//aspyr, kvnokishi"
    assert data["year"] == "2026"
    assert data["thumbnail_url"] == "https://image-cdn.example/large.jpg"
    assert data["search_candidates"], "expected search candidates from parsed metadata"


def test_resolve_spotify_metadata_tolerates_angle_brackets_in_payload(monkeypatch):
    entity = make_spotify_entity(title="Track <Beyond> Reality")

    def fake_get(url, **kwargs):
        if "/embed/track/" in url:
            return FakeResponse(200, text=make_spotify_track_embed_html(entity))
        return FakeResponse(404, text="")

    monkeypatch.setattr(extractor.requests, "get", fake_get)
    data = resolve_spotify_metadata("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert data["title"] == "Track <Beyond> Reality"


def test_fetch_playlist_entries_spotify_playlist(monkeypatch):
    import json

    playlist_entity = {
        "title": "Kotomi Mixtape",
        "trackList": [
            {"title": "Song A", "subtitle": "Artist A", "duration": 210000, "uri": "spotify:track:abc123"},
            {"title": "Song B", "subtitle": "Artist B", "duration": 195000, "uri": "spotify:track:def456"},
        ],
        "visualIdentity": {"image": [{"maxWidth": 640, "url": "https://image-cdn.example/cover.jpg"}]},
    }
    payload = {"props": {"pageProps": {"state": {"data": {"entity": playlist_entity}}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'

    def fake_get(url, **kwargs):
        assert "/embed/playlist/" in url
        return FakeResponse(200, text=html)

    monkeypatch.setattr(extractor.requests, "get", fake_get)
    data = fetch_playlist_entries("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")

    assert data["playlist_title"] == "Kotomi Mixtape"
    assert data["total_count"] == 2
    assert data["entries"][0]["index"] == 1
    assert data["entries"][0]["url"] == "https://open.spotify.com/track/abc123"
    assert data["thumbnail_url"] == "https://image-cdn.example/cover.jpg"


# ---------------------------------------------------------------------------
# Filename sanitization hardening
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reserved", ["CON", "Nul", "AUX", "COM1", "LPT4", "con.mp3"])
def test_sanitize_filename_blocks_reserved_device_names(reserved):
    assert sanitize_filename(reserved) != reserved
    assert not sanitize_filename(reserved).upper().startswith("CON") or reserved.upper() != "CON"


def test_sanitize_filename_strips_control_characters():
    assert sanitize_filename("song\x00\x1f\x7ftitle") == "songtitle"


def test_sanitize_filename_allows_normal_titles():
    assert sanitize_filename("My Song - 2026") == "My Song - 2026"


# ---------------------------------------------------------------------------
# CLI argument validation
# ---------------------------------------------------------------------------

def _make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="x")
    parser.add_argument("--format", default="mp3")
    parser.add_argument("--bitrate", default="320k")
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--resolution", default="original")
    parser.add_argument("--playlist", action="store_true")
    return parser


def _args(parser, **overrides):
    defaults = {"source": "https://example.com/x", "format": "mp3", "bitrate": "320k",
                "sample_rate": 48000, "resolution": "original", "playlist": False}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_validate_cli_args_accepts_valid_input():
    parser = _make_parser()
    fmt, bitrate = validate_cli_args(_args(parser), parser)
    assert fmt == "mp3"
    assert bitrate == "320k"


@pytest.mark.parametrize("overrides", [
    {"format": "mp6"},
    {"bitrate": "999k", "format": "mp3"},
    {"sample_rate": 22050},
    {"resolution": "8k"},
])
def test_validate_cli_args_rejects_invalid_values(overrides):
    parser = _make_parser()
    with pytest.raises(SystemExit):
        validate_cli_args(_args(parser, **overrides), parser)


def test_validate_cli_args_wav_accepts_bit_depth():
    parser = _make_parser()
    fmt, bitrate = validate_cli_args(_args(parser, format="wav", bitrate="24-bit"), parser)
    assert fmt == "wav"
    assert bitrate == "24-bit"


def test_validate_cli_args_rejects_playlist_on_local_file():
    parser = _make_parser()
    with pytest.raises(SystemExit):
        validate_cli_args(_args(parser, playlist=True, source=r"D:\Music\song.mp3"), parser)


# ---------------------------------------------------------------------------
# Disk-space guard
# ---------------------------------------------------------------------------

def test_ensure_free_disk_space_raises_when_full(tmp_path, monkeypatch):
    import shutil as _shutil

    class FakeUsage:
        free = 10 * 1024 * 1024  # 10 MB
        total = 100 * 1024 * 1024
        used = 90 * 1024 * 1024

    monkeypatch.setattr(_shutil, "disk_usage", lambda p: FakeUsage())
    with pytest.raises(RuntimeError, match="Not enough disk space"):
        ensure_free_disk_space(str(tmp_path))


def test_ensure_free_disk_space_passes_when_space_available(tmp_path, monkeypatch):
    import shutil as _shutil

    real = _shutil.disk_usage
    monkeypatch.setattr(_shutil, "disk_usage", real)  # real disk, plenty of space
    ensure_free_disk_space(str(tmp_path), min_free_bytes=1)


# ---------------------------------------------------------------------------
# Hardware encoder argument construction
# ---------------------------------------------------------------------------

def test_vaapi_encoder_args_include_device_and_upload_chain():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_gpu=True,
        gpu_codec="h264_vaapi",
        resolution="1080p",
    )
    assert "-vaapi_device" in cmd
    for arg in VAAPI_ENCODER_ARGS:
        assert arg in cmd
    # VAAPI must not request hwaccel decode (software decode + hwupload instead)
    assert "-hwaccel" not in cmd
    vf_values = [v for i, v in enumerate(cmd) if cmd[i - 1] == "-vf"]
    assert vf_values and "hwupload" in vf_values[0] and "format=nv12" in vf_values[0]
    assert "scale=-2:1080" in vf_values[0]


def test_vaapi_encoder_args_without_resolution_still_upload():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_gpu=True,
        gpu_codec="h264_vaapi",
    )
    vf_values = [v for i, v in enumerate(cmd) if cmd[i - 1] == "-vf"]
    assert vf_values and "hwupload" in vf_values[0]


def test_webm_video_args_use_vp9():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.webm",
        target_format="webm",
        use_gpu=True,
    )
    assert "libvpx-vp9" in cmd


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def test_version_constant_is_semver_like():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)

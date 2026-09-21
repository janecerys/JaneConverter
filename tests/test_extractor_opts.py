"""
Tests for extractor yt-dlp option enhancements.
"""

from unittest.mock import patch
from janeconverter.extractor import build_video_format_selector, fetch_media_stream


def test_video_format_selector_prioritizes_resolution_over_codec():
    original = build_video_format_selector("original")
    four_k = build_video_format_selector("4k")

    assert original == "bv*+ba/b"
    assert four_k == "bv*[height<=2160]+ba/b[height<=2160]/best[height<=2160]"
    assert "vcodec^=av01" not in four_k
    assert "vcodec^=vp9" not in four_k


def test_extractor_options_keep_provider_client_selection_available(tmp_path):
    captured_opts = {}

    class MockYoutubeDL:
        def __init__(self, opts):
            nonlocal captured_opts
            captured_opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, query, download=True):
            return None

    with patch("janeconverter.extractor.yt_dlp.YoutubeDL", MockYoutubeDL):
        try:
            fetch_media_stream("https://example.com/test", str(tmp_path), audio_only=False, resolution="original")
        except Exception:
            pass

    assert captured_opts.get("concurrent_fragment_downloads") == 4
    assert "extractor_args" not in captured_opts
    assert captured_opts.get("format_sort") == ["res", "fps", "proto:https", "br"]
    assert captured_opts.get("format") == "bv*+ba/b"

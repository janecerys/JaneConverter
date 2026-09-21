"""
Tests for extractor yt-dlp option enhancements.
"""

from unittest.mock import patch
from janeconverter.extractor import fetch_media_stream


def test_extractor_options_include_parallel_and_client_args(tmp_path):
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
            fetch_media_stream("https://example.com/test", str(tmp_path), audio_only=False)
        except Exception:
            pass

    assert captured_opts.get("concurrent_fragment_downloads") == 4
    extractor_args = captured_opts.get("extractor_args", {})
    assert "youtube" in extractor_args
    assert "android" in extractor_args["youtube"]["player_client"]
    assert "web" in extractor_args["youtube"]["player_client"]

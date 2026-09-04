"""
Unit tests for engine/extractor.py
"""

import pytest
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.extractor import is_url, identify_source_type, sanitize_filename, resolve_spotify_metadata

def test_is_url():
    assert is_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_url("http://open.spotify.com/track/123") is True
    assert is_url("https://soundcloud.com/artist/track") is True
    assert is_url("C:\\Videos\\my_video.mp4") is False
    assert is_url("random text") is False
    assert is_url("") is False
    assert is_url(None) is False

def test_identify_source_type():
    assert identify_source_type("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") == "spotify"
    assert identify_source_type("https://www.youtube.com/watch?v=123") == "youtube"
    assert identify_source_type("https://youtu.be/123") == "youtube"
    assert identify_source_type("https://soundcloud.com/user/track") == "soundcloud"
    assert identify_source_type("https://www.tiktok.com/@user/video/123") == "tiktok"
    assert identify_source_type("https://x.com/user/status/123") == "twitter"
    assert identify_source_type("https://twitter.com/user/status/123") == "twitter"
    assert identify_source_type("https://facebook.com/watch/?v=123") == "facebook"
    assert identify_source_type("https://reddit.com/r/videos/comments/123") == "reddit"
    assert identify_source_type("https://twitch.tv/videos/123") == "twitch"
    assert identify_source_type("https://example.com/stream.mp4") == "generic_url"
    assert identify_source_type("D:\\JaneConverter\\sample.wav") == "local_file"

def test_sanitize_filename():
    unsafe = 'Video: "Best / Worst" * 2026? <test> | name'
    clean = sanitize_filename(unsafe)
    for bad in ['\\', '/', '*', '?', ':', '"', '<', '>', '|']:
        assert bad not in clean
    assert len(clean) > 0

def test_resolve_spotify_metadata_online():
    # Public Spotify track (Rick Astley - Never Gonna Give You Up)
    url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    data = resolve_spotify_metadata(url)
    assert isinstance(data, dict)
    assert "title" in data
    assert "artist" in data
    assert "search_query" in data
    assert len(data["search_query"]) > 0

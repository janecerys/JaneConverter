"""
Unit tests for playlist detection, extraction, and sequential ordered formatting
"""

import os
import sys
import re
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.extractor import is_playlist_url, format_duration, fetch_playlist_entries, sanitize_filename
from run_converter import process_playlist_conversion

def test_is_playlist_url():
    # True cases
    assert is_playlist_url("https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb") is True
    assert is_playlist_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") is True
    assert is_playlist_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3") is True
    assert is_playlist_url("https://soundcloud.com/user/sets/my-mixtape") is True
    assert is_playlist_url("https://artist.bandcamp.com/album/greatest-hits") is True

    # False cases (single tracks or non-playlists)
    assert is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert is_playlist_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") is False
    assert is_playlist_url("https://soundcloud.com/user/single-track") is False
    assert is_playlist_url("D:\\Music\\song.mp3") is False
    assert is_playlist_url("random text") is False
    assert is_playlist_url("") is False

def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(-5) == "0:00"
    assert format_duration(45) == "0:45"
    assert format_duration(65) == "1:05"
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3665) == "1:01:05"

def test_ordered_playlist_naming_format():
    # User requirement:
    # 1. Song1
    # 2. Song2
    # 3. Song3
    entries = [
        {"index": 1, "title": "Song One"},
        {"index": 2, "title": "02. Song Two"},
        {"index": 3, "title": "3 - Song Three"},
        {"index": 4, "title": "Track Four (Original Mix)"},
    ]

    expected = [
        "1. Song One",
        "2. Song Two",
        "3. Song Three",
        "4. Track Four (Original Mix)"
    ]

    results = []
    for entry in entries:
        idx = entry["index"]
        raw_title = entry["title"]
        clean_title = re.sub(r'^\d+[\.\s\-_]+\s*', '', sanitize_filename(raw_title)).strip()
        if not clean_title:
            clean_title = sanitize_filename(raw_title)
        results.append(f"{idx}. {clean_title}")

    assert results == expected

def test_fetch_spotify_playlist_online():
    url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
    data = fetch_playlist_entries(url)
    assert isinstance(data, dict)
    assert "playlist_title" in data
    assert len(data["playlist_title"]) > 0
    assert "entries" in data
    assert len(data["entries"]) > 0

    first = data["entries"][0]
    assert first["index"] == 1
    assert "title" in first
    assert "artist" in first
    assert "url" in first
    assert first["url"].startswith("https://open.spotify.com/track/")

def test_fetch_spotify_album_online():
    url = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"
    data = fetch_playlist_entries(url)
    assert isinstance(data, dict)
    assert "Emotion" in data["playlist_title"]
    assert len(data["entries"]) >= 10
    first = data["entries"][0]
    assert first["index"] == 1
    assert "Run Away With Me" in first["title"]

def test_fetch_youtube_playlist_flat():
    url = "https://www.youtube.com/playlist?list=PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb"
    data = fetch_playlist_entries(url)
    assert isinstance(data, dict)
    assert "playlist_title" in data
    assert len(data["entries"]) > 0
    first = data["entries"][0]
    assert first["index"] == 1
    assert "title" in first
    assert "url" in first
    assert first["url"].startswith("https://www.youtube.com/watch?v=")

def test_process_playlist_conversion_local_files():
    import wave
    import struct
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    try:
        # Create two 0.5s dummy WAV files
        wav1 = os.path.join(temp_dir, "sample1.wav")
        wav2 = os.path.join(temp_dir, "sample2.wav")
        for p in (wav1, wav2):
            with wave.open(p, "w") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                data = struct.pack("<h", 0) * (44100 // 2 * 2)
                wf.writeframes(data)

        entries = [
            {"index": 1, "title": "First Song", "artist": "Jane", "url": wav1},
            {"index": 2, "title": "Second Song", "artist": "Jane", "url": wav2},
        ]

        out_dir = os.path.join(temp_dir, "output")
        summary = process_playlist_conversion(
            playlist_title="Kotomi Mixtape",
            selected_entries=entries,
            output_dir=out_dir,
            target_format="mp3",
            check_updates=False
        )

        assert summary["successful_count"] == 2
        assert summary["failed_count"] == 0
        expected_folder = os.path.join(out_dir, "Kotomi Mixtape")
        assert os.path.exists(expected_folder)

        file1 = os.path.join(expected_folder, "1. First Song.mp3")
        file2 = os.path.join(expected_folder, "2. Second Song.mp3")
        assert os.path.exists(file1)
        assert os.path.exists(file2)
        assert os.path.getsize(file1) > 1000
        assert os.path.getsize(file2) > 1000

        meta_folder = os.path.join(expected_folder, "metadata")
        assert os.path.exists(meta_folder)
        assert os.path.exists(os.path.join(meta_folder, "playlist_credits.txt"))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

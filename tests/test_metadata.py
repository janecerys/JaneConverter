"""
Unit tests for cover art extraction, credits file generation, and metadata embedding.
"""

import os
import sys
import pytest
from PIL import Image

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.extractor import download_and_convert_thumbnail, resolve_spotify_metadata
from engine.converter import build_ffmpeg_args
from run_converter import write_credits_file

def test_download_and_convert_thumbnail_local(tmp_path):
    src_img_path = os.path.join(str(tmp_path), "source_art.png")
    out_jpg_path = os.path.join(str(tmp_path), "converted_art.jpg")

    img = Image.new("RGBA", (500, 500), color=(120, 40, 200, 255))
    img.save(src_img_path, format="PNG")

    result = download_and_convert_thumbnail(src_img_path, out_jpg_path)
    assert result is not None
    assert os.path.exists(out_jpg_path)

    with Image.open(out_jpg_path) as out_img:
        assert out_img.format == "JPEG"
        assert out_img.mode == "RGB"
        assert out_img.size == (500, 500)

def test_write_credits_file(tmp_path):
    credits_path = os.path.join(str(tmp_path), "test_song_credits.txt")
    meta = {
        "title": "Hyperpop Anthem",
        "artist": "project//aspyr",
        "album": "The Heavenly Demon",
        "track": "01",
        "year": "2026",
        "source_url": "https://soundcloud.com/project-aspyr/hyperpop-anthem",
        "platform": "soundcloud",
        "duration": 185,
        "duration_str": "3:05",
        "description": "Produced, mixed, and mastered by Kotomi in FL Studio.\nVocal arrangement by Seung.",
        "tags": ["dariacore", "hyperpop", "color bass"],
        "categories": ["Music"]
    }

    res_path = write_credits_file(credits_path, meta)
    assert res_path == credits_path
    assert os.path.exists(credits_path)

    with open(credits_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "JANECONVERTER - MEDIA CREDITS & METADATA" in content
    assert "Title:        Hyperpop Anthem" in content
    assert "Artist:       project//aspyr" in content
    assert "Album:        The Heavenly Demon" in content
    assert "Release Date: 2026" in content
    assert "Duration:     3:05" in content
    assert "Platform:     Soundcloud" in content
    assert "Produced, mixed, and mastered by Kotomi in FL Studio." in content
    assert "Vocal arrangement by Seung." in content
    assert "Tags:       dariacore, hyperpop, color bass" in content
    assert "Categories: Music" in content

def test_build_ffmpeg_args_with_cover_art_mp3(tmp_path):
    cover_file = os.path.join(str(tmp_path), "cover.jpg")
    with open(cover_file, "wb") as f:
        f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")

    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.mp3",
        target_format="mp3",
        bitrate="320k",
        sample_rate=48000,
        cover_path=cover_file,
        metadata={"title": "Test Song", "artist": "Kotomi", "album": "Debut EP"}
    )

    assert "-i" in cmd
    assert cover_file in cmd
    assert "-map" in cmd
    assert "0:a" in cmd
    assert "1:v" in cmd
    assert "-id3v2_version" in cmd
    assert "3" in cmd
    assert "attached_pic" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-vn" not in cmd

def test_build_ffmpeg_args_with_cover_art_flac(tmp_path):
    cover_file = os.path.join(str(tmp_path), "cover.jpg")
    with open(cover_file, "wb") as f:
        f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")

    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.flac",
        target_format="flac",
        cover_path=cover_file,
        metadata={"title": "Lossless Master", "artist": "Jane Cerys"}
    )

    assert cover_file in cmd
    assert "0:a" in cmd
    assert "1:v" in cmd
    assert "attached_pic" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-vn" not in cmd

def test_build_ffmpeg_args_with_cover_art_m4a(tmp_path):
    cover_file = os.path.join(str(tmp_path), "cover.jpg")
    with open(cover_file, "wb") as f:
        f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")

    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.m4a",
        target_format="m4a",
        cover_path=cover_file
    )

    assert cover_file in cmd
    assert "0:a" in cmd
    assert "1:v" in cmd
    assert "attached_pic" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd

def test_build_ffmpeg_args_without_cover_art():
    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.mp3",
        target_format="mp3",
        cover_path=None
    )

    assert "-vn" in cmd
    assert "attached_pic" not in cmd
    assert "1:v" not in cmd

@pytest.mark.online
def test_spotify_metadata_fields():
    url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    data = resolve_spotify_metadata(url)

    assert isinstance(data, dict)
    assert data.get("title") is not None
    assert data.get("artist") is not None
    assert "thumbnail_url" in data
    assert "year" in data
    assert "description" in data
    assert "search_query" in data

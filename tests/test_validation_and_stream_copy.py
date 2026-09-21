"""
Tests for output validation, stream-copy guardrails, and SoX resampler logic.
"""

import os
import subprocess
import pytest
from janeconverter.converter import (
    probe_media_streams,
    validate_output_file,
    is_stream_copy_safe,
    build_ffmpeg_args,
    convert_media,
    get_ffmpeg_binary,
)


def test_probe_media_streams_nonexistent():
    assert probe_media_streams("nonexistent_file_path_12345.mp4") is None


def test_validate_output_file_missing(tmp_path):
    missing_file = str(tmp_path / "missing.mp3")
    with pytest.raises(RuntimeError, match="ValidationFailed: destination file .* was not created"):
        validate_output_file(missing_file, "mp3")


def test_validate_output_file_empty(tmp_path):
    tiny_file = tmp_path / "empty.mp3"
    tiny_file.write_bytes(b"too small")
    with pytest.raises(RuntimeError, match="ValidationFailed: destination file .* is corrupted or empty"):
        validate_output_file(str(tiny_file), "mp3")


def test_validate_output_file_corrupted_headers(tmp_path):
    junk_file = tmp_path / "junk.mp3"
    junk_file.write_bytes(b"A" * 500)
    with pytest.raises(RuntimeError, match="ValidationFailed: destination file .* has invalid or unreadable media headers"):
        validate_output_file(str(junk_file), "mp3")


def test_is_stream_copy_safe_guardrails(tmp_path):
    # 1. Normalization must disallow stream copy
    assert not is_stream_copy_safe(
        "dummy.mp4", "mp4", normalize_audio=True
    )

    # 2. Resolution downscaling must disallow stream copy
    assert not is_stream_copy_safe(
        "dummy.mp4", "mp4", resolution="720p"
    )

    # 3. Active cover path must disallow stream copy
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"dummy image data")
    assert not is_stream_copy_safe(
        "dummy.mp3", "mp3", cover_path=str(cover)
    )

    # 4. Mocked stream compatibility
    mock_mp4 = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"}
        ]
    }
    # Video cover thumbnails are not embedded into video outputs, so they must
    # not force an otherwise compatible video to be re-encoded.
    assert is_stream_copy_safe(
        "dummy.mp4",
        "mp4",
        sample_rate=48000,
        cover_path=str(cover),
        probed_info=mock_mp4,
    )
    # MP4 to MP4: safe
    assert is_stream_copy_safe("dummy.mp4", "mp4", sample_rate=48000, probed_info=mock_mp4)
    # MP4 to WEBM (incompatible codecs h264/aac in webm): unsafe
    assert not is_stream_copy_safe("dummy.mp4", "webm", sample_rate=48000, probed_info=mock_mp4)
    # Video conversion does not change audio sample rate, so the UI's audio
    # sample-rate default must not force a video re-encode.
    assert is_stream_copy_safe("dummy.mp4", "mp4", sample_rate=44100, probed_info=mock_mp4)
    # Audio extraction still must reject a requested sample-rate change.
    assert not is_stream_copy_safe("dummy.mp4", "m4a", sample_rate=44100, probed_info=mock_mp4)
    # Extract AAC audio to m4a: safe
    assert is_stream_copy_safe("dummy.mp4", "m4a", sample_rate=48000, probed_info=mock_mp4)
    # Extract AAC audio to mp3: unsafe (needs transcode)
    assert not is_stream_copy_safe("dummy.mp4", "mp3", sample_rate=48000, probed_info=mock_mp4)


def test_build_ffmpeg_args_stream_copy():
    audio_cmd = build_ffmpeg_args(
        input_path="input.m4a",
        output_path="output.aac",
        target_format="aac",
        stream_copy=True,
    )
    assert "-c:a" in audio_cmd
    assert audio_cmd[audio_cmd.index("-c:a") + 1] == "copy"
    assert "-vn" in audio_cmd

    video_cmd = build_ffmpeg_args(
        input_path="input.mp4",
        output_path="output.mkv",
        target_format="mkv",
        stream_copy=True,
    )
    assert "-c:v" in video_cmd
    assert video_cmd[video_cmd.index("-c:v") + 1] == "copy"
    assert "-c:a" in video_cmd
    assert video_cmd[video_cmd.index("-c:a") + 1] == "copy"


def test_convert_media_stream_copy_e2e(tmp_path):
    ffmpeg = get_ffmpeg_binary()
    source_mp3 = tmp_path / "source.mp3"

    # Generate a short 0.2s valid test mp3 using ffmpeg
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
         "-c:a", "libmp3lame", "-ar", "48000", str(source_mp3)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

    output_dir = str(tmp_path / "out")
    # Stream copy to another MP3 file (same container, no filters)
    result = convert_media(
        input_path=str(source_mp3),
        output_dir=output_dir,
        output_filename="remuxed",
        target_format="mp3",
        sample_rate=48000,
        normalize_audio=False,
    )

    assert os.path.isfile(result)
    assert os.path.getsize(result) > 100
    # Output must be readable by probe_media_streams
    info = probe_media_streams(result)
    assert info is not None
    assert any(s.get("codec_name") == "mp3" for s in info.get("streams", []))


def test_convert_media_preserve_quality_source_format(tmp_path):
    ffmpeg = get_ffmpeg_binary()
    source_mp4 = tmp_path / "source.mp4"

    # Generate a short 0.2s valid test mp4 video with ffmpeg
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=0.2:size=320x240:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
         "-c:v", "libx264", "-c:a", "aac", str(source_mp4)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

    output_dir = str(tmp_path / "out_raw")
    result = convert_media(
        input_path=str(source_mp4),
        output_dir=output_dir,
        output_filename="raw_video",
        target_format="source",
    )

    assert os.path.isfile(result)
    assert result.endswith(".mp4")
    assert os.path.getsize(result) == os.path.getsize(str(source_mp4))
    info = probe_media_streams(result)
    assert info is not None
    assert any(s.get("codec_type") == "video" for s in info.get("streams", []))


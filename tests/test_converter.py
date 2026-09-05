"""
Unit tests for engine/converter.py and engine/updater.py
"""

import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.converter import (
    build_ffmpeg_args,
    get_unique_target_path,
    get_host_gpus,
    get_best_hardware_encoder,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_VIDEO_FORMATS
)
from engine.updater import (
    get_current_engine_version,
    check_for_engine_updates,
    is_git_repo,
    get_current_repo_commit,
    check_for_repo_updates,
    check_and_apply_all_updates
)

def test_build_ffmpeg_args_mp3():
    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.mp3",
        target_format="mp3",
        bitrate="320k",
        sample_rate=48000,
        normalize_audio=True,
        metadata={"title": "Test Song", "artist": "Kotomi"}
    )
    assert "ffmpeg" in cmd[0]
    assert "-vn" in cmd
    assert "libmp3lame" in cmd
    assert "320k" in cmd
    assert "48000" in cmd
    assert any("loudnorm" in arg for arg in cmd)
    assert "-metadata" in cmd
    assert "title=Test Song" in cmd
    assert "artist=Kotomi" in cmd
    assert cmd[-1] == "output.mp3"

def test_build_ffmpeg_args_wav():
    cmd = build_ffmpeg_args(
        input_path="input.mp4",
        output_path="output.wav",
        target_format="wav"
    )
    assert "-vn" in cmd
    assert "pcm_s24le" in cmd
    assert cmd[-1] == "output.wav"

def test_build_ffmpeg_args_wav_16bit():
    cmd = build_ffmpeg_args(
        input_path="input.mp4",
        output_path="output.wav",
        target_format="wav",
        bitrate="16-bit"
    )
    assert "-vn" in cmd
    assert "pcm_s16le" in cmd
    assert cmd[-1] == "output.wav"

def test_build_ffmpeg_args_wav_32bit():
    cmd = build_ffmpeg_args(
        input_path="input.mp4",
        output_path="output.wav",
        target_format="wav",
        bitrate="32-bit"
    )
    assert "-vn" in cmd
    assert "pcm_f32le" in cmd
    assert cmd[-1] == "output.wav"

def test_build_ffmpeg_args_flac():
    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.flac",
        target_format="flac"
    )
    assert "-vn" in cmd
    assert "flac" in cmd
    assert "8" in cmd
    assert "s32" in cmd

def test_build_ffmpeg_args_flac_16bit():
    cmd = build_ffmpeg_args(
        input_path="input.wav",
        output_path="output.flac",
        target_format="flac",
        bitrate="16-bit"
    )
    assert "-vn" in cmd
    assert "flac" in cmd
    assert "8" in cmd
    assert "s16" in cmd

def test_build_ffmpeg_args_mp4_nvenc():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        resolution="1080p",
        use_nvenc=True
    )
    assert "h264_nvenc" in cmd
    assert any("scale=-2:1080" in arg for arg in cmd)
    assert cmd[-1] == "output.mp4"

def test_build_ffmpeg_args_mp4_cpu():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_nvenc=False
    )
    assert "libx264" in cmd
    assert "h264_nvenc" not in cmd

def test_build_ffmpeg_args_mp4_amf():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_gpu=True,
        gpu_codec="h264_amf"
    )
    assert "h264_amf" in cmd
    assert "-hwaccel" in cmd

def test_build_ffmpeg_args_mp4_qsv():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_gpu=True,
        gpu_codec="h264_qsv"
    )
    assert "h264_qsv" in cmd

def test_build_ffmpeg_args_mp4_videotoolbox():
    cmd = build_ffmpeg_args(
        input_path="input.mov",
        output_path="output.mp4",
        target_format="mp4",
        use_gpu=True,
        gpu_codec="h264_videotoolbox"
    )
    assert "h264_videotoolbox" in cmd

def test_get_host_gpus_and_encoder():
    gpus = get_host_gpus()
    assert isinstance(gpus, list)
    enc = get_best_hardware_encoder()
    assert isinstance(enc, dict)
    assert "has_gpu" in enc
    assert "encoder" in enc
    assert "args" in enc

def test_build_ffmpeg_args_gif():
    cmd = build_ffmpeg_args(
        input_path="input.mp4",
        output_path="output.gif",
        target_format="gif"
    )
    assert any("palettegen" in arg for arg in cmd)
    assert cmd[-1] == "output.gif"

def test_unsupported_format_raises_error():
    with pytest.raises(ValueError) as exc:
        build_ffmpeg_args("in.mp4", "out.xyz", "xyz")
    assert "Unsupported conversion format" in str(exc.value)

def test_get_unique_target_path(tmp_path):
    target = os.path.join(str(tmp_path), "song.mp3")
    assert get_unique_target_path(str(tmp_path), "song.mp3") == target

    # Create file
    with open(target, "w") as f:
        f.write("content")

    second = get_unique_target_path(str(tmp_path), "song.mp3")
    assert second == os.path.join(str(tmp_path), "song_1.mp3")

    with open(second, "w") as f:
        f.write("content2")

    third = get_unique_target_path(str(tmp_path), "song.mp3")
    assert third == os.path.join(str(tmp_path), "song_2.mp3")

def test_engine_updater_version_check():
    ver = get_current_engine_version()
    assert ver != ""
    assert isinstance(ver, str)
    info = check_for_engine_updates()
    assert isinstance(info, dict)
    assert "current_version" in info
    assert "online" in info

def test_repo_updater_git_check():
    assert is_git_repo() is True
    commit = get_current_repo_commit()
    assert isinstance(commit, str)
    assert len(commit) >= 7

def test_repo_updater_check_for_updates():
    info = check_for_repo_updates()
    assert isinstance(info, dict)
    assert "has_update" in info
    assert "is_git" in info
    assert info["is_git"] is True
    assert "current_commit" in info

def test_check_and_apply_all_updates():
    logs = []
    def log_cb(msg):
        logs.append(msg)

    result = check_and_apply_all_updates(status_callback=log_cb)
    assert isinstance(result, dict)
    assert "repo_updated" in result
    assert "engine_updated" in result
    assert "already_up_to_date" in result
    assert len(logs) > 0

"""
Media Converter Engine for JaneConverter
Transcodes media to high-fidelity audio (MP3, WAV, FLAC, AAC, OGG) and video (MP4, MKV, WEBM, MOV, GIF).
Supports NVIDIA NVENC acceleration, EBU R128 loudness normalization, sample rate control,
and metadata tagging.
"""

import os
import re
import subprocess
from typing import Optional, Dict, Any, Callable

SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "flac", "aac", "m4a", "ogg"}
SUPPORTED_VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "gif"}

def get_unique_target_path(directory: str, filename: str) -> str:
    """Appends an incrementing counter if a file already exists to prevent overwriting."""
    base_target = os.path.join(directory, filename)
    if not os.path.exists(base_target):
        return base_target

    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = os.path.join(directory, f"{stem}_{counter}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1

def build_ffmpeg_args(
    input_path: str,
    output_path: str,
    target_format: str,
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    metadata: Optional[Dict[str, str]] = None,
    cover_path: Optional[str] = None
) -> list:
    """Constructs command line argument list for FFmpeg transcode, including optional cover art embedding."""
    target_format = target_format.lower().strip(".")
    has_valid_cover = bool(cover_path and os.path.exists(cover_path))

    # Determine if target container format supports attached picture stream
    can_embed_art = has_valid_cover and target_format in ("mp3", "flac", "m4a", "aac")

    if can_embed_art:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-i", cover_path, "-map", "0:a", "-map", "1:v"]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_path]

    # Metadata tags
    if metadata:
        for k, v in metadata.items():
            if v:
                cmd.extend(["-metadata", f"{k}={v}"])

    # 1. Audio Conversion
    if target_format in SUPPORTED_AUDIO_FORMATS:
        if not can_embed_art:
            cmd.append("-vn")

        # Audio filters
        audio_filters = []
        if normalize_audio:
            # Industry standard EBU R128 loudness normalization
            audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])

        if sample_rate and target_format not in ("flac",):
            cmd.extend(["-ar", str(sample_rate)])

        # Codecs and cover art mapping
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
            if can_embed_art:
                cmd.extend([
                    "-c:v", "copy",
                    "-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                    "-disposition:v", "attached_pic"
                ])
        elif target_format == "wav":
            cmd.extend(["-c:a", "pcm_s24le"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "8"])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format in ("aac", "m4a"):
            cmd.extend(["-c:a", "aac", "-b:a", bitrate])
            if can_embed_art:
                cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis", "-q:a", "7"])

    # 2. Video Conversion
    elif target_format in SUPPORTED_VIDEO_FORMATS:
        if target_format == "gif":
            vf = "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
            cmd.extend(["-vf", vf])
        else:
            # Video encoder
            v_codec = "h264_nvenc" if use_nvenc else "libx264"
            preset = "p4" if use_nvenc else "medium"

            video_filters = []
            if resolution == "4k":
                video_filters.append("scale=-2:2160")
            elif resolution == "1440p":
                video_filters.append("scale=-2:1440")
            elif resolution == "1080p":
                video_filters.append("scale=-2:1080")
            elif resolution == "720p":
                video_filters.append("scale=-2:720")
            elif resolution == "480p":
                video_filters.append("scale=-2:480")

            if video_filters:
                cmd.extend(["-vf", ",".join(video_filters)])

            audio_filters = []
            if normalize_audio:
                audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

            if audio_filters:
                cmd.extend(["-af", ",".join(audio_filters)])

            if target_format == "webm":
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus", "-b:a", "160k"])
            else:
                cmd.extend([
                    "-c:v", v_codec,
                    "-preset", preset,
                    "-c:a", "aac",
                    "-b:a", "192k"
                ])
    else:
        raise ValueError(f"Unsupported conversion format: '{target_format}'")

    cmd.append(output_path)
    return cmd

def convert_media(
    input_path: str,
    output_dir: str,
    output_filename: str,
    target_format: str,
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    metadata: Optional[Dict[str, str]] = None,
    cover_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Transcodes input_path into the specified target format and writes to output_dir.
    Optionally embeds cover art image and tags metadata.
    Automatically handles NVENC GPU fallback to CPU, and cover embedding fallback if needed.
    """
    os.makedirs(output_dir, exist_ok=True)
    target_format = target_format.lower().strip(".")
    final_output_name = f"{output_filename}.{target_format}"
    destination_path = get_unique_target_path(output_dir, final_output_name)

    def report(frac: float, msg: str):
        if progress_callback:
            progress_callback(frac, msg)

    report(0.80, f"Transcoding media to {target_format.upper()}...")

    cmd = build_ffmpeg_args(
        input_path=input_path,
        output_path=destination_path,
        target_format=target_format,
        bitrate=bitrate,
        sample_rate=sample_rate,
        normalize_audio=normalize_audio,
        resolution=resolution,
        use_nvenc=use_nvenc,
        metadata=metadata,
        cover_path=cover_path
    )

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=no_window
        )
    except subprocess.CalledProcessError as e:
        # If NVENC failed, retry with CPU libx264
        if use_nvenc and target_format in ("mp4", "mkv", "mov"):
            report(0.85, "NVENC hardware encoder unavailable, switching to CPU transcode...")
            return convert_media(
                input_path=input_path,
                output_dir=output_dir,
                output_filename=output_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=False,
                metadata=metadata,
                cover_path=cover_path,
                progress_callback=progress_callback
            )
        # If cover art embedding failed, retry without cover art
        if cover_path:
            report(0.85, "Cover art embedding encountered an issue, transcoding media directly...")
            return convert_media(
                input_path=input_path,
                output_dir=output_dir,
                output_filename=output_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=use_nvenc,
                metadata=metadata,
                cover_path=None,
                progress_callback=progress_callback
            )
        err_detail = e.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg transcode error: {err_detail}") from e

    report(1.0, f"Conversion complete: {os.path.basename(destination_path)}")
    return destination_path

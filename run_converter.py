"""
Main Pipeline Runner and CLI Driver for JaneConverter
Orchestrates stream fetching, Spotify resolution, and FFmpeg transcode.
"""

import os
import sys
import uuid
import shutil
import argparse
from typing import Optional, Dict, Any, Callable

if sys.stdout is not None and hasattr(sys.stdout, "encoding") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONVERTED_DIR = os.path.join(BASE_DIR, "converted")
DEFAULT_TEMP_DIR = os.path.join(BASE_DIR, "temp")

from engine.extractor import is_url, sanitize_filename, fetch_media_stream, identify_source_type
from engine.converter import convert_media, SUPPORTED_AUDIO_FORMATS, SUPPORTED_VIDEO_FORMATS
from engine.updater import update_engine

def process_conversion(
    source: str,
    output_dir: Optional[str] = None,
    target_format: str = "mp3",
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    keep_temp: bool = False,
    check_updates: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Orchestrates downloading/extracting stream and transcoding into the desired format.
    Automatically manages per-job temporary workspace and cleanup.
    """
    if check_updates:
        update_engine(status_callback=lambda m: print(f"[AutoUpdate] {m}"))

    if not output_dir:
        output_dir = DEFAULT_CONVERTED_DIR
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(DEFAULT_TEMP_DIR, exist_ok=True)

    def report(pct: float, msg: str):
        if progress_callback:
            progress_callback(pct, msg)
        print(f"[{int(pct * 100)}%] {msg}")

    target_format = target_format.lower().strip(".")
    is_audio_target = target_format in SUPPORTED_AUDIO_FORMATS

    job_id = uuid.uuid4().hex[:8]
    work_dir = os.path.join(DEFAULT_TEMP_DIR, f"job_{job_id}")
    os.makedirs(work_dir, exist_ok=True)

    print("=" * 60)
    print(f"[*] JANECONVERTER PIPELINE")
    print(f"Source: {source}")
    print(f"Target Format: {target_format.upper()}")
    print(f"Output Directory: {output_dir}")
    print(f"Hardware NVENC: {use_nvenc}")
    print("=" * 60)

    try:
        # Stage 1: Stream Extraction or File Ingestion
        report(0.05, f"Analyzing source link and fetching media stream...")
        stream_info = fetch_media_stream(
            source=source,
            output_dir=work_dir,
            audio_only=is_audio_target,
            progress_callback=report
        )

        input_media = stream_info["media_path"]
        title = stream_info.get("title", "converted_media")
        safe_title = sanitize_filename(title)
        artist = stream_info.get("artist", "")
        album = stream_info.get("album", "")

        metadata = {
            "title": title,
            "artist": artist,
            "album": album
        }

        # Stage 2: Conversion & Transcode
        report(0.78, f"Transcoding '{safe_title}' to {target_format.upper()}...")
        result_path = convert_media(
            input_path=input_media,
            output_dir=output_dir,
            output_filename=safe_title,
            target_format=target_format,
            bitrate=bitrate,
            sample_rate=sample_rate,
            normalize_audio=normalize_audio,
            resolution=resolution,
            use_nvenc=use_nvenc,
            metadata=metadata,
            progress_callback=report
        )

        report(1.0, f"Ready! File exported to: {os.path.basename(result_path)}")
        print("\n" + "=" * 60)
        print(f"DONE! Exported: {os.path.abspath(result_path)}")
        print("=" * 60)
        return result_path

    finally:
        if not keep_temp and os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

def main():
    parser = argparse.ArgumentParser(description="JaneConverter: Universal Media Downloader & Converter")
    parser.add_argument("--source", "-s", required=True, help="Media URL (YouTube, Spotify, SoundCloud, TikTok, Twitter, etc.) or local file path")
    parser.add_argument("--format", "-f", default="mp3", help="Target output format (mp3, wav, flac, aac, mp4, mkv, gif)")
    parser.add_argument("--output", "-o", default=DEFAULT_CONVERTED_DIR, help="Destination directory for converted files")
    parser.add_argument("--bitrate", "-b", default="320k", help="Audio bitrate (320k, 256k, 192k, 128k)")
    parser.add_argument("--sample-rate", "-r", type=int, default=48000, help="Audio sample rate in Hz (44100, 48000, 96000)")
    parser.add_argument("--normalize", "-n", action="store_true", help="Apply EBU R128 loudness normalization")
    parser.add_argument("--resolution", default="original", help="Video resolution (original, 4k, 1440p, 1080p, 720p, 480p)")
    parser.add_argument("--no-nvenc", action="store_true", help="Disable NVIDIA NVENC GPU acceleration (use CPU libx264)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate downloaded stream files in temp directory")

    args = parser.parse_args()
    process_conversion(
        source=args.source,
        output_dir=args.output,
        target_format=args.format,
        bitrate=args.bitrate,
        sample_rate=args.sample_rate,
        normalize_audio=args.normalize,
        resolution=args.resolution,
        use_nvenc=not args.no_nvenc,
        keep_temp=args.keep_temp
    )

if __name__ == "__main__":
    main()

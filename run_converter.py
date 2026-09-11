"""
Main Pipeline Runner and CLI Driver for JaneConverter
Orchestrates stream fetching, Spotify resolution, and FFmpeg transcode.
"""

import os
import sys
import re
import uuid
import shutil
import json
import hashlib
import argparse
import time
from typing import Optional, Dict, Any, Callable

if sys.stdout is not None and hasattr(sys.stdout, "encoding") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from engine.extractor import (
    is_url, sanitize_filename, fetch_media_stream,
    is_playlist_url, fetch_playlist_entries, download_and_convert_thumbnail, format_duration,
    identify_source_type
)
from engine.converter import (
    convert_media,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_VIDEO_FORMATS,
    get_best_hardware_encoder
)
from engine.updater import check_for_engine_updates
from engine.version import __version__
from engine.paths import DEFAULT_CONVERTED_DIR, DEFAULT_TEMP_DIR
from engine.auth import normalize_browser_session

MIN_FREE_DISK_BYTES = 256 * 1024 * 1024  # keep a reasonable minimum without rejecting small conversions


def media_library_folder(
    output_dir: str,
    target_format: str,
    source_type: str,
    content_category: Optional[str] = None,
) -> str:
    """Return the organized library folder for a converted item."""
    media_kind = "Music" if target_format.lower().strip(".") in SUPPORTED_AUDIO_FORMATS else "Videos"
    category = str(content_category or "").strip().lower()
    if category in ("miscellaneous", "misc"):
        misc_kind = "Audio" if media_kind == "Music" else "Videos"
        return os.path.join(output_dir, "Miscellaneous", misc_kind)
    source_labels = {
        "spotify": "Spotify",
        "youtube": "YouTube",
        "soundcloud": "SoundCloud",
        "tiktok": "TikTok",
        "twitter": "Twitter",
        "facebook": "Facebook",
        "reddit": "Reddit",
        "twitch": "Twitch",
        "local": "Local Files",
        "local_file": "Local Files",
        "generic_url": "Other Sources",
    }
    source_key = str(source_type or "other").lower().strip()
    source_label = source_labels.get(source_key, "Other Sources")
    return os.path.join(output_dir, media_kind, source_label)


def _unique_directory_path(parent: str, name: str) -> str:
    """Return a new directory path without merging two exports with the same title."""
    candidate = os.path.join(parent, name)
    if not os.path.exists(candidate):
        return candidate
    index = 2
    while True:
        candidate = os.path.join(parent, f"{name} ({index})")
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _metadata_folder(parent: str, source: str, title: str) -> str:
    """Give each single export an isolated metadata directory."""
    token = hashlib.sha256(f"{source}\0{title}".encode("utf-8", errors="replace")).hexdigest()[:10]
    return os.path.join(parent, "metadata", f"{sanitize_filename(title)}_{token}")


def playlist_source_type(selected_entries: list) -> str:
    """Infer the source platform for a playlist batch from its first item."""
    for entry in selected_entries:
        source = entry.get("url", "") if isinstance(entry, dict) else ""
        if source:
            return identify_source_type(source)
    return "other"

def ensure_free_disk_space(path: str, min_free_bytes: int = MIN_FREE_DISK_BYTES,
                           estimated_bytes: int = 0):
    """Raises RuntimeError if the drive holding `path` has less than the required free space."""
    required = max(min_free_bytes, int(estimated_bytes or 0) * 2)
    try:
        usage = shutil.disk_usage(path)
    except Exception:
        return  # Un probing-able path; let downstream operations surface real errors
    if usage.free < required:
        free_gb = usage.free / (1024 ** 3)
        raise RuntimeError(
            f"Not enough disk space at '{os.path.abspath(path)}' "
            f"({free_gb:.1f} GB free; about {required / (1024 ** 3):.1f} GB is recommended). "
            "Free up space and try again."
        )

def write_credits_file(output_path: str, meta: Dict[str, Any]) -> str:
    """
    Writes a formatted, human-readable credits and metadata file.
    """
    title = meta.get("title", "Unknown Title")
    artist = meta.get("artist", "Unknown Artist")
    album = meta.get("album", "")
    track = meta.get("track", "")
    year = meta.get("year", "")
    source_url = meta.get("source_url", "") or meta.get("webpage_url", "")
    platform = meta.get("platform", "") or meta.get("source_type", "")
    dur_val = meta.get("duration", 0)
    dur_str = meta.get("duration_str", "") or (format_duration(dur_val) if dur_val else "")
    description = meta.get("description", "").strip()
    tags = meta.get("tags", [])
    categories = meta.get("categories", [])

    lines = [
        "=" * 80,
        "JANECONVERTER - MEDIA CREDITS & METADATA",
        "=" * 80,
        f"Title:        {title}",
        f"Artist:       {artist}",
    ]
    if album:
        lines.append(f"Album:        {album}")
    if track:
        lines.append(f"Track:        {track}")
    if year:
        lines.append(f"Release Date: {year}")
    if dur_str:
        lines.append(f"Duration:     {dur_str}")
    if platform:
        lines.append(f"Platform:     {platform.replace('_', ' ').title()}")
    if source_url:
        lines.append(f"Source URL:   {source_url}")

    if description:
        lines.extend([
            "",
            "-" * 80,
            "CREDITS & DESCRIPTION",
            "-" * 80,
            description
        ])

    if tags or categories:
        lines.extend([
            "",
            "-" * 80,
            "TAGS & CATEGORIES",
            "-" * 80
        ])
        if tags:
            tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
            lines.append(f"Tags:       {tag_str}")
        if categories:
            cat_str = ", ".join(categories) if isinstance(categories, list) else str(categories)
            lines.append(f"Categories: {cat_str}")

    lines.extend([
        "=" * 80,
        ""
    ])

    content = "\n".join(lines)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def process_conversion(
    source: str,
    output_dir: Optional[str] = None,
    target_format: str = "mp3",
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    use_gpu: Optional[bool] = None,
    save_cover_art: bool = True,
    save_metadata: bool = True,
    keep_temp: bool = False,
    check_updates: bool = False,
    abort_event: Optional[Any] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    content_category: Optional[str] = None,
    auth_browser: Optional[str] = None
) -> str:
    """
    Orchestrates downloading/extracting stream, embedding cover art, exporting credits,
    and transcoding into the desired format.
    """
    if abort_event and abort_event.is_set():
        raise KeyboardInterrupt("Conversion aborted by user.")

    if check_updates:
        engine_info = check_for_engine_updates()
        if engine_info.get("has_update"):
            print(
                f"[Update] Extractor engine update available: "
                f"v{engine_info.get('current_version')} -> v{engine_info.get('latest_version')}."
            )

    if not output_dir:
        output_dir = DEFAULT_CONVERTED_DIR
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(DEFAULT_TEMP_DIR, exist_ok=True)
    estimated_size = 0
    if os.path.isfile(source):
        try:
            estimated_size = os.path.getsize(source)
        except OSError:
            pass
    ensure_free_disk_space(output_dir, estimated_bytes=estimated_size)

    active_gpu = use_gpu if use_gpu is not None else use_nvenc

    last_report = [0.0, 0.0]

    def report(pct: float, msg: str):
        pct = max(last_report[1], max(0.0, min(1.0, float(pct))))
        now = time.monotonic()
        if pct >= 1.0 or now - last_report[0] >= 0.15 or int(pct * 100) != int(last_report[1] * 100):
            last_report[:] = [now, pct]
            if progress_callback:
                progress_callback(pct, msg)
            print(f"[{int(pct * 100)}%] {msg}")

    target_format = target_format.lower().strip(".")
    is_audio_target = target_format in SUPPORTED_AUDIO_FORMATS

    job_id = uuid.uuid4().hex[:8]
    work_dir = os.path.join(DEFAULT_TEMP_DIR, f"job_{job_id}")
    os.makedirs(work_dir, exist_ok=True)

    enc_info = get_best_hardware_encoder()
    gpu_desc = f"{enc_info['short_name']} ({enc_info['encoder_label']})" if active_gpu and enc_info["has_gpu"] else "CPU Multi-Core"

    print("=" * 60)
    print("[*] JANECONVERTER PIPELINE")
    print(f"Source: {source}")
    print(f"Target Format: {target_format.upper()}")
    print(f"Output Directory: {output_dir}")
    print(f"Hardware Acceleration: {active_gpu} [{gpu_desc}]")
    print(f"Cover Art: {save_cover_art} | Metadata: {save_metadata}")
    print("=" * 60)

    try:
        # Stage 1: Stream Extraction or File Ingestion
        report(0.05, "Analyzing source link and fetching media stream...")
        stream_info = fetch_media_stream(
            source=source,
            output_dir=work_dir,
            audio_only=is_audio_target,
            abort_event=abort_event,
            progress_callback=report,
            auth_browser=auth_browser
        )

        input_media = stream_info["media_path"]
        title = stream_info.get("title", "converted_media")
        safe_title = sanitize_filename(title)
        artist = stream_info.get("artist", "")
        album = stream_info.get("album", "")
        year = stream_info.get("year", "")
        description = stream_info.get("description", "")
        cover_path = stream_info.get("thumbnail_path")

        # Keep the export root tidy and make the origin obvious at a glance.
        organized_output_dir = media_library_folder(
            output_dir, target_format, stream_info.get("source_type", "other"), content_category
        )
        os.makedirs(organized_output_dir, exist_ok=True)
        metadata_dir = _metadata_folder(organized_output_dir, source, title)
        if save_cover_art or save_metadata:
            os.makedirs(metadata_dir, exist_ok=True)

        # Save standalone cover art image if requested
        if save_cover_art and cover_path and os.path.exists(cover_path):
            standalone_cover = os.path.join(metadata_dir, f"{safe_title}.jpg")
            try:
                shutil.copy2(cover_path, standalone_cover)
                print(f"[+] Saved cover art: {os.path.basename(standalone_cover)}")
            except Exception:
                pass

        # Save metadata text file if requested
        if save_metadata:
            meta_path = os.path.join(metadata_dir, f"{safe_title}_info.txt")
            write_credits_file(meta_path, {
                "title": title,
                "artist": artist,
                "album": album,
                "year": year,
                "source_url": source,
                "platform": stream_info.get("platform") or stream_info.get("source_type", ""),
                "duration": stream_info.get("duration", 0),
                "duration_str": stream_info.get("duration_str", ""),
                "description": description,
                "tags": stream_info.get("tags", []),
                "categories": stream_info.get("categories", [])
            })
            print(f"[+] Saved metadata: {os.path.basename(meta_path)}")

        # Stage 2: Transcode & Cover Art Embedding
        report(0.70, f"Transcoding to {target_format.upper()} (Bitrate: {bitrate})...")
        metadata = {
            "title": title,
            "artist": artist,
            "album": album,
            "date": str(year) if year else "",
            "comment": "Converted by JaneConverter"
        }

        result_path = convert_media(
            input_path=input_media,
            output_dir=organized_output_dir,
            output_filename=safe_title,
            target_format=target_format,
            bitrate=bitrate,
            sample_rate=sample_rate,
            normalize_audio=normalize_audio,
            resolution=resolution,
            use_nvenc=active_gpu,
            use_gpu=active_gpu,
            metadata=metadata,
            cover_path=cover_path if save_cover_art else None,
            abort_event=abort_event,
            progress_callback=report
        )

        report(1.0, f"Ready! File exported to: {os.path.basename(result_path)}")
        print("\n" + "=" * 60)
        print(f"DONE! Exported: {os.path.abspath(result_path)}")
        print("=" * 60)
        if save_metadata:
            manifest_path = os.path.join(metadata_dir, "manifest.json")
            try:
                with open(manifest_path, "w", encoding="utf-8") as manifest_file:
                    json.dump({
                        "media_path": os.path.abspath(result_path),
                        "metadata_dir": os.path.abspath(metadata_dir),
                        "source": source,
                        "source_type": stream_info.get("source_type", "other"),
                        "category": content_category or ("Music" if is_audio_target else "Videos"),
                        "title": title,
                    }, manifest_file, indent=2, ensure_ascii=False)
            except OSError as exc:
                print(f"[!] Could not write metadata manifest: {exc}")
        return result_path

    finally:
        if not keep_temp and os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

def process_playlist_conversion(
    playlist_title: str,
    selected_entries: list,
    output_dir: Optional[str] = None,
    target_format: str = "mp3",
    bitrate: str = "320k",
    sample_rate: int = 48000,
    normalize_audio: bool = False,
    resolution: str = "original",
    use_nvenc: bool = True,
    use_gpu: Optional[bool] = None,
    save_cover_art: bool = True,
    save_metadata: bool = True,
    keep_temp: bool = False,
    check_updates: bool = False,
    source_type: Optional[str] = None,
    abort_event: Optional[Any] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    content_category: Optional[str] = None,
    auth_browser: Optional[str] = None
) -> Dict[str, Any]:
    """
    Batch-downloads and transcodes selected playlist items into a dedicated playlist folder.
    Embeds cover art, writes credits files, and names output files strictly by playlist order.
    """
    if abort_event and abort_event.is_set():
        raise KeyboardInterrupt("Playlist conversion aborted by user.")

    if check_updates:
        engine_info = check_for_engine_updates()
        if engine_info.get("has_update"):
            print(
                f"[Update] Extractor engine update available: "
                f"v{engine_info.get('current_version')} -> v{engine_info.get('latest_version')}."
            )

    if not output_dir:
        output_dir = DEFAULT_CONVERTED_DIR
    ensure_free_disk_space(output_dir)

    active_gpu = use_gpu if use_gpu is not None else use_nvenc

    source_type = source_type or playlist_source_type(selected_entries)
    organized_output_dir = media_library_folder(output_dir, target_format, source_type, content_category)
    safe_folder = sanitize_filename(playlist_title) or "Playlist_Media"
    playlist_dir = _unique_directory_path(organized_output_dir, safe_folder)
    metadata_dir = os.path.join(playlist_dir, "metadata")
    os.makedirs(playlist_dir, exist_ok=True)
    os.makedirs(DEFAULT_TEMP_DIR, exist_ok=True)
    if save_metadata or save_cover_art:
        os.makedirs(metadata_dir, exist_ok=True)

    target_format = target_format.lower().strip(".")
    is_audio_target = target_format in SUPPORTED_AUDIO_FORMATS

    total_items = len(selected_entries)
    if total_items == 0:
        raise ValueError("No playlist items selected for conversion.")

    last_report = [0.0, 0.0]

    def report_overall(frac: float, msg: str):
        frac = max(last_report[1], max(0.0, min(1.0, float(frac))))
        now = time.monotonic()
        if frac >= 1.0 or now - last_report[0] >= 0.15 or int(frac * 100) != int(last_report[1] * 100):
            last_report[:] = [now, frac]
            if progress_callback:
                progress_callback(frac, msg)
            print(f"[{int(frac * 100)}%] {msg}")

    enc_info = get_best_hardware_encoder()
    gpu_desc = f"{enc_info['short_name']} ({enc_info['encoder_label']})" if active_gpu and enc_info["has_gpu"] else "CPU Multi-Core"

    print("=" * 60)
    print("[*] JANECONVERTER PLAYLIST BATCH PIPELINE")
    print(f"Playlist: {playlist_title}")
    print(f"Selected Items: {total_items}")
    print(f"Target Directory: {playlist_dir}")
    print(f"Format: {target_format.upper()} | Bitrate: {bitrate}")
    print(f"Hardware Acceleration: {active_gpu} [{gpu_desc}]")
    print(f"Cover Art: {save_cover_art} | Metadata: {save_metadata}")
    print("=" * 60)

    # Pre-fetch album / playlist cover art if available
    playlist_cover_dest = os.path.join(metadata_dir, "cover.jpg")
    if save_cover_art and not os.path.exists(playlist_cover_dest):
        first_thumb = next((e.get("thumbnail") for e in selected_entries if e.get("thumbnail")), None)
        if first_thumb:
            download_and_convert_thumbnail(first_thumb, playlist_cover_dest)

    converted_files = []
    failed_files = []
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    for i, entry in enumerate(selected_entries):
        if abort_event and abort_event.is_set():
            raise KeyboardInterrupt("Playlist conversion aborted by user.")

        idx = entry.get("index", i + 1)
        raw_title = entry.get("title", f"Track_{idx}")
        artist = entry.get("artist", "")
        item_url = entry.get("url", "")

        # Clean any preexisting numeric prefixes to guarantee clean '1. Song1' format
        clean_title = re.sub(r'^\d+[\.\s\-_]+\s*', '', sanitize_filename(raw_title)).strip()
        if not clean_title:
            clean_title = sanitize_filename(raw_title)

        ordered_filename = f"{idx}. {clean_title}"
        base_pct = i / total_items
        slice_pct = 1.0 / total_items

        def item_progress_hook(sub_frac: float, sub_msg: str):
            if abort_event and abort_event.is_set():
                raise KeyboardInterrupt("Playlist conversion aborted by user.")
            scaled_pct = max(base_pct, base_pct + (sub_frac * slice_pct))
            report_overall(scaled_pct, f"[{i+1}/{total_items}] #{idx}: {clean_title} ({int(sub_frac * 100)}%)")

        report_overall(base_pct, f"[{i+1}/{total_items}] Fetching #{idx}: {clean_title}...")

        track_job_id = uuid.uuid4().hex[:8]
        track_work_dir = os.path.join(DEFAULT_TEMP_DIR, f"track_{track_job_id}")
        os.makedirs(track_work_dir, exist_ok=True)

        try:
            stream_info = fetch_media_stream(
                source=item_url,
                output_dir=track_work_dir,
                audio_only=is_audio_target,
                fallback_title=raw_title,
                fallback_artist=artist,
                abort_event=abort_event,
                progress_callback=item_progress_hook,
                auth_browser=auth_browser
            )

            input_media = stream_info["media_path"]
            track_artist = artist or stream_info.get("artist", "")
            track_cover = stream_info.get("thumbnail_path") or (playlist_cover_dest if os.path.exists(playlist_cover_dest) else None)

            # Save per-track cover image into metadata folder if desired
            if save_cover_art and stream_info.get("thumbnail_path"):
                track_jpg = os.path.join(metadata_dir, f"{ordered_filename}.jpg")
                try:
                    shutil.copy2(stream_info["thumbnail_path"], track_jpg)
                except Exception:
                    pass
                if not os.path.exists(playlist_cover_dest):
                    try:
                        shutil.copy2(stream_info["thumbnail_path"], playlist_cover_dest)
                    except Exception:
                        pass

            # Save per-track credits / description into metadata folder if available
            if save_metadata and stream_info.get("description"):
                track_credits = os.path.join(metadata_dir, f"{ordered_filename}_credits.txt")
                try:
                    write_credits_file(track_credits, stream_info)
                except Exception:
                    pass

            metadata = {
                "title": clean_title,
                "artist": track_artist,
                "album": playlist_title,
                "track": f"{idx}"
            }
            if stream_info.get("year"):
                metadata["date"] = stream_info["year"]
            if stream_info.get("description"):
                metadata["comment"] = stream_info["description"][:1000]

            result_path = convert_media(
                input_path=input_media,
                output_dir=playlist_dir,
                output_filename=ordered_filename,
                target_format=target_format,
                bitrate=bitrate,
                sample_rate=sample_rate,
                normalize_audio=normalize_audio,
                resolution=resolution,
                use_nvenc=active_gpu,
                use_gpu=active_gpu,
                metadata=metadata,
                cover_path=track_cover if save_cover_art else None,
                abort_event=abort_event,
                progress_callback=item_progress_hook
            )

            converted_files.append(result_path)
            consecutive_failures = 0
            print(f"[+] Converted: {os.path.basename(result_path)}")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            if abort_event and abort_event.is_set():
                raise KeyboardInterrupt("Playlist conversion aborted by user.")
            failed_files.append({"index": idx, "title": raw_title, "error": str(e)})
            consecutive_failures += 1
            print(f"[!] Error converting track #{idx} '{raw_title}': {e}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                remaining = total_items - (i + 1)
                print(
                    f"[!] {MAX_CONSECUTIVE_FAILURES} tracks failed in a row - aborting batch "
                    f"({remaining} remaining tracks skipped). The network connection or source "
                    "service appears unavailable."
                )
                break
        finally:
            if not keep_temp and os.path.exists(track_work_dir):
                try:
                    shutil.rmtree(track_work_dir, ignore_errors=True)
                except Exception:
                    pass

    # Save overall playlist credits index inside metadata folder
    if save_metadata:
        summary_credits_path = os.path.join(metadata_dir, "playlist_credits.txt")
        try:
            pl_lines = [
                "=" * 80,
                f"PLAYLIST: {playlist_title}",
                "=" * 80,
                f"Total Tracks Converted: {len(converted_files)} / {total_items}",
                f"Format: {target_format.upper()} | Bitrate: {bitrate}",
                "-" * 80,
                "TRACK LISTING:",
                "-" * 80
            ]
            for e in selected_entries:
                idx = e.get("index", "?")
                t_tit = e.get("title", "Track")
                t_art = e.get("artist", "")
                t_dur = e.get("duration_str", "")
                pl_lines.append(f"{idx}. {t_tit} - {t_art} ({t_dur})")
            pl_lines.extend(["=" * 80, ""])
            with open(summary_credits_path, "w", encoding="utf-8") as f:
                f.write("\n".join(pl_lines))
            print(f"[+] Exported playlist summary: {os.path.basename(summary_credits_path)}")
        except Exception:
            pass

    if save_metadata:
        try:
            with open(os.path.join(metadata_dir, "manifest.json"), "w", encoding="utf-8") as manifest_file:
                json.dump({
                    "playlist_title": playlist_title,
                    "source_type": source_type,
                    "category": content_category or ("Music" if is_audio_target else "Videos"),
                    "playlist_dir": os.path.abspath(playlist_dir),
                    "metadata_dir": os.path.abspath(metadata_dir),
                    "total_selected": total_items,
                    "converted_files": [os.path.abspath(p) for p in converted_files],
                    "failed_files": failed_files,
                }, manifest_file, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"[!] Could not write playlist manifest: {exc}")

    report_overall(1.0, f"Completed playlist! {len(converted_files)}/{total_items} tracks converted.")
    print("=" * 60)
    print(f"PLAYLIST SUMMARY: {len(converted_files)} succeeded, {len(failed_files)} failed.")
    print(f"Export Directory: {playlist_dir}")
    print("=" * 60)

    return {
        "playlist_dir": playlist_dir,
        "metadata_dir": metadata_dir,
        "total_selected": total_items,
        "successful_count": len(converted_files),
        "failed_count": len(failed_files),
        "converted_files": converted_files,
        "failed_files": failed_files
    }

CLI_FORMATS = sorted(SUPPORTED_AUDIO_FORMATS | SUPPORTED_VIDEO_FORMATS)
CLI_BITRATES = {"320k", "256k", "192k", "128k"}
CLI_BIT_DEPTHS = {"16-bit", "24-bit", "32-bit", "32-bit float"}
CLI_OGG_QUALITIES = {"q10", "q8", "q6", "q4"}
CLI_VIDEO_QUALITIES = {"best", "high", "balanced", "small"}
CLI_SAMPLE_RATES = {44100, 48000, 96000}
CLI_RESOLUTIONS = {"original", "4k", "1440p", "1080p", "720p", "480p"}

def parse_playlist_indexes(value: str, total: int, parser: argparse.ArgumentParser):
    """Parse a 1-based, comma-separated playlist selection safely."""
    indexes = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            index = int(item)
        except ValueError:
            parser.error("--playlist-indexes must contain comma-separated numbers.")
        if index < 1 or index > total:
            parser.error(f"Playlist item {index} is outside the available range 1-{total}.")
        if index not in indexes:
            indexes.append(index)
    if not indexes:
        parser.error("--playlist-indexes must select at least one playlist item.")
    return indexes

def validate_cli_args(args, parser: argparse.ArgumentParser):
    """Validates CLI argument combinations, exiting with a clear message on invalid input."""
    fmt = args.format.lower().strip(".")
    if fmt not in SUPPORTED_AUDIO_FORMATS and fmt not in SUPPORTED_VIDEO_FORMATS:
        parser.error(f"Unsupported format '{args.format}'. Choose from: {', '.join(CLI_FORMATS)}")

    bitrate = args.bitrate.lower().strip()
    if fmt in SUPPORTED_VIDEO_FORMATS:
        if bitrate == "320k":
            # Preserve the audio-oriented CLI default while making a bare
            # ``--format mp4`` invocation choose a sensible video preset.
            bitrate = "balanced"
        if bitrate not in CLI_VIDEO_QUALITIES:
            parser.error(
                f"Invalid video quality '{args.bitrate}'. Choose from: {', '.join(sorted(CLI_VIDEO_QUALITIES))}"
            )
    elif fmt in ("wav", "flac"):
        if bitrate not in CLI_BIT_DEPTHS:
            parser.error(f"Invalid bit depth '{args.bitrate}' for {fmt}. Choose from: {', '.join(sorted(CLI_BIT_DEPTHS))}")
    elif fmt == "ogg":
        if bitrate not in CLI_OGG_QUALITIES and bitrate not in CLI_BITRATES:
            parser.error(
                f"Invalid quality '{args.bitrate}' for ogg. Choose from: {', '.join(sorted(CLI_OGG_QUALITIES))}"
            )
    else:
        if bitrate not in CLI_BITRATES:
            parser.error(f"Invalid bitrate '{args.bitrate}'. Choose from: {', '.join(sorted(CLI_BITRATES))}")

    if args.sample_rate not in CLI_SAMPLE_RATES:
        parser.error(f"Invalid sample rate {args.sample_rate}. Choose from: {', '.join(str(r) for r in sorted(CLI_SAMPLE_RATES))}")

    if args.resolution not in CLI_RESOLUTIONS:
        parser.error(f"Invalid resolution '{args.resolution}'. Choose from: {', '.join(sorted(CLI_RESOLUTIONS))}")

    if args.playlist and not is_url(args.source):
        parser.error("--playlist requires a URL; a local file path cannot be a playlist.")

    return fmt, bitrate

def main():
    parser = argparse.ArgumentParser(description="JaneConverter: Universal Media Downloader & Converter")
    parser.add_argument("--source", "-s", required=True, help="Media URL (YouTube, Spotify, SoundCloud, TikTok, Twitter, etc.) or local file path")
    parser.add_argument("--format", "-f", default="mp3", help=f"Target output format ({', '.join(CLI_FORMATS)})")
    parser.add_argument("--output", "-o", default=DEFAULT_CONVERTED_DIR, help="Destination directory for converted files")
    parser.add_argument("--bitrate", "-b", default="320k", help="Audio bitrate, lossless bit depth, OGG quality, or video quality (best, high, balanced, small)")
    parser.add_argument("--sample-rate", "-r", type=int, default=48000, help="Audio sample rate in Hz (44100, 48000, 96000)")
    parser.add_argument("--normalize", "-n", action="store_true", help="Apply EBU R128 loudness normalization")
    parser.add_argument("--resolution", default="original", help="Video resolution (original, 4k, 1440p, 1080p, 720p, 480p)")
    parser.add_argument("--no-gpu", action="store_true", help="Disable hardware GPU acceleration (use multi-core CPU libx264)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep intermediate downloaded stream files in temp directory")
    parser.add_argument("--playlist", "-p", action="store_true", help="Force treat input source as playlist")
    parser.add_argument("--list-playlist", action="store_true", help="List playlist entries for a graphical frontend and exit")
    parser.add_argument("--playlist-indexes", help="Convert only selected 1-based playlist items, e.g. 1,3,5")
    parser.add_argument("--no-cover-art", action="store_true", help="Disable downloading and embedding cover art")
    parser.add_argument("--no-metadata", action="store_true", help="Disable exporting credits and metadata text files")
    parser.add_argument("--category", choices=("Music", "Video", "Miscellaneous"), default=None,
                        help="Library category. Miscellaneous stores media under Audio or Videos.")
    parser.add_argument(
        "--browser-session",
        choices=("none", "chrome", "edge", "firefox", "brave", "vivaldi", "opera", "chromium", "safari"),
        default="none",
        help="Use an existing logged-in browser session for authorized content; no password or cookie file is stored.",
    )
    parser.add_argument("--no-update", action="store_true", help="Skip the read-only yt-dlp update availability check on startup")
    parser.add_argument("--version", action="version", version=f"JaneConverter {__version__}")

    args = parser.parse_args()
    args.format, args.bitrate = validate_cli_args(args, parser)

    if args.list_playlist and not is_url(args.source):
        parser.error("--list-playlist requires a URL.")

    if not args.no_update:
        engine_info = check_for_engine_updates()
        if engine_info.get("has_update"):
            print(
                f"[AutoUpdate] Extractor engine update available: "
                f"v{engine_info.get('current_version')} -> v{engine_info.get('latest_version')}."
            )

    save_cover = not args.no_cover_art
    save_meta = not args.no_metadata
    use_gpu = not args.no_gpu

    if args.list_playlist:
        args.browser_session = normalize_browser_session(args.browser_session)
        pdata = fetch_playlist_entries(args.source, auth_browser=args.browser_session)
        def clean_field(value):
            return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
        print(f"PLAYLIST\t{clean_field(pdata.get('playlist_title'))}")
        for entry in pdata.get("entries", []):
            print("ENTRY\t{}\t{}\t{}\t{}\t{}".format(
                entry.get("index", 0),
                clean_field(entry.get("title")),
                clean_field(entry.get("artist")),
                entry.get("duration_str", ""),
                clean_field(entry.get("url")),
            ))
        return

    if args.playlist or is_playlist_url(args.source):
        print("[*] Detected playlist source. Fetching items...")
        args.browser_session = normalize_browser_session(args.browser_session)
        pdata = fetch_playlist_entries(args.source, auth_browser=args.browser_session)
        selected_entries = pdata["entries"]
        if args.playlist_indexes:
            selected_indexes = parse_playlist_indexes(args.playlist_indexes, len(selected_entries), parser)
            selected_entries = [entry for entry in selected_entries if entry.get("index") in selected_indexes]
        print(f"[*] Found {len(pdata['entries'])} tracks in '{pdata['playlist_title']}'. Converting {len(selected_entries)}...")
        summary = process_playlist_conversion(
            playlist_title=pdata["playlist_title"],
            selected_entries=selected_entries,
            output_dir=args.output,
            target_format=args.format,
            bitrate=args.bitrate,
            sample_rate=args.sample_rate,
            normalize_audio=args.normalize,
            resolution=args.resolution,
            use_nvenc=use_gpu,
            use_gpu=use_gpu,
            save_cover_art=save_cover,
            save_metadata=save_meta,
            keep_temp=args.keep_temp,
            content_category=args.category,
            auth_browser=args.browser_session
        )
        failed = summary.get("failed_count", 0)
        if failed:
            print(f"[!] {failed} track(s) failed to convert.")
            sys.exit(1)
    else:
        args.browser_session = normalize_browser_session(args.browser_session)
        process_conversion(
            source=args.source,
            output_dir=args.output,
            target_format=args.format,
            bitrate=args.bitrate,
            sample_rate=args.sample_rate,
            normalize_audio=args.normalize,
            resolution=args.resolution,
            use_nvenc=use_gpu,
            use_gpu=use_gpu,
            save_cover_art=save_cover,
            save_metadata=save_meta,
            keep_temp=args.keep_temp,
            content_category=args.category,
            auth_browser=args.browser_session
        )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
        sys.exit(130)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"\n[!] Error: {e}")
        sys.exit(1)

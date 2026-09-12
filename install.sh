#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required. Install it with your operating system package manager." >&2
    exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "FFmpeg and ffprobe are required. Install FFmpeg with your operating system package manager." >&2
    exit 1
fi

python3 -m venv .venv
"$SCRIPT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$SCRIPT_DIR/.venv/bin/python" -m pip install -r requirements.txt

if command -v cargo >/dev/null 2>&1; then
    cargo build --release --manifest-path "$SCRIPT_DIR/native_ui/Cargo.toml"
    cp "$SCRIPT_DIR/native_ui/target/release/janeconverter-native" "$SCRIPT_DIR/JaneConverterNative"
    chmod +x "$SCRIPT_DIR/JaneConverterNative"
else
    echo "Rust/Cargo was not found; the legacy Python interface is still available." >&2
fi

echo "JaneConverter is installed. Start it with ./run_converter.sh"

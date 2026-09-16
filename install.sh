#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required. Install it with your operating system package manager." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Python 3.10 or newer is required. The detected python3 is too old." >&2
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
    if cargo build --release --manifest-path "$SCRIPT_DIR/native_ui/Cargo.toml"; then
        cp "$SCRIPT_DIR/native_ui/target/release/janeconverter-native" "$SCRIPT_DIR/JaneConverterNative"
        chmod +x "$SCRIPT_DIR/JaneConverterNative"
    else
        if [[ -e "$SCRIPT_DIR/JaneConverterNative" ]]; then
            mv "$SCRIPT_DIR/JaneConverterNative" "$SCRIPT_DIR/JaneConverterNative.stale"
            echo "Rust build failed; moved the old native frontend aside so it cannot be launched against newer source code." >&2
        else
            echo "Rust build failed; the legacy Python interface is still available." >&2
        fi
    fi
else
    if [[ -e "$SCRIPT_DIR/JaneConverterNative" ]]; then
        mv "$SCRIPT_DIR/JaneConverterNative" "$SCRIPT_DIR/JaneConverterNative.stale"
        echo "Rust/Cargo was not found; moved the old native frontend aside so it cannot be launched against newer source code." >&2
    else
        echo "Rust/Cargo was not found; the legacy Python interface is still available." >&2
    fi
fi

echo "JaneConverter is installed. Start it with ./run_converter.sh"

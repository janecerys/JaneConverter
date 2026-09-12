#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x "$SCRIPT_DIR/JaneConverterNative" ]]; then
    exec "$SCRIPT_DIR/JaneConverterNative" "$@"
fi

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/gui.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/gui.py" "$@"
fi

echo "JaneConverter needs Python 3.10 or newer. Run ./install.sh first." >&2
exit 1

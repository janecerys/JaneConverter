#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

PREFERENCE_FILE="$SCRIPT_DIR/frontend.preference"
if [[ -n "${JANECONVERTER_DATA_DIR:-}" ]] && [[ -f "${JANECONVERTER_DATA_DIR}/frontend.preference" ]]; then
    PREFERENCE_FILE="${JANECONVERTER_DATA_DIR}/frontend.preference"
fi
FRONTEND_PREFERENCE=""
if [[ -f "$PREFERENCE_FILE" ]]; then
    FRONTEND_PREFERENCE="$(tr -d '[:space:]' < "$PREFERENCE_FILE" | tr '[:upper:]' '[:lower:]')"
fi

if [[ "$FRONTEND_PREFERENCE" != "python" ]] && [[ -x "$SCRIPT_DIR/JaneConverterNative" ]]; then
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

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

echo "This removes JaneConverter's local environment, generated exports, logs, and saved settings."
read -r -p "Type REMOVE to continue: " confirmation
if [[ "$confirmation" != "REMOVE" ]]; then
    echo "Cancelled."
    exit 0
fi

for path in \
    "$SCRIPT_DIR/.venv" \
    "$SCRIPT_DIR/converted" \
    "$SCRIPT_DIR/temp" \
    "$SCRIPT_DIR/logs" \
    "$SCRIPT_DIR/updates"; do
    if [[ -e "$path" ]]; then
        rm -rf -- "$path"
    fi
done

for path in \
    "$SCRIPT_DIR/config.json" \
    "$SCRIPT_DIR/frontend.preference" \
    "$SCRIPT_DIR/native.settings" \
    "$SCRIPT_DIR/JaneConverterNative"; do
    if [[ -e "$path" ]]; then
        rm -f -- "$path"
    fi
done

echo "JaneConverter's local data was removed. Your source checkout and downloaded media elsewhere were left untouched."

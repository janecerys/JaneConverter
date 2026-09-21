#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FFMPEG_PATH=""
FFPROBE_PATH=""
NODE_PATH=""
OUTPUT_DIR="$REPO_ROOT/dist"
KEEP_STAGING=0
BUILD_ROOT=""

usage() {
  cat <<'EOF'
Usage: packaging/build_macos.sh [options]
  --ffmpeg PATH       native FFmpeg executable
  --ffprobe PATH      native FFprobe executable
  --node PATH         native Node.js executable
  --output-dir PATH   artifact directory (default: dist)
  --keep-staging      retain the intermediate payload
EOF
}

while (($#)); do
  case "$1" in
    --ffmpeg) FFMPEG_PATH="${2:?missing value for --ffmpeg}"; shift 2 ;;
    --ffprobe) FFPROBE_PATH="${2:?missing value for --ffprobe}"; shift 2 ;;
    --node) NODE_PATH="${2:?missing value for --node}"; shift 2 ;;
    --output-dir) OUTPUT_DIR="${2:?missing value for --output-dir}"; shift 2 ;;
    --keep-staging) KEEP_STAGING=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS release packages must be built natively on Darwin." >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "arm64" && "$ARCH" != "x86_64" ]]; then
  echo "Unsupported architecture: $ARCH. macOS releases support arm64 and x86_64." >&2
  exit 1
fi
if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" == "1" ]]; then
  echo "Rosetta-translated builds are not supported; run the build natively." >&2
  exit 1
fi

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required build tool not found: $1" >&2
    exit 1
  }
}

resolve_executable() {
  local explicit="$1" command_name="$2" description="$3" resolved directory
  if [[ -n "$explicit" ]]; then
    directory="$(cd -- "$(dirname -- "$explicit")" && pwd)"
    resolved="$directory/$(basename -- "$explicit")"
  else
    resolved="$(command -v "$command_name" || true)"
  fi
  if [[ -z "$resolved" || ! -f "$resolved" || ! -x "$resolved" ]]; then
    echo "$description was not found or is not executable. Pass its explicit path." >&2
    exit 1
  fi
  printf '%s\n' "$resolved"
}

assert_macho_arch() {
  local executable="$1" description="$2" architectures
  if ! file "$executable" | grep -q 'Mach-O'; then
    echo "$description is not a Mach-O executable: $executable" >&2
    exit 1
  fi
  architectures="$(lipo -archs "$executable")"
  if ! grep -qw "$ARCH" <<<"$architectures"; then
    echo "$description does not contain the native $ARCH architecture: $architectures" >&2
    exit 1
  fi
}

cleanup() {
  if ((KEEP_STAGING == 0)) && [[ -n "$BUILD_ROOT" && -d "$BUILD_ROOT" && "$BUILD_ROOT" == "$OUTPUT_DIR"/consumer-build-* ]]; then
    rm -rf -- "$BUILD_ROOT"
  fi
}
trap cleanup EXIT

for command_name in uv npm cargo codesign file find grep hdiutil install lipo shasum sysctl xattr; do
  require_command "$command_name"
done

FFMPEG_PATH="$(resolve_executable "$FFMPEG_PATH" ffmpeg FFmpeg)"
FFPROBE_PATH="$(resolve_executable "$FFPROBE_PATH" ffprobe FFprobe)"
NODE_PATH="$(resolve_executable "$NODE_PATH" node Node.js)"
assert_macho_arch "$FFMPEG_PATH" FFmpeg
assert_macho_arch "$FFPROBE_PATH" FFprobe
assert_macho_arch "$NODE_PATH" Node.js
cargo --version >/dev/null

cd -- "$REPO_ROOT"
uv sync --locked --python 3.12
uv run --locked pyinstaller --version >/dev/null
VERSION="$(uv run --locked python -c 'from janeconverter.version import __version__; print(__version__)' 2>/dev/null)"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine the version from src/janeconverter/version.py." >&2
  exit 1
fi

OUTPUT_DIR="$(mkdir -p -- "$OUTPUT_DIR" && cd -- "$OUTPUT_DIR" && pwd)"
BUILD_ROOT="$OUTPUT_DIR/consumer-build-$VERSION-macos-$ARCH"
STAGING_ROOT="$BUILD_ROOT/resources"
RUNTIME_ROOT="$STAGING_ROOT/runtime"
RUNTIME_ENGINE="$RUNTIME_ROOT/engine"
RUNTIME_BIN="$RUNTIME_ROOT/bin"
PYINSTALLER_ROOT="$BUILD_ROOT/pyinstaller"
TAURI_TARGET="$BUILD_ROOT/tauri-target"
ARTIFACT="$OUTPUT_DIR/JaneConverter-$VERSION-macos-$ARCH.dmg"

rm -rf -- "$BUILD_ROOT"
rm -f -- "$ARTIFACT" "$ARTIFACT.sha256"
mkdir -p -- "$RUNTIME_ENGINE" "$RUNTIME_BIN" "$PYINSTALLER_ROOT/spec"

echo "Building the frozen engine (onedir)..."
uv run --locked pyinstaller --noconfirm --clean --onedir --contents-directory _internal \
  --name JaneConverterEngine \
  --paths "$REPO_ROOT/src" \
  --distpath "$PYINSTALLER_ROOT/dist" \
  --workpath "$PYINSTALLER_ROOT/work" \
  --specpath "$PYINSTALLER_ROOT/spec" \
  "$REPO_ROOT/packaging/engine_entry.py"

BUILT_ENGINE="$PYINSTALLER_ROOT/dist/JaneConverterEngine"
[[ -x "$BUILT_ENGINE/JaneConverterEngine" ]] || {
  echo "PyInstaller did not produce the expected onedir engine." >&2
  exit 1
}
cp -a -- "$BUILT_ENGINE/." "$RUNTIME_ENGINE/"
install -m 0755 -- "$FFMPEG_PATH" "$RUNTIME_BIN/ffmpeg"
install -m 0755 -- "$FFPROBE_PATH" "$RUNTIME_BIN/ffprobe"
install -m 0755 -- "$NODE_PATH" "$RUNTIME_BIN/node"
install -m 0644 -- "$REPO_ROOT/LICENSE" "$STAGING_ROOT/LICENSE"
xattr -dr com.apple.quarantine "$STAGING_ROOT" 2>/dev/null || true

if find "$RUNTIME_ROOT" -type f \( \
  -name 'JaneConverterPython*' -o -name 'JaneConverterNative*' -o \
  -name 'Program.cs' -o -name '*.py' -o -name 'pip' -o -name 'npm' -o \
  -name 'cargo' -o -name 'rustc' \) -print -quit | grep -q .; then
  echo "Private runtime contains a forbidden source or build-tool file." >&2
  exit 1
fi

echo "Validating and ad-hoc signing the private runtime..."
while IFS= read -r -d '' candidate; do
  if file "$candidate" | grep -q 'Mach-O'; then
    assert_macho_arch "$candidate" "Staged Mach-O file"
    codesign --force --sign - --timestamp=none "$candidate"
    codesign --verify --strict "$candidate"
  fi
done < <(find "$RUNTIME_ROOT" -type f -print0)

"$RUNTIME_ENGINE/JaneConverterEngine" --version >/dev/null
"$RUNTIME_BIN/ffmpeg" -version >/dev/null
"$RUNTIME_BIN/ffprobe" -version >/dev/null
"$RUNTIME_BIN/node" --version >/dev/null

TAURI_CONFIG="$BUILD_ROOT/tauri.release.json"
export JANECONVERTER_RELEASE_VERSION="$VERSION"
export JANECONVERTER_RUNTIME_ROOT="$RUNTIME_ROOT"
export JANECONVERTER_STAGED_LICENSE="$STAGING_ROOT/LICENSE"
export JANECONVERTER_TAURI_CONFIG="$TAURI_CONFIG"
uv run --locked python - <<'PY'
import json
import os
from pathlib import Path

source = Path("desktop-ui/src-tauri/tauri.conf.json")
config = json.loads(source.read_text(encoding="utf-8"))
config["productName"] = "JaneConverter"
config["version"] = os.environ["JANECONVERTER_RELEASE_VERSION"]
config["build"]["beforeBuildCommand"] = ""
config["bundle"]["active"] = True
# Keep the app bundle so it can be verified after Tauri creates the DMG.
config["bundle"]["targets"] = ["app", "dmg"]
config["bundle"]["resources"] = {
    os.environ["JANECONVERTER_RUNTIME_ROOT"]: "runtime",
    os.environ["JANECONVERTER_STAGED_LICENSE"]: "LICENSE",
}
config["bundle"].setdefault("macOS", {})["signingIdentity"] = "-"
Path(os.environ["JANECONVERTER_TAURI_CONFIG"]).write_text(
    json.dumps(config, indent=2) + "\n", encoding="utf-8"
)
PY

echo "Building the production Tauri app and DMG..."
export CARGO_TARGET_DIR="$TAURI_TARGET"
export npm_config_cache="$BUILD_ROOT/npm-cache"
(
  cd -- "$REPO_ROOT/desktop-ui"
  npm ci --no-audit --no-fund --ignore-scripts
  npm run build
  ./node_modules/.bin/tauri build --config "$TAURI_CONFIG"
)

BUNDLED_APP="$TAURI_TARGET/release/bundle/macos/JaneConverter.app"
[[ -d "$BUNDLED_APP" ]] || {
  echo "Tauri did not produce the expected macOS app bundle." >&2
  exit 1
}
codesign --verify --deep --strict --verbose=2 "$BUNDLED_APP"
BUNDLED_UI="$BUNDLED_APP/Contents/MacOS/janeconverter-desktop"
[[ -x "$BUNDLED_UI" ]] || {
  echo "The app bundle does not contain the expected desktop executable." >&2
  exit 1
}
assert_macho_arch "$BUNDLED_UI" "Bundled desktop executable"
BUNDLED_RUNTIME="$BUNDLED_APP/Contents/Resources/runtime"
[[ -x "$BUNDLED_RUNTIME/engine/JaneConverterEngine" ]] || {
  echo "The app bundle does not contain the staged engine." >&2
  exit 1
}
assert_macho_arch "$BUNDLED_RUNTIME/engine/JaneConverterEngine" "Bundled engine"
"$BUNDLED_RUNTIME/engine/JaneConverterEngine" --version >/dev/null
"$BUNDLED_RUNTIME/bin/ffmpeg" -version >/dev/null
"$BUNDLED_RUNTIME/bin/ffprobe" -version >/dev/null
"$BUNDLED_RUNTIME/bin/node" --version >/dev/null

DMG_DIRECTORY="$TAURI_TARGET/release/bundle/dmg"
DMG_COUNT="$(find "$DMG_DIRECTORY" -type f -name '*.dmg' | wc -l | tr -d ' ')"
if [[ "$DMG_COUNT" != "1" ]]; then
  echo "Expected exactly one Tauri DMG, found $DMG_COUNT." >&2
  exit 1
fi
BUILT_DMG="$(find "$DMG_DIRECTORY" -type f -name '*.dmg' -print -quit)"
cp -p -- "$BUILT_DMG" "$ARTIFACT"
(
  cd -- "$OUTPUT_DIR"
  shasum -a 256 "$(basename -- "$ARTIFACT")" >"$(basename -- "$ARTIFACT").sha256"
)
echo "Created $ARTIFACT"

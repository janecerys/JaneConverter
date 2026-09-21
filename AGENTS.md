# AGENTS.md

Guidance for agents and contributors working in this repository.

## Project

JaneConverter is a universal media downloader and converter with a Tauri desktop app and a Python CLI. It downloads and converts media through a React/TypeScript frontend, a Rust native bridge, and a Python conversion engine.

## Repository layout

- `src/janeconverter/` - Python conversion engine package
- `tests/` - Python test suite
- `desktop-ui/` - Tauri 2 + React + TypeScript desktop app (`src-tauri/` holds the Rust bridge)
- `browser-extension/` - optional Browser Bridge (not bundled in production packages)
- `packaging/` - release build scripts and packaging contracts
- `.github/workflows/` - CI and release pipelines

## Toolchains and runtimes

- Python backend uses `uv`. The pinned local interpreter is Python 3.12 (`.python-version`). The package declares `requires-python = ">=3.10"`, so CI verifies both 3.10 and 3.12.
- Rust uses the latest stable toolchain. Do not pin an older toolchain or add a `rust-toolchain` file.
- Node.js 22 and npm for the frontend.
- Run Python through `uv` only (`uv run`, `uv sync`). Do not invoke bare `python`, `python3`, or `pip`.

## Commands

Setup:

```bash
uv sync --locked
cd desktop-ui && npm ci
```

Python tests (hermetic by default; online tests need `-m online`):

```bash
uv run --locked pytest tests/ -v
```

Python lint:

```bash
uv run --locked pyflakes src/janeconverter packaging/engine_entry.py
```

Desktop UI:

```bash
cd desktop-ui
npm test -- --run
npm run build
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo test --manifest-path src-tauri/Cargo.toml
```

## Conventions

- Keep build and packaging scripts under `packaging/`. Do not add build scripts to the repository root.
- Keep the layout organized: engine code in `src/janeconverter/`, frontend in `desktop-ui/`, extension in `browser-extension/`, packaging in `packaging/`.
- The version is a single source in `src/janeconverter/version.py`. Bump it there; release tags must match `v<version>`.
- Keep files focused and small. Prefer 4-space indentation for Python and Rust, 2-space for JSON/TOML/YAML configuration.
- Do not modify unrelated code or add features beyond the current request.

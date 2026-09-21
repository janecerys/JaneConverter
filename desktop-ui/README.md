# JaneConverter Desktop UI

This is the supported desktop application for JaneConverter.

## Stack

- Tauri 2
- React and TypeScript
- Tailwind CSS
- Framer Motion
- Rust native bridge

The UI is a static frontend compiled into the Tauri executable. Node.js builds the frontend and is bundled privately for the conversion engine's JavaScript challenges, so end users do not install it separately.

## Local development

From this directory, run `npm ci` and `npm run dev` for a browser-only frontend preview.

For the native shell, run `uv sync` at the repository root, then `npm run tauri:dev`. The project also requires uv, Python 3.10+, FFmpeg/FFprobe, Rust/Cargo, and the Tauri 2 platform prerequisites.

The Rust backend expects the JaneConverter uv project root two levels above `src-tauri`. In source mode it runs `uv run --locked janeconverter`; packaged builds invoke the private frozen engine directly. Source mode uses project-local converted, temporary, and settings paths by default.

## Verification

Run `npm test` and `npm run build`. Run backend tests from the repository root with `uv run pytest`.

The backend can be tested with `cargo test --manifest-path src-tauri/Cargo.toml`.

Production Windows and Linux artifacts are built by the platform-specific scripts under `packaging/`. They expose one Tauri executable and keep the frozen Python conversion engine private.

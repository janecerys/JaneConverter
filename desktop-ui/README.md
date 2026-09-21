# JaneConverter Desktop UI

This is the supported desktop application for JaneConverter.

## Stack

- Tauri 2
- React and TypeScript
- Tailwind CSS
- Framer Motion
- Rust native bridge

The UI is a static frontend compiled into the Tauri executable. Node.js is only needed to develop or build it; end users do not need a Node runtime to launch the packaged desktop executable.

## Local development

From this directory, run `npm ci` and `npm run dev` for a browser-only frontend preview.

For the native shell, run `npm run tauri:dev`. The project also requires Python 3.10+, the root Python dependencies, FFmpeg/FFprobe, Rust/Cargo, and the Tauri 2 platform prerequisites.

The Rust backend expects the JaneConverter project root two levels above `src-tauri`. It calls the existing `run_converter.py` pipeline and uses project-local converted, temporary, and settings paths by default.

## Verification

Run `npm test` and `npm run build`.

The backend can be tested with `cargo test --manifest-path src-tauri/Cargo.toml`.

Production Windows and Linux artifacts are built by the platform-specific scripts under `packaging/`. They expose one Tauri executable and keep the frozen Python conversion engine private.

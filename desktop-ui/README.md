# JaneConverter Desktop UI

This is the new native desktop surface for JaneConverter.

## Stack

- Tauri 2
- React and TypeScript
- Tailwind CSS
- Framer Motion
- Rust native bridge

The UI is a static frontend compiled into the Tauri executable. Node.js is only needed to develop or build it; end users do not need a Node runtime to launch the packaged desktop executable.

## Local development

From this directory, run npm install and npm run dev.

For the native shell, run npm run tauri:dev.

The Rust backend expects the JaneConverter project root two levels above src-tauri. It calls the existing run_converter.py pipeline and uses project-local converted, temp, settings, and update paths by default.

## Verification

Run npm test and npm run build.

The backend can be tested with a project-local Rust toolchain using cargo test --manifest-path src-tauri/Cargo.toml.

The root build_release.ps1 stages the universal launcher as JaneConverter.exe plus JaneConverterDesktop.exe and JaneConverterNative.exe. JaneConverter.exe reads the saved preference and starts the selected interface; --tauri, --rust, and --legacy-python remain available for diagnostics.

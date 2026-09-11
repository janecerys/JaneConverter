param(
    [string]$Version = "",
    [switch]$AllowPythonFallback
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir
if (-not $Version) {
    $Version = [regex]::Match((Get-Content -Raw "engine\version.py"), '__version__\s*=\s*"([^"]+)"').Groups[1].Value
}
if (-not $Version) { throw "Could not determine application version." }

$staging = Join-Path $scriptDir "dist\JaneConverter-$Version"
$archive = Join-Path $scriptDir "dist\JaneConverter-$Version-windows.zip"
if (Test-Path $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null

$files = @(
    "gui.py", "run_converter.py", "Program.cs", "setup.bat", "install.bat",
    "install.ps1", "uninstall.ps1", "build_release.ps1", "update_helper.py", "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE"
)
foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $scriptDir $file) -Destination (Join-Path $staging $file)
}
Copy-Item -LiteralPath (Join-Path $scriptDir "engine") -Destination (Join-Path $staging "engine") -Recurse
Copy-Item -LiteralPath (Join-Path $scriptDir "assets") -Destination (Join-Path $staging "assets") -Recurse

# Never ship generated development state. Stale bytecode can mask source
# changes and cache files make the portable artifact less reproducible.
Get-ChildItem -LiteralPath $staging -Recurse -Force -Directory |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".venv", "venv", "temp", "converted") } |
    Sort-Object FullName -Descending |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Get-ChildItem -LiteralPath $staging -Recurse -Force -File |
    Where-Object { $_.Extension -in @(".pyc", ".pyo", ".log") } |
    Remove-Item -Force

# Build and package the native Rust frontend when the Rust toolchain is
# available. The launcher retains the Python GUI as a recovery fallback for
# source checkouts and environments that cannot build the native binary.
$nativeBinary = Join-Path $scriptDir "native_ui\target\release\janeconverter-native.exe"
$cargo = Get-Command cargo.exe -ErrorAction SilentlyContinue
if ($cargo) {
    # Keep Cargo's generated files out of the source checkout. This also
    # allows release builds from protected or read-only source locations.
    $cargoTarget = Join-Path $scriptDir "dist\cargo-target-$Version"
    $env:CARGO_TARGET_DIR = $cargoTarget
    & $cargo.Source build --release --manifest-path (Join-Path $scriptDir "native_ui\Cargo.toml")
    if ($LASTEXITCODE -ne 0) { throw "Native Rust frontend build failed." }
    $nativeBinary = Join-Path $cargoTarget "release\janeconverter-native.exe"
} elseif (Test-Path -LiteralPath $nativeBinary) {
    $nativeBinaryInfo = Get-Item -LiteralPath $nativeBinary
    $nativeSourceFiles = @(
        (Get-ChildItem -LiteralPath (Join-Path $scriptDir "native_ui\src") -Recurse -File |
            Where-Object { $_.Extension -eq ".rs" })
        (Get-Item -LiteralPath (Join-Path $scriptDir "native_ui\Cargo.toml"))
        (Get-Item -LiteralPath (Join-Path $scriptDir "native_ui\Cargo.lock"))
    )
    $latestNativeSource = $nativeSourceFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestNativeSource -and $latestNativeSource.LastWriteTimeUtc -gt $nativeBinaryInfo.LastWriteTimeUtc) {
        throw "The Rust frontend binary is older than its source. Install Rust or pass -AllowPythonFallback for a development-only package."
    }
}
if (Test-Path -LiteralPath $nativeBinary) {
    Copy-Item -LiteralPath $nativeBinary -Destination (Join-Path $staging "JaneConverterNative.exe")
    if ($cargo -and (Test-Path -LiteralPath (Join-Path $scriptDir "dist\cargo-target-$Version"))) {
        Remove-Item -LiteralPath (Join-Path $scriptDir "dist\cargo-target-$Version") -Recurse -Force
    }
} elseif (-not $AllowPythonFallback) {
    throw "The Rust frontend was not built. Install Rust or pass -AllowPythonFallback for a development-only package."
}

$candidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($csc) {
    & $csc /target:winexe /win32icon:"$staging\assets\icon.ico" /out:"$staging\JaneConverter.exe" "$staging\Program.cs" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Native launcher compilation failed." }
}

$requiredFiles = @("JaneConverter.exe", "gui.py", "run_converter.py", "update_helper.py", "requirements.txt", "README.md", "LICENSE", "assets\icon.ico", "engine\version.py")
if (-not $AllowPythonFallback) { $requiredFiles += "JaneConverterNative.exe" }
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $staging $requiredFile) -PathType Leaf)) {
        throw "Release package is missing required file: $requiredFile"
    }
}
if (Get-ChildItem -LiteralPath $staging -Recurse -Force -File |
    Where-Object { $_.Extension -in @(".pyc", ".pyo", ".log") }) {
    throw "Release package contains generated cache or log files."
}

Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $archive -CompressionLevel Optimal
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$archive.sha256" -Value "$hash  $(Split-Path $archive -Leaf)" -Encoding ascii
Write-Host "Created $archive"
Write-Host "SHA256: $hash"

param(
    [string]$Version = "",
    [switch]$SkipPortable,
    [switch]$KeepStaging
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent $scriptDir
$scriptDir = $repoRoot
Set-Location $scriptDir

if (-not $Version) {
    $Version = [regex]::Match(
        (Get-Content -Raw "engine\version.py"),
        '__version__\s*=\s*"([^"]+)"'
    ).Groups[1].Value
}
if (-not $Version) { throw "Could not determine application version." }

$buildRoot = Join-Path $scriptDir "dist\consumer-build-$Version"
$runtimeRoot = Join-Path $buildRoot "runtime"
$pyinstallerRoot = Join-Path $buildRoot "pyinstaller"
$outputInstaller = Join-Path $scriptDir "dist\JaneConverter-Setup.exe"
$hookPath = Join-Path $scriptDir "packaging\windows\installer-hooks.nsh"
$manifestPath = Join-Path $scriptDir "packaging\consumer-manifest.json"

if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
if (Test-Path -LiteralPath $outputInstaller) { Remove-Item -LiteralPath $outputInstaller -Force }
New-Item -ItemType Directory -Path $runtimeRoot,$pyinstallerRoot -Force | Out-Null

$python = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw "Python is required to build the consumer runtime." }
    $python = $pythonCommand.Source
}

& $python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required. Install the development dependencies before building the consumer installer."
}

$ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
$ffprobeCommand = Get-Command ffprobe.exe -ErrorAction SilentlyContinue
if (-not $ffmpegCommand -or -not $ffprobeCommand) {
    throw "Both ffmpeg.exe and ffprobe.exe are required to build a self-contained installer."
}

$cargo = Get-Command cargo.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $cargo -or -not $npm) {
    throw "Rust/Cargo and npm are build-time requirements for the consumer installer."
}

function Invoke-Checked {
    param(
        [scriptblock]$Action,
        [string]$Description
    )
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE." }
}

$commonPyInstallerArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
    "--paths", $scriptDir,
    "--distpath", $runtimeRoot,
    "--workpath", (Join-Path $pyinstallerRoot "work"),
    "--specpath", $pyinstallerRoot,
    "--add-binary", "$($ffmpegCommand.Source);.",
    "--add-binary", "$($ffprobeCommand.Source);."
)

Write-Host "Building self-contained conversion engine..." -ForegroundColor Cyan
Invoke-Checked {
    & $python @commonPyInstallerArgs "--name" "JaneConverterEngine" (Join-Path $scriptDir "packaging\engine_entry.py")
} "JaneConverterEngine build"

Write-Host "Building self-contained Legacy Python interface..." -ForegroundColor Cyan
$legacyArgs = $commonPyInstallerArgs + @(
    "--name", "JaneConverterPython",
    "--windowed",
    "--add-data", "$(Join-Path $scriptDir 'assets');assets",
    (Join-Path $scriptDir "gui.py")
)
Invoke-Checked { & $python @legacyArgs } "JaneConverterPython build"

Write-Host "Building the Legacy Rust recovery interface..." -ForegroundColor Cyan
$previousCargoTarget = $env:CARGO_TARGET_DIR
$nativeTarget = Join-Path $buildRoot "native-target"
$env:CARGO_TARGET_DIR = $nativeTarget
try {
    Invoke-Checked {
        & $cargo.Source build --release --manifest-path (Join-Path $scriptDir "native_ui\Cargo.toml")
    } "Legacy Rust build"
} finally {
    if ($null -eq $previousCargoTarget) {
        Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
    } else {
        $env:CARGO_TARGET_DIR = $previousCargoTarget
    }
}
Copy-Item -LiteralPath (Join-Path $nativeTarget "release\janeconverter-native.exe") -Destination (Join-Path $runtimeRoot "JaneConverterNative.exe")

Copy-Item -LiteralPath $ffmpegCommand.Source -Destination (Join-Path $runtimeRoot "ffmpeg.exe")
Copy-Item -LiteralPath $ffprobeCommand.Source -Destination (Join-Path $runtimeRoot "ffprobe.exe")
New-Item -ItemType Directory -Path (Join-Path $runtimeRoot "browser-extension") -Force | Out-Null
foreach ($extensionFile in @("manifest.json", "popup.html", "popup.js", "README.md")) {
    Copy-Item -LiteralPath (Join-Path $scriptDir "browser-extension\$extensionFile") -Destination (Join-Path $runtimeRoot "browser-extension\$extensionFile")
}

$cscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$csc = $cscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) { throw "The Windows C# compiler is required to build the universal launcher." }
& $csc /target:winexe /win32icon:"$scriptDir\assets\icon.ico" /out:"$runtimeRoot\JaneConverter.exe" "$scriptDir\Program.cs" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Universal launcher build failed." }

$requiredRuntime = @(
    "JaneConverter.exe", "JaneConverterEngine.exe", "JaneConverterPython.exe",
    "JaneConverterNative.exe", "ffmpeg.exe", "ffprobe.exe",
    "browser-extension\manifest.json"
)
foreach ($requiredFile in $requiredRuntime) {
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot $requiredFile) -PathType Leaf)) {
        throw "Consumer runtime is missing $requiredFile."
    }
}

$baseConfig = Get-Content -Raw (Join-Path $scriptDir "desktop-ui\src-tauri\tauri.conf.json") | ConvertFrom-Json

function Set-JsonProperty {
    param(
        [Parameter(Mandatory = $true)] $Object,
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] $Value
    )

    if ($Object.PSObject.Properties[$Name]) {
        $Object.PSObject.Properties[$Name].Value = $Value
    } else {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value -Force
    }
}

$baseConfig.productName = "JaneConverter"
$baseConfig.bundle.active = $true
$baseConfig.bundle.targets = @("nsis")
Set-JsonProperty $baseConfig.bundle "resources" ([ordered]@{
    $runtimeRoot = "runtime"
})
$windowsConfig = [ordered]@{
    nsis = [ordered]@{
        installerHooks = $hookPath
        installMode = "currentUser"
        installerIcon = (Join-Path $scriptDir "assets\icon.ico")
        startMenuFolder = "JaneConverter"
    }
}
Set-JsonProperty $baseConfig.bundle "windows" $windowsConfig
$consumerConfig = Join-Path $buildRoot "tauri.consumer.json"
$baseConfig | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $consumerConfig -Encoding utf8

Write-Host "Building the consumer Main UI installer..." -ForegroundColor Cyan
$desktopNodeModules = Join-Path $scriptDir "desktop-ui\node_modules"
$desktopDist = Join-Path $scriptDir "desktop-ui\dist"
$hadDesktopNodeModules = Test-Path -LiteralPath $desktopNodeModules
$hadDesktopDist = Test-Path -LiteralPath $desktopDist
$previousNpmCache = $env:npm_config_cache
$previousCargoTarget = $env:CARGO_TARGET_DIR
$env:npm_config_cache = Join-Path $buildRoot "npm-cache"
$env:CARGO_TARGET_DIR = Join-Path $buildRoot "tauri-target"
try {
    Push-Location (Join-Path $scriptDir "desktop-ui")
    try {
        Invoke-Checked {
            & $npm.Source ci --no-audit --no-fund --ignore-scripts
        } "Desktop UI dependency installation"
        Invoke-Checked {
            & $npm.Source run build
        } "Desktop UI frontend build"
        Invoke-Checked {
            $tauriCli = Join-Path (Get-Location) "node_modules\.bin\tauri.cmd"
            & $tauriCli build --config $consumerConfig
        } "Tauri consumer installer build"
    } finally {
        Pop-Location
    }
} finally {
    if ($null -eq $previousNpmCache) {
        Remove-Item Env:npm_config_cache -ErrorAction SilentlyContinue
    } else {
        $env:npm_config_cache = $previousNpmCache
    }
    if ($null -eq $previousCargoTarget) {
        Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
    } else {
        $env:CARGO_TARGET_DIR = $previousCargoTarget
    }
}

$builtInstaller = Get-ChildItem -LiteralPath (Join-Path $buildRoot "tauri-target\release\bundle\nsis") -Filter "*-setup.exe" -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $builtInstaller) { throw "Tauri completed without producing an NSIS installer." }
Copy-Item -LiteralPath $builtInstaller.FullName -Destination $outputInstaller -Force
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outputInstaller).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$outputInstaller.sha256" -Value "$hash  $(Split-Path $outputInstaller -Leaf)" -Encoding ascii

if (-not $SkipPortable) {
    Write-Host "Building the portable/developer safety-net archive..." -ForegroundColor Cyan
    & (Join-Path $scriptDir "build_release.ps1") -Version $Version
    if ($LASTEXITCODE -ne 0) { throw "Portable safety-net build failed." }
}

if (-not $KeepStaging) {
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
    if (-not $hadDesktopNodeModules -and (Test-Path -LiteralPath $desktopNodeModules)) {
        Remove-Item -LiteralPath $desktopNodeModules -Recurse -Force
    }
    if (-not $hadDesktopDist -and (Test-Path -LiteralPath $desktopDist)) {
        Remove-Item -LiteralPath $desktopDist -Recurse -Force
    }
}
Write-Host "Created $outputInstaller" -ForegroundColor Green
Write-Host "SHA256: $hash" -ForegroundColor DarkGray

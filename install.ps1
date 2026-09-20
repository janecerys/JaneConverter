# JaneConverter Automated Setup Script for Windows
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "             JaneConverter - Automated Setup              " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
Set-Location $scriptDir

# Helper to refresh current process PATH from registry
function Refresh-EnvPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

# Helper to execute native commands and verify exit codes
function Invoke-Native {
    param([scriptblock]$Command, [string]$StepName)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: $StepName failed with exit code $LASTEXITCODE." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Get-DefaultBrowser {
    $progId = ""
    try {
        $userChoice = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice" -Name ProgId -ErrorAction Stop
        $progId = [string]$userChoice.ProgId
    } catch {
        # The association can be unavailable on locked-down or freshly created profiles.
    }

    $definitions = @(
        [PSCustomObject]@{
            Name = "Vivaldi"
            ProgIdPatterns = @("Vivaldi*")
            CommandNames = @("vivaldi.exe")
            CandidatePaths = @("$env:LocalAppData\Vivaldi\Application\vivaldi.exe", "$env:ProgramFiles\Vivaldi\Application\vivaldi.exe", "${env:ProgramFiles(x86)}\Vivaldi\Application\vivaldi.exe")
            ExtensionsUrl = "vivaldi://extensions"
        },
        [PSCustomObject]@{
            Name = "Google Chrome"
            ProgIdPatterns = @("ChromeHTML*", "GoogleChromeHTML*")
            CommandNames = @("chrome.exe")
            CandidatePaths = @("$env:LocalAppData\Google\Chrome\Application\chrome.exe", "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe")
            ExtensionsUrl = "chrome://extensions"
        },
        [PSCustomObject]@{
            Name = "Microsoft Edge"
            ProgIdPatterns = @("MSEdgeHTM*")
            CommandNames = @("msedge.exe")
            CandidatePaths = @("$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:LocalAppData\Microsoft\Edge\Application\msedge.exe")
            ExtensionsUrl = "edge://extensions"
        },
        [PSCustomObject]@{
            Name = "Brave"
            ProgIdPatterns = @("BraveHTML*")
            CommandNames = @("brave.exe")
            CandidatePaths = @("$env:LocalAppData\BraveSoftware\Brave-Browser\Application\brave.exe", "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe", "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe")
            ExtensionsUrl = "brave://extensions"
        },
        [PSCustomObject]@{
            Name = "Opera"
            ProgIdPatterns = @("OperaStableHTM*", "OperaGXStableHTM*")
            CommandNames = @("opera.exe", "launcher.exe")
            CandidatePaths = @("$env:LocalAppData\Programs\Opera\launcher.exe", "$env:LocalAppData\Programs\Opera GX\launcher.exe", "$env:ProgramFiles\Opera\launcher.exe")
            ExtensionsUrl = "opera://extensions"
        },
        [PSCustomObject]@{
            Name = "Chromium"
            ProgIdPatterns = @("ChromiumHTM*")
            CommandNames = @("chromium.exe")
            CandidatePaths = @("$env:LocalAppData\Chromium\Application\chrome.exe", "$env:ProgramFiles\Chromium\Application\chrome.exe")
            ExtensionsUrl = "chrome://extensions"
        }
    )

    foreach ($definition in $definitions) {
        $isDefault = $false
        foreach ($pattern in $definition.ProgIdPatterns) {
            if ($progId -and $progId -like $pattern) {
                $isDefault = $true
                break
            }
        }
        if (-not $isDefault) {
            continue
        }

        $executable = $null
        foreach ($commandName in $definition.CommandNames) {
            $command = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($command -and $command.Source) {
                $executable = $command.Source
                break
            }
        }
        if (-not $executable) {
            foreach ($candidatePath in $definition.CandidatePaths) {
                if ($candidatePath -and (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
                    $executable = $candidatePath
                    break
                }
            }
        }
        if ($executable) {
            return [PSCustomObject]@{
                Name = $definition.Name
                Executable = $executable
                ExtensionsUrl = $definition.ExtensionsUrl
            }
        }
    }
    return $null
}

function Show-BrowserBridgeManualInstructions {
    param([string]$ExtensionPath)

    Write-Host ""
    Write-Host "Manual Browser Bridge installation:" -ForegroundColor Cyan
    Write-Host "1. Open your browser's extensions page." -ForegroundColor DarkGray
    Write-Host "2. Enable Developer mode." -ForegroundColor DarkGray
    Write-Host "3. Choose Load unpacked." -ForegroundColor DarkGray
    Write-Host "4. Select this folder:" -ForegroundColor DarkGray
    Write-Host "   $ExtensionPath" -ForegroundColor Cyan
}

function Open-BrowserBridgeInstallPage {
    param([string]$ExtensionPath)

    $manifestPath = Join-Path $ExtensionPath "manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host "NOTICE: The bundled browser extension was not found at '$ExtensionPath'." -ForegroundColor DarkGray
        return
    }

    Write-Host ""
    Write-Host "JaneConverter includes an optional Browser Bridge for signed-in media." -ForegroundColor Cyan
    Write-Host "It stays local, uses only the current source session, and never saves your browser cookies." -ForegroundColor DarkGray
    $installChoice = Read-Host "Open the default browser's extension manager now? (y/N)"
    if ($installChoice -notmatch "^(?i)y(?:es)?$") {
        Show-BrowserBridgeManualInstructions $ExtensionPath
        return
    }

    $browser = Get-DefaultBrowser
    if (-not $browser) {
        Write-Host "NOTICE: A supported Chromium default browser was not detected." -ForegroundColor DarkGray
        Show-BrowserBridgeManualInstructions $ExtensionPath
        return
    }

    try {
        Start-Process -FilePath $browser.Executable -ArgumentList $browser.ExtensionsUrl -ErrorAction Stop | Out-Null
        Write-Host "-> Opened $($browser.Name) extension manager." -ForegroundColor Green
        Write-Host "   Enable Developer mode, choose Load unpacked, and select:" -ForegroundColor Cyan
        Write-Host "   $ExtensionPath" -ForegroundColor Cyan
        Write-Host "   Browser security requires this one confirmation; setup will not modify browser profiles silently." -ForegroundColor DarkGray
    } catch {
        Write-Host "NOTICE: Could not open $($browser.Name) extension manager: $($_.Exception.Message)" -ForegroundColor DarkGray
        Show-BrowserBridgeManualInstructions $ExtensionPath
    }
}

function Get-UsablePythonRuntime {
    $candidatePaths = New-Object System.Collections.Generic.List[string]

    # Try every matching executable instead of trusting the first PATH entry.
    foreach ($commandName in @("python.exe", "python3.exe", "py.exe")) {
        $commands = @(Get-Command $commandName -All -ErrorAction SilentlyContinue)
        foreach ($command in $commands) {
            if ($command.Source -and -not $candidatePaths.Contains($command.Source)) {
                [void]$candidatePaths.Add($command.Source)
            }
        }
    }

    # The Python launcher and these common install locations can find Python
    # even when the user installed it outside the usual PATH directory.
    $knownPaths = @()
    if ($env:LocalAppData) {
        $knownPaths += Join-Path $env:LocalAppData "Programs\Python\Launcher\py.exe"
    }
    if ($env:ProgramFiles) {
        $knownPaths += Join-Path $env:ProgramFiles "Python Launcher\py.exe"
    }
    if ($env:WINDIR) {
        $knownPaths += Join-Path $env:WINDIR "py.exe"
    }
    foreach ($knownPath in $knownPaths) {
        if ((Test-Path -LiteralPath $knownPath -PathType Leaf) -and -not $candidatePaths.Contains($knownPath)) {
            [void]$candidatePaths.Add($knownPath)
        }
    }

    # Python installers register their install directory here even when PATH
    # was not updated. Read those entries as a final local discovery fallback.
    foreach ($registryRoot in @(
        "HKCU:\Software\Python\PythonCore",
        "HKLM:\Software\Python\PythonCore",
        "HKLM:\Software\WOW6432Node\Python\PythonCore"
    )) {
        if (-not (Test-Path -LiteralPath $registryRoot)) {
            continue
        }
        foreach ($versionKey in @(Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue)) {
            $installKeyPath = Join-Path $versionKey.PSPath "InstallPath"
            try {
                $installKey = Get-Item -LiteralPath $installKeyPath -ErrorAction Stop
                $installPath = $installKey.GetValue("")
                if ($installPath) {
                    $registeredPython = Join-Path ([string]$installPath) "python.exe"
                    if (-not $candidatePaths.Contains($registeredPython)) {
                        [void]$candidatePaths.Add($registeredPython)
                    }
                }
            } catch {
                # A malformed registry entry should not prevent other candidates.
            }
        }
    }

    foreach ($candidatePath in $candidatePaths) {
        if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
            continue
        }

        $isPythonLauncher = ([System.IO.Path]::GetFileName($candidatePath) -ieq "py.exe")
        if ($isPythonLauncher) {
            $versionArguments = @("-3", "--version")
            $executableArguments = @("-3", "-c", "import sys; print(sys.executable)")
        } else {
            $versionArguments = @("--version")
            $executableArguments = @("-c", "import sys; print(sys.executable)")
        }

        try {
            # Windows 11 can expose a Microsoft Store app-execution alias even
            # when Python is not installed. Treat a failed version command as missing.
            $versionOutput = & $candidatePath @versionArguments 2>&1
            if ($LASTEXITCODE -ne 0) {
                continue
            }
            $versionText = ($versionOutput | Out-String).Trim()
            $versionMatch = [regex]::Match($versionText, 'Python\s+([0-9]+)\.([0-9]+)')
            if (-not $versionMatch.Success) {
                continue
            }
            $candidateMajor = [int]$versionMatch.Groups[1].Value
            $candidateMinor = [int]$versionMatch.Groups[2].Value
            if (($candidateMajor -lt 3) -or (($candidateMajor -eq 3) -and ($candidateMinor -lt 10))) {
                continue
            }
            $resolvedExecutable = (& $candidatePath @executableArguments 2>$null | Select-Object -Last 1 | Out-String).Trim()
            if (-not (Test-Path -LiteralPath $resolvedExecutable -PathType Leaf)) {
                $resolvedExecutable = $candidatePath
            }
            return [PSCustomObject]@{
                Command = $resolvedExecutable
                VersionText = $versionText
                Major = $candidateMajor
                Minor = $candidateMinor
            }
        } catch {
            # Try the next executable when a PATH or registry candidate is stale.
        }
    }
    return $null
}

# 1. Check Python
Write-Host "[1/6] Checking Python runtime..." -ForegroundColor Yellow
$pythonRuntime = Get-UsablePythonRuntime
if (-not $pythonRuntime) {
    Write-Host "Python was not found. Attempting automatic installation via winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Native { winget install --id Python.Python.3.12 --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements } "Python installation"
        Refresh-EnvPath
        $pythonRuntime = Get-UsablePythonRuntime
    } else {
        Write-Host "ERROR: Please install Python 3.10+ from https://www.python.org/downloads/ and check 'Add to PATH'." -ForegroundColor Red
        exit 1
    }
}
if (-not $pythonRuntime) {
    Write-Host "ERROR: Python installation completed, but a usable Python runtime was not found in PATH. Open a new terminal and run setup.bat again." -ForegroundColor Red
    exit 1
}
$pyVer = $pythonRuntime.VersionText
Write-Host "-> Found: $pyVer ($($pythonRuntime.Command))" -ForegroundColor Green
$pyMajor = $pythonRuntime.Major
$pyMinor = $pythonRuntime.Minor
if (($pyMajor -lt 3) -or (($pyMajor -eq 3) -and ($pyMinor -lt 10))) {
    Write-Host "ERROR: Python 3.10 or newer is required." -ForegroundColor Red
    exit 1
}

# Keep JaneConverter's dependencies isolated from the user's other Python work.
$venvPath = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPythonw = Join-Path $venvPath "Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host "Creating private JaneConverter Python environment..." -ForegroundColor Cyan
    $venvArguments = @("-m", "venv")
    if (Test-Path -LiteralPath $venvPath) {
        # Repair a partial environment left by an interrupted or unsupported bootstrap.
        $venvArguments += "--clear"
    }
    $venvArguments += $venvPath
    Invoke-Native { & $pythonRuntime.Command @venvArguments } "Private Python environment"
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host "ERROR: Python was found at '$($pythonRuntime.Command)', but setup could not create '$venvPython'." -ForegroundColor Red
    Write-Host "Remove the incomplete .venv folder and run setup.bat again, or install a standard Python 3.10+ build from python.org." -ForegroundColor Red
    exit 1
}

# 2. Check FFmpeg (Required for audio/video conversion)
Write-Host "[2/6] Checking FFmpeg engine..." -ForegroundColor Yellow
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg not found. Installing Gyan.FFmpeg via winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Native { winget install --id Gyan.FFmpeg --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements } "FFmpeg installation"
        Refresh-EnvPath
    } else {
        Write-Host "ERROR: winget is unavailable, so FFmpeg could not be installed automatically." -ForegroundColor Red
    }
}
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "-> FFmpeg is ready." -ForegroundColor Green
} else {
    Write-Host "ERROR: FFmpeg was not detected in PATH. FFmpeg is required for media conversion." -ForegroundColor Red
    Write-Host "Please install FFmpeg or restart your terminal if it was just installed via winget." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: ffprobe was not detected. Install the complete FFmpeg package and try again." -ForegroundColor Red
    exit 1
}

# 3. Check Node.js (Recommended for YouTube challenge resolution)
Write-Host "[3/6] Checking Node.js runtime..." -ForegroundColor Yellow
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js not found. Installing OpenJS.NodeJS.LTS via winget (a Windows security prompt may appear)..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install --id OpenJS.NodeJS.LTS --exact --source winget --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-Host "NOTICE: Node.js installation was not completed. You can continue without it, but some YouTube sources may fail." -ForegroundColor DarkGray
        }
        Refresh-EnvPath
    }
}
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = & node -v
    Write-Host "-> Node.js is ready ($nodeVer)." -ForegroundColor Green
} else {
    Write-Host "NOTICE: Node.js is recommended for uninterrupted stream extraction." -ForegroundColor DarkGray
}

# 4. Install Python Dependencies
Write-Host "[4/6] Installing Python studio dependencies..." -ForegroundColor Yellow
Write-Host "Updating pip (this may take a minute; no input is required)..." -ForegroundColor Cyan
Invoke-Native { & $venvPython -m pip install --upgrade pip --disable-pip-version-check --no-input } "Pip upgrade"
Write-Host "Installing JaneConverter dependencies (download progress will appear)..." -ForegroundColor Cyan
Invoke-Native { & $venvPython -m pip install --disable-pip-version-check --no-input -r requirements.txt } "Requirements installation"
Write-Host "-> Python dependencies installed." -ForegroundColor Green

# 5. Verify Core Python Modules
Write-Host "[5/6] Verifying core modules..." -ForegroundColor Yellow
$verifyCmd = "import customtkinter, psutil, PIL, yt_dlp, requests; print('OK')"
$verifyOut = & $venvPython -c $verifyCmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Dependency verification failed:`n$verifyOut" -ForegroundColor Red
    exit 1
}
Write-Host "-> All core packages verified successfully." -ForegroundColor Green
Invoke-Native { & $venvPython -m pip check } "Private environment dependency check"

# 6. Build Executable Launcher & Desktop Shortcut
Write-Host "[6/6] Building native launcher and desktop shortcut..." -ForegroundColor Yellow

# Build the optional Rust frontend when Cargo is available. If the toolchain is
# absent or unavailable, keep the Python UI as the reliable fallback. Never
# leave an older native executable in place after its source has changed.
$nativeBinaryPath = Join-Path $scriptDir "JaneConverterNative.exe"
$cargo = Get-Command cargo.exe -ErrorAction SilentlyContinue
if ($cargo) {
    Write-Host "-> Rust/Cargo detected. Building the native frontend..." -ForegroundColor Cyan
    & $cargo.Source build --release --manifest-path (Join-Path $scriptDir "native_ui\Cargo.toml")
    if ($LASTEXITCODE -eq 0) {
        $builtNativePath = Join-Path $scriptDir "native_ui\target\release\janeconverter-native.exe"
        if (Test-Path -LiteralPath $builtNativePath) {
            Copy-Item -LiteralPath $builtNativePath -Destination $nativeBinaryPath -Force
            Write-Host "-> Built JaneConverterNative.exe." -ForegroundColor Green
        } else {
            Write-Host "NOTICE: Rust build completed without producing the native executable. Python UI remains available." -ForegroundColor DarkGray
        }
    } else {
        if (Test-Path -LiteralPath $nativeBinaryPath) {
            Move-Item -LiteralPath $nativeBinaryPath -Destination ($nativeBinaryPath + ".stale") -Force
            Write-Host "NOTICE: Rust frontend build failed; moved the old native frontend aside. Python UI remains available." -ForegroundColor DarkGray
        } else {
            Write-Host "NOTICE: Rust frontend build failed. Python UI remains available." -ForegroundColor DarkGray
        }
    }
} elseif (Test-Path -LiteralPath $nativeBinaryPath) {
    $nativeSourceFiles = @(
        (Get-ChildItem -LiteralPath (Join-Path $scriptDir "native_ui\src") -Recurse -File | Where-Object { $_.Extension -eq ".rs" }),
        (Get-Item -LiteralPath (Join-Path $scriptDir "native_ui\Cargo.toml")),
        (Get-Item -LiteralPath (Join-Path $scriptDir "native_ui\Cargo.lock"))
    )
    $latestNativeSource = $nativeSourceFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $nativeBinary = Get-Item -LiteralPath $nativeBinaryPath
    if ($latestNativeSource -and $latestNativeSource.LastWriteTimeUtc -gt $nativeBinary.LastWriteTimeUtc) {
        Move-Item -LiteralPath $nativeBinaryPath -Destination ($nativeBinaryPath + ".stale") -Force
        Write-Host "NOTICE: Moved the older Rust frontend aside; the current Python UI will be used until Rust is installed." -ForegroundColor DarkGray
    }
} else {
    Write-Host "NOTICE: Rust/Cargo not found. The legacy Python interface remains available." -ForegroundColor DarkGray
}

# Build the Main UI (Tauri + React) beside the universal launcher. The
# installed Rust UI above remains the recovery path when Node.js or the Tauri
# build cannot be used on a particular machine.
$desktopBinaryPath = Join-Path $scriptDir "JaneConverterDesktop.exe"
$desktopUiDir = Join-Path $scriptDir "desktop-ui"
$desktopCargoManifest = Join-Path $desktopUiDir "src-tauri\Cargo.toml"
$desktopPackageJson = Join-Path $desktopUiDir "package.json"
$desktopCargo = Get-Command cargo.exe -ErrorAction SilentlyContinue
$desktopNpm = Get-Command npm -ErrorAction SilentlyContinue
$desktopBuilt = $false
if ($desktopCargo -and $desktopNpm -and (Test-Path -LiteralPath $desktopCargoManifest) -and (Test-Path -LiteralPath $desktopPackageJson)) {
    Write-Host "-> Building the Main UI (Tauri + React)..." -ForegroundColor Cyan
    $desktopCargoTarget = Join-Path $desktopUiDir ".cargo-target"
    $desktopNpmCache = Join-Path $desktopUiDir ".npm-cache"
    $previousCargoTarget = $env:CARGO_TARGET_DIR
    $previousNpmCache = $env:npm_config_cache
    $desktopLocationPushed = $false
    try {
        $env:CARGO_TARGET_DIR = $desktopCargoTarget
        $env:npm_config_cache = $desktopNpmCache
        Push-Location $desktopUiDir
        $desktopLocationPushed = $true
        & $desktopNpm.Source ci --no-audit --no-fund --ignore-scripts
        if ($LASTEXITCODE -ne 0) {
            throw "Main UI dependency installation failed with exit code $LASTEXITCODE."
        }
        & $desktopNpm.Source run tauri:build
        if ($LASTEXITCODE -ne 0) {
            throw "Main UI build failed with exit code $LASTEXITCODE."
        }
        $builtDesktopPath = Join-Path $desktopCargoTarget "release\janeconverter-desktop.exe"
        if (-not (Test-Path -LiteralPath $builtDesktopPath -PathType Leaf)) {
            throw "Tauri completed without producing janeconverter-desktop.exe."
        }
        Copy-Item -LiteralPath $builtDesktopPath -Destination $desktopBinaryPath -Force
        $desktopBuilt = $true
        Write-Host "-> Built JaneConverterDesktop.exe. Main UI is now the default launcher." -ForegroundColor Green
    } catch {
        Write-Host "NOTICE: Main UI build was not completed: $($_.Exception.Message)" -ForegroundColor DarkGray
        if (Test-Path -LiteralPath $desktopBinaryPath -PathType Leaf) {
            Write-Host "NOTICE: Keeping the existing JaneConverterDesktop.exe." -ForegroundColor DarkGray
            $desktopBuilt = $true
        } else {
            Write-Host "NOTICE: The universal launcher will use the available legacy interface." -ForegroundColor DarkGray
        }
    } finally {
        if ($desktopLocationPushed) {
            Pop-Location
        }
        if ($null -eq $previousCargoTarget) {
            Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue
        } else {
            $env:CARGO_TARGET_DIR = $previousCargoTarget
        }
        if ($null -eq $previousNpmCache) {
            Remove-Item Env:npm_config_cache -ErrorAction SilentlyContinue
        } else {
            $env:npm_config_cache = $previousNpmCache
        }
    }
} elseif (Test-Path -LiteralPath $desktopBinaryPath -PathType Leaf) {
    Write-Host "-> Existing JaneConverterDesktop.exe found. Main UI is available." -ForegroundColor Green
    $desktopBuilt = $true
} else {
    Write-Host "NOTICE: Node.js/Rust or the Main UI sources are unavailable. The legacy interface remains available." -ForegroundColor DarkGray
}

if ($desktopBuilt -and (Test-Path -LiteralPath $desktopBinaryPath -PathType Leaf)) {
    Set-Content -LiteralPath (Join-Path $scriptDir "frontend.preference") -Value "tauri" -Encoding ascii
    Write-Host "-> Set the universal launcher preference to Main UI." -ForegroundColor Green
}

# Keep the universal launcher as the only visible executable entry point.
# The selected interface remains available through Settings and the launcher
# preference; these child binaries are implementation details.
foreach ($internalLauncher in @("JaneConverterDesktop.exe", "JaneConverterNative.exe", "JaneConverterPython.exe")) {
    $internalLauncherPath = Join-Path $scriptDir $internalLauncher
    if (Test-Path -LiteralPath $internalLauncherPath -PathType Leaf) {
        $internalLauncherItem = Get-Item -LiteralPath $internalLauncherPath
        $internalLauncherItem.Attributes = $internalLauncherItem.Attributes -bor [System.IO.FileAttributes]::Hidden
    }
}

$cscPath = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $cscPath)) {
    $cscPath = "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
}

$buildSuccess = $false
if (Test-Path $cscPath) {
    & $cscPath /target:winexe /win32icon:"$scriptDir\assets\icon.ico" /out:"$scriptDir\JaneConverter.exe" "$scriptDir\Program.cs" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $buildSuccess = $true
        Write-Host "-> Compiled JaneConverter.exe with embedded icon." -ForegroundColor Green
    } else {
        Write-Host "WARNING: C# compilation returned error code $LASTEXITCODE." -ForegroundColor Yellow
    }
} else {
    Write-Host "NOTICE: .NET C# compiler not found. You can run JaneConverter via 'python gui.py'." -ForegroundColor DarkGray
}

$desktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$shortcutPath = Join-Path $desktopPath "JaneConverter.lnk"
try {
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut($shortcutPath)
    if ($buildSuccess -and (Test-Path "$scriptDir\JaneConverter.exe")) {
        $sc.TargetPath = "$scriptDir\JaneConverter.exe"
    } else {
        $sc.TargetPath = $venvPythonw
        $sc.Arguments = "`"$scriptDir\gui.py`""
    }
    $sc.WorkingDirectory = $scriptDir
    if (Test-Path "$scriptDir\assets\icon.ico") {
        $sc.IconLocation = "$scriptDir\assets\icon.ico"
    }
    $sc.Description = "JaneConverter - Universal Media Studio"
    $sc.Save()
    Write-Host "-> Created Desktop shortcut: JaneConverter.lnk" -ForegroundColor Green

    if ($buildSuccess -and (Test-Path "$scriptDir\JaneConverter.exe")) {
        foreach ($variantName in @("JaneConverter Legacy.lnk", "JaneConverter Rust.lnk")) {
            $variantShortcut = Join-Path $desktopPath $variantName
            if (Test-Path -LiteralPath $variantShortcut) {
                Remove-Item -LiteralPath $variantShortcut -Force
            }
        }
        Write-Host "-> Kept JaneConverter.exe as the only launcher shortcut." -ForegroundColor Green
    }
} catch {
    Write-Host "Notice: Could not write desktop shortcut: $_" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "      Setup Complete! JaneConverter is ready to use!        " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""

Open-BrowserBridgeInstallPage (Join-Path $scriptDir "browser-extension")

Write-Host "Launching JaneConverter Studio..." -ForegroundColor Cyan

if ($buildSuccess -and (Test-Path "$scriptDir\JaneConverter.exe")) {
    Start-Process "$scriptDir\JaneConverter.exe"
} else {
    Start-Process $venvPythonw -ArgumentList "`"$scriptDir\gui.py`"" -WorkingDirectory $scriptDir
}

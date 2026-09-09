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

# 1. Check Python
Write-Host "[1/6] Checking Python runtime..." -ForegroundColor Yellow
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Host "Python not found in PATH. Attempting automatic installation via winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Native { winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements } "Python installation"
        Refresh-EnvPath
    } else {
        Write-Host "ERROR: Please install Python 3.10+ from https://www.python.org/downloads/ and check 'Add to PATH'." -ForegroundColor Red
        exit 1
    }
}
$pyVer = & python --version 2>&1
Write-Host "-> Found: $pyVer" -ForegroundColor Green
$pyVersionMatch = [regex]::Match(($pyVer | Out-String), '([0-9]+)\.([0-9]+)')
if ($pyVersionMatch.Success) {
    $pyMajor = [int]$pyVersionMatch.Groups[1].Value
    $pyMinor = [int]$pyVersionMatch.Groups[2].Value
    if (($pyMajor -lt 3) -or (($pyMajor -eq 3) -and ($pyMinor -lt 10))) {
        Write-Host "ERROR: Python 3.10 or newer is required." -ForegroundColor Red
        exit 1
    }
}

# Keep JaneConverter's dependencies isolated from the user's other Python work.
$venvPath = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPythonw = Join-Path $venvPath "Scripts\pythonw.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating private JaneConverter Python environment..." -ForegroundColor Cyan
    Invoke-Native { python -m venv $venvPath } "Private Python environment"
}

# 2. Check FFmpeg (Required for audio/video conversion)
Write-Host "[2/6] Checking FFmpeg engine..." -ForegroundColor Yellow
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg not found. Installing Gyan.FFmpeg via winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
        Refresh-EnvPath
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
    Write-Host "Node.js not found. Installing OpenJS.NodeJS.LTS via winget..." -ForegroundColor Cyan
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        & winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
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
Invoke-Native { & $venvPython -m pip install --upgrade pip --quiet } "Pip upgrade"
Invoke-Native { & $venvPython -m pip install -r requirements.txt --quiet } "Requirements installation"
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

# 6. Build Executable Launcher & Desktop Shortcut
Write-Host "[6/6] Building native launcher and desktop shortcut..." -ForegroundColor Yellow

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
} catch {
    Write-Host "Notice: Could not write desktop shortcut: $_" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host "      Setup Complete! JaneConverter is ready to use!        " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Launching JaneConverter Studio..." -ForegroundColor Cyan

if ($buildSuccess -and (Test-Path "$scriptDir\JaneConverter.exe")) {
    Start-Process "$scriptDir\JaneConverter.exe"
} else {
    Start-Process $venvPythonw -ArgumentList "`"$scriptDir\gui.py`"" -WorkingDirectory $scriptDir
}

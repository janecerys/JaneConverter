$ErrorActionPreference = "Stop"
$appData = Join-Path $env:LOCALAPPDATA "JaneConverter"
$venv = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) ".venv"

Write-Host "This removes JaneConverter's private environment and application data." -ForegroundColor Yellow
Write-Host "Your exported media is included in: $appData\converted" -ForegroundColor Yellow
$answer = Read-Host "Type REMOVE to continue"
if ($answer -cne "REMOVE") { Write-Host "Nothing was removed."; exit 0 }

if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
if (Test-Path $appData) { Remove-Item -LiteralPath $appData -Recurse -Force }
Write-Host "JaneConverter application data and private environment removed."

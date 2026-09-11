$ErrorActionPreference = "Stop"
$installDir = [IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Definition))
$portableItems = @(
    "converted", "temp", "logs", "updates", "config.json", "frontend.preference", "native.settings"
)
$appData = Join-Path $env:LOCALAPPDATA "JaneConverter"
$configuredData = $env:JANECONVERTER_DATA_DIR
$dataRoots = @($installDir, $appData)
if (-not [string]::IsNullOrWhiteSpace($configuredData)) {
    $dataRoots += [IO.Path]::GetFullPath($configuredData)
}
$venv = Join-Path $installDir ".venv"

Write-Host "This removes JaneConverter's private environment and application data." -ForegroundColor Yellow
Write-Host "Portable exported media is included in: $installDir\converted" -ForegroundColor Yellow
Write-Host "Legacy per-user data is included in: $appData" -ForegroundColor Yellow
$answer = Read-Host "Type REMOVE to continue"
if ($answer -cne "REMOVE") { Write-Host "Nothing was removed."; exit 0 }

if (Test-Path $venv) { Remove-Item -LiteralPath $venv -Recurse -Force }
foreach ($dataRoot in ($dataRoots | Select-Object -Unique)) {
    if ([IO.Path]::GetFullPath($dataRoot).TrimEnd('\') -eq $installDir.TrimEnd('\')) {
        foreach ($item in $portableItems) {
            $target = Join-Path $dataRoot $item
            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        }
    } elseif (Test-Path -LiteralPath $dataRoot) {
        Remove-Item -LiteralPath $dataRoot -Recurse -Force
    }
}
Write-Host "JaneConverter application data and private environment removed."

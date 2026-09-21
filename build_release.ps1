param(
    [string]$Version = "",
    [string]$FFmpegPath = "",
    [string]$FFprobePath = "",
    [string]$NodePath = "",
    [string]$OutputDirectory = "",
    [switch]$KeepStaging
)

$arguments = @("-SkipInstaller")
foreach ($item in @{
    Version = $Version
    FFmpegPath = $FFmpegPath
    FFprobePath = $FFprobePath
    NodePath = $NodePath
    OutputDirectory = $OutputDirectory
}.GetEnumerator()) {
    if ($item.Value) { $arguments += @("-$($item.Key)", $item.Value) }
}
if ($KeepStaging) { $arguments += "-KeepStaging" }

& (Join-Path $PSScriptRoot "packaging\build_consumer.ps1") @arguments

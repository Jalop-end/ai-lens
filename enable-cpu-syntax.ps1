# enable-cpu-syntax.ps1 (Bridge to scripts/windows/enable-cpu-syntax.ps1)
$targetScript = Join-Path $PSScriptRoot "scripts\windows\enable-cpu-syntax.ps1"
if (Test-Path $targetScript) {
    . $targetScript
}

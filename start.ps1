<#
.SYNOPSIS
    Universal PowerShell start launcher for AI Lens.
.EXAMPLE
    .\start 3.8
    .\start 3.8 "YOUR_GEMINI_API_KEY"
    .\start with Gemini
    .\start with Gemini(3.8) "YOUR_GEMINI_API_KEY"
    .\start status
    .\start diag
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $scriptDir "ai-lens.bat"

$first = if ($Arguments -and $Arguments.Count -gt 0) { $Arguments[0].ToLower().Trim() } else { "" }
if ($first -in @("status", "stop", "diag", "diagnostika", "diagnostics", "security", "specs", "languages", "levels", "config")) {
    & $bat @Arguments
} else {
    & $bat start @Arguments
}

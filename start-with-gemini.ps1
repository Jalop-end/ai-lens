<#
.SYNOPSIS
    Starts AI Lens with Google Gemini API (short-term RAM key).
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir "ai-lens.bat") start with Gemini @Arguments

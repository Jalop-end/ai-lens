<#
.SYNOPSIS
    Starts AI Lens directly with Google Gemini API key and automatic model detection.
.EXAMPLE
    gemini( AIzaSy... )
    gemini "AIzaSy..."
    gemini "AIzaSy..." 3.8flash
    gemini "AIzaSy..." 3.5 cs High
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir "Gemini.bat") @Arguments

<#
.SYNOPSIS
    Universal PowerShell launcher for AI Lens.
    Works out of the box with or without an active virtual environment.
.EXAMPLE
    .\ai-lens.bat en High
    .\ai-lens cs High
    .\ai-lens diag
    .\ai-lens start with Gemini
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$scriptDir;$env:PYTHONPATH"
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    foreach ($cand in @(
        "$env:USERPROFILE\Desktop\ai-lens-main\.venv\Scripts\python.exe",
        "$env:USERPROFILE\Desktop\ai-lens-main3\.venv\Scripts\python.exe",
        (Join-Path $scriptDir "..\ai-lens\.venv\Scripts\python.exe")
    )) {
        if (Test-Path $cand) {
            $venvPython = $cand
            break
        }
    }
}

if (Test-Path $venvPython) {
    & $venvPython -m ai_lens @Arguments
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        & python -m ai_lens @Arguments
    } else {
        $pyCmd = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCmd) {
            & py -m ai_lens @Arguments
        } else {
            Write-Error "[AI Lens] Python nebyl nalezen. Nainstalujte prosim Python z https://www.python.org/"
            exit 1
        }
    }
}

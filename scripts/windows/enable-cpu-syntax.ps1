# enable-cpu-syntax.ps1
# Poskytuje čistou podporu pro:
#   .\ai-lens.bat start with Gemini
#   start with Gemini
#   @\ CPU
#   gemini
# přímo ve Windows PowerShellu.

if (Test-Path Alias:start) {
    Remove-Item Alias:start -Force -ErrorAction SilentlyContinue
}

function global:Find-AiLensBat {
    if (Test-Path ".\ai-lens.bat") { return (Resolve-Path ".\ai-lens.bat").Path }
    if (Test-Path "..\ai-lens.bat") { return (Resolve-Path "..\ai-lens.bat").Path }
    if (Test-Path "..\..\ai-lens.bat") { return (Resolve-Path "..\..\ai-lens.bat").Path }
    $scriptDir = $PSScriptRoot
    if ($scriptDir) {
        if (Test-Path (Join-Path $scriptDir "ai-lens.bat")) { return (Join-Path $scriptDir "ai-lens.bat") }
        if (Test-Path (Join-Path $scriptDir "..\ai-lens.bat")) { return (Resolve-Path (Join-Path $scriptDir "..\ai-lens.bat")).Path }
        if (Test-Path (Join-Path $scriptDir "..\..\ai-lens.bat")) { return (Resolve-Path (Join-Path $scriptDir "..\..\ai-lens.bat")).Path }
    }
    foreach ($cand in @(
        "$env:USERPROFILE\ai-lens-1\ai-lens.bat",
        "$env:USERPROFILE\Desktop\ai-lens-main\ai-lens.bat",
        "$env:USERPROFILE\Desktop\ai-lens-main3\ai-lens.bat",
        "$env:USERPROFILE\ai-lens\ai-lens.bat"
    )) {
        if (Test-Path $cand) { return $cand }
    }
    return ".\ai-lens.bat"
}

# Přidání kořenové složky do PATH pro aktuální session
$rootCandidate = (Split-Path (Find-AiLensBat) -Parent)
if ($rootCandidate -and (Test-Path $rootCandidate) -and ($env:PATH -notlike "*$rootCandidate*")) {
    $env:PATH = "$rootCandidate;$env:PATH"
}

function global:Find-AiLensPython {
    $bat = Find-AiLensBat
    $root = Split-Path $bat -Parent
    $cands = @(
        (Join-Path $root ".venv\Scripts\python.exe"),
        "$env:USERPROFILE\Desktop\ai-lens-main\.venv\Scripts\python.exe",
        "$env:USERPROFILE\Desktop\ai-lens-main3\.venv\Scripts\python.exe",
        (Join-Path $root "..\ai-lens\.venv\Scripts\python.exe")
    )
    foreach ($c in $cands) {
        if (Test-Path $c) { return (Resolve-Path $c).Path }
    }
    $sysPy = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($sysPy) { return $sysPy }
    return "python"
}

function global:ai-lens {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
        [string[]]$AllArgs
    )
    $py = Find-AiLensPython
    if (Test-Path $py) {
        & $py -m ai_lens @AllArgs
    } else {
        $bat = Find-AiLensBat
        & $bat @AllArgs
    }
}

function global:start {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
        [string[]]$AllArgs
    )
    $aiLensBat = Find-AiLensBat
    $py = Find-AiLensPython

    $firstArg = if ($AllArgs -and $AllArgs.Count -gt 0) { $AllArgs[0].ToLower().Trim() } else { "" }
    $secondArg = if ($AllArgs -and $AllArgs.Count -gt 1) { $AllArgs[1].ToLower().Trim() } else { "" }

    # start with Gemini
    if ($firstArg -eq "with" -and $secondArg -like "*gemini*") {
        if (Test-Path $py) {
            & $py -m ai_lens start with Gemini
            return
        }
        if (Test-Path $aiLensBat) {
            & $aiLensBat start with Gemini
            return
        }
    }

    if ($firstArg -in @("diag", "diagnostika", "status", "stop")) {
        if (Test-Path $py) {
            & $py -m ai_lens @AllArgs
            return
        }
        if (Test-Path $aiLensBat) {
            & $aiLensBat @AllArgs
            return
        }
    }

    $isAiLensArg = $firstArg -in @("with", "gemini", "cs", "en", "sk", "de", "diag", "diagnostika", "status", "stop", "secret", "cpu", "gpu", "low", "medium", "high")

    if ($isAiLensArg -or -not $AllArgs -or $AllArgs.Count -eq 0) {
        if (Test-Path $py) {
            if ($firstArg -in @("diag", "diagnostika", "status", "stop", "secret")) {
                & $py -m ai_lens @AllArgs
            } else {
                & $py -m ai_lens start @AllArgs
            }
            return
        }
        if (Test-Path $aiLensBat) {
            & $aiLensBat start @AllArgs
            return
        }
    }

    Microsoft.PowerShell.Management\Start-Process @AllArgs
}

function global:gemini {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
        [string[]]$AllArgs
    )
    $py = Find-AiLensPython
    if (Test-Path $py) {
        & $py -m ai_lens start with Gemini @AllArgs
    } else {
        $aiLensBat = Find-AiLensBat
        & $aiLensBat start with Gemini @AllArgs
    }
}

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

        # start with gemini
        if ($line -match '(?i)^\s*(?:(?:(?:\.\\)?ai-lens(?:\.bat)?\s+)?start(?:\.bat|\.ps1)?|(?:\.\\)?start(?:\.bat|\.ps1)?)\s+with\s+gemini.*$') {
            $cmd = if (Test-Path ".\ai-lens.bat") { ".\ai-lens.bat" } elseif (Test-Path "..\ai-lens.bat") { "..\ai-lens.bat" } else { "ai-lens" }
            $newLine = "$cmd start with Gemini"
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        # .\ai-lens.bat spuštěný z podsložky (ai_lens nebo scripts)
        elseif ($line -match '^\s*\.\\ai-lens(?:\.bat)?\b' -and -not (Test-Path ".\ai-lens.bat")) {
            $realBat = Find-AiLensBat
            if ($realBat -and (Test-Path $realBat)) {
                $newLine = $line -replace '^\s*\.\\ai-lens(?:\.bat)?', "& `"$realBat`""
                [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
                [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
            }
        }
        # @\ CPU / && CPU
        elseif ($line -match 'ai-lens.*(?<!["''])@\\') {
            $newLine = $line -replace '(?<!["''])@\\', '"@\"'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        elseif ($line -match 'ai-lens.*&&\s*cpu') {
            $newLine = $line -replace '&&\s*cpu', 'CPU'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }

        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
}

Write-Host "[AI Lens] Podpora pro '.\ai-lens.bat start with Gemini' a '@\' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green


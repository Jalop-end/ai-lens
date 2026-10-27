# enable-cpu-syntax.ps1
# Poskytuje čistou podporu pro:
#   .\ai-lens.bat start with Gemini
#   start with Gemini
#   @\ CPU
# přímo ve Windows PowerShellu.

if (Test-Path Alias:start) {
    Remove-Item Alias:start -Force -ErrorAction SilentlyContinue
}

function global:start {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
        [string[]]$AllArgs
    )
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
    $aiLensBat = Join-Path $scriptDir "ai-lens.bat"
    if (-not (Test-Path $aiLensBat)) {
        foreach ($cand in @(
            "$env:USERPROFILE\ai-lens-1\ai-lens.bat",
            "$env:USERPROFILE\Desktop\ai-lens-main\ai-lens.bat",
            "$env:USERPROFILE\Desktop\ai-lens-main3\ai-lens.bat",
            "$env:USERPROFILE\ai-lens\ai-lens.bat"
        )) {
            if (Test-Path $cand) {
                $aiLensBat = $cand
                break
            }
        }
    }

    $firstArg = if ($AllArgs -and $AllArgs.Count -gt 0) { $AllArgs[0].ToLower().Trim() } else { "" }
    $secondArg = if ($AllArgs -and $AllArgs.Count -gt 1) { $AllArgs[1].ToLower().Trim() } else { "" }

    # start with Gemini
    if ($firstArg -eq "with" -and $secondArg -like "*gemini*") {
        if (Test-Path $aiLensBat) {
            & $aiLensBat start with Gemini
            return
        }
    }

    $isAiLensArg = $firstArg -in @("with", "gemini", "cs", "en", "sk", "de", "diag", "status", "stop", "cpu", "gpu", "low", "medium", "high")

    if (Test-Path $aiLensBat) {
        if ($isAiLensArg -or -not $AllArgs -or $AllArgs.Count -eq 0) {
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
    $scriptDir = $PSScriptRoot
    if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
    $aiLensBat = Join-Path $scriptDir "ai-lens.bat"
    if (-not (Test-Path $aiLensBat)) {
        $aiLensBat = ".\ai-lens.bat"
    }
    & $aiLensBat start with Gemini
}

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

        # start with gemini
        if ($line -match '(?i)^\s*(?:(?:(?:\.\\)?ai-lens(?:\.bat)?\s+)?start(?:\.bat|\.ps1)?|(?:\.\\)?start(?:\.bat|\.ps1)?)\s+with\s+gemini.*$') {
            $newLine = ".\ai-lens.bat start with Gemini"
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        # @\ CPU / && CPU
        elseif ($line -match 'ai-lens.*(?<!["''])@\\') {
            $newLine = $line -replace '(?<!["''])@\\', '"@\"'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        elseif ($line -match 'ai-lens.*&&\s*cpu') {
            $newLine = $line -replace '&&\s*cpu', '"@\"'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
    Write-Host "[AI Lens] Podpora pro '.\ai-lens.bat start with Gemini' a '@\' byla úspěšně aktivována v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] Spuštění Gemini API režimu: .\ai-lens.bat start with Gemini" -ForegroundColor Yellow
}

# Auto-persist into PowerShell Profile
try {
    $profPath = $PROFILE
    if ($profPath) {
        $profDir = Split-Path -Parent $profPath
        if (-not (Test-Path $profDir)) {
            New-Item -ItemType Directory -Path $profDir -Force | Out-Null
        }
        $profileHook = @'

# AI Lens Syntax & Launcher Support
$aiLensHelper = Join-Path $env:USERPROFILE "ai-lens-1\enable-cpu-syntax.ps1"
if (Test-Path $aiLensHelper) {
    . $aiLensHelper
}
'@
        if (-not (Test-Path $profPath)) {
            Set-Content -Path $profPath -Value $profileHook -Encoding utf8
        } else {
            $existing = Get-Content -Path $profPath -Raw
            if ($existing -notmatch 'enable-cpu-syntax\.ps1') {
                Add-Content -Path $profPath -Value $profileHook -Encoding utf8
            }
        }
    }
} catch {
    # Ignore profile write permission issues
}

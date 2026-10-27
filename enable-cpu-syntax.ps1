# enable-cpu-syntax.ps1
# Umoznuje pouzivat syntaxi:
#   .\ai-lens.bat start with Gemini(version) (api_key)
#   .\ai-lens.bat start with Gemini(version) <api_key>
#   start with Gemini(3.8) (api_key)
#   start with Gemini(3.8) <api_key>
#   start 3.8
#   start 3.8 (api_key) / start 3.8 <api_key> / start 3.8 "api_key"
#   gemini( api_key ) / gemini <api_key>
#   @\ a && CPU
# primo ve Windows PowerShell bez chyb v parseru a bez nutnosti rucnich uvozovek.

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
    $isAiLensArg = $firstArg -in @("with", "gemini", "3.8", "3.5", "2.5", "2.0", "1.5", "flash", "pro", "cs", "en", "sk", "de", "diag", "status", "stop", "cpu", "gpu", "low", "medium", "high") -or ($firstArg -like "gemini*") -or ($firstArg -like "3.*") -or ($firstArg -like "2.*")

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
    $batPath = Join-Path $scriptDir "Gemini.bat"
    if (-not (Test-Path $batPath)) {
        foreach ($cand in @(
            "$env:USERPROFILE\ai-lens-1\Gemini.bat",
            "$env:USERPROFILE\Desktop\ai-lens-main\Gemini.bat",
            "$env:USERPROFILE\Desktop\ai-lens-main3\Gemini.bat",
            "$env:USERPROFILE\ai-lens\Gemini.bat"
        )) {
            if (Test-Path $cand) {
                $batPath = $cand
                break
            }
        }
    }
    if (-not (Test-Path $batPath)) {
        $batPath = ".\Gemini.bat"
    }
    & $batPath @AllArgs
}

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

        # 1. start with Gemini(version) (api_key) / <api_key> / "api_key" / etc.
        if ($line -match '(?i)^\s*(?:(?:(?:\.\\)?ai-lens(?:\.bat)?\s+)?start(?:\.bat|\.ps1)?|(?:\.\\)?start(?:\.bat|\.ps1)?)\s+with\s+gemini(?:\((.*?)\)|<(.*?)>)?(?:\s+[\(<]\s*([^>\)]*?)\s*[\)>]|\s+"?(.*?)"?)?\s*$') {
            $verParen = if ($Matches[1]) { $Matches[1].Trim() } elseif ($Matches[2]) { $Matches[2].Trim() } else { "" }
            $keyRaw = if ($Matches[3]) { $Matches[3].Trim() } elseif ($Matches[4]) { $Matches[4].Trim().Trim('"').Trim("'") } else { "" }
            $verToken = if ($verParen) { "`"Gemini($verParen)`"" } else { "Gemini" }
            $keyToken = if ($keyRaw) { "`"$keyRaw`"" } else { "" }
            $newLine = ".\ai-lens.bat start with $verToken $keyToken".Trim()
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        # 2. start 3.8 / start 3.8 (api_key) / start 3.8 <api_key> / start 3.8 "api_key" / .\start 3.8
        elseif ($line -match '(?i)^\s*(?:(?:(?:\.\\)?ai-lens(?:\.bat)?\s+)?start(?:\.bat|\.ps1)?|(?:\.\\)?start(?:\.bat|\.ps1)?)\s+(\d+(?:\.\d+)?[a-z0-9\-]*(?:flash|pro)?)(?:\s+[\(<]\s*([^>\)]*?)\s*[\)>]|\s+([^\s]+))?\s*$') {
            $ver = $Matches[1].Trim()
            $key = if ($Matches[2]) { $Matches[2].Trim() } elseif ($Matches[3]) { $Matches[3].Trim().Trim('"').Trim("'") } else { "" }
            $keyToken = if ($key) { "`"$key`"" } else { "" }
            $newLine = ".\ai-lens.bat start $ver $keyToken".Trim()
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        # 3. gemini( api_key ) / gemini(3.8) (api_key) / gemini <api_key>
        elseif ($line -match '(?i)^\s*(?:(?:\.\\)?gemini(?:\.bat|\.ps1)?)\s*[\(<]\s*([^>\)]*?)\s*[\)>](?:\s+[\(<]\s*([^>\)]*?)\s*[\)>]|\s+(.*))?$') {
            $arg1 = $Matches[1].Trim().Trim('"').Trim("'")
            $extra = if ($Matches[2]) { "`"$($Matches[2].Trim())`"" } elseif ($Matches[3]) { $Matches[3].Trim() } else { "" }
            $newLine = ".\Gemini.bat `"$arg1`" $extra".Trim()
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        elseif ($line -match '^\s*gemini\s+(.*)$') {
            $rawArg = $Matches[1].Trim()
            $newLine = ".\Gemini.bat " + $rawArg
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        # 4. @\ CPU / && CPU
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
    Write-Host "[AI Lens] Podpora pro 'start with Gemini(version) (api_key)', 'start with Gemini(version) <api_key>', 'start 3.8', '@\' a 'gemini' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] PSReadLine neni k dispozici. V PowerShellu pouzijte: .\ai-lens.bat start with `"Gemini(3.8)`" `"<api_key>`"" -ForegroundColor Yellow
}

# Auto-persist into PowerShell Profile so new terminal windows have full support automatically
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

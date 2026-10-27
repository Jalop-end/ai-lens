# enable-cpu-syntax.ps1
# Umoznuje pouzivat syntaxi `gemini( api_key )`, `gemini <api_key>`, `@\` a `start with Gemini`
# primo v PowerShellu bez chyb v parseru a bez nutnosti rucnich uvozovek.

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        if ($line -match '^\s*gemini\s*\(\s*(.*?)\s*\)(.*)$') {
            $keyArg = $Matches[1].Trim().Trim('"').Trim("'")
            $extra = $Matches[2].Trim()
            $newLine = ".\Gemini.bat `"$keyArg`" $extra".Trim()
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        } elseif ($line -match '^\s*gemini\s+(.*)$') {
            $rawArg = $Matches[1].Trim()
            $newLine = ".\Gemini.bat " + $rawArg
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        } elseif ($line -match '^\s*start\s+with\s+gemini(.*)$') {
            $newLine = ".\ai-lens.bat start with Gemini" + $Matches[1]
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        } elseif ($line -match 'ai-lens.*(?<!["''])@\\') {
            $newLine = $line -replace '(?<!["''])@\\', '"@\"'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        } elseif ($line -match 'ai-lens.*&&\s*cpu') {
            $newLine = $line -replace '&&\s*cpu', '"@\"'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
    Write-Host "[AI Lens] Podpora pro 'gemini( api_key )', 'gemini <api_key>', '@\' a 'start with Gemini' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] PSReadLine neni k dispozici. V PowerShellu pouzijte: .\Gemini.bat `"<api_key>`" nebo .\ai-lens.bat cs High `"@\`"" -ForegroundColor Yellow
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
        $batPath = ".\Gemini.bat"
    }
    & $batPath @AllArgs
}

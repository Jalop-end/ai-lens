# enable-cpu-syntax.ps1
# Umoznuje pouzivat syntaxi `@\` i ve Windows PowerShell bez nutnosti uvozovek,
# a zaroven pridava primou podporu pro prikazy 'gemini "<api_key>"' a 'start with Gemini'.

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        if ($line -match '^\s*gemini\s+(.*)$') {
            $newLine = ".\Gemini.bat " + $Matches[1]
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
    Write-Host "[AI Lens] Podpora pro 'gemini <api_key>', '@\' a 'start with Gemini' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] PSReadLine neni k dispozici. V PowerShellu pouzijte: .\Gemini.bat `"<api_key>`" nebo .\ai-lens.bat cs High `"@\`"" -ForegroundColor Yellow
}

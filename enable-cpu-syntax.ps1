# enable-cpu-syntax.ps1
# Umoznuje pouzivat syntaxi `@\` i ve Windows PowerShell bez nutnosti uvozovek.
# Ve Windows PowerShell je znak @ rezervovany pro pole a splatting.
# Tento skript zaregistruje PSReadLine handler pro klavesu Enter, ktery pred odeslanim
# automaticky uzavre `@\` do uvozovek "@\" pro bezchybne zpracovani.

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        if ($line -match 'ai-lens.*(?<!["''])@\\') {
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
    Write-Host "[AI Lens] Podpora pro '@\' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] PSReadLine neni k dispozici. V PowerShellu pouzijte: .\ai-lens.bat cs High `"@\`"" -ForegroundColor Yellow
}

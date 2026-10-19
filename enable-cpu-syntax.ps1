# enable-cpu-syntax.ps1
# Umožňuje používat syntaxi `&& CPU` i ve Windows PowerShell 5.1
# Ve Windows PowerShell 5.1 není operátor && nativní (byl přidán až v PowerShell 7).
# Tento skript zaregistruje PSReadLine handler pro klávesu Enter, který před odesláním
# automaticky převede '&& CPU' na bezpečný parametr pro ai-lens.

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
        if ($line -match 'ai-lens.*&&\s*cpu') {
            $newLine = $line -replace '&&\s*cpu', '"&&" CPU'
            [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
            [Microsoft.PowerShell.PSConsoleReadLine]::Insert($newLine)
        }
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
    Write-Host "[AI Lens] Podpora pro '&& CPU' byla uspesne aktivovana v PowerShellu." -ForegroundColor Green
} else {
    Write-Host "[AI Lens] PSReadLine neni k dispozici. V PowerShell 5.1 pouzijte: .\ai-lens.bat cs High `"&&`" CPU nebo CMD." -ForegroundColor Yellow
}

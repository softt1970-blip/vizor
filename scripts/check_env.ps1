Write-Host "Проверка окружения VIZOR..." -ForegroundColor Cyan
Get-Process | Where-Object {$_.ProcessName -match "ollama|docker|code"} | Select-Object ProcessName, Id

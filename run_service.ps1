# Runs NewsRoom forever, restarting it if it crashes. Register with Task Scheduler (see README).
Set-Location -LiteralPath $PSScriptRoot
while ($true) {
    python -m newsroom.main
    Write-Host "NewsRoom exited ($LASTEXITCODE); restarting in 30s..."
    Start-Sleep -Seconds 30
}

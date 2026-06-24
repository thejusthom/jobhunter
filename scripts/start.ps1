# Start the server with Litestream replication (Windows).
# Usage: .\scripts\start.ps1

Set-Location (Split-Path $PSScriptRoot -Parent)

# Load .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}

# Restore DB from B2 if it doesn't exist locally (fresh device)
if (-not (Test-Path jobhunter.db)) {
    Write-Host "[litestream] No local DB found - restoring from B2..."
    & .\litestream.exe restore -config litestream.yml jobhunter.db
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[litestream] No backup found, starting fresh"
    }
}

Write-Host "[litestream] Starting replication + server..."
& .\litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"

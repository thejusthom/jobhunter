# Start the server (Windows). Backblaze/Litestream disabled - GitHub backup repo only.
# Usage: .\scripts\start.ps1

Set-Location (Split-Path $PSScriptRoot -Parent)

# Load .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}

# Fresh device with no local DB: pull the latest snapshot from the GitHub backup repo.
if (-not (Test-Path jobhunter.db)) {
    Write-Host "[backup] No local DB - restoring latest from GitHub backup repo..."
    python restore_db.py
}

Write-Host "[backend] Starting server (GitHub backup only; Backblaze disabled)..."
python -m uvicorn server:app --host 0.0.0.0 --port 8000

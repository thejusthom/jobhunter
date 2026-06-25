@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."
call venv\Scripts\activate.bat

:: Load .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

:: Backblaze/Litestream is disabled. Backups go to the private GitHub repo only
:: (manual "Back up now" in Settings, or backup_db.py). On a fresh device with no
:: local DB, pull the latest snapshot from the GitHub backup repo.
if not exist jobhunter.db (
    echo [backup] No local DB - restoring latest from GitHub backup repo...
    python restore_db.py
)

echo [backend] Starting server (GitHub backup only; Backblaze disabled)...
python server.py

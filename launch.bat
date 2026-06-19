@echo off
setlocal enabledelayedexpansion
title JobHunter Launcher
cd /d "%~dp0"

echo ========================================
echo   JobHunter - Starting all services
echo ========================================
echo.

:: Activate venv
call venv\Scripts\activate.bat

:: Load .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    set "%%a=%%b"
)

:: Restore DB from B2 if missing (fresh device)
if not exist jobhunter.db (
    echo [litestream] No local DB - restoring from Backblaze B2...
    litestream.exe restore -config litestream.yml jobhunter.db
    if errorlevel 1 echo [litestream] No backup found, starting fresh
)

:: Safety check: don't replicate an empty DB (would overwrite real backup)
set SAFE_TO_REPLICATE=1
if exist jobhunter.db (
    for /f %%s in ('python -c "import sqlite3;c=sqlite3.connect('jobhunter.db');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2^>nul') do set JOB_COUNT=%%s
    if not defined JOB_COUNT set JOB_COUNT=0
    if "!JOB_COUNT!"=="0" (
        echo [WARNING] DB has 0 jobs - starting WITHOUT replication to protect B2 backup.
        echo [WARNING] If this is expected, delete jobhunter.db and restart to restore from B2.
        set SAFE_TO_REPLICATE=0
    )
)

:: Start frontend dev server in background
echo [frontend] Starting Vite dev server...
start "JobHunter Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   Press Ctrl+C to stop the server.
echo ========================================
echo.

if "!SAFE_TO_REPLICATE!"=="1" (
    echo [backend] Starting server with Litestream replication (!JOB_COUNT! jobs in DB)...
    litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"
) else (
    echo [backend] Starting server WITHOUT replication (empty DB protection)...
    python -m uvicorn server:app --host 0.0.0.0 --port 8000
)

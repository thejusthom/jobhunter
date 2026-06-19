@echo off
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

:: Start frontend dev server in background
echo [frontend] Starting Vite dev server...
start "JobHunter Frontend" cmd /c "cd frontend && npm run dev"

:: Start backend with Litestream replication
echo [backend] Starting server with Litestream replication...
echo.
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   DB sync:  Backblaze B2 (every 10s)
echo.
echo   Press Ctrl+C to stop the server.
echo ========================================
echo.

litestream.exe replicate -config litestream.yml -exec "python -m uvicorn server:app --host 0.0.0.0 --port 8000"

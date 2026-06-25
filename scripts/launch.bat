@echo off
setlocal enabledelayedexpansion
title JobHunter Launcher
cd /d "%~dp0.."

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

:: Backblaze/Litestream disabled - GitHub backup repo only.
:: On a fresh device with no local DB, pull the latest snapshot from GitHub.
if not exist jobhunter.db (
    echo [backup] No local DB - restoring latest from GitHub backup repo...
    python restore_db.py
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

echo [backend] Starting server (GitHub backup only; Backblaze disabled)...
python -m uvicorn server:app --host 0.0.0.0 --port 8000

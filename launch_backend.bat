@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat

:: Load .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

:: Restore DB from B2 if missing
if not exist jobhunter.db (
    echo [litestream] No local DB - restoring from B2...
    litestream.exe restore -config litestream.yml jobhunter.db
    if errorlevel 1 echo [litestream] No backup found, starting fresh
)

echo [backend] Starting server with Litestream replication...
litestream.exe replicate -config litestream.yml -exec "python server.py"

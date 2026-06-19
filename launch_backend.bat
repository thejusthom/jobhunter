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

:: Safety check: don't replicate an empty DB (would overwrite real backup)
if exist jobhunter.db (
    for /f %%s in ('python -c "import sqlite3;c=sqlite3.connect('jobhunter.db');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2^>nul') do set JOB_COUNT=%%s
    if not defined JOB_COUNT set JOB_COUNT=0
    if "!JOB_COUNT!"=="0" (
        echo [WARNING] DB has 0 jobs - starting WITHOUT replication to protect B2 backup.
        echo [WARNING] If this is expected, delete jobhunter.db and restart to restore from B2.
        python server.py
        exit /b
    )
)

echo [backend] Starting server with Litestream replication (%JOB_COUNT% jobs in DB)...
litestream.exe replicate -config litestream.yml -exec "python server.py"

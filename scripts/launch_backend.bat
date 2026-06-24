@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."
call venv\Scripts\activate.bat

:: Load .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

:: Always restore latest DB from B2 before starting
:: This ensures we never replicate stale data back to B2
echo [litestream] Pulling latest DB from B2...
if exist jobhunter.db (
    :: Backup current local DB in case restore fails
    copy /y jobhunter.db jobhunter.db.local-backup >nul 2>&1
    litestream.exe restore -config litestream.yml -o jobhunter.db.b2 jobhunter.db 2>nul
    if exist jobhunter.db.b2 (
        :: Compare: use whichever has more jobs
        for /f %%a in ('python -c "import sqlite3;c=sqlite3.connect('jobhunter.db');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2^>nul') do set LOCAL_JOBS=%%a
        for /f %%a in ('python -c "import sqlite3;c=sqlite3.connect('jobhunter.db.b2');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2^>nul') do set B2_JOBS=%%a
        if not defined LOCAL_JOBS set LOCAL_JOBS=0
        if not defined B2_JOBS set B2_JOBS=0
        echo [litestream] Local: !LOCAL_JOBS! jobs, B2: !B2_JOBS! jobs
        if !B2_JOBS! GEQ !LOCAL_JOBS! (
            echo [litestream] Using B2 version (newer or equal)
            move /y jobhunter.db.b2 jobhunter.db >nul
        ) else (
            echo [litestream] Keeping local version (has more data)
            del jobhunter.db.b2 >nul 2>&1
        )
    ) else (
        echo [litestream] No B2 backup found, using local DB
    )
) else (
    echo [litestream] No local DB - restoring from B2...
    litestream.exe restore -config litestream.yml jobhunter.db
    if errorlevel 1 echo [litestream] No backup found, starting fresh
)

:: Safety check: don't replicate an empty DB
for /f %%s in ('python -c "import sqlite3;c=sqlite3.connect('jobhunter.db');print(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])" 2^>nul') do set JOB_COUNT=%%s
if not defined JOB_COUNT set JOB_COUNT=0
if "!JOB_COUNT!"=="0" (
    echo [WARNING] DB has 0 jobs - starting WITHOUT replication to protect B2 backup.
    python server.py
    exit /b
)

echo [backend] Starting server with Litestream replication (!JOB_COUNT! jobs)...
litestream.exe replicate -config litestream.yml -exec "python server.py"

@echo off
echo Closing Chrome gracefully...
taskkill /IM chrome.exe >nul 2>&1
timeout /t 5 /nobreak >nul

echo Starting Chrome with remote debugging on port 9222...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data" ^
    --profile-directory=Default ^
    --no-first-run ^
    --restore-last-session

echo Chrome started! You can now use Auto Apply in JobHunter.
echo (Keep this window open or close it - doesn't matter)
timeout /t 3 /nobreak >nul

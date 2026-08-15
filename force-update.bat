@echo off
title FORCE UPDATE - PES Bot (no clicking required)
cd /d "%~dp0"

echo ============================================================
echo  FORCE UPDATE - update without any clicking
echo  Use on machines stuck at the "New version detected" popup
echo ============================================================
echo.

:: [1/3] ปิดเฉพาะ "บอท PES" เท่านั้น (login.py / auto_update.py ที่ค้าง)
::       ห้ามใช้ taskkill /im python.exe เด็ดขาด — จะไปฆ่า agent.py ของระบบ remote
::       ทำให้เครื่องหลุดจากหน้า dashboard ทั้งฟลีต
echo [1/3] Closing PES bot only (remote agent is NOT touched) ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*login.py*' -or $_.CommandLine -like '*auto_update.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] Running silent update (mode from SILENT_UPDATE_MODE in config.py) ...
py auto_update.py --silent

echo [3/3] Making sure the bot is running again ...
timeout /t 15 /nobreak >nul
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*login.py*' }) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo      Bot is not running - starting login.bat
    start "" login.bat
) else (
    echo      Bot was already relaunched by the updater.
)

:: [4/4] ปลุก agent ของระบบ remote กลับมาถ้ามันไม่ได้รันอยู่
::       (เผื่อเครื่องเคยโดน force-update.bat เวอร์ชันเก่าฆ่า agent ทิ้งไป)
echo [4/4] Making sure the remote agent is alive ...
powershell -NoProfile -Command "if (-not (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*agent.py*' })) { $a = Get-ChildItem -Path C:\Users\*\Downloads\remote\remote-file\agent.py,C:\remote-file\agent.py,D:\remote-file\agent.py -ErrorAction SilentlyContinue | Select-Object -First 1; if ($a) { Start-Process pythonw -ArgumentList $a.FullName -WorkingDirectory $a.DirectoryName } }" >nul 2>&1

echo.
echo Done - this window closes in 5 seconds.
timeout /t 5 /nobreak >nul
exit

@echo off
title Sync Time -^> Bangkok (UTC+7)

:: ── ขอสิทธิ์ Administrator อัตโนมัติ (ตั้งเวลา/ไทม์โซนต้องใช้ admin) ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo =========================================
echo   SYNC TIME -^> BANGKOK (Asia/Bangkok, UTC+7)
echo =========================================
echo.

:: 1) ตั้ง timezone เป็น Bangkok
echo [1/4] Setting timezone: SE Asia Standard Time (Bangkok)...
tzutil /s "SE Asia Standard Time"

:: 2) เปิดบริการ Windows Time (w32time)
echo [2/4] Starting Windows Time service...
sc config w32time start= auto >nul 2>&1
net start w32time >nul 2>&1

:: 3) ตั้งค่า NTP server (time.windows.com + pool.ntp.org + th.pool.ntp.org)
echo [3/4] Configuring NTP servers...
w32tm /config /manualpeerlist:"time.windows.com,0x9 pool.ntp.org,0x9 th.pool.ntp.org,0x9" /syncfromflags:manual /update >nul 2>&1

:: 4) sync เวลาจริงจาก internet
echo [4/4] Resyncing clock from internet...
net stop w32time >nul 2>&1
net start w32time >nul 2>&1
w32tm /resync /force
if %errorlevel% neq 0 (
    echo    First resync failed, retrying in 3s...
    timeout /t 3 /nobreak >nul
    w32tm /resync /force
)

echo.
echo -----------------------------------------
echo  Timezone :
tzutil /g
echo.
echo  Date     : %date%
echo  Time     : %time%
echo -----------------------------------------
echo.
echo =========================================
echo   DONE! Clock synced to Bangkok time.
echo =========================================
echo.
pause

@echo off
title PES Bot Runner with AutoUpdate

:loop
echo ------------------------------------------
echo        STEP 0: Cleanup (logs + stale python)...
echo ------------------------------------------
:: ลบ log เก่าทิ้ง + ฆ่า python ที่รัน login.py ค้างแรม (ไม่งั้นโหลด module เก่าค้าง ไม่ยอมอัปเดต)
powershell -NoProfile -Command "Remove-Item '%~dp0logs\*.txt' -Force -ErrorAction SilentlyContinue; try { $ps = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" -ErrorAction Stop } catch { try { $ps = Get-WmiObject Win32_Process -Filter \"Name='python.exe'\" -ErrorAction Stop } catch { $ps = @() } }; $ps | Where-Object { $_.CommandLine -like '*login.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul
:: ปิด adb server ค้าง (บางที adb เก่าแขวน แคปจอ/กดไม่ได้) — บอทจะเปิดใหม่เอง
"%~dp0adb\adb.exe" kill-server >nul 2>&1
taskkill /f /im adb.exe >nul 2>&1

echo ------------------------------------------
echo        STEP 1: Checking for updates...
echo ------------------------------------------
py auto_update.py
set UPD=%errorlevel%

:: exit 10 = อัปเดตเสร็จแล้ว -> วนกลับไปเช็ค/เริ่มใหม่เองอัตโนมัติ (ไม่ต้องมีคนกด)
if "%UPD%"=="10" (
    echo.
    echo =======================================================
    echo  [Updater] Update completed! Restarting automatically...
    echo =======================================================
    timeout /t 3 /nobreak >nul
    goto loop
)

echo.
echo ------------------------------------------
echo        STEP 2: Starting PES Bot...
echo ------------------------------------------
py login.py
set BOT=%errorlevel%

:: exit 12 = ตัวอัปเดตเงียบกำลังทำงาน มันจะเปิด login.bat ให้เองหลังอัปเดตเสร็จ
if "%BOT%"=="12" (
    echo [Updater] Silent update in progress - it will relaunch this bot automatically.
    exit
)

:: exit 0 = ผู้ใช้กดปิดโปรแกรมเอง -> จบเลย ไม่ต้องเปิดซ้ำ
if "%BOT%"=="0" (
    echo Bot closed by user. Bye.
    exit
)

:: อื่นๆ = บอทดับผิดปกติ (crash) -> เปิดใหม่เองใน 15 วิ (ปิดหน้าต่างนี้เพื่อหยุด)
echo.
echo [Runner] Bot exited with code %BOT% - restarting in 15s...
echo          (Close this window if you want to stop the bot)
timeout /t 15 >nul
goto loop

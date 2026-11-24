@echo off
title Clear Backup Folders
cd /d "%~dp0"

echo =========================================
echo       CLEARING BACKUP FOLDERS...
echo =========================================
echo.

echo [1/3] Killing bot processes (python/adb) that may lock files...
:: *** ห้ามใช้ taskkill /f /im python.exe เด็ดขาด ***
::  มันฆ่า python ทุกตัวในเครื่อง รวม agent.py ของระบบ remote และ agent-sidecar.py
::  ที่คอยปลุก agent ด้วย -> กดปุ่มนี้ทีไรเครื่องหลุดจากหน้า dashboard ทันที
::  ฆ่าเฉพาะโปรเซสของบอทเท่านั้น โดยดูจาก command line และกัน agent ไว้ชัดๆ
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*login.py*' -or $_.CommandLine -like '*auto_update.py*' -or $_.CommandLine -like '*main-pes.py*' -or $_.CommandLine -like '*cap-id.py*' -or $_.CommandLine -like '*checkTH.py*') -and $_.CommandLine -notlike '*agent.py*' -and $_.CommandLine -notlike '*agent-sidecar.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
taskkill /f /im adb.exe     >nul 2>&1
timeout /t 1 /nobreak >nul
echo.

set FOLDERS=backup backup-id found-hero no-hero login-success login-failed random-fail fast-random file-error run-file timeout logs check-coin debug-ocr

echo [2/3] Deleting folders...
for %%F in (%FOLDERS%) do (
    if exist "%%F" (
        rem ลบไฟล์ทั้งหมด (read-only ก็ลบ) ก่อน แล้วค่อยลบโฟลเดอร์ — กันเคสไฟล์ล็อค rd เงียบ
        del /f /s /q "%%F\*.*" >nul 2>&1
        rd /s /q "%%F" 2>nul
        if exist "%%F" (
            rem ถ้ายังลบไม่ออก ลองอีกรอบหลังรอครึ่งวิ (เคส handle ค้าง)
            timeout /t 1 /nobreak >nul
            rd /s /q "%%F" 2>nul
        )
        if exist "%%F" (
            echo  [FAIL] Still locked: %%F   ^<-- ปิดบอท/Explorer ที่เปิดโฟลเดอร์นี้แล้วลองใหม่
        ) else (
            echo  [OK] Deleted folder: %%F
        )
    ) else (
        echo  [--] Not found: %%F
    )
)

echo.
echo [3/3] Clearing files in input-id...
if exist "input-id" (
    del /f /q "input-id\*.*" 2>nul
    echo  [OK] Cleared files in: input-id
) else (
    echo  [--] Not found: input-id
)

echo.
echo =========================================
echo   All folders have been cleared successfully!
echo =========================================
pause

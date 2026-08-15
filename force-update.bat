@echo off
title FORCE UPDATE - PES Bot (no clicking required)
cd /d "%~dp0"

echo ============================================================
echo  FORCE UPDATE - อัปเดตแบบไม่ต้องกดอะไรเลย
echo  ใช้กับเครื่องที่ค้างอยู่หน้าต่าง "ตรวจพบเวอร์ชันใหม่"
echo ============================================================
echo.

echo [1/3] ปิดหน้าต่างอัปเดตที่ค้างรอคนกด + บอทที่รันอยู่...
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe  >nul 2>&1
taskkill /f /im py.exe      >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] อัปเดตแบบเงียบ (ใช้โหมดจาก SILENT_UPDATE_MODE ใน config.py)...
py auto_update.py --silent

echo [3/3] ตรวจว่าบอทถูกเปิดใหม่แล้วหรือยัง...
timeout /t 15 /nobreak >nul
tasklist | find /i "python.exe" >nul
if errorlevel 1 (
    echo      ยังไม่มีบอทรันอยู่ - เปิด login.bat ให้เอง
    start "" login.bat
) else (
    echo      บอทถูกเปิดใหม่โดยตัวอัปเดตแล้ว
)

echo.
echo เสร็จแล้ว - หน้าต่างนี้จะปิดใน 5 วินาที
timeout /t 5 /nobreak >nul
exit

@echo off
title PES Bot Runner with AutoUpdate

echo ──────────────────────────────────────────
echo        STEP 1: Checking for updates...
echo ──────────────────────────────────────────
py auto_update.py

:: ตรวจสอบค่า Exit Code ของระบบอัปเดต
:: ถ้า errorlevel = 10 แปลว่าอัปเดตสำเร็จ ให้ปิดโปรแกรม (Kill) ทันทีเพื่อให้กดเปิดใหม่
if %errorlevel% equ 10 (
    echo.
    echo =======================================================
    echo  [Updater] อัปเดตเสร็จแล้ว! กรุณาเปิด login.bat ใหม่อีกครั้งเพื่อใช้งานบอทเวอร์ชันล่าสุด
    echo =======================================================
    pause
    exit
)

echo.
echo ──────────────────────────────────────────
echo        STEP 2: Starting PES Bot...
echo ──────────────────────────────────────────
py login.py
pause
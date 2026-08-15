@echo off
:: ════════════════════════════════════════════════════════════════════
::  setup-autostart.bat — ติดตั้งให้เครื่องนี้ "เปิดบอทเอง + อัปเดตเอง"
::  รันครั้งเดียวต่อเครื่อง (คลิกขวา > Run as administrator)
::
::  ติดตั้ง 2 งานใน Task Scheduler:
::    1) PES Bot AutoStart — เปิด login.bat ทุกครั้งที่ล็อกอินเข้าเครื่อง
::    2) PES Bot Watchdog  — ทุก 10 นาที ถ้าไม่มีบอทรันอยู่ = เปิด login.bat ให้
::
::  ผลลัพธ์: เครื่องที่ไม่ได้เปิด login.bat ไว้ จะถูกเปิดให้เองภายใน 10 นาที
::           และ login.bat จะเช็ค/ดึงอัปเดตให้อัตโนมัติในขั้นตอนแรกอยู่แล้ว
:: ════════════════════════════════════════════════════════════════════
cd /d "%~dp0"
title Setup AutoStart - PES Bot

echo ============================================================
echo  ติดตั้ง AutoStart + Watchdog ให้เครื่องนี้
echo  โฟลเดอร์บอท: %~dp0
echo ============================================================
echo.

echo [1/2] สร้างงาน "PES Bot AutoStart" (เปิดตอนล็อกอิน)...
schtasks /create /tn "PES Bot AutoStart" /tr "\"%~dp0login.bat\"" /sc onlogon /rl highest /f
if errorlevel 1 echo      ^>^> ล้มเหลว - ต้องรันไฟล์นี้แบบ Run as administrator

echo.
echo [2/2] สร้างงาน "PES Bot Watchdog" (เช็คทุก 10 นาที)...
schtasks /create /tn "PES Bot Watchdog" /tr "\"%~dp0watchdog.bat\"" /sc minute /mo 10 /rl highest /f
if errorlevel 1 echo      ^>^> ล้มเหลว - ต้องรันไฟล์นี้แบบ Run as administrator

echo.
echo ============================================================
echo  เสร็จแล้ว! ตรวจสอบ/ลบงานได้ด้วยคำสั่ง:
echo    schtasks /query /tn "PES Bot AutoStart"
echo    schtasks /query /tn "PES Bot Watchdog"
echo    schtasks /delete /tn "PES Bot Watchdog" /f
echo ============================================================
pause

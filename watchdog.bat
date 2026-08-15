@echo off
:: ════════════════════════════════════════════════════════════════
::  watchdog.bat — เช็คว่าบอทยังรันอยู่ไหม ไม่รันก็เปิดให้เอง
::  ถูกเรียกโดย Task Scheduler ทุก 10 นาที (ติดตั้งด้วย setup-autostart.bat)
::  พอบอทถูกเปิด มันจะเช็คอัปเดตเองในขั้นตอนแรกของ login.bat อยู่แล้ว
:: ════════════════════════════════════════════════════════════════
cd /d "%~dp0"

:: หา process python ที่กำลังรัน login.py อยู่จริงๆ (ไม่นับสคริปต์ python ตัวอื่น)
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*login.py*' }) { exit 0 } else { exit 1 }"

if errorlevel 1 (
    echo [Watchdog] ไม่พบบอทที่รันอยู่ - เปิด login.bat ให้ใหม่
    start "" "%~dp0login.bat"
) else (
    echo [Watchdog] บอทยังรันอยู่ปกติ
)
exit

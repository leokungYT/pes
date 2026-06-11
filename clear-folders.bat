@echo off
title Clear Backup Folders
cd /d "%~dp0"

echo =========================================
echo       CLEARING BACKUP FOLDERS...
echo =========================================
echo.

set FOLDERS=backup backup-id found-hero no-hero input-id login-success login-failed random-fail fast-random file-error run-file timeout logs check-coin debug-ocr

for %%F in (%FOLDERS%) do (
    if exist "%%F" (
        rd /s /q "%%F"
        echo  [OK] Deleted folder: %%F
    ) else (
        echo  [--] Not found: %%F
    )
)

echo.
echo =========================================
echo   All folders have been cleared successfully!
echo =========================================
pause

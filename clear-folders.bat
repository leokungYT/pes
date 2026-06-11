@echo off
title Clear Backup Folders
cd /d "%~dp0"

echo =========================================
echo       CLEARING BACKUP FOLDERS...
echo =========================================
echo.

set FOLDERS=backup backup-id found-hero no-hero login-success login-failed random-fail fast-random file-error run-file timeout logs check-coin debug-ocr

for %%F in (%FOLDERS%) do (
    if exist "%%F" (
        rd /s /q "%%F"
        echo  [OK] Deleted folder: %%F
    ) else (
        echo  [--] Not found: %%F
    )
)

if exist "input-id" (
    del /q "input-id\*.*" 2>nul
    echo  [OK] Cleared files in: input-id
) else (
    echo  [--] Not found: input-id
)

echo.
echo =========================================
echo   All folders have been cleared successfully!
echo =========================================
pause

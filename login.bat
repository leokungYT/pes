@echo off
title PES Bot Runner with AutoUpdate

echo ------------------------------------------
echo        STEP 1: Checking for updates...
echo ------------------------------------------
py auto_update.py

:: Check the exit code from auto_update.py
:: If exit code is 10, the bot was updated successfully. Close current process to restart.
if %errorlevel% equ 10 (
    echo.
    echo =======================================================
    echo  [Updater] Update completed successfully! 
    echo  Please restart login.bat to run the latest version.
    echo =======================================================
    pause
    exit
)

echo.
echo ------------------------------------------
echo        STEP 2: Starting PES Bot...
echo ------------------------------------------
py login.py
pause
@echo off
chcp 65001 >nul
title Ranger+Gear Dependency Installer
cd /d "%~dp0"

echo.
echo ====================================================
echo  Ranger+Gear Dependency Installer
echo ====================================================
echo.

:: Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo [INFO] Download Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/7] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [2/7] Installing OpenCV...
pip install opencv-python

echo.
echo [3/7] Installing NumPy...
pip install numpy

echo.
echo [4/7] Installing Colorama...
pip install colorama

echo.
echo [5/7] Installing Pillow (Image processing)...
pip install Pillow

echo.
echo [6/7] Installing CustomTkinter (Modern GUI)...
pip install customtkinter

echo.
echo [7/7] Installing EasyOCR (Gear OCR)...
pip install easyocr

echo.
echo ====================================================
echo  [8/8] Checking Tesseract-OCR
echo ====================================================
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo  [OK] Tesseract found at C:\Program Files\Tesseract-OCR
) else (
    echo  [MISSING] Tesseract is NOT installed!
    echo  The bot needs it at: C:\Program Files\Tesseract-OCR\tesseract.exe
    echo.
    echo  Download and install ^(default path, install once per machine^):
    echo  https://github.com/UB-Mannheim/tesseract/wiki
    echo.
    echo  NOTE: Tesseract is no longer shipped inside this repo -
    echo        it made every auto-update download 28 MB instead of ~7 MB.
)

echo.
echo ====================================================
echo  [IMPORTANT] Visual C++ Redistributable
echo ====================================================
echo.
echo  If EasyOCR/PyTorch shows DLL errors, install this:
echo  https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo ====================================================
echo  Installation Complete!
echo ====================================================
echo.
pause

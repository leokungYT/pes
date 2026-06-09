# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PES Mobile Bot is a Python automation tool for the Pro Evolution Soccer (PES) mobile game. It uses Android Debug Bridge (ADB) to connect to mobile devices and automate gameplay sequences like logins, gacha rolls, hero searches, and item collection. The bot supports multi-device automation with a modern GUI built using CustomTkinter.

**Version:** 2.0.12 (see `version.txt`)

## Core Components

### Main Entry Points

1. **`main-pes.py`** (2,303 lines)
   - Primary GUI application using CustomTkinter
   - Multi-device connection and management via ADB
   - Orchestrates the box opening sequence (play1→play31, box1→box4)
   - Real-time device monitoring with live screenshots
   - Features: device selection, backup file management, reset controls

2. **`login.py`** (4,454 lines, largest module)
   - Core automation logic for PES gameplay sequences
   - Handles OCR-based detection using Tesseract and EasyOCR
   - Manages complex state machine: login flow, gacha sequences, hero search, quest completion
   - Thread-safe device handling with custom exception hierarchy
   - Loads device-specific image templates from `img/` directory
   - Configuration driven by `config.py` imports

### Configuration & Setup

- **`config.py`** (210 lines)
  - Master configuration file with Thai-language comments
  - Control flags: `EVENT_IMG`, `DO_BOX`, `DO_GACHA`, `FIND_HERO`, `GACHA_FREE`, `NOSCAN`, `SKIPANIMATION`
  - Directory paths: `IMG_DIR` (img/), `INPUT_DIR` (input-id/), `LOGIN_SUCCESS_DIR` (login-success/)
  - Hero lists for backup and search: `HERO_LIST`, `HERO_LIST_FREE`, `list_find_hero`
  - OCR and coin checking toggles: `DEBUG_OCR`, `CHECK_COIN`
  - Auto-update behavior: `SILENT_UPDATE_MODE`, `OVERWRITE_CONFIG_ON_UPDATE`
  - Optional sequences: `GETCODE`, `GETQUEST`

- **`config_gen.py`** (95 lines)
  - Generates UI dialogs for live config editing (without file writes)
  - Used by main-pes.py's config dialog feature

### Utility & Support Files

- **`auto_update.py`** (356 lines)
  - GitHub-based version checking (reads `version.txt` from main branch)
  - Downloads and extracts latest ZIP from repo releases
  - Shows update dialog with upgrade/skip options

- **`login_new.py`** (3,064 lines)
  - Alternate/legacy login implementation
  - Likely used for experimental features or fallback

- **Test Files**
  - `test_questfive.py`: Tests quest-related image recognition
  - `test_find_hero_ocr.py`: Tests hero-finding OCR logic
  - `test_ocr.py`: General OCR testing
  - `test_drag.py`: Tests drag/swipe mechanics
  - `fix.py`, `patch_*.py`: Hotfixes and patches for specific issues

### Image Assets & Data Flow

- **`img/` directory** (~90 BMP template images)
  - Game state detection: `play1.bmp` through `play31.bmp` (main gameplay flow markers)
  - UI elements: `cancel.bmp`, `download.bmp`, `icon.bmp`, `namesom.bmp`
  - Gacha sequences: `gacha1.bmp` through `gacha5.bmp`, `gachafree1.bmp`, `gachafree2.bmp`
  - Hero detection: `heroo1.bmp`, `heroo2.bmp`, `heroo3.bmp`
  - Error/fix screens: `fixloading.bmp`, `fixnet.bmp`, `fixalert*.bmp` (for error recovery)
  - Final sequences: `fin1.bmp` through `fin8.bmp` (hero search flow)
  - Quest mode: `img/getquest/` subdirectory with quest templates
  - Checkpoint markers: `checkpointlogin.bmp`, `checkpointgacha.bmp`, `checkpointfind.bmp`, `checkpointcoin.bmp`

- **`input-id/` directory** (runtime)
  - Device-specific login credentials (text files with user IDs)

- **Output directories** (created by login.py)
  - `backup-id/`: Successful hero drops from main gacha
  - `backup/`: Binary backup files (.dat format)
  - `login-success/`: Successful login sessions
  - `fast-random/`: Quick hero output when NOSCAN=1
  - `no-hero/`: Sessions where no target hero was found
  - `found-hero/`: Sessions where target hero was found
  - `timeout/`: Sessions that exceeded timeout
  - `login-failed/`: Failed login attempts
  - `file-error/`: File processing errors
  - `random-fail/`: Unexplained failures

## Technology Stack

**Core Libraries:**
- `opencv-python` (cv2): Image template matching for game state detection
- `numpy`: Image processing
- `pytesseract`: OCR text extraction (configured to use Windows Tesseract-OCR installation)
- `easyocr`: Alternative OCR engine (fallback if Tesseract unavailable)
- `ppadb`: Pure Python ADB client for device communication

**GUI:**
- `customtkinter` (ctk): Modern dark-themed UI framework
- `tkinter`: Standard Python GUI library (fallback)
- `PIL`: Image loading and display

**Other:**
- `colorama`: Colored terminal output
- `torch`: Optional ML library (disabled to single-thread to reduce CPU contention)

## Key Architectural Patterns

### Multi-Device Threading
- Each connected device runs in its own thread
- Global `_gui_queue` provides thread-safe communication to GUI
- `file_pick_lock` and `ocr_lock` prevent race conditions when multiple devices access shared resources (like OCR engine)
- Device state tracked in global dicts: `DEVICE_RESET_FLAGS`, `DEVICE_FILE_ASSIGNMENTS`, `DEVICE_LAST_GAME_CHECK`

### OCR and CPU Management
- Thread count forced to 1 across OpenCV, MKL, BLAS, Torch to prevent CPU thrashing
- OCR operations serialized via `ocr_lock` (only one device performs OCR at a time)
- Image template caching (`IMAGE_CACHE`) to avoid redundant disk reads

### Image Matching & Template Detection
- `img_search()` function uses OpenCV's `matchTemplate()` with normalized cross-correlation (TM_CCOEFF_NORMED)
- Threshold of 0.8 by default; configurable
- Groups overlapping matches using `cv2.groupRectangles()`
- Returns center coordinates of detected templates

### State Machine (login.py)
- Navigates through predefined game screens using template detection
- Exception-based control flow:
  - `DeviceResetException`: Triggers device restart
  - `CycleTimeoutException`: Timeout handling
  - `SellScreenException`: Unexpected screen state
  - `RestartFromQuest8Exception`: Quest mode recovery

### Configuration-Driven Behavior
- Feature toggles in `config.py` enable/disable entire sequences without code changes
- Sequences are modular: LOGIN → (BOX) → (GACHA) → (GACHA_FREE) → (FIND_HERO) → (GETQUEST)
- List-based hero names with auto-duplicate detection (e.g., "Lamine=x2")

## Development Workflow

### Adding a New Game Sequence

1. Capture BMP screenshots of each state transition (place in `img/` with naming convention like `seq1.bmp`, `seq2.bmp`)
2. Add configuration flag in `config.py` (e.g., `DO_NEWSEQ = 0`)
3. Add sequence handler in `login.py` with template matching loop:
   ```python
   while time.time() < deadline:
       img = get_screen_capture(device)
       if img_search(img, os.path.join(IMG_DIR, "seq1.bmp")):
           device.shell("input tap x y")
       time.sleep(0.5)
   ```
4. Hook into main flow by importing config and calling sequence function

### Modifying OCR Recognition

- Test script: `test_ocr.py` (loads and processes test images)
- Region-based OCR uses `Region(x, y, width, height)` class
- OCR results are cached and logged to `logs/` if `DEBUG_OCR=1`
- Switch engines: Tesseract (faster, offline) vs. EasyOCR (more accurate, requires downloads)

### Multi-Device Testing

- Devices auto-discovered via ADB (list shown in GUI)
- GUI displays real-time device status: IDLE, WORKING, STUCK, WAITING
- Each device can be manually RESET via button in UI
- Images and logs are device-aware (stored with device serial in filename or directory)

## Common Configuration Scenarios

```python
# Minimal mode: Just login and backup ID, no extra sequences
DO_BOX = 0
DO_GACHA = 0
FIND_HERO = 0

# Full automation: Everything enabled
DO_BOX = 1
DO_GACHA = 1
GACHA_FREE = 1
FIND_HERO = 1
GETQUEST = 1

# Fast mode: Skip OCR scanning for speed
NOSCAN = 1  # Saves output to fast-random/ instead of scanning for hero names

# Debug mode: Capture OCR frames for inspection
DEBUG_OCR = 1
FIND_HERO = 1
```

## ADB Integration

- **Location:** `adb/` subdirectory contains Windows ADB binaries (adb.exe, AdbWinApi.dll, AdbWinUsbApi.dll)
- **Client:** Pure Python ADB (`ppadb.client.Client`)
- **Device Communication:** Via `device.shell()` for input commands (e.g., `input tap x y`, `input swipe x1 y1 x2 y2 duration`)
- **Screenshot Path:** `/sdcard/screen.png` (device-side temp file), pulled to local storage
- **Auth Path:** Device data at `/data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat`

## Debugging Tips

- **GUI not responding:** Check if OCR or image matching is blocking (monitor `logs/` directory)
- **Template matching fails:** Verify BMP image is in `img/` with correct name; test with `test_ocr.py`
- **Device stuck:** Hit the "↺ RESET" button in GUI; device will restart and retry from the beginning
- **OCR inaccurate:** Switch OCR engine (pytesseract vs. easyocr) in `login.py`; enable `DEBUG_OCR=1` to inspect cropped regions
- **Multi-device conflicts:** Check `ocr_lock` and `file_pick_lock` aren't over-contending; reduce `GACHA_FREE_LOOPS` or add delays

## Repository Notes

- **GitHub Remote:** `leokungYT/pes` (auto-update pulls from main branch)
- **No Requirements.txt:** Install dependencies manually: `pip install opencv-python numpy pytesseract easyocr ppadb customtkinter pillow colorama torch`
- **Tesseract External:** Windows installer at `Tesseract-OCR/` (subdirectory) or from `C:\Program Files\Tesseract-OCR\tesseract.exe`
- **Comments in Thai:** Many inline comments are in Thai; translation may be helpful for non-Thai speakers

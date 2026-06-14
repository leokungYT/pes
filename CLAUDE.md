# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PES Mobile Bot is a Python automation tool for the Pro Evolution Soccer (PES) mobile game. It uses Android Debug Bridge (ADB) to connect to mobile devices and automate gameplay sequences like logins, gacha rolls, hero searches, and item collection. The bot supports multi-device automation with a modern GUI built using CustomTkinter.

**Version:** 2.0.12 (see `version.txt`)

## Commands

```bat
# Primary launcher — runs auto_update.py first, then login.py
login.bat

# GUI launcher (equivalent to python main-pes.py)
genid.bat

# Reset all data folders to empty (backup-id, input-id, found-hero, etc.)
clear-folders.bat

# Install all Python dependencies
install-pip.bat
```

```bash
# Run individual scripts directly
python main-pes.py     # GUI application
python login.py        # Headless automation engine

# Install dependencies manually (no requirements.txt)
pip install opencv-python numpy ppadb customtkinter pillow colorama easyocr
# Optional: pip install pytesseract torch
```

**Tesseract** must be installed separately: `C:\Program Files\Tesseract-OCR\tesseract.exe`  
**ADB binaries** are in the `adb/` subdirectory (Windows).

## Core Architecture

### Entry Points

- **`main-pes.py`** — Primary GUI (CustomTkinter). Manages multi-device ADB connections, orchestrates the box opening sequence (play1→play31, box1→box4), and displays live device screenshots and status.
- **`login.py`** — Core automation engine. Implements the full state machine: LOGIN → (BOX) → (GACHA) → (GACHA_FREE) → (FIND_HERO) → (GETQUEST). Called per-device from `main-pes.py` in threads.
- **`config.py`** — All feature flags and configuration. Edit this to enable/disable sequences and set hero lists. Comments are in Thai.

### Auto-Update Flow

`login.bat` calls `auto_update.py` before launching `login.py`. Exit code protocol:
- **Exit 10** — update downloaded; user must restart `login.bat` manually
- **Exit 12** — `login.py` triggered a silent background update and relaunched itself; the batch window closes automatically

`auto_update.py` fetches `version.txt` from the `leokungYT/pes` GitHub main branch and downloads the ZIP if versions differ. `OVERWRITE_CONFIG_ON_UPDATE = False` in `config.py` prevents overwriting local settings during update.

### Multi-Device Threading Model

Each connected device runs in its own thread inside `login.py`. Communication back to the GUI uses a global `_gui_queue` (thread-safe). Shared resources are guarded by two locks:
- `file_pick_lock` — controls which device processes which input file from `input-id/`
- `ocr_lock` — serializes OCR so only one device runs it at a time (prevents CPU spikes)

Device state is tracked in module-level dicts: `DEVICE_RESET_FLAGS`, `DEVICE_FILE_ASSIGNMENTS`, `DEVICE_LAST_GAME_CHECK`.

### Image Matching

`img_search()` in `login.py` uses `cv2.matchTemplate()` with `TM_CCOEFF_NORMED` (threshold 0.8). Screenshots are downscaled to 50% (`SCREENCAP_SCALE = 0.5`) before matching for speed. Template images are BMP files in `img/`, cached in `IMAGE_CACHE` to avoid re-reading from disk. Pre-computed image paths live in the `_P` dict at module level; quest-sequence paths are in `_QUESTFIVE_PATHS`.

### State Machine & Control Flow

The automation sequence uses exception-based control flow:
- `DeviceResetException` → restart device session
- `CycleTimeoutException` → session timed out
- `SellScreenException` → unexpected screen state
- `RestartFromQuest8Exception` → quest mode recovery

### OCR

Two engines are supported, both optional:
- **pytesseract** (faster, offline) — auto-detected at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- **easyocr** (more accurate) — fallback

OCR regions use `Region(x, y, width, height)`. Enable `DEBUG_OCR=1` in `config.py` to save cropped regions to `debug-ocr/`.

## Configuration Flags (`config.py`)

| Flag | Default | Description |
|---|---|---|
| `EVENT_IMG` | 0 | Use event image sequence (play22→play31) vs. Back-spam to cancel |
| `DO_BOX` | 0 | Enable box opening (play26–play31, box1–box4) |
| `DO_GACHA` | 0 | Enable gacha roll sequence |
| `GACHA_CHECK` | 0 | After gacha, go straight to hero search |
| `GACHA_FREE` | 0 | Enable free gacha sequence |
| `GACHA_FREE_LOOPS` | 10 | Number of free gacha repetitions |
| `FIND_HERO` | 0 | Enable hero scanning (fin1–fin8 flow) |
| `NOSCAN` | 1 | Skip OCR; save to `fast-random/` instead of `backup-id/` |
| `SKIPANIMATION` | 1 | Spam-click to skip gacha animations |
| `LOGIN_FAST` | 1 | Clear app and end the cycle immediately on hitting the login checkpoint (fastest path) |
| `CHECK_COIN` | 0 | Scan and log coin amounts via OCR |
| `DEBUG_OCR` | 0 | Save OCR crop images to `debug-ocr/` |
| `AUTORUN` | 0 | Start bot automatically on launch |
| `TIMEOUT_ENABLE` | 0 | Enable per-session timeout |
| `TIMEOUT_MINUTES` | 10 | Timeout duration |
| `GETCODE` | 0 | Enter a promo code before box sequence |
| `GETCODE_TEXT` | `"eFCONNECT"` | Promo code text typed during getcode sequence |
| `SEND_CODE` | `"M-CBFTKHBALEF"` | Code used by `playcode.py` standalone sender |
| `GETQUEST` | 0 | Collect quest rewards before box sequence |
| `SILENT_UPDATE_MODE` | `'keep'` | `'keep'` preserves local files; `'clean'` wipes on update |
| `OVERWRITE_CONFIG_ON_UPDATE` | `True` | Whether auto-update overwrites `config.py` |

Hero lists: `HERO_LIST` (backup from main gacha), `HERO_LIST_FREE` (free gacha), `list_find_hero` (OCR scan targets). Append `=x2` to a name to require 2 copies (e.g., `"Lamine=x2"`).

Hero image matching: `HERO_IMG_MAP` maps BMP filenames in `img/` to hero names for template-based (non-OCR) hero detection (e.g., `{"heroo1.bmp": "sasuke"}`).

Quest images are stored in `img/getquest/` (path controlled by `GETQUEST_IMG_DIR`).

## Data Flow

**Input:** `input-id/` — text files with per-device login credentials  
**Output directories** (auto-created by `login.py`):
- `backup-id/` — sessions where target hero was found (OCR scan mode)
- `fast-random/` — sessions when `NOSCAN=1`
- `found-hero/`, `no-hero/` — hero search results
- `backup/` — raw `.dat` save files
- `login-success/`, `login-failed/`, `timeout/`, `file-error/`, `random-fail/`, `run-file/`
- `logs/` — per-device log files
- `debug-ocr/` — OCR debug crops (only when `DEBUG_OCR=1`)

## ADB Integration

- Binaries: `adb/adb.exe` (Windows)
- Client: `ppadb.client.Client` (pure Python)
- Screenshot flow: `adb shell screencap /sdcard/screen.png` → pull to local → OpenCV
- Save data path on device: `/data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat`

## Adding a New Game Sequence

1. Capture BMP screenshots of each screen state → place in `img/` (e.g., `seq1.bmp`, `seq2.bmp`)
2. Add a flag in `config.py` (e.g., `DO_NEWSEQ = 0`)
3. Add a handler in `login.py`:
   ```python
   while time.time() < deadline:
       img = get_screen_capture(device)
       if img_search(img, os.path.join(IMG_DIR, "seq1.bmp")):
           device.shell("input tap x y")
       time.sleep(0.5)
   ```
4. Import the flag from `config` and call the handler in the main flow

## Other Files

- **`login_new.py`** — experimental/alternate login implementation
- **`auto_update.py`** — GitHub release version checking and download
- **`config_gen.py`** — generates live config-edit dialogs (no file writes)
- **`playcode.py`** — standalone promo code sender (uses `SEND_CODE` from config)
- **`patch_*.py`, `fix.py`, `refactor_login.py`** — one-off code-rewriting scripts; check git log for context. Note `refactor_login.py` has a stale hardcoded path (`d:/bot/pes/login.py`) and is not runnable as-is.

## Notes

- All inline comments are in Thai.
- Thread counts for OpenCV, MKL, BLAS, NumExpr, and Torch are all forced to 1 at startup to prevent CPU thrashing with multiple devices.
- Both `main-pes.py` and `login.py` call `os.chdir()` to the script directory on startup so relative paths (`img/`, `input-id/`) always resolve correctly regardless of how the script was launched.
- `socket.setdefaulttimeout(15.0)` is set at module level in `login.py` to prevent indefinite hangs on ADB socket operations.
- GitHub remote: `leokungYT/pes` (used by `auto_update.py`)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only Python + ADB automation bot that mass-processes PES mobile game account files (`.dat`) across many MuMu emulator instances in parallel, driving the game via OpenCV template matching + OCR. Comments and user-facing text are in Thai. There is no test suite or linter — verify changes with `python -c "import ast; ast.parse(open('login.py', encoding='utf-8').read())"` and by running the bot against an emulator.

**The bot must be fully restarted for code changes to take effect** — only `config.py` is hot-reloaded (via `importlib.reload` at the start of every cycle in `process_device_login`); the scripts themselves are not.

## Commands

- `login.bat` — main entry point: runs `auto_update.py` (exit 10 = updated, restart needed), then `py login.py`. Exit code 12 from login.py = silent background update in progress.
- `genid.bat` → `py main-pes.py` — the account-generator sibling bot (uses `config_gen.py` instead of `config.py`).
- `py cap-id.py` — captures `<user_code>.png` screenshots per `.dat` (imports helpers from `login.py`).
- `install-pip.bat` — installs dependencies (opencv-python, numpy, colorama, Pillow, customtkinter, easyocr; Tesseract is bundled/installed separately).
- `clear-folders.bat` — wipes all runtime result folders.

Updates ship by pushing to the `main` branch of `leokungYT/pes` on GitHub — `auto_update.py` compares `version.txt` against the raw branch copy and downloads the branch ZIP (not releases). Bump `version.txt` to trigger client updates. `config.py` is only overwritten on update if `OVERWRITE_CONFIG_ON_UPDATE = True`.

## Architecture (login.py, ~6200 lines — the primary bot)

One `process_device_login(device)` worker thread per emulator instance (started staggered 10s apart), each looping cycles: pick `.dat` from `input-id/` → push to device → launch game → play8/checkpoint login → optional sequences (getcode / getquest / box / gacha / find-hero / check-coin, all toggled in `config.py`) → sort file into a result folder.

### Exception-based control flow (the key pattern)

Cycles are unwound with custom exceptions caught in a big `try/except` ladder at the bottom of `process_device_login` (~line 6080+). When adding recovery behavior, raise one of these rather than returning status codes:

- `DeviceResetException` — abort current file (released back / already moved); force-stop app, next cycle picks a new file.
- `DeviceTimeoutException` — cycle exceeded `TIMEOUT_MINUTES` → file goes to `timeout/`.
- `RestartFromPlay8Exception` — relaunch same file from the play8 step, **keeping login state** (no AUTH wipe, no re-push). Set up via `trigger_restart_from_play8()` / `DEVICE_RESTART_PLAY8[serial]`; the cycle top checks this dict and skips file-pick + push.
- `FixClearReenterException` — re-enter same file with a full re-push (keeps the file lock via `DEVICE_REENTER_FILE`).
- `ResetGachaException` — restart a gacha sub-sequence; caught **locally** inside gacha loops, not at the top ladder. Beware: it can escape from unexpected places (see below).
- `SellScreenException` — sell screen detected → file to `login-failed/`.

### get_screen_capture() has side effects

`get_screen_capture(device)` (~line 2050) is not a plain screenshot: it relaunches the game if dead, and auto-detects/dismisses floating popups (fixnet, fixtip, fixevent, fixgachanew, …). Critically, it **raises** the control-flow exceptions above when it sees terminal states (e.g. `fixclear1.png` → moves file to `file-error/` + `DeviceResetException`; fixgachanew during `in_new_gacha_loop` → `ResetGachaException`). Any loop calling it must either let those propagate to the right handler or catch them deliberately (e.g. the Back-spam-until-cancel loop catches `ResetGachaException` and keeps spamming). For a raw frame with no side effects, use `fast_screencap(device)`.

### Image matching & OCR

- `img_search(gray_img, path, threshold=0.8)` — cv2 `matchTemplate` (TM_CCOEFF_NORMED), returns center points. Templates in `img/` (mixed `.bmp`/`.png` — the loader transparently tries the other extension; cached in `IMAGE_CACHE`). Filenames encode game screens: `play1..play31`, `box1..4`, `gacha*`, `checkpoint*`, `fix*` (popup fixers). Subfolders: `img/getquest/`, `img/fin-cap/`, `img/setcode/`.
- OCR (`read_screen_text`, guarded by `ocr_lock`): EasyOCR first, Pytesseract fallback (hard-coded `C:\Program Files\Tesseract-OCR\tesseract.exe`). `DEBUG_OCR=1` dumps crops to `debug-ocr/`.

### File lifecycle

`pick_next_file()` thread-safely claims a `.dat` from `input-id/` (lock = copy in `run-file/` + `in_use_files` set); `release_file()` releases it. Outcomes move the file to: `login-success/`, `login-failed/`, `file-error/`, `timeout/`, `backup-id/`, `fast-random/`, `found-hero/`, `no-hero/`. The generic `except Exception` handler returns the file to `input-id/` (never sorts on unknown errors). All these folders are git-ignored and contain user credentials — never commit them.

### Device / emulator layer

ppadb (`from ppadb.client import Client as AdbClient`), bundled `adb/` directory, devices on `127.0.0.1:55xx`. MuMu root is toggled live via `MuMuManager.exe` (`USE_MUMU_ROOT`); file ops on device use `su -c` (`USE_SU`). Game package: `jp.konami.pesam`; account file lives at `/data/data/jp.konami.pesam/files/SaveData/AUTH/`.

### GUI & logging

customtkinter GUI (`LoginBotGUI`); worker threads never touch Tk directly — everything goes through `gui_log(serial, msg, step=, status=)`, which also appends to `logs/<serial>.txt` (throttled). `status` (`working`/`stuck`/`error`) drives the device-row color. `DEBUG_CONSOLE=0` suppresses console prints (logs still written). Headless mode (no customtkinter) spawns workers directly.

## Gotchas

- Windows PowerShell 5.1 environment; `login.py` disables console QuickEdit to prevent cmd freezes.
- `main-pes.py` duplicates much of login.py's helper layer with different names (`ImgSearchADB` instead of `img_search`) and its own config (`config_gen.py`) — fixes to shared logic usually need mirroring by hand.
- `patch.py` is a one-off dev script that string-replaces a hard-coded block inside `login.py` — do not run it casually.
- Per-device state lives in module-level dicts keyed by serial (`DEVICE_FILE_ASSIGNMENTS`, `DEVICE_RESTART_PLAY8`, `DEVICE_PAST_LOGIN`, …) — clean these up when changing recovery flows, and remember counters must be reset when a new file is picked.

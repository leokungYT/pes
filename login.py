import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

try:
    import torch
    if hasattr(torch, "set_num_threads"):
        torch.set_num_threads(1)
    if hasattr(torch, "set_num_interop_threads"):
        torch.set_num_interop_threads(1)
except Exception:
    pass

import cv2
import numpy as np
import time
import subprocess
import threading
import shutil
import concurrent.futures
import glob
from ppadb.client import Client as AdbClient
from colorama import Fore, Style, init

# เปลี่ยน working directory มาที่โฟลเดอร์ของสคริปต์ (pes) เสมอ
# เพื่อให้ relative path เช่น 'input-id' หรือ 'img' ชี้ไปถูกที่
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    import customtkinter as ctk
    from PIL import Image, ImageTk
    GUI_ENABLED = True
except ImportError:
    GUI_ENABLED = False
    print(f"{Fore.YELLOW}[WARN] customtkinter or PIL not found. GUI disabled.{Style.RESET_ALL}")

cv2.setNumThreads(1)
init(autoreset=True)

try:
    import pytesseract
    if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except ImportError:
    pytesseract = None

try:
    import easyocr
except ImportError:
    easyocr = None

# ── Region Class ──────────────────────────────────────────────────────────────
class Region:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

# ── Globals ──────────────────────────────────────────────────────────────────
import queue as _queue_mod
adb_path      = "adb"
bot_running   = False
gui_instance  = None
_gui_queue    = _queue_mod.Queue()   # thread-safe queue for all GUI updates

# ── โหลด config จาก config.py ──────────────────────────────────────────────
from config import EVENT_IMG, DO_BOX, DO_GACHA, HERO_LIST, IMG_DIR, INPUT_DIR, LOGIN_SUCCESS_DIR, FIND_HERO, HERO_IMG_MAP, GACHA_FREE, HERO_LIST_FREE, DEBUG_OCR, CHECK_COIN, GACHA_FREE_LOOPS, NOSCAN, SKIPANIMATION
try:
    from config import GACHA_CHECK
except ImportError:
    GACHA_CHECK = 0
try:
    from config import list_find_hero
except ImportError:
    list_find_hero = HERO_LIST

REMOTE_AUTH_DIR   = "/data/data/jp.konami.pesam/files/SaveData/AUTH"
REMOTE_DAT_FILE   = f"{REMOTE_AUTH_DIR}/online_user_id_data.dat"

IMAGE_CACHE          = {}
DEVICE_RESET_FLAGS   = {}
DEVICE_FILE_ASSIGNMENTS = {}
DEVICE_DISABLE_FIXEVENT = {}
DEVICE_LAST_GAME_CHECK  = {}  # throttle: เช็คเกมออนทุก 30 วิ

file_pick_lock = threading.Lock()
ocr_lock       = threading.Lock()   # ป้องกัน OCR หลาย device พร้อมกัน (ลด CPU spike)
in_use_files   = set()   # filenames currently being processed
_gui_last_update = {}    # throttle GUI text updates per-device

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(LOGIN_SUCCESS_DIR, exist_ok=True)
BACKUP_ID_DIR = "backup-id"
NO_HERO_DIR   = "no-hero"
FOUND_HERO_DIR = "found-hero"
os.makedirs(BACKUP_ID_DIR, exist_ok=True)
os.makedirs(NO_HERO_DIR, exist_ok=True)
os.makedirs(FOUND_HERO_DIR, exist_ok=True)
FAST_RANDOM_DIR = "fast-random"
os.makedirs(FAST_RANDOM_DIR, exist_ok=True)
FILE_ERROR_DIR = "file-error"
os.makedirs(FILE_ERROR_DIR, exist_ok=True)
RUN_FILE_DIR = "run-file"
os.makedirs(RUN_FILE_DIR, exist_ok=True)
RANDOM_FAIL_DIR = "random-fail"
os.makedirs(RANDOM_FAIL_DIR, exist_ok=True)
LOGIN_FAILED_DIR = "login-failed"
os.makedirs(LOGIN_FAILED_DIR, exist_ok=True)

# ── Exceptions ────────────────────────────────────────────────────────────────
class DeviceResetException(Exception):  pass
class CycleTimeoutException(Exception): pass
class SellScreenException(Exception):  pass

# ═════════════════════════════════════════════════════════════════════════════
# GUI
# ═════════════════════════════════════════════════════════════════════════════
if GUI_ENABLED:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class DeviceMonitorWidget(ctk.CTkFrame):
        def __init__(self, parent, device_id, index):
            super().__init__(parent, fg_color="#383838", corner_radius=6, height=32)
            self.device_id = device_id
            self.pack_propagate(False)

            chk = ctk.CTkCheckBox(self, text="", width=20, height=20,
                                   checkbox_width=16, checkbox_height=16)
            chk.pack(side="left", padx=(6, 2))
            chk.select()

            ctk.CTkLabel(self, text=f"#{index}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ffffff", width=25).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(self, text=device_id,
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color="#ccc").pack(side="left", padx=(0, 6))

            self.lbl_status = ctk.CTkLabel(self, text="Ready",
                                           font=ctk.CTkFont(size=10, weight="bold"),
                                           text_color="#4caf50", width=60)
            self.lbl_status.pack(side="right", padx=6)

            self.lbl_file = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=9),
                                         text_color="#aaa", width=180)
            self.lbl_file.pack(side="right", padx=4)

            ctk.CTkButton(self, text="↺", width=22, height=20,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          fg_color="#e53935",
                          command=lambda: trigger_manual_reset(device_id)
                          ).pack(side="right", padx=2)

            # Cache last values to skip redundant configure calls
            self._last_status = "Ready"
            self._last_step   = ""

        def update_state(self, step=None, status=None, **kwargs):
            if status and status != self._last_status:
                self._last_status = status
                colors = {'working': "#4caf50", 'stuck': "#e53935",
                          'waiting': "#ff9800", 'idle': "#888"}
                self.lbl_status.configure(text=status.upper(),
                                          text_color=colors.get(status.lower(), "#888"))
            if step and step != self._last_step:
                self._last_step = step
                self.lbl_file.configure(text=step[:35])

    # ─────────────────────────────────────────────────────────────────────────
    class LoginBotGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            global gui_instance
            gui_instance = self
            self.title("🔑 loginสะสม PES")
            self.geometry("780x550")
            self.adb_connected = False
            self.device_monitors  = {}
            self.threads          = []
            self.is_started       = False
            self.stat_labels      = {}
            self.stat_rows        = {}
            self.login_times      = []
            self._log_buffer      = []     # batch log lines
            self._prev_stats      = {}     # cache previous stat counts to skip no-op updates
            self.setup_ui()
            self.after(500,  self.connect_adb)
            self.after(2000, self.update_realtime_stats)
            self.after(10000, self.auto_scan_devices)
            self.after(100,  self._process_gui_queue)   # centralized GUI queue poller
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # ── UI build ──────────────────────────────────────────────────────
        def setup_ui(self):
            from datetime import datetime

            # Toolbar
            toolbar = ctk.CTkFrame(self, height=40, fg_color="#333333", corner_radius=0)
            toolbar.pack(fill="x")
            toolbar.pack_propagate(False)

            self.lbl_status = ctk.CTkLabel(toolbar, text="   ● OFFLINE",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#888")
            self.lbl_status.pack(side="left", padx=5)

            self.btn_start = ctk.CTkButton(toolbar, text="▶ START",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           width=80, height=24,
                                           fg_color="#2cc985", hover_color="#229f69",
                                           command=self.toggle_bot)
            self.btn_start.pack(side="left", padx=10)

            counter_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
            counter_frame.pack(side="right", padx=10)

            self.lbl_file_count = ctk.CTkLabel(counter_frame, text="📁 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#aaaaaa")
            self.lbl_file_count.pack(side="left", padx=8)

            self.lbl_succ_count = ctk.CTkLabel(counter_frame, text="✅ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#4caf50")
            self.lbl_succ_count.pack(side="left", padx=8)

            self.lbl_hero_count = ctk.CTkLabel(counter_frame, text="⭐ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#ffc107")
            self.lbl_hero_count.pack(side="left", padx=8)

            self.lbl_fail_count = ctk.CTkLabel(counter_frame, text="❌ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#ff5555")
            self.lbl_fail_count.pack(side="left", padx=8)

            self.lbl_avg_time = ctk.CTkLabel(counter_frame, text="⏱ Avg: -",
                                             font=ctk.CTkFont(size=12, weight="bold"),
                                             text_color="#2196f3")
            self.lbl_avg_time.pack(side="left", padx=8)

            ctk.CTkLabel(toolbar,
                         text=f"Started: {datetime.now().strftime('%H:%M:%S')}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#aaaaaa").pack(side="right", padx=15)

            # Main content
            main_frame = ctk.CTkFrame(self, fg_color="transparent")
            main_frame.pack(fill="both", expand=True, padx=6, pady=4)
            main_frame.grid_columnconfigure(0, weight=3)
            main_frame.grid_columnconfigure(1, weight=2)
            main_frame.grid_rowconfigure(0, weight=1)

            left_frame = ctk.CTkFrame(main_frame, fg_color="#2b2b2b", corner_radius=8)
            left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            hdr = ctk.CTkFrame(left_frame, fg_color="#383838", corner_radius=0, height=28)
            hdr.pack(fill="x")
            ctk.CTkLabel(hdr, text="   DEVICES",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#cccccc", anchor="w").pack(side="left")
            self.dev_scroll = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
            self.dev_scroll.pack(fill="both", expand=True, padx=3, pady=3)

            right_frame = ctk.CTkFrame(main_frame, fg_color="#2b2b2b", corner_radius=8)
            right_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
            rhdr = ctk.CTkFrame(right_frame, fg_color="#383838", corner_radius=0, height=28)
            rhdr.pack(fill="x")
            ctk.CTkLabel(rhdr, text="   🏆 SUMMARY STATS",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#f2c94c", anchor="w").pack(side="left")
            self.result_scroll = ctk.CTkScrollableFrame(right_frame, fg_color="transparent")
            self.result_scroll.pack(fill="both", expand=True, padx=3, pady=3)

            # Log
            log_frame = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=6, height=80)
            log_frame.pack(fill="x", padx=6, pady=(0, 4))
            log_frame.pack_propagate(False)
            self.log_text = ctk.CTkTextbox(log_frame,
                                           font=ctk.CTkFont(family="Consolas", size=10),
                                           text_color="#8b949e", fg_color="#1e1e1e")
            self.log_text.pack(fill="both", expand=True, padx=2, pady=2)
            self.log_text.configure(state="disabled")

            # Bottom bar
            base_path  = os.path.dirname(os.path.abspath(__file__))
            bottom_bar = ctk.CTkFrame(self, height=32, fg_color="#333333", corner_radius=0)
            bottom_bar.pack(fill="x")

            ctk.CTkButton(bottom_bar, text="🔌 Connect Missing", width=100, height=22,
                          font=ctk.CTkFont(size=10), fg_color="#4caf50",
                          command=self.connect_missing_devices
                          ).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📂 input-id", width=70, height=22,
                          font=ctk.CTkFont(size=10), fg_color="#555555",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(base_path, INPUT_DIR)}"')
                          ).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="✅ login-success", width=90, height=22,
                          font=ctk.CTkFont(size=10), fg_color="#555555",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(base_path, LOGIN_SUCCESS_DIR)}"')
                          ).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="⚙️ Config", width=70, height=22,
                          font=ctk.CTkFont(size=10), fg_color="#1565c0",
                          hover_color="#0d47a1",
                          command=self.open_config_dialog
                          ).pack(side="left", padx=3, pady=4)
            ctk.CTkButton(bottom_bar, text="📋 Logs", width=60, height=22,
                          font=ctk.CTkFont(size=10), fg_color="#555555",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(base_path, LOG_DIR)}"')
                          ).pack(side="left", padx=3, pady=4)
            ctk.CTkLabel(bottom_bar, text="v1.0",
                         font=ctk.CTkFont(size=10), text_color="#888888"
                         ).pack(side="right", padx=8)

        # ── Helpers ─────────────────────────────────────────────────
        def open_config_dialog(self):
            import importlib, config as cfg
            importlib.reload(cfg)   # อ่านค่าล่าสุดจากไฟล์

            win = ctk.CTkToplevel(self)
            win.title("⚙️ Config")
            win.geometry("340x480")
            win.resizable(False, False)
            win.grab_set()   # modal

            ctk.CTkLabel(win, text="Bot Configuration",
                         font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 8))

            # ── EVENT_IMG toggle ────────────────────────────
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row, text="Event Image (play22→play31)",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_event = ctk.IntVar(value=cfg.EVENT_IMG)
            ctk.CTkSwitch(row, text="", variable=var_event,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── DO_BOX toggle ──────────────────────────────
            row2 = ctk.CTkFrame(win, fg_color="transparent")
            row2.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row2, text="Open Box Sequence (1-4)",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_box = ctk.IntVar(value=cfg.DO_BOX)
            ctk.CTkSwitch(row2, text="", variable=var_box,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── DO_GACHA toggle ────────────────────────────
            row3 = ctk.CTkFrame(win, fg_color="transparent")
            row3.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row3, text="Gacha Mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_gacha = ctk.IntVar(value=cfg.DO_GACHA)
            ctk.CTkSwitch(row3, text="", variable=var_gacha,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── FIND_HERO toggle ───────────────────────────
            row4 = ctk.CTkFrame(win, fg_color="transparent")
            row4.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row4, text="Find Hero Mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_find_hero = ctk.IntVar(value=getattr(cfg, 'FIND_HERO', 0))
            ctk.CTkSwitch(row4, text="", variable=var_find_hero,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── GACHA_FREE toggle ──────────────────────────
            row5 = ctk.CTkFrame(win, fg_color="transparent")
            row5.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row5, text="Gacha Free Mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_gacha_free = ctk.IntVar(value=getattr(cfg, 'GACHA_FREE', 0))
            ctk.CTkSwitch(row5, text="", variable=var_gacha_free,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── GACHA_FREE_LOOPS entry ─────────────────────
            row5_loops = ctk.CTkFrame(win, fg_color="transparent")
            row5_loops.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row5_loops, text="  └─ Loops count",
                         font=ctk.CTkFont(size=11, slant="italic")).pack(side="left", padx=(10, 0))
            entry_gfree_loops = ctk.CTkEntry(row5_loops, width=50, height=20, justify="center")
            entry_gfree_loops.insert(0, str(getattr(cfg, 'GACHA_FREE_LOOPS', 2)))
            entry_gfree_loops.pack(side="right")

            # ── CHECK_COIN toggle ──────────────────────────
            row6 = ctk.CTkFrame(win, fg_color="transparent")
            row6.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row6, text="Check Coin Mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_check_coin = ctk.IntVar(value=getattr(cfg, 'CHECK_COIN', 0))
            ctk.CTkSwitch(row6, text="", variable=var_check_coin,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── NOSCAN toggle ─────────────────────────────
            row7 = ctk.CTkFrame(win, fg_color="transparent")
            row7.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row7, text="No Scan Mode (ข้ามสแกน → fast-random)",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_noscan = ctk.IntVar(value=getattr(cfg, 'NOSCAN', 0))
            ctk.CTkSwitch(row7, text="", variable=var_noscan,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── SKIPANIMATION toggle ─────────────────────────────
            row8 = ctk.CTkFrame(win, fg_color="transparent")
            row8.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row8, text="Skip Animation (Fast Taps)",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_skipanim = ctk.IntVar(value=getattr(cfg, 'SKIPANIMATION', 0))
            ctk.CTkSwitch(row8, text="", variable=var_skipanim,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── GACHA_CHECK toggle ─────────────────────────────
            row9 = ctk.CTkFrame(win, fg_color="transparent")
            row9.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row9, text="Gachafree + check mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_gacha_check = ctk.IntVar(value=getattr(cfg, 'GACHA_CHECK', 0))
            ctk.CTkSwitch(row9, text="", variable=var_gacha_check,
                          onvalue=1, offvalue=0).pack(side="right")

            # ── Save button ───────────────────────────────
            def _save():
                global EVENT_IMG, DO_BOX, DO_GACHA, FIND_HERO, GACHA_FREE, CHECK_COIN, GACHA_FREE_LOOPS, NOSCAN, SKIPANIMATION, GACHA_CHECK
                new_event = var_event.get()
                new_box   = var_box.get()
                new_gacha = var_gacha.get()
                new_find  = var_find_hero.get()
                new_gfree = var_gacha_free.get()
                new_ccoin = var_check_coin.get()
                new_noscan = var_noscan.get()
                new_skipanim = var_skipanim.get()
                new_gacha_check = var_gacha_check.get()
                try:
                    new_gfree_loops = int(entry_gfree_loops.get())
                except ValueError:
                    new_gfree_loops = 2

                # เขียนลง config.py
                cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
                with open(cfg_path, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                content = re.sub(r"^EVENT_IMG\s*=\s*\d", f"EVENT_IMG = {new_event}",
                                 content, flags=re.MULTILINE)
                content = re.sub(r"^DO_BOX\s*=\s*\d", f"DO_BOX = {new_box}",
                                 content, flags=re.MULTILINE)
                content = re.sub(r"^DO_GACHA\s*=\s*\d", f"DO_GACHA = {new_gacha}",
                                 content, flags=re.MULTILINE)
                if re.search(r"^FIND_HERO\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^FIND_HERO\s*=\s*\d", f"FIND_HERO = {new_find}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nFIND_HERO = {new_find}\n"
                if re.search(r"^GACHA_FREE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_FREE\s*=\s*\d", f"GACHA_FREE = {new_gfree}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_FREE = {new_gfree}\n"
                if re.search(r"^GACHA_FREE_LOOPS\s*=\s*\d+", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_FREE_LOOPS\s*=\s*\d+", f"GACHA_FREE_LOOPS = {new_gfree_loops}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_FREE_LOOPS = {new_gfree_loops}\n"
                if re.search(r"^CHECK_COIN\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^CHECK_COIN\s*=\s*\d", f"CHECK_COIN = {new_ccoin}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nCHECK_COIN = {new_ccoin}\n"
                if re.search(r"^NOSCAN\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^NOSCAN\s*=\s*\d", f"NOSCAN = {new_noscan}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nNOSCAN = {new_noscan}\n"
                if re.search(r"^SKIPANIMATION\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^SKIPANIMATION\s*=\s*\d", f"SKIPANIMATION = {new_skipanim}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nSKIPANIMATION = {new_skipanim}\n"
                if re.search(r"^GACHA_CHECK\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_CHECK\s*=\s*\d", f"GACHA_CHECK = {new_gacha_check}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_CHECK = {new_gacha_check}\n"
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(content)
                # อัปเดต runtime ด้วย
                EVENT_IMG  = new_event
                DO_BOX     = new_box
                DO_GACHA   = new_gacha
                FIND_HERO  = new_find
                GACHA_FREE = new_gfree
                GACHA_FREE_LOOPS = new_gfree_loops
                CHECK_COIN = new_ccoin
                NOSCAN     = new_noscan
                GACHA_CHECK = new_gacha_check
                importlib.reload(cfg)
                label_status.configure(text=f"✅ Saved!",
                                       text_color="#4caf50")
                self.log(f"Config saved: EVENT={new_event}, BOX={new_box}, GACHA={new_gacha}, HERO={new_find}, GFREE={new_gfree}({new_gfree_loops} loops), COIN={new_ccoin}, NOSCAN={new_noscan}, GACHACHECK={new_gacha_check}")

            ctk.CTkButton(win, text="💾 Save", fg_color="#2cc985",
                          hover_color="#229f69", command=_save).pack(pady=8)
            label_status = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
            label_status.pack()

        # ── Helpers ───────────────────────────────────────────────────────
        def log(self, msg):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_buffer.append(f"[{ts}] {msg}\n")
            # Flush buffer immediately if it's large, otherwise the queue poller handles it
            if len(self._log_buffer) >= 20:
                self._flush_log_buffer()

        def _flush_log_buffer(self):
            """Batch-insert all pending log lines in one configure cycle."""
            if not self._log_buffer:
                return
            lines = self._log_buffer[:50]   # cap per flush to keep UI responsive
            self._log_buffer = self._log_buffer[50:]
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", "".join(lines))
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except Exception:
                pass

        def add_stat_row(self, name, count, is_error=False):
            if name not in self.stat_rows:
                bg  = "#3d2020" if is_error else "#2a3a2a"
                clr = "#e53935" if is_error else "#4caf50"
                row = ctk.CTkFrame(self.result_scroll, fg_color=bg,
                                   corner_radius=6, height=26)
                row.pack(fill="x", pady=1)
                row.pack_propagate(False)
                ctk.CTkLabel(row, text=f"  {name}",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="white", anchor="w"
                             ).pack(side="left", fill="x", expand=True)
                lbl = ctk.CTkLabel(row, text=str(count),
                                   font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color=clr)
                lbl.pack(side="right", padx=8)
                self.stat_labels[name] = lbl
                self.stat_rows[name]   = row
            else:
                self.stat_labels[name].configure(text=str(count))

        # ── ADB ───────────────────────────────────────────────────────────
        def connect_adb(self):
            self.log("Searching for ADB...")
            def _thread():
                if find_adb_executable():
                    connect_known_ports()
                    devices = get_connected_devices()
                    _gui_queue.put(('adb_ready', devices))
                else:
                    _gui_queue.put(('log', '● ADB NOT FOUND'))
            threading.Thread(target=_thread, daemon=True).start()

        def _on_adb_ready(self, devices):
            self.adb_connected = True
            for i, serial in enumerate(devices):
                if serial not in self.device_monitors:
                    m = DeviceMonitorWidget(self.dev_scroll, serial,
                                            len(self.device_monitors) + 1)
                    m.pack(fill="x", pady=1)
                    self.device_monitors[serial] = m
            self.lbl_status.configure(
                text=f"   ● ONLINE ({len(self.device_monitors)})",
                text_color="#4caf50")
            self.log(f"Found {len(devices)} devices.")

        def connect_missing_devices(self):
            self.log("Scanning for missing emulators...")
            def _bg_connect():
                connect_known_ports(quiet=False, kill_server=False)
                devices = get_connected_devices()
                new_devs = [d for d in devices if d not in self.device_monitors]
                if new_devs:
                    self.after(0, lambda: self._add_missing_devices(new_devs))
            threading.Thread(target=_bg_connect, daemon=True).start()

        def _add_missing_devices(self, new_devs):
            for dev in new_devs:
                if dev not in self.device_monitors:
                    m = DeviceMonitorWidget(self.dev_scroll, dev,
                                            len(self.device_monitors) + 1)
                    m.pack(fill="x", pady=1)
                    self.device_monitors[dev] = m
                    if self.is_started:
                        d = AdbClient(host="127.0.0.1", port=5037).device(dev)
                        if d:
                            t = threading.Thread(target=process_device_login,
                                                 args=(d,), daemon=True)
                            t.start()
                            self.threads.append(t)
                    self.log(f"Connected: {dev}")
            self.lbl_status.configure(
                text=f"   ● ONLINE ({len(self.device_monitors)})",
                text_color="#4caf50")

        def auto_scan_devices(self):
            def _thread():
                connect_known_ports(quiet=True, kill_server=False)
                devices = get_connected_devices()
                new_devs = [dev for dev in devices if dev not in self.device_monitors]
                if new_devs:
                    _gui_queue.put(('auto_scan', new_devs))
            threading.Thread(target=_thread, daemon=True).start()
            self.after(10000, self.auto_scan_devices)

        def _on_auto_scan_result(self, new_devs):
            for dev in new_devs:
                if dev not in self.device_monitors:
                    m = DeviceMonitorWidget(self.dev_scroll, dev, len(self.device_monitors) + 1)
                    m.pack(fill="x", pady=1)
                    self.device_monitors[dev] = m
                    self.log(f"Auto-detected: {dev} (Ready)")
            self.lbl_status.configure(
                text=f"   ● ONLINE ({len(self.device_monitors)})",
                text_color="#4caf50")

        # ── Bot control ───────────────────────────────────────────────────
        def toggle_bot(self):
            global bot_running
            if not bot_running:
                bot_running = True
                self.is_started = True
                self.btn_start.configure(text="⏹ STOP",
                                         fg_color="#e53935", hover_color="#c62828")
                self.start_bot_threads()
            else:
                bot_running = False
                self.btn_start.configure(text="▶ START",
                                         fg_color="#2cc985", hover_color="#229f69")

        def start_bot_threads(self):
            devices = list(self.device_monitors.keys())
            if not devices:
                self.log("No devices loaded yet, connecting ADB...")
                connect_known_ports(quiet=False, kill_server=False)
                for i, serial in enumerate(get_connected_devices()):
                    if serial not in self.device_monitors:
                        m = DeviceMonitorWidget(self.dev_scroll, serial, i + 1)
                        m.pack(fill="x", pady=1)
                        self.device_monitors[serial] = m
                self.lbl_status.configure(
                    text=f"   ● ONLINE ({len(self.device_monitors)})",
                    text_color="#4caf50")
                devices = list(self.device_monitors.keys())

            if not devices:
                self.log("ERROR: Still no devices found!")
                return

            client = AdbClient(host="127.0.0.1", port=5037)
            self.log(f"Starting threads for {len(devices)} devices...")
            for serial in devices:
                device = client.device(serial)
                if device is None:
                    self.log(f"ERROR: Cannot get device {serial} from ADB!")
                    continue
                self.log(f"✅ Started bot on {serial}")
                t = threading.Thread(target=process_device_login,
                                     args=(device,), daemon=True)
                t.start()
                self.threads.append(t)
                time.sleep(0.5)   # ลดจาก 1s → 0.5s

        def update_device(self, serial, **kwargs):
            if serial in self.device_monitors:
                self.device_monitors[serial].update_state(**kwargs)

        def update_realtime_stats(self):
            def _bg_scan():
                try:
                    input_count   = len(glob.glob(os.path.join(INPUT_DIR, "*.dat")))
                    success_count = len(glob.glob(os.path.join(LOGIN_SUCCESS_DIR, "*.dat")))
                    
                    found_files = (glob.glob(os.path.join(FOUND_HERO_DIR, "**", "*.dat"), recursive=True) +
                                   glob.glob(os.path.join(BACKUP_ID_DIR, "**", "*.dat"), recursive=True))
                    hero_count  = len(found_files)
                    
                    hero_counts = {}
                    for fpath in found_files:
                        fname = os.path.basename(fpath)
                        parts = fname.split('+')
                        if len(parts) > 1:
                            h_key = "+".join(parts[:-1]).strip()
                            if h_key:
                                hero_counts[h_key] = hero_counts.get(h_key, 0) + 1
                    
                    _gui_queue.put(('stats', (input_count, success_count, hero_count, hero_counts)))
                except Exception:
                    pass

            t = threading.Thread(target=_bg_scan, daemon=True)
            t.start()
            self.after(15000, self.update_realtime_stats)

        def _apply_stats_ui(self, input_count, success_count, hero_count, hero_counts):
            try:
                # อัปเดตเฉพาะค่าที่เปลี่ยน — ไม่ destroy/recreate widget ทุกรอบ
                prev = self._prev_stats
                if prev.get('input') != input_count:
                    self.lbl_file_count.configure(text=f"📁 {input_count}")
                    prev['input'] = input_count
                if prev.get('success') != success_count:
                    self.lbl_succ_count.configure(text=f"✅ {success_count}")
                    prev['success'] = success_count
                if hasattr(self, 'lbl_hero_count') and prev.get('hero') != hero_count:
                    self.lbl_hero_count.configure(text=f"⭐ {hero_count}")
                    prev['hero'] = hero_count

                # Build desired stat rows
                desired = {}
                if success_count:
                    desired["✅ login สำเร็จ"] = (success_count, False)
                for h_name, count in hero_counts.items():
                    desired[f"⭐ {h_name}"] = (count, False)

                # Remove rows no longer needed
                stale = [k for k in self.stat_rows if k not in desired]
                for k in stale:
                    self.stat_rows[k].destroy()
                    del self.stat_rows[k]
                    if k in self.stat_labels:
                        del self.stat_labels[k]

                # Add or update rows
                for name, (count, is_error) in desired.items():
                    self.add_stat_row(name, count, is_error)
                    
                if self.login_times:
                    avg = sum(self.login_times) / len(self.login_times)
                    new_text = f"⏱ Avg: {avg/60:.1f}m" if avg >= 60 else f"⏱ Avg: {avg:.0f}s"
                    if prev.get('avg_text') != new_text:
                        self.lbl_avg_time.configure(text=new_text)
                        prev['avg_text'] = new_text
            except Exception:
                pass

        def _process_gui_queue(self):
            """Central poller: drain _gui_queue and apply updates. Runs every 30ms for maximum smoothness."""
            try:
                processed = 0
                while processed < 100:    # cap per tick to keep UI alive
                    try:
                        kind, data = _gui_queue.get_nowait()
                    except Exception:
                        break
                    processed += 1
                    if kind == 'device_update':
                        serial, kwargs = data
                        if serial in self.device_monitors:
                            self.device_monitors[serial].update_state(**kwargs)
                    elif kind == 'log':
                        self.log(data)
                    elif kind == 'stats':
                        self._apply_stats_ui(*data)
                    elif kind == 'adb_ready':
                        self._on_adb_ready(data)
                    elif kind == 'auto_scan':
                        self._on_auto_scan_result(data)

                # Flush any pending log buffer
                self._flush_log_buffer()
                # Force Tkinter to process all idle tasks and update screen graphics immediately to prevent any freezing
                self.update_idletasks()
            except Exception:
                pass
            finally:
                self.after(30, self._process_gui_queue)

        def on_closing(self):
            from tkinter import messagebox
            if messagebox.askokcancel("Quit", "หยุดบอทและปิดโปรแกรม?"):
                self.destroy()
                os._exit(0)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════
def trigger_manual_reset(serial):
    DEVICE_RESET_FLAGS[serial] = True
    print(f"{Fore.YELLOW}[MANUAL] Reset triggered for {serial}{Style.RESET_ALL}")
    update_gui(serial, status="resetting", step="Manual Reset")

def check_device_reset(serial, cycle_start=None):
    if DEVICE_RESET_FLAGS.get(serial):
        DEVICE_RESET_FLAGS[serial] = False
        raise DeviceResetException(serial)

def update_gui(serial, **kwargs):
    """Queue a device update — never call GUI directly from worker threads."""
    if gui_instance:
        _gui_queue.put(('device_update', (serial, kwargs)))

_GUI_LOG_INTERVAL = 2  # seconds — ส่ง text update ไป GUI ทุก 2 วินาทีต่อ device

def gui_log(serial, msg, step=None, status=None):
    print(f"{Fore.CYAN}[{serial}] {msg}{Style.RESET_ALL}")
    # Throttle GUI text updates — ส่ง step/status ทุกครั้ง แต่ log text ส่งทุก 2 วิ
    now = time.time()
    last = _gui_last_update.get(serial, 0)
    if status or (now - last >= _GUI_LOG_INTERVAL):
        _gui_last_update[serial] = now
        update_gui(serial, log=msg, step=step, status=status)
        # Queue log text to GUI (will be batched by _process_gui_queue)
        if gui_instance:
            _gui_queue.put(('log', f"[{serial}] {msg}"))
    elif step:
        # step สำคัญ ส่งทุกครั้ง แต่ไม่ส่ง log text
        update_gui(serial, step=step)
    # บันทึก log ลงไฟล์แยกตาม device (ทำใน worker thread โดยตรง ไม่ block GUI)
    try:
        safe_name = serial.replace(".", "_").replace(":", "_")
        log_file = os.path.join(LOG_DIR, f"{safe_name}.txt")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            step_str = f" [{step}]" if step else ""
            f.write(f"[{ts}]{step_str} {msg}\n")
    except Exception:
        pass

# ═════════════════════════════════════════════════════════════════════════════
# ADB helpers
# ═════════════════════════════════════════════════════════════════════════════
def find_adb_executable():
    global adb_path
    base = os.path.dirname(os.path.abspath(__file__))
    for loc in [os.path.join(base, "adb", "adb.exe"),
                os.path.join(base, "adb", "adb"), "adb"]:
        if os.path.exists(loc):
            try:
                r = subprocess.run([loc, "version"], capture_output=True, text=True,
                                   timeout=5, shell=(os.name == 'nt'))
                if r.returncode == 0:
                    adb_path = loc
                    print(f"{Fore.GREEN}[ADB] Found: {adb_path}{Style.RESET_ALL}")
                    return True
            except Exception:
                pass
    found = shutil.which("adb")
    if found:
        adb_path = os.path.abspath(found)
        return True
    return False

def connect_known_ports(quiet=False, kill_server=True):
    try:
        if kill_server:
            subprocess.run([adb_path, "kill-server"],  capture_output=True, timeout=5, shell=(os.name == 'nt'))
            time.sleep(0.8)
            subprocess.run([adb_path, "start-server"], capture_output=True, timeout=5, shell=(os.name == 'nt'))
            time.sleep(0.8)

        ports = range(5555, 5756, 2)
        if not quiet:
            print(f"{Fore.YELLOW}[ADB] Scanning {len(ports)} ports...{Style.RESET_ALL}")

        def _try(port):
            try:
                addr = f"127.0.0.1:{port}"
                r = subprocess.run([adb_path, "connect", addr],
                                   capture_output=True, timeout=2, text=True,
                                   shell=(os.name == 'nt'))
                out = r.stdout.lower()
                if ("connected" in out or "already connected" in out) and "cannot" not in out:
                    return addr
            except Exception:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            connected = [r for r in ex.map(_try, ports) if r]

        if not quiet and connected:
            print(f"{Fore.GREEN}[ADB] Found {len(connected)} device(s){Style.RESET_ALL}")
    except Exception as e:
        if not quiet:
            print(f"{Fore.RED}[ADB] Scan error: {e}{Style.RESET_ALL}")

def get_connected_devices():
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=10, **kwargs)
        lines = result.stdout.strip().split("\n")[1:]
        raw_list = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                raw_list.append(parts[0])
        port_map = {}
        for serial in raw_list:
            port = None
            if "127.0.0.1:" in serial:
                try: port = int(serial.split(":")[1])
                except: pass
            elif "emulator-" in serial:
                try: port = int(serial.split("-")[1]) + 1
                except: pass
            if port:
                if port not in port_map or "127.0.0.1" in serial:
                    port_map[port] = serial
            else:
                port_map[serial] = serial
        return list(port_map.values())
    except: return []

# ═════════════════════════════════════════════════════════════════════════════
# Screen / image
# ═════════════════════════════════════════════════════════════════════════════
def fast_screencap(device):
    try:
        conn = device.client.create_connection(timeout=device.client.timeout)
        conn.send(f"host:transport:{device.serial}")
        conn.check_status()
        conn.send("shell:screencap")
        conn.check_status()
        raw = conn.read_all()
        
        if len(raw) > 16:
            w = int.from_bytes(raw[0:4], byteorder='little')
            h = int.from_bytes(raw[4:8], byteorder='little')
            # 12 bytes header
            expected_size = w * h * 4
            if len(raw) >= 12 + expected_size:
                img_data = raw[12:12+expected_size]
                img = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 4))
                return cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
    except Exception:
        pass

    # Fallback
    try:
        raw = device.screencap()
        if raw:
            return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    except:
        pass
    return None

def is_game_running(device):
    """Check if jp.konami.pesam is running on the device (throttled every 30s)."""
    serial = device.serial
    now = time.time()
    last_check = DEVICE_LAST_GAME_CHECK.get(serial, 0)
    if now - last_check < 30:
        return True  # ยังไม่ถึงเวลาเช็ค ถือว่าออนอยู่
    DEVICE_LAST_GAME_CHECK[serial] = now
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        result = subprocess.run(
            [adb_path, "-s", serial, "shell", "pidof jp.konami.pesam"],
            capture_output=True, text=True, timeout=5, **kwargs
        )
        pid = result.stdout.strip()
        return bool(pid)  # มี PID = เกมออนอยู่
    except Exception:
        return True  # ADB error ถือว่าออนอยู่ (ไม่ relaunch มั่ว)

def get_screen_capture(device):
    try:
        # เช็คเกมออนอยู่หรือไม่ (ทุก 30 วิ)
        if not is_game_running(device):
            gui_log(device.serial, "⚠️ Game not running! Relaunching...", step="Relaunch")
            device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
            time.sleep(14)
            DEVICE_LAST_GAME_CHECK[device.serial] = time.time()

        img = fast_screencap(device)
        if img is None:
            return None
        
        if img is not None:
            # === fixnet floating check ===
            fn_pts = img_search(img, os.path.join(IMG_DIR, "fixnet.bmp"))
            if fn_pts:
                gui_log(device.serial, "Floating: fixnet.bmp found! Clicking...", step="Fix Net")
                x, y = fn_pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                time.sleep(1)
                
                # Search for fixnet1.bmp for up to 10 seconds
                gui_log(device.serial, "Waiting for fixnet1.bmp (up to 10s)...", step="Fix Net 1")
                deadline_fn1 = time.time() + 10
                while time.time() < deadline_fn1:
                    img_fn1 = fast_screencap(device)
                    if img_fn1 is not None:
                        fn1_pts = img_search(img_fn1, os.path.join(IMG_DIR, "fixnet1.bmp"))
                        if fn1_pts:
                            x_fn1, y_fn1 = fn1_pts[0]
                            device.shell(f"input swipe {x_fn1} {y_fn1} {x_fn1} {y_fn1} 100")
                            gui_log(device.serial, "Clicked fixnet1.bmp!", step="Fix Net 1")
                            time.sleep(1)
                            break
                    time.sleep(0.5)

                img = fast_screencap(device)  # Re-capture fresh image after clicks
                if img is None:
                    return None

            dl_pts = img_search(img, os.path.join(IMG_DIR, "download.bmp"))
            if dl_pts:
                gui_log(device.serial, "Floating: download.bmp found! Clicking...", step="Floating")
                x, y = dl_pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
            
            fg_pts = img_search(img, os.path.join(IMG_DIR, "fixgoogle.bmp"))
            if fg_pts:
                gui_log(device.serial, "Floating: fixgoogle.bmp found! Clicking...", step="Floating")
                x, y = fg_pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")

            sell_pts = img_search(img, os.path.join(IMG_DIR, "sell.bmp"))
            if sell_pts:
                gui_log(device.serial, "🛑 Floating: sell.bmp found! Force closing app and moving file to login-failed", step="Sell Detected")
                device.shell("am force-stop jp.konami.pesam")
                time.sleep(1)
                
                original_name = DEVICE_FILE_ASSIGNMENTS.get(device.serial)
                if original_name:
                    file_path = os.path.join(INPUT_DIR, original_name)
                    dest_path = os.path.join(LOGIN_FAILED_DIR, original_name)
                    if os.path.exists(file_path):
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        shutil.copy2(file_path, dest_path)
                        os.remove(file_path)
                        gui_log(device.serial, f"✅ Sorted (Sell): {original_name} -> {LOGIN_FAILED_DIR}", step="Sell Sorted")
                
                raise SellScreenException("sell.bmp detected")

            fc_pts = img_search(img, os.path.join(IMG_DIR, "fixclear.bmp"))
            if fc_pts:
                gui_log(device.serial, "Floating: fixclear.bmp found! Clearing app and moving file to file-error", step="Fix Clear")
                device.shell("pm clear jp.konami.pesam")
                
                original_name = DEVICE_FILE_ASSIGNMENTS.get(device.serial)
                if original_name:
                    file_path = os.path.join(INPUT_DIR, original_name)
                    dest_path = os.path.join(FILE_ERROR_DIR, original_name)
                    if os.path.exists(file_path):
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        shutil.copy2(file_path, dest_path)
                        os.remove(file_path)
                        gui_log(device.serial, f"Moved {original_name} to file-error", step="Fix Clear")
                
                raise DeviceResetException("fixclear.bmp detected")

            flg1_pts = img_search(img, os.path.join(IMG_DIR, "fixlg1.bmp"))
            if flg1_pts:
                gui_log(device.serial, "Floating: fixlg1.bmp found! Looping fixlg2 -> fixlg3", step="Fix Lg")
                deadline_lg = time.time() + 60
                seen_lg3 = False
                while time.time() < deadline_lg:
                    img_lg = fast_screencap(device)
                    if img_lg is not None:
                        pts3 = img_search(img_lg, os.path.join(IMG_DIR, "fixlg3.bmp"))
                        if pts3:
                            x, y = pts3[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(device.serial, "Clicked fixlg3.bmp", step="Fix Lg")
                            time.sleep(2)
                            seen_lg3 = True
                            deadline_lg = time.time() + 10  # Extend deadline after click
                            continue
                        elif seen_lg3:
                            gui_log(device.serial, "fixlg3.bmp disappeared, resuming normal work...", step="Fix Lg")
                            break
                        
                        pts2 = img_search(img_lg, os.path.join(IMG_DIR, "fixlg2.bmp"))
                        if pts2:
                            x, y = pts2[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(device.serial, "Clicked fixlg2.bmp", step="Fix Lg")
                            time.sleep(2)
                            continue
                    time.sleep(0.5)
                
                img = fast_screencap(device)

            fl_pts = img_search(img, os.path.join(IMG_DIR, "fixloading.bmp"))
            if fl_pts:
                gui_log(device.serial, "Floating: fixloading.bmp found! Executing fixload1 -> fixload2", step="Fix Loading")
                # Wait up to 20 seconds for fixload1 and click it until it disappears
                deadline1 = time.time() + 20
                clicked_1 = False
                while time.time() < deadline1:
                    img_tmp1 = fast_screencap(device)
                    if img_tmp1 is not None:
                            pts1 = img_search(img_tmp1, os.path.join(IMG_DIR, "fixload1.bmp"))
                            if pts1:
                                x, y = pts1[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                gui_log(device.serial, "Clicked fixload1.bmp", step="Fix Loading")
                                time.sleep(2)
                                clicked_1 = True
                                deadline1 = time.time() + 10 # Extend deadline after click
                                continue
                            elif clicked_1:
                                # It was clicked and is no longer found
                                break
                    time.sleep(0.5)

                if clicked_1:
                    # Wait up to 10 seconds for fixload2
                    deadline2 = time.time() + 10
                    while time.time() < deadline2:
                        img_tmp2 = fast_screencap(device)
                        if img_tmp2 is not None:
                                pts2 = img_search(img_tmp2, os.path.join(IMG_DIR, "fixload2.bmp"))
                                if pts2:
                                    x, y = pts2[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    gui_log(device.serial, "Clicked fixload2.bmp", step="Fix Loading")
                                    time.sleep(2)
                                    break
                        time.sleep(0.5)

                # Re-capture the screen after fixing so the caller gets a fresh image
                img = fast_screencap(device)

            # fixevent.bmp floating check
            if not DEVICE_DISABLE_FIXEVENT.get(device.serial, False):
                fe_pts = img_search(img, os.path.join(IMG_DIR, "fixevent.bmp"))
                if fe_pts:
                    gui_log(device.serial, "Floating: fixevent.bmp found! Checking if it persists for 8s...", step="Fix Event")
                    persisted = True
                    for _ in range(8):
                        time.sleep(1)
                        img_check = fast_screencap(device)
                        if img_check is None:
                            persisted = False
                            break
                        pts_check = img_search(img_check, os.path.join(IMG_DIR, "fixevent.bmp"))
                        if not pts_check:
                            persisted = False
                            break
                    
                    if persisted:
                        gui_log(device.serial, "fixevent.bmp persisted for 8s! Clicking...", step="Fix Event")
                        img_click = fast_screencap(device)
                        if img_click is not None:
                            pts_click = img_search(img_click, os.path.join(IMG_DIR, "fixevent.bmp"))
                            if pts_click:
                                x, y = pts_click[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                gui_log(device.serial, f"Clicked fixevent.bmp at ({x}, {y})", step="Fix Event")
                                time.sleep(2)
                        img = fast_screencap(device)

            # fixalert1.bmp floating check
            fa_pts = img_search(img, os.path.join(IMG_DIR, "fixalert1.bmp"))
            if fa_pts:
                gui_log(device.serial, "Floating: fixalert1.bmp found! Executing fixalert2 -> fixalert3", step="Fix Alert")
                # Wait up to 15 seconds for fixalert2 and click until gone
                deadline_fa2 = time.time() + 15
                clicked_fa2 = False
                while time.time() < deadline_fa2:
                    img_fa2 = fast_screencap(device)
                    if img_fa2 is not None:
                        pts_fa2 = img_search(img_fa2, os.path.join(IMG_DIR, "fixalert2.bmp"))
                        if pts_fa2:
                            x, y = pts_fa2[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(device.serial, "Clicked fixalert2.bmp", step="Fix Alert")
                            time.sleep(2)
                            clicked_fa2 = True
                            deadline_fa2 = time.time() + 10  # ต่อเวลารอหายไป
                        elif clicked_fa2:
                            break  # เคยกดแล้ว + หายแล้ว → ไป fixalert3
                    time.sleep(0.5)

                if clicked_fa2:
                    # Wait up to 15 seconds for fixalert3 and click until gone
                    deadline_fa3 = time.time() + 15
                    while time.time() < deadline_fa3:
                        img_fa3 = fast_screencap(device)
                        if img_fa3 is not None:
                            pts_fa3 = img_search(img_fa3, os.path.join(IMG_DIR, "fixalert3.bmp"))
                            if pts_fa3:
                                x, y = pts_fa3[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                gui_log(device.serial, "Clicked fixalert3.bmp", step="Fix Alert")
                                time.sleep(2)
                                deadline_fa3 = time.time() + 10  # ต่อเวลารอหายไป
                            else:
                                break  # หายแล้ว → ไปต่อ
                        time.sleep(0.5)

                # Re-capture after fixing
                img = fast_screencap(device)

        # (screenshot preview removed — login.py ไม่มี preview widget, ลด GUI lag)
        return img
    except (DeviceResetException, SellScreenException):
        raise
    except Exception:
        return None

def load_template(path):
    if path not in IMAGE_CACHE:
        if os.path.exists(path):
            t = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if t is not None:
                IMAGE_CACHE[path] = t
                return t
        
        # Try alternate extension (.bmp <-> .png) if not found
        base, ext = os.path.splitext(path)
        alt_exts = [".bmp", ".png"]
        alt_exts = [e for e in alt_exts if e.lower() != ext.lower()]
        for alt in alt_exts:
            alt_path = base + alt
            if os.path.exists(alt_path):
                t = cv2.imread(alt_path, cv2.IMREAD_GRAYSCALE)
                if t is not None:
                    IMAGE_CACHE[path] = t
                    return t
                    
    return IMAGE_CACHE.get(path)

def img_search(gray_img, find_path, threshold=0.8):
    """Returns list of (cx, cy) match centers."""
    if gray_img is None:
        return []
    tmpl = load_template(find_path)
    if tmpl is None:
        return []
    h, w = tmpl.shape
    res  = cv2.matchTemplate(gray_img, tmpl, cv2.TM_CCOEFF_NORMED)
    locs = list(zip(*np.where(res >= threshold)[::-1]))
    if not locs:
        return []
    rects = [[x, y, w, h] for x, y in locs] * 2
    rects, _ = cv2.groupRectangles(rects, groupThreshold=1, eps=1)
    return [(x + w // 2, y + h // 2) for x, y, w, h in rects] if len(rects) else []

# ═════════════════════════════════════════════════════════════════════════════
# OCR Helper (Ref: find-gearname.py)
# ═════════════════════════════════════════════════════════════════════════════
_reader = None

def read_screen_text(img, region=None, serial="unknown"):
    """OCR Logic using EasyOCR (priority) or Pytesseract — Enhanced for max accuracy"""
    if img is None: return ""
    
    # Crop region (numpy view copy to avoid sharing memory across threads)
    if region:
        img = img[region.y : region.y + region.h, region.x : region.x + region.w].copy()
    
    # Run OCR concurrently in parallel at full performance without queue waiting
    return _read_screen_text_locked(img, serial)

def _read_screen_text_locked(img, serial):
    """Internal OCR — เรียกผ่าน read_screen_text เท่านั้น (มี lock แล้ว)"""
    if img is None: return ""
    
    # ── Debug: บันทึกภาพที่สแกนเมื่อ DEBUG_OCR=1 ──
    if DEBUG_OCR == 1:
        debug_dir = "debug-ocr"
        os.makedirs(debug_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        safe_serial = serial.replace(":", "-").replace(".", "_")
        debug_name = f"{safe_serial}_{ts}"
        # บันทึกภาพ crop ดิบ
        cv2.imwrite(os.path.join(debug_dir, f"{debug_name}_raw.png"), img)
    
    # 1. Try EasyOCR
    if easyocr is not None:
        global _reader
        try:
            print(f"[OCR] [{serial}] Attempting EasyOCR...")
            if _reader is None:
                _reader = easyocr.Reader(['en'], gpu=False)
            
            # Apply bilateral filter to smooth card textures but keep text edges extremely sharp
            cleaned_img = cv2.bilateralFilter(img, 9, 75, 75)
            # Resize 2x using Cubic interpolation for cleaner character strokes
            resized_easy = cv2.resize(cleaned_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            
            results = _reader.readtext(resized_easy, detail=0)
            res = " ".join(results).strip()
            if res:
                print(f"[OCR] [{serial}] EasyOCR Result: '{res}'")
                return res
        except Exception as e:
            print(f"[OCR] EasyOCR Error: {e}")
            pass

    # 2. Fallback to Pytesseract — Enhanced multi-pass
    if pytesseract is not None:
        try:
            print(f"[OCR] Attempting Pytesseract (Enhanced)...")
            # แปลงเป็นเทา
            if len(img.shape) == 3:
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                img_gray = img
                
            # ขยายภาพ 4 เท่าเพื่อให้ตัวหนังสือใหญ่ขึ้น (4x ดีกว่า 3x สำหรับตัวเล็ก)
            img_resized = cv2.resize(img_gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            
            # ── Debug: บันทึกภาพ preprocessed ──
            if DEBUG_OCR == 1:
                cv2.imwrite(os.path.join(debug_dir, f"{debug_name}_methodRaw.png"), img_resized)
            
            # ── สแกนโหมดเดียวเพื่อความรวดเร็ว ──
            all_results = []
            configs = [
                (img_resized, "--psm 7", "Raw-psm7"), # raw grayscale single line
            ]
            
            for proc_img, psm, label in configs:
                text = pytesseract.image_to_string(
                    proc_img, lang="eng",
                    config=f"{psm}"
                )
                res = text.strip()
                if res:
                    print(f"[OCR] {label}: '{res}'")
                    all_results.append(res)
            
            combined_result = " | ".join(all_results)
            if combined_result:
                print(f"[OCR] ★ Combined Result: '{combined_result}'")
            else:
                print(f"[OCR] Pytesseract returned EMPTY string (all methods)")
            return combined_result
        except Exception as e:
            print(f"[OCR] Pytesseract Error: {e}")
            pass
            
    return ""

def is_hero_match(hero_name, ocr_text):
    if not hero_name or not ocr_text:
        return False
    
    import unicodedata
    def clean_str(s):
        normalized = unicodedata.normalize('NFKD', s)
        ascii_bytes = normalized.encode('ASCII', 'ignore')
        ascii_str = ascii_bytes.decode('ASCII')
        return "".join([c.lower() for c in ascii_str if c.isalnum() or c.isspace()]).strip()
        
    cleaned_hero = clean_str(hero_name)
    cleaned_ocr = clean_str(ocr_text)
    
    # OCR Typos / Aliases mapping
    if "aubamevang" in cleaned_ocr:
        cleaned_ocr = cleaned_ocr.replace("aubamevang", "aubameyang")
    if "aubamevang" in cleaned_hero:
        cleaned_hero = cleaned_hero.replace("aubamevang", "aubameyang")
        
    if not cleaned_hero or not cleaned_ocr:
        return False
    # ป้องกัน OCR ข้อความสั้นเกินไป (noise/ขยะจากหน้าจอ) จับคู่ผิดพลาด
    if len(cleaned_ocr) < 5:
        return False
        
    if cleaned_hero in cleaned_ocr:
        return True
        
    hero_words = cleaned_hero.split()
    if len(hero_words) > 1:
        if all(w in cleaned_ocr for w in hero_words):
            return True
        match_count = sum(1 for w in hero_words if w in cleaned_ocr)
        if match_count >= max(2, len(hero_words) * 0.7):
            return True
            
    # คำเดี่ยว >= 5 ตัว — อนุญาตเฉพาะฮีโร่ชื่อคำเดียว (เช่น "Mbappe", "Marcelo")
    # ถ้าชื่อหลายคำ (เช่น "Peter Schmeichel") ห้ามจับคู่ด้วยคำเดียว ป้องกันชื่อซ้ำคนอื่น
    if len(hero_words) == 1:
        if len(hero_words[0]) >= 5 and hero_words[0] in cleaned_ocr:
            return True
            
    # Fuzzy sequence similarity matching (90% spelling match ratio)
    import difflib
    len_hero = len(cleaned_hero)
    len_ocr = len(cleaned_ocr)
    if len_hero >= 5:
        # Check windows of size len_hero - 1, len_hero, len_hero + 1
        for w_size in [len_hero - 1, len_hero, len_hero + 1]:
            if w_size < 4 or w_size > len_ocr:
                continue
            for start in range(len_ocr - w_size + 1):
                sub = cleaned_ocr[start:start + w_size]
                matcher = difflib.SequenceMatcher(None, cleaned_hero, sub)
                if matcher.quick_ratio() >= 0.85:
                    if matcher.ratio() >= 0.88: # ~90% similarity
                        return True
            
    return False

# ═════════════════════════════════════════════════════════════════════════════
# File management  ← แก้ตรงนี้
# ═════════════════════════════════════════════════════════════════════════════
def pick_next_file():
    """
    Thread-safe: pick ONE .dat from input-id that is NOT already in use
    AND does NOT already exist in login-success (เคย login แล้ว).
    Returns (full_path, basename) or (None, None).
    """
    with file_pick_lock:
        # Snapshot ไฟล์ที่ทำงานสำเร็จ/แยกประเภทไปแล้ว ทั้งหมด
        done_files = (glob.glob(os.path.join(LOGIN_SUCCESS_DIR, "*.dat")) +
                      glob.glob(os.path.join(BACKUP_ID_DIR, "**", "*.dat"), recursive=True) +
                      glob.glob(os.path.join(NO_HERO_DIR, "*.dat")) +
                      glob.glob(os.path.join(FOUND_HERO_DIR, "**", "*.dat"), recursive=True))
        already_done = {os.path.basename(p) for p in done_files}

        for f in sorted(glob.glob(os.path.join(INPUT_DIR, "*.dat"))):
            name = os.path.basename(f)
            if name in in_use_files:       # กำลัง process อยู่แล้ว
                continue
            if name in already_done:       # เคยทำไปแล้ว → ข้าม
                continue
            in_use_files.add(name)
            try:
                shutil.copy2(f, os.path.join(RUN_FILE_DIR, name))
            except Exception:
                pass
            return f, name
        return None, None

def release_file(name):
    """ปล่อยไฟล์ออกจาก in-use set และลบออกจาก run-file."""
    if name:
        with file_pick_lock:
            in_use_files.discard(name)
            try:
                run_path = os.path.join(RUN_FILE_DIR, name)
                if os.path.exists(run_path):
                    os.remove(run_path)
            except Exception:
                pass

# ═════════════════════════════════════════════════════════════════════════════
def push_dat_to_device(device, local_path):
    serial     = device.serial
    safe_id    = serial.replace(".", "_").replace(":", "_")
    tmp_local  = os.path.join(INPUT_DIR, f"_push_{safe_id}.dat")
    tmp_remote = "/data/local/tmp/online_user_id_data.dat"
    
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}

    try:
        # 1. Force stop app
        gui_log(serial, "Step 1: Force stopping app...", step="Cleanup")
        subprocess.run([adb_path, "-s", serial, "shell", "am force-stop jp.konami.pesam"], 
                       capture_output=True, timeout=5, **kwargs)
        time.sleep(0.5)

        # 2. Clear remote dir
        gui_log(serial, "Step 2: Clearing auth directory...", step="Cleanup")
        subprocess.run([adb_path, "-s", serial, "shell", f"su -c 'rm -rf {REMOTE_AUTH_DIR}/* && mkdir -p {REMOTE_AUTH_DIR}'"], 
                       capture_output=True, text=True, timeout=5, **kwargs)
        time.sleep(0.3)

        # 3. Copy to local temp and Push
        gui_log(serial, "Step 3: Pushing file to device...", step="Push")
        shutil.copy2(local_path, tmp_local)
        subprocess.run([adb_path, "-s", serial, "push", tmp_local, tmp_remote],
                       capture_output=True, text=True, timeout=20, **kwargs)

        # 4. Move to game folder
        gui_log(serial, "Step 4: Applying data to game...", step="Inject")
        subprocess.run([adb_path, "-s", serial, "shell", f"su -c 'cp {tmp_remote} {REMOTE_DAT_FILE} && chmod 666 {REMOTE_DAT_FILE} && rm -f {tmp_remote}'"],
                       capture_output=True, text=True, timeout=5, **kwargs)
        
        # 5. Verify
        gui_log(serial, "Step 5: Verifying...", step="Verify")
        time.sleep(0.5)
        check_res = subprocess.run([adb_path, "-s", serial, "shell", f"su -c 'ls -l {REMOTE_DAT_FILE}'"], 
                                   capture_output=True, text=True, timeout=5, **kwargs)
        check = check_res.stdout.strip()
        
        if "No such" not in check and check:
            gui_log(serial, f"Verified: {check}", step="Push OK")
            return True
        else:
            return False

    except Exception as e:
        gui_log(serial, f"Push Error: {e}", step="Error")
        return False
    finally:
        if os.path.exists(tmp_local):
            os.remove(tmp_local)

def find_hero_mode(device, cycle_start, serial, original_name, file_path):
    """
    Dedicated function to find heroes with robust checking (Triple Check).
    Checks multiple times to ensure a consistent match and avoid false positives.
    """
    gui_log(serial, "Find Hero sequence started...", step="Find Hero", status="working")
    
    def _check_fixteam(img_current):
        pts_team = img_search(img_current, os.path.join(IMG_DIR, "fixteam.bmp"), threshold=0.95)
        if pts_team:
            gui_log(serial, "fixteam.bmp detected! Spamming Back...", step="Fix Team")
            while True:
                check_device_reset(serial, cycle_start)
                device.shell("input keyevent 4")
                time.sleep(0.4)
                img_c = get_screen_capture(device)
                if img_c is not None:
                    pts_c = img_search(img_c, os.path.join(IMG_DIR, "cancel.bmp"))
                    if pts_c:
                        x, y = pts_c[0]
                        gui_log(serial, f"cancel.bmp found at ({x},{y})! Clicking and stopping back spam.", step="Fix Team Stop")
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(1.0)
                        break
            return True
        return False

    # 1. fin1 -> fin2 -> fin3 -> fin4 -> fin5 -> fin6 -> fin7 -> fin8 -> fin9 navigation
    nav_steps_1 = [
        ("fin1.bmp", "fin2.bmp"),
        ("fin2.bmp", "fin3.bmp"),
        ("fin3.bmp", "fin4.bmp"),
        ("fin4.bmp", "fin5.bmp"),
        ("fin5.bmp", "fin6.bmp"),
    ]
    for name_curr, name_next in nav_steps_1:
        gui_log(serial, f"Waiting for {name_curr}...", step=f"{name_curr} Waiting")
        last_click_time = 0
        fixfind_first_seen = None
        while True:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                if _check_fixteam(img):
                    continue
                    
                if img_search(img, os.path.join(IMG_DIR, name_next), threshold=0.95):
                    gui_log(serial, f"{name_next} detected! Proceeding to next step.", step=f"{name_next} Seen")
                    break
                    
                if name_curr == "fin5.bmp":
                    pts_ff = img_search(img, os.path.join(IMG_DIR, "fixfind.bmp"), threshold=0.95)
                    if pts_ff:
                        if fixfind_first_seen is None:
                            fixfind_first_seen = time.time()
                            gui_log(serial, "fixfind.bmp detected, watching for 15s...", step="fixfind Watch")
                        elif time.time() - fixfind_first_seen >= 15.0:
                            gui_log(serial, "fixfind.bmp stuck for 15s! Proceeding to fin6...", step="fixfind Restart")
                            break
                    else:
                        if "fixfind_first_seen" in locals():
                            fixfind_first_seen = None

                    pts_ff2 = img_search(img, os.path.join(IMG_DIR, "fixfinv2.bmp"), threshold=0.95)
                    if pts_ff2:
                        gui_log(serial, "fixfinv2.bmp detected! Clicking fixout.bmp...", step="fixfinv2 Action")
                        pts_out = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.95)
                        if pts_out:
                            x_o, y_o = pts_out[0]
                            device.shell(f"input swipe {x_o} {y_o} {x_o} {y_o} 100")
                            gui_log(serial, f"Clicked fixout.bmp at ({x_o}, {y_o})", step="fixout Click")
                            time.sleep(1.0)
                        break

                pts = img_search(img, os.path.join(IMG_DIR, name_curr), threshold=0.95)
                if pts:
                    now = time.time()
                    if now - last_click_time >= 5.0:
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, f"Clicked {name_curr}", step=f"{name_curr} Click")
                        last_click_time = now
            time.sleep(0.5)

    while True:
        nav_steps_2 = [
            ("fin6.bmp", "fin7.bmp"),
            ("fin7.bmp", "fin8.bmp"),
            ("fin8.bmp", "fin9.bmp"),
        ]
        for name_curr, name_next in nav_steps_2:
            gui_log(serial, f"Waiting for {name_curr}...", step=f"{name_curr} Waiting")
            last_click_time = 0
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    if _check_fixteam(img):
                        continue
                        
                    if img_search(img, os.path.join(IMG_DIR, name_next), threshold=0.95):
                        gui_log(serial, f"{name_next} detected! Proceeding to next step.", step=f"{name_next} Seen")
                        break
                    pts = img_search(img, os.path.join(IMG_DIR, name_curr), threshold=0.95)
                    if pts:
                        now = time.time()
                        if now - last_click_time >= 5.0:
                            x, y = pts[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(serial, f"Clicked {name_curr}", step=f"{name_curr} Click")
                            last_click_time = now
                time.sleep(0.5)

        # 2. Wait, click, and verify fin9.bmp
        gui_log(serial, "Waiting fin9.bmp...", step="fin9 Wait")
        fin9_verified = False
        while True:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                if _check_fixteam(img):
                    continue
                    
                # Check if verify.png is already visible on screen
                if img_search(img, os.path.join(IMG_DIR, "verify.png"), threshold=0.9):
                    gui_log(serial, "verify.png detected! Proceeding to swipe...", step="fin9 Verified")
                    fin9_verified = True
                    break
            
                # Find and click fin9.bmp
                pts9 = img_search(img, os.path.join(IMG_DIR, "fin9.bmp"), threshold=0.95)
                if pts9:
                    x, y = pts9[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    gui_log(serial, "Clicked fin9.bmp", step="fin9 Click")
                    time.sleep(3.0)  # รอให้หน้าจอเปลี่ยน/แสดง verify.png
                
                    # Check immediately after click
                    img_after = get_screen_capture(device)
                    if img_after is not None:
                        if img_search(img_after, os.path.join(IMG_DIR, "verify.png"), threshold=0.9):
                            gui_log(serial, "verify.png detected after click! Proceeding...", step="fin9 Verified")
                            fin9_verified = True
                            break
            time.sleep(0.5)

        # 3. Swipe coordinate 529 360 536 161 (scroll down)
        gui_log(serial, "Swiping at 529 360 536 161...", step="Swipe 529 360")
        device.shell("input swipe 529 360 536 161 2000")
    
        # 4. Wait 10s then click Position 1 (329, 274) with verification (requires at least 2 verify icons)
        gui_log(serial, "Sleeping 10s after swipe...", step="Sleep Post-Swipe")
        time.sleep(10.0)
    
        need_restart = False
        fixfind_first_seen = None
        while True:
            check_device_reset(serial, cycle_start)
            gui_log(serial, "Clicking Position 1 (329, 274)...", step="Click Pos1")
            device.shell("input swipe 329 274 329 274 100")
        
            # Search for 5s to find at least 2 verify icons on screen
            deadline_pos1 = time.time() + 5.0
            verified_pos1 = False
            while time.time() < deadline_pos1:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    pts_ff = img_search(img, os.path.join(IMG_DIR, "fixfind.bmp"), threshold=0.95)
                    if pts_ff:
                        if fixfind_first_seen is None:
                            fixfind_first_seen = time.time()
                            gui_log(serial, "fixfind.bmp detected, watching for 15s...", step="fixfind Watch")
                        elif time.time() - fixfind_first_seen >= 15.0:
                            gui_log(serial, "fixfind.bmp stuck for 15s! Restarting from fin6...", step="fixfind Restart")
                            need_restart = True
                            break
                    else:
                        fixfind_first_seen = None

                    pts_ff2 = img_search(img, os.path.join(IMG_DIR, "fixfinv2.bmp"), threshold=0.95)
                    if pts_ff2:
                        gui_log(serial, "fixfinv2.bmp detected! Clicking fixout.bmp...", step="fixfinv2 Action")
                        pts_out = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.95)
                        if pts_out:
                            x_o, y_o = pts_out[0]
                            device.shell(f"input swipe {x_o} {y_o} {x_o} {y_o} 100")
                            gui_log(serial, f"Clicked fixout.bmp at ({x_o}, {y_o})", step="fixout Click")
                            time.sleep(1.0)
                        need_restart = True
                        break

                    pts_v = img_search(img, os.path.join(IMG_DIR, "verify.png"), threshold=0.9)
                    if len(pts_v) >= 2:
                        gui_log(serial, f"Detected {len(pts_v)} verify icons (>= 2)! Position 1 Verified.", step="Pos1 Verified")
                        verified_pos1 = True
                        break
                time.sleep(0.5)
            
            if need_restart or verified_pos1:
                break
            else:
                gui_log(serial, "Failed to find 2 verify icons in 5s! Retrying click on Position 1...", step="Pos1 Retry")

        if need_restart:
            continue

        time.sleep(2.5)

        # 4b. Click Position 2 (319, 338) with verification (requires at least 3 verify icons)
        fixfind_first_seen = None
        while True:
            check_device_reset(serial, cycle_start)
            gui_log(serial, "Clicking Position 2 (319, 338)...", step="Click Pos2")
            device.shell("input swipe 319 338 319 338 100")
        
            # Search for 5s to find at least 3 verify icons on screen
            deadline_pos2 = time.time() + 5.0
            verified_pos2 = False
            while time.time() < deadline_pos2:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    pts_ff = img_search(img, os.path.join(IMG_DIR, "fixfind.bmp"), threshold=0.95)
                    if pts_ff:
                        if fixfind_first_seen is None:
                            fixfind_first_seen = time.time()
                            gui_log(serial, "fixfind.bmp detected, watching for 15s...", step="fixfind Watch")
                        elif time.time() - fixfind_first_seen >= 15.0:
                            gui_log(serial, "fixfind.bmp stuck for 15s! Restarting from fin6...", step="fixfind Restart")
                            need_restart = True
                            break
                    else:
                        fixfind_first_seen = None

                    pts_ff2 = img_search(img, os.path.join(IMG_DIR, "fixfinv2.bmp"), threshold=0.95)
                    if pts_ff2:
                        gui_log(serial, "fixfinv2.bmp detected! Clicking fixout.bmp...", step="fixfinv2 Action")
                        pts_out = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.95)
                        if pts_out:
                            x_o, y_o = pts_out[0]
                            device.shell(f"input swipe {x_o} {y_o} {x_o} {y_o} 100")
                            gui_log(serial, f"Clicked fixout.bmp at ({x_o}, {y_o})", step="fixout Click")
                            time.sleep(1.0)
                        need_restart = True
                        break

                    pts_v = img_search(img, os.path.join(IMG_DIR, "verify.png"), threshold=0.9)
                    if len(pts_v) >= 3:
                        gui_log(serial, f"Detected {len(pts_v)} verify icons (>= 3)! Position 2 Verified.", step="Pos2 Verified")
                        verified_pos2 = True
                        break
                time.sleep(0.5)
            
            if need_restart or verified_pos2:
                break
            else:
                gui_log(serial, "Failed to find 3 verify icons in 5s! Retrying click on Position 2...", step="Pos2 Retry")

        if need_restart:
            continue

        time.sleep(3.0)  # รอหน้าจอเปลี่ยนเสร็จ


        # 5b. Wait and click fin13.bmp with stuck protection (click once, then retry if still on screen for 10s)
        gui_log(serial, "Waiting for fin13.bmp...", step="fin13 Wait")
        clicked_fin13 = False
        while True:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                if _check_fixteam(img):
                    continue
                    
                pts13 = img_search(img, os.path.join(IMG_DIR, "fin13.bmp"), threshold=0.95)
                if pts13:
                    x, y = pts13[0]
                    gui_log(serial, f"Found fin13.bmp! Performing normal click at ({x}, {y})...", step="fin13 First Click")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2.5)  # รอระยะนิ่งเปลี่ยนหน้าจอ
                
                    # ตรวจเช็คต่อไปว่า fin13 ค้างอยู่บนหน้าจอครบ 10 วินาทีหรือไม่
                    stuck_start = time.time()
                    while True:
                        check_device_reset(serial, cycle_start)
                        img_check = get_screen_capture(device)
                        if img_check is None:
                            time.sleep(0.5)
                            continue
                    
                        pts_check = img_search(img_check, os.path.join(IMG_DIR, "fin13.bmp"), threshold=0.95)
                        if not pts_check:
                            # fin13 หายไปแล้วสำเร็จ!
                            gui_log(serial, "fin13.bmp disappeared successfully!", step="fin13 Gone")
                            break
                    
                        # ถ้ายังเจอค้างอยู่บนจอ
                        x_sk, y_sk = pts_check[0] # อัปเดตพิกัดเผื่อปุ่มเลื่อน
                        elapsed = time.time() - stuck_start
                        if elapsed >= 10.0:
                            # ค้างครบ 10 วินาที ค่อยกดซ้ำอีกรอบ!
                            gui_log(serial, f"fin13.bmp stuck for {elapsed:.1f}s! Clicking again...", step="fin13 Stuck Retry")
                            device.shell(f"input swipe {x_sk} {y_sk} {x_sk} {y_sk} 100")
                            stuck_start = time.time()  # รีเซ็ตเวลาเริ่มต้นค้างใหม่เพื่อเฝ้ารออีก
                    
                        time.sleep(0.5)
                
                    clicked_fin13 = True
                    break
            time.sleep(0.5)

        if not clicked_fin13:
            gui_log(serial, "fin13.bmp not clicked (timeout), proceeding anyway...", step="fin13 Skip")

        break # Successfully finished fin13, break the main retry loop

    # 6. Wait for checkpointfind (OCR Screen)
    gui_log(serial, "Waiting checkpointfind.bmp...", step="checkpointfind")
    deadline_cp = time.time() + 45
    found_cp = False
    while time.time() < deadline_cp:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "checkpointfind.bmp"))
            if pts:
                gui_log(serial, "checkpointfind.bmp found!", step="Find Hero CP")
                found_cp = True
                break
        time.sleep(1)
    
    if not found_cp:
        gui_log(serial, "checkpointfind.bmp not found! Proceeding with scan anyway.", step="CP Fail")
    
    time.sleep(3) # Let screen settle

    # 6. OCR Scanning (Lock 1, Lock 2 & Lock 3 with Robust Two-Pass Double Check)
    found_heroes = []
    last_lock1_text = ""
    last_lock2_text = ""
    last_lock3_text = ""
    target_list = list_find_hero if (list_find_hero and any(list_find_hero)) else HERO_LIST
    target_heroes = [h.strip() for h in target_list if h and h.strip()]

    for pass_num in range(1, 3):
        found_heroes.clear()
        
        # Capture screen once for this pass (maximum speed, zero mismatch)
        img = get_screen_capture(device)
        if img is not None:
            # Lock 1 Scanning
            lock1_region = Region(154, 134, 679, 39)
            lock1_text = read_screen_text(img, region=lock1_region, serial=serial)
            last_lock1_text = lock1_text if lock1_text else ""
            gui_log(serial, f"Lock 1 OCR: {lock1_text if lock1_text else '<EMPTY>'}", step="Scan Lock 1")
            for h in target_heroes:
                if is_hero_match(h, lock1_text):
                    if h not in found_heroes:
                        found_heroes.append(h)
                        gui_log(serial, f"Lock 1 Match: {h}", step=f"⭐ {h}")

            # Lock 2 Scanning
            lock2_region = Region(156, 249, 646, 34)
            lock2_text = read_screen_text(img, region=lock2_region, serial=serial)
            last_lock2_text = lock2_text if lock2_text else ""
            gui_log(serial, f"Lock 2 OCR: {lock2_text if lock2_text else '<EMPTY>'}", step="Scan Lock 2")
            for h in target_heroes:
                if is_hero_match(h, lock2_text):
                    if h not in found_heroes:
                        found_heroes.append(h)
                        gui_log(serial, f"Lock 2 Match: {h}", step=f"⭐ {h}")

            # Lock 3 Scanning
            lock3_region = Region(157, 360, 658, 34)
            lock3_text = read_screen_text(img, region=lock3_region, serial=serial)
            last_lock3_text = lock3_text if lock3_text else ""
            gui_log(serial, f"Lock 3 OCR: {lock3_text if lock3_text else '<EMPTY>'}", step="Scan Lock 3")
            for h in target_heroes:
                if is_hero_match(h, lock3_text):
                    if h not in found_heroes:
                        found_heroes.append(h)
                        gui_log(serial, f"Lock 3 Match: {h}", step=f"⭐ {h}")
        
        # If at least one hero matched, exit scanning successfully!
        if found_heroes:
            break
            
        # If we failed to find any hero in Pass 1, wait 2s and scan one more time!
        if pass_num == 1:
            gui_log(serial, "No hero found on Pass 1. Retrying in 2s for screen to settle...", step="OCR Retry")
            time.sleep(2.0)

    # 7. Shutdown and Move
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    clean_orig = original_name
    if "+" in clean_orig: clean_orig = clean_orig.split("+")[-1]
    elif "-" in clean_orig: clean_orig = clean_orig.split("-")[-1]

    if found_heroes:
        num_heroes = len(found_heroes)
        if num_heroes >= 3:
            subfolder = "hero3"
        elif num_heroes == 2:
            subfolder = "hero2"
        else:
            subfolder = "hero1"
        dest_dir = os.path.join(FOUND_HERO_DIR, subfolder)
        os.makedirs(dest_dir, exist_ok=True)

        hero_prefix = "+".join(found_heroes)
        final_name = f"{hero_prefix}+{clean_orig}"
        gui_log(serial, f"⭐ MATCH: {hero_prefix}", step=f"⭐ {hero_prefix}")
    else:
        l1_lower = last_lock1_text.lower()
        l2_lower = last_lock2_text.lower()
        l3_lower = last_lock3_text.lower()
        
        is_empty_state = (
            "n 'chang trv" in l1_lower or 
            "found ter conditions" in l2_lower or
            "no matching" in l1_lower or
            "no matching" in l2_lower or
            "no matching" in l3_lower or
            "filter conditions" in l1_lower or
            "filter conditions" in l2_lower or
            "filter conditions" in l3_lower or
            "conditions" in l1_lower or
            "conditions" in l2_lower or
            "conditions" in l3_lower
        )
        
        if is_empty_state:
            dest_dir = NO_HERO_DIR
            final_name = clean_orig
            gui_log(serial, "No hero match found (Verified empty state).", step="No Match")
        else:
            dest_dir = FILE_ERROR_DIR
            final_name = clean_orig
            gui_log(serial, "Scan did not show verified empty state. Sending to file-error for safety.", step="Scan Safety")

    dest = os.path.join(dest_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(2)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.copy2(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted: {dest_dir}", step="Sorted", status="working")
        except Exception as me:
            gui_log(serial, f"⚠️ Sort failed: {me}", step="Sort Error")
        
        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    return True

def gacha_free_mode(device, cycle_start, serial, original_name, file_path):
    """
    Gacha Free mode (G loops):
    Each loop: swipe to find gachafree1 → click → gachafree2 → click → checkpointgacha → OCR
    Accumulates hero names from all loops.
    """
    gui_log(serial, "Gacha Free sequence started...", step="GachaFree", status="working")

    # Helper: เช็ค fixcoin.bmp (priority #1) — ถ้าเจอกด Back แค่ 1 ครั้ง
    fixcoin_handled = False
    def _check_fixcoin():
        nonlocal fixcoin_handled
        img_fc = get_screen_capture(device)
        if img_fc is not None:
            pts_fc = img_search(img_fc, os.path.join(IMG_DIR, "fixcoin.bmp"), threshold=0.95)
            if pts_fc:
                if not fixcoin_handled:
                    gui_log(serial, "fixcoin.bmp detected! Pressing Back (once)...", step="Fix Coin")
                    device.shell("input keyevent 4")  # KEYCODE_BACK
                    time.sleep(1.5)
                    fixcoin_handled = True
                return True
            else:
                fixcoin_handled = False  # fixcoin หายแล้ว → reset flag
        return False

    def _check_fixgachafree(img_fg=None):
        if img_fg is None:
            img_fg = get_screen_capture(device)
        if img_fg is not None:
            pts_fg1 = img_search(img_fg, os.path.join(IMG_DIR, "fixgachafree1.bmp"), threshold=0.95)
            if pts_fg1:
                gui_log(serial, "fixgachafree1 detected! Running recovery sequence...", step="Fix GachaFree")
                x, y = pts_fg1[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                time.sleep(1.5)
                
                gui_log(serial, "Waiting for fixgachafree2.bmp...", step="Fix2 Wait")
                while True:
                    img2 = get_screen_capture(device)
                    if img2 is not None:
                        pts_fg2 = img_search(img2, os.path.join(IMG_DIR, "fixgachafree2.bmp"), threshold=0.95)
                        if pts_fg2:
                            gui_log(serial, "Clicked fixgachafree2!", step="Fix2 Click")
                            x2, y2 = pts_fg2[0]
                            device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                            time.sleep(1.5)
                            break
                    time.sleep(0.5)
                    
                gui_log(serial, "Waiting for fixgachafree3.bmp...", step="Fix3 Wait")
                while True:
                    img3 = get_screen_capture(device)
                    if img3 is not None:
                        pts_fg3 = img_search(img3, os.path.join(IMG_DIR, "fixgachafree3.bmp"), threshold=0.95)
                        if pts_fg3:
                            gui_log(serial, "Clicked fixgachafree3!", step="Fix3 Click")
                            x3, y3 = pts_fg3[0]
                            device.shell(f"input swipe {x3} {y3} {x3} {y3} 100")
                            time.sleep(2.0)
                            break
                    time.sleep(0.5)
                
                return True
        return False

    # 1. gacha1 → gacha2 (ทำแค่ครั้งเดียวตอนเริ่ม)
    for i in range(1, 3):
        name = f"gacha{i}.bmp"
        gui_log(serial, f"Waiting {name}...", step=name)
        deadline = time.time() + 30
        while time.time() < deadline:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()  # priority #1
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, name))
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(1.2)
                    break
            time.sleep(0.3)

    # 2. ทำลูปสุ่มกาชาฟรีตามจำนวนที่กำหนดใน config
    found_heroes = []  # เก็บชื่อฮีโร่ที่เจอจากทุก loop
    end_swip_detected = False

    for loop_num in range(1, GACHA_FREE_LOOPS + 1):
        if end_swip_detected:
            break
        gui_log(serial, f"=== Gacha Free Loop {loop_num}/{GACHA_FREE_LOOPS} ===", step=f"Loop {loop_num}")

        # 2a. เลื่อนหา gachafree1.bmp (เช็คก่อน → ไม่เจอ → เลื่อน, ครบ 10 รอบ = ข้าม loop นี้)
        gui_log(serial, f"[Loop {loop_num}] Looking for gachafree1.bmp...", step="Swipe Free")
        found_free = False
        miss_count = 0
        max_miss = 10
        next_first_seen = None  # ติดตาม next.bmp ค้าง
        endswip_first_seen = None  # ติดตาม endswip.bmp ค้าง

        while miss_count < max_miss:
            check_device_reset(serial, cycle_start)
            
            img = get_screen_capture(device)
            if img is not None:
                if _check_fixgachafree(img):
                    miss_count = 0  # รีเซ็ตการนับเผื่อให้มันหา gachafree1 ต่อได้โดยไม่หลุด loop
                    continue
                # === Priority: เช็ค endswip.bmp ===
                pts_es = img_search(img, os.path.join(IMG_DIR, "endswip.bmp"))
                if pts_es:
                    if endswip_first_seen is None:
                        endswip_first_seen = time.time()
                        gui_log(serial, "endswip.bmp detected, watching for 5s...", step="End Watch")
                    elif time.time() - endswip_first_seen >= 5:
                        gui_log(serial, "🛑 endswip.bmp stuck for 5s! Ending Gacha Free cycle.", step="End Swipe")
                        gui_log(serial, f"=== Gacha Free Loop {GACHA_FREE_LOOPS}/{GACHA_FREE_LOOPS} ===", step=f"Loop {GACHA_FREE_LOOPS}")
                        end_swip_detected = True
                        break
                else:
                    endswip_first_seen = None

                # === Priority: เช็ค next.bmp ค้าง ===
                pts_next = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                if pts_next:
                    if next_first_seen is None:
                        next_first_seen = time.time()
                        gui_log(serial, f"[Loop {loop_num}] next.bmp detected, watching...", step="Next Watch")
                    elif time.time() - next_first_seen >= 10:
                        # ค้างครบ 10 วิ → กดจนหาย
                        gui_log(serial, f"[Loop {loop_num}] next.bmp stuck for 10s! Clicking until gone...", step="Next Stuck")
                        next_click_start = time.time()
                        while True:
                            check_device_reset(serial, cycle_start)
                            if time.time() - next_click_start > 15:
                                break
                            img_n = get_screen_capture(device)
                            if img_n is not None:
                                pts_n = img_search(img_n, os.path.join(IMG_DIR, "next.bmp"))
                                if pts_n:
                                    x_n, y_n = pts_n[0]
                                    device.shell(f"input swipe {x_n} {y_n} {x_n} {y_n} 100")
                                    time.sleep(0.8)
                                else:
                                    break  # หายแล้ว
                            else:
                                break
                        gui_log(serial, f"[Loop {loop_num}] next.bmp gone! Resetting swipe search to 1/{max_miss}", step="Next Reset")
                        next_first_seen = None
                        miss_count = 0  # reset เริ่มเลื่อนใหม่
                        time.sleep(1.0)
                        continue
                else:
                    next_first_seen = None  # ไม่เจอ next → reset timer

                # === หา gachafree1 ===
                pts = img_search(img, os.path.join(IMG_DIR, "gachafree1.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] gachafree1 found! Clicking ({x},{y})", step="Free Found")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(0.8)
                    found_free = True
                    # กดจนกว่าจะหายไป (timeout 15s กันค้าง)
                    deadline_gone = time.time() + 15
                    while time.time() < deadline_gone:
                        check_device_reset(serial, cycle_start)
                        img2 = get_screen_capture(device)
                        if img2 is not None:
                            pts2 = img_search(img2, os.path.join(IMG_DIR, "gachafree1.bmp"), threshold=0.95)
                            if pts2:
                                x2, y2 = pts2[0]
                                device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                                time.sleep(0.8)
                            else:
                                break
                        else:
                            break
                    time.sleep(0.5)
                    break
            miss_count += 1
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not here, swiping... ({miss_count}/{max_miss})", step="Swipe")
            device.shell("input swipe 618 308 54 306 1500")
            time.sleep(2.0)

        if not found_free:
            if end_swip_detected:
                break
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not found after {max_miss} swipes, skipping loop", step="Skip")
            continue  # ข้ามไป loop ถัดไป (หรือจบถ้า loop 2)

        # 2b. รอ gachafree2.bmp → กดจนกว่าจะหายไป (timeout 15s → file-error)
        gui_log(serial, f"[Loop {loop_num}] Waiting gachafree2.bmp...", step="gachafree2")
        deadline_gf2 = time.time() + 15
        clicked_gf2 = False
        while time.time() < deadline_gf2:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()  # priority #1
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, "gachafree2.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] gachafree2 found! Clicking ({x},{y})", step="Free2 Found")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(0.8)
                    clicked_gf2 = True
                    deadline_gf2 = time.time() + 10  # ต่อเวลารอหายไป
                elif clicked_gf2:
                    break  # เคยกดแล้ว + หายไปแล้ว → ไปต่อ
            time.sleep(0.3)

        # ถ้าไม่เจอ gachafree2 เลย → file-error แล้วไปไฟล์ใหม่
        if not clicked_gf2:
            gui_log(serial, f"[Loop {loop_num}] gachafree2 not found in 15s → file-error", step="Error")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)
            dest = os.path.join(FILE_ERROR_DIR, original_name)
            if os.path.exists(file_path):
                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                    shutil.copy2(file_path, dest)
                    os.remove(file_path)
                    gui_log(serial, f"Sorted → file-error: {original_name}", step="Sorted")
                except Exception as e:
                    gui_log(serial, f"Sort failed: {e}", step="Sort Error")
            release_file(original_name)
            return True  # break ออกไปเริ่มไฟล์ใหม่

        # ── SKIPANIMATION mode: กด [611,129] ซ้ำๆเร็วๆ จนเจอ skiphero → คลิก → ไปหา next ──
        if SKIPANIMATION == 1:
            gui_log(serial, f"[Loop {loop_num}] SKIPANIMATION=1 → Tapping (611,129) super-rapidly in background...", step="Skip Anim")
            
            # เปิดเธรดกดพิกัดรัวฝั่งเบื้องหลัง (Background Thread) เพื่อรันการกดรัวแบบคู่ขนาน ไม่บล็อกการแคปหน้าจอ
            tapping_active = [True]
            
            def tap_worker():
                # รันคำสั่งกดรัว 50 ครั้งต่อคำสั่ง คู่วิธี Loop รวม 25 รอบ (ทั้งหมด 1,250 ครั้ง)
                for _ in range(25):
                    if not tapping_active[0]:
                        break
                    device.shell("for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 50; do input tap 611 129; done")

            t_tap = threading.Thread(target=tap_worker, daemon=True)
            t_tap.start()
            
            skip_deadline = time.time() + 30  # timeout 30s กันค้าง
            skiphero_found = False
            while time.time() < skip_deadline:
                check_device_reset(serial, cycle_start)
                # ดึงภาพหน้าจอดิบผ่าน fast_screencap โดยตรง ไม่ผ่านระบบตรวจสอบลอยตัว/อัปเดต GUI เพื่อความเร็วระดับสูงสุด
                img_skip = fast_screencap(device)
                if img_skip is not None:
                    pts_skip = img_search(img_skip, os.path.join(IMG_DIR, "skiphero.bmp"))
                    if pts_skip:
                        tapping_active[0] = False  # สั่งหยุดยิงทันที
                        x_sk, y_sk = pts_skip[0]
                        gui_log(serial, f"[Loop {loop_num}] skiphero.bmp found! Clicking ({x_sk},{y_sk}) repeatedly until gone...", step="Skip Hero")
                        
                        # วนลูปกดซ้ำๆ จนกว่าจะหายไปเลย
                        while True:
                            check_device_reset(serial, cycle_start)
                            device.shell(f"input swipe {x_sk} {y_sk} {x_sk} {y_sk} 100")
                            time.sleep(0.2)
                            img_check = fast_screencap(device)
                            if img_check is None:
                                continue
                            pts_check = img_search(img_check, os.path.join(IMG_DIR, "skiphero.bmp"))
                            if not pts_check:
                                gui_log(serial, f"[Loop {loop_num}] skiphero.bmp disappeared!", step="Skip Hero Gone")
                                break
                            else:
                                x_sk, y_sk = pts_check[0]  # อัปเดตพิกัด
                        
                        skiphero_found = True
                        break
                time.sleep(0.01)
            
            tapping_active[0] = False
            if not skiphero_found:
                gui_log(serial, f"[Loop {loop_num}] skiphero.bmp not found in 30s, proceeding...", step="Skip Timeout")

        # ── NOSCAN mode: skip checkpointgacha → jump to next ──
        if NOSCAN == 1:
            gui_log(serial, f"[Loop {loop_num}] NOSCAN=1 → Skipping checkpointgacha/OCR/scanout", step="NoScan Skip")
        else:
            # 2c. รอ checkpointgacha.bmp → กด (478,320) → รอ checkpointgacha1 → OCR scan
            gui_log(serial, f"[Loop {loop_num}] Waiting checkpointgacha or fixcheckpointgacha...", step="CP Wait")
            deadline_cp = time.time() + 45
            while time.time() < deadline_cp:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    # 1. เช็ค checkpointgacha ปกติ
                    pts = img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp"))
                    if pts:
                        gui_log(serial, f"[Loop {loop_num}] checkpointgacha found! Clicking (478,320) continuously...", step="Click Loop")
                        click_count = 0
                        click_start = time.time()
                        while True:
                            check_device_reset(serial, cycle_start)
                            if time.time() - click_start > 15:
                                gui_log(serial, f"[Loop {loop_num}] Click loop timed out (15s) without seeing checkpointgacha1.bmp!", step="Click Timeout")
                                break
                            _check_fixcoin()  # priority #1
                            device.shell("input swipe 478 320 478 320 100")
                            click_count += 1
                            time.sleep(0.3)
                            
                            # แถม: เช็ค fixlocked สั้นๆ หลังกด
                            img_check = get_screen_capture(device)
                            if img_check is not None:
                                pts_fl = img_search(img_check, os.path.join(IMG_DIR, "fixlocked.bmp"))
                                if pts_fl:
                                    x_fl, y_fl = pts_fl[0]
                                    device.shell(f"input swipe {x_fl} {y_fl} {x_fl} {y_fl} 100")
                                    time.sleep(0.8)
                                    continue
                                    
                                # เช็คว่าเจอ checkpointgacha1.bmp หรือยัง
                                pts_cp1 = img_search(img_check, os.path.join(IMG_DIR, "checkpointgacha1.bmp"))
                                if pts_cp1:
                                    gui_log(serial, f"[Loop {loop_num}] checkpointgacha1.bmp found after {click_count} clicks!", step="CP1 Found")
                                    break
                        break
                    
                    # 2. เช็ค fixcheckpointgacha (ถ้าเจอให้กด fixlocked แล้วไปต่อ)
                    pts_fix = img_search(img, os.path.join(IMG_DIR, "fixcheckpointgacha.bmp"))
                    if pts_fix:
                        gui_log(serial, f"[Loop {loop_num}] fixcheckpointgacha detected! Searching fixlocked...", step="Fix CP")
                        pts_fl = img_search(img, os.path.join(IMG_DIR, "fixlocked.bmp"))
                        if pts_fl:
                            x_fl, y_fl = pts_fl[0]
                            device.shell(f"input swipe {x_fl} {y_fl} {x_fl} {y_fl} 100")
                            gui_log(serial, "Clicked fixlocked via fix-cp path", step="Fix Done")
                            time.sleep(0.8)
                        break
                time.sleep(0.3)

            # 2c2. รอ checkpointgacha1.bmp → แล้วค่อย OCR scan จริงๆ
            gui_log(serial, f"[Loop {loop_num}] Waiting checkpointgacha1 (OCR)...", step="CP1 Wait")
            deadline_cp1 = time.time() + 30
            while time.time() < deadline_cp1:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "checkpointgacha1.bmp"))
                    if pts:
                        time.sleep(0.8)  # ให้หน้าจอและตัวหนังสือเฟดอินจนเสร็จเรียบร้อย ป้องกันภาพเบลอ
                        img = get_screen_capture(device)
                        gacha_region = Region(68, 28, 579, 57)
                        ocr_text = read_screen_text(img, region=gacha_region, serial=serial)
                        display_text = ocr_text if ocr_text else "<EMPTY>"
                        gui_log(serial, f"[Loop {loop_num}] OCR Result: {display_text}", step="OCR Done")
                        print(f"[{serial}] GachaFree Loop{loop_num} OCR: {display_text}")
 
                        for h in HERO_LIST_FREE:
                            if is_hero_match(h, ocr_text):
                                h_clean = h.strip()
                                if h_clean not in found_heroes:
                                    found_heroes.append(h_clean)
                                    gui_log(serial, f"[Loop {loop_num}] ⭐ Match: {h_clean}", step=f"⭐ {h_clean}")
                        break
                time.sleep(0.3)

            # 2d. รอ scanout.bmp → click
            gui_log(serial, f"[Loop {loop_num}] Waiting scanout.bmp...", step="Scanout")
            deadline_so = time.time() + 15
            while time.time() < deadline_so:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "scanout.bmp"))
                    if pts:
                        x, y = pts[0]
                        gui_log(serial, f"[Loop {loop_num}] scanout.bmp found! Clicking ({x},{y})", step="Scanout OK")
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(1.2)
                        break
                time.sleep(0.3)

        # 2e. รอ next.bmp → click (จบ loop นี้แล้วค่อยไป loop ถัดไป)
        gui_log(serial, f"[Loop {loop_num}] Waiting next.bmp...", step="Next")
        if NOSCAN == 1:
            # NOSCAN mode: หา next.bmp ไปเรื่อยๆจนกว่าจะเจอ (ไม่มี timeout)
            while True:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                    if pts:
                        x, y = pts[0]
                        gui_log(serial, f"[Loop {loop_num}] next.bmp found! Clicking ({x},{y})", step="Next OK")
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(1.2)
                        break
                time.sleep(0.3)
        else:
            deadline_next = time.time() + 15
            while time.time() < deadline_next:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                    if pts:
                        x, y = pts[0]
                        gui_log(serial, f"[Loop {loop_num}] next.bmp found! Clicking ({x},{y})", step="Next OK")
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(1.2)
                        break
                time.sleep(0.3)

    # 3. จบตามลูปที่ตั้งค่า → Sort file
    if GACHA_CHECK == 1:
        gui_log(serial, "GachaFree finished. Gacha+Check mode active: waiting for backhome...", step="GachaFree Done")
        
        # 1. Wait for backhome.bmp indefinitely
        clicked_home = False
        while True:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts_home = img_search(img, os.path.join(IMG_DIR, "backhome.bmp"))
                if pts_home:
                    x, y = pts_home[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    gui_log(serial, f"Clicked backhome.bmp at ({x}, {y})!", step="Back Home Click")
                    clicked_home = True
                    time.sleep(4)
                    break
            time.sleep(1)
        
        if clicked_home:
            # 1b. Wait for backhome1.bmp indefinitely, click until gone
            gui_log(serial, "Waiting for backhome1.bmp...", step="Back Home 1 Wait")
            clicked_home1 = False
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    pts_home1 = img_search(img, os.path.join(IMG_DIR, "backhome1.bmp"))
                    if pts_home1:
                        x, y = pts_home1[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, f"Clicked backhome1.bmp at ({x}, {y})!", step="Back Home 1 Click")
                        clicked_home1 = True
                        time.sleep(2.0)
                        continue
                    else:
                        if clicked_home1:
                            gui_log(serial, "backhome1.bmp is gone!", step="Back Home 1 Gone")
                            break
                time.sleep(1.0)
        
        # 2. Run Find Hero sequence continuously!
        return find_hero_mode(device, cycle_start, serial, original_name, file_path)

    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    clean_orig = original_name
    if "+" in clean_orig: clean_orig = clean_orig.split("+")[-1]
    elif "-" in clean_orig: clean_orig = clean_orig.split("-")[-1]

    # ถ้า NOSCAN=1 → ส่งไป fast-random/ เสมอ
    if NOSCAN == 1:
        dest_dir = FAST_RANDOM_DIR
        final_name = clean_orig
        gui_log(serial, f"NOSCAN → {dest_dir}/{final_name}", step="Fast Random")
    elif found_heroes:
        num_heroes = len(found_heroes)
        if num_heroes >= 3:
            subfolder = "hero3"
        elif num_heroes == 2:
            subfolder = "hero2"
        else:
            subfolder = "hero1"
        dest_dir = os.path.join(BACKUP_ID_DIR, subfolder)
        os.makedirs(dest_dir, exist_ok=True)

        hero_prefix = "+".join(found_heroes)
        final_name = f"{hero_prefix}+{clean_orig}"
        gui_log(serial, f"⭐ GachaFree Match: {hero_prefix}", step=f"⭐ {hero_prefix}")
    else:
        dest_dir = RANDOM_FAIL_DIR
        final_name = clean_orig
        gui_log(serial, "GachaFree: No hero matched", step="No Match")

    dest = os.path.join(dest_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(1)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.copy2(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted (GachaFree): {dest_dir}", step="Sorted", status="working")
        except Exception as me:
            gui_log(serial, f"⚠️ GachaFree Sort failed: {me}", step="Sort Error")
        
        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    return True

def check_coin_mode(device, cycle_start, serial, original_name, file_path):
    """
    Check Coin sequence:
    1. Wait for checkpointcoin.bmp
    2. OCR at Region(52, 10, 106, 41) to extract the number (digits only)
    3. Rename file: [digits]+original_name (stripping any old [digits]+ from original name to avoid nesting)
    4. Move file to 'check-coin' directory
    5. Force-stop game and return True
    """
    import re
    gui_log(serial, "Waiting checkpointcoin...", step="Coin Wait", status="working")
    
    # 1. Wait for checkpointcoin.bmp
    deadline = time.time() + 60
    found_cp = False
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "checkpointcoin.bmp"))
            if pts:
                found_cp = True
                break
        time.sleep(1)
        
    if not found_cp:
        gui_log(serial, "checkpointcoin.bmp not found! Moving to random-fail.", step="Coin Timeout")
        device.shell("am force-stop jp.konami.pesam")
        time.sleep(1)
        dest_dir = RANDOM_FAIL_DIR
        final_name = original_name
        dest = os.path.join(dest_dir, final_name)
        if os.path.exists(file_path):
            time.sleep(2)
            try:
                if os.path.exists(dest):
                    os.remove(dest)
                shutil.copy2(file_path, dest)
                os.remove(file_path)
            except Exception as e:
                print(f"[{serial}] Failed to move file to random-fail: {e}")
        release_file(original_name)
        return True

    # 2. OCR at Region(52, 10, 106, 41)
    gui_log(serial, "checkpointcoin detected! Scanning coins...", step="Scanning Coin")
    coin_number = None
    for attempt in range(3):
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            coin_region = Region(52, 10, 106, 41)
            ocr_text = read_screen_text(img, region=coin_region, serial=serial)
            digits = "".join(re.findall(r"\d+", ocr_text))
            if digits:
                coin_number = digits
                break
        time.sleep(1)

    if not coin_number:
        gui_log(serial, "Could not read coins via OCR! Using '0'", step="OCR Fail")
        coin_number = "0"

    # 3. Rename file and strip old [digits]+ prefix
    match = re.match(r"^\[\d+\]\+(.+)$", original_name)
    if match:
        base_name = match.group(1)
    else:
        base_name = original_name

    final_name = f"[{coin_number}]+{base_name}"
    gui_log(serial, f"🪙 Coins: {coin_number} -> {final_name}", step="Coin Match")
    print(f"[{serial}] Coin Scan Result: {coin_number} -> file: {final_name}")

    # 4. Move file to 'check-coin' directory
    CHECK_COIN_DIR = "check-coin"
    os.makedirs(CHECK_COIN_DIR, exist_ok=True)
    
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    dest = os.path.join(CHECK_COIN_DIR, final_name)
    if os.path.exists(file_path):
        time.sleep(2)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.copy2(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted: {final_name} -> {CHECK_COIN_DIR}", step="Sorted", status="working")
        except Exception as e:
            gui_log(serial, f"⚠️ Sort failed: {e}", step="Sort Error")

        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    gui_log(serial, f"Cycle finished for {original_name}", step="Done")
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Main bot loop
# ═════════════════════════════════════════════════════════════════════════════
def process_device_login(device):
    serial = device.serial
    gui_log(serial, "Bot started", step="Init", status="working")

    while bot_running:
        import random
        time.sleep(random.uniform(0.5, 2.0)) # Jitter ป้องกัน ADB ค้าง
        file_path     = None
        original_name = None

        try:
            DEVICE_DISABLE_FIXEVENT[serial] = False
            check_device_reset(serial)
            gui_log(serial, "--- Starting New Cycle ---", step="New Cycle", status="working")

            # 0. Force-stop
            gui_log(serial, "Force closing app...", step="Cleanup", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            # 1. Pick file
            file_path, original_name = pick_next_file()
            if file_path is None:
                gui_log(serial, "No files left — waiting...", step="No Files", status="idle")
                time.sleep(3)
                continue

            gui_log(serial, f"File: {original_name}", step="File OK", status="working")
            DEVICE_FILE_ASSIGNMENTS[serial] = original_name
            cycle_start = time.time()

            # 2. Push file
            gui_log(serial, "Pushing file...", step="Push")
            if not push_dat_to_device(device, file_path):
                gui_log(serial, "Push FAILED!", step="Error", status="stuck")
                release_file(original_name)
                time.sleep(5)
                continue



            # 3. Launch with Black Screen Check (45s check, threshold > 85% dark -> force-stop & relaunch)
            gui_log(serial, "Launching PES...", step="Launch", status="working")
            
            for black_attempt in range(3):
                device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
                black_start = time.time()
                is_stuck = False
                while time.time() - black_start < 45:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        try:
                            # Convert to grayscale for thresholding
                            if len(img.shape) == 3:
                                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            else:
                                gray = img
                            _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
                            num_black = cv2.countNonZero(thresh)
                            total = gray.shape[0] * gray.shape[1]
                            black_ratio = num_black / total
                            if black_ratio < 0.85:
                                # จอสว่างแล้ว (>15% pixels not black)
                                gui_log(serial, "Screen OK! (app loaded)", step="Launch OK")
                                is_stuck = False
                                break
                            else:
                                is_stuck = True
                        except Exception:
                            is_stuck = True
                    else:
                        is_stuck = True
                    time.sleep(1)
                
                if is_stuck:
                    gui_log(serial, f"[BLACK] Dark screen detected! (attempt {black_attempt+1}/3) Restarting app...", step="Black Stuck")
                    device.shell("am force-stop jp.konami.pesam")
                    time.sleep(2)
                else:
                    break
            
            time.sleep(8)

            # 4. Wait for play8 — คลิกซ้ำจนหาย
            gui_log(serial, "Waiting play8...", step="play8")
            play8_clicked = False
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
                    if pts:
                        # Prioritize fixlg3 if both are present
                        pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                        if pts_lg3:
                            gui_log(serial, "play8 and fixlg3 found! Clicking fixlg3 first", step="play8")
                            x, y = pts_lg3[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(2)
                            continue
                            
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        play8_clicked = True
                        time.sleep(5)
                    elif play8_clicked:
                        break
                time.sleep(1.5)

            # 5. Wait checkpointlogin
            gui_log(serial, "Waiting checkpointlogin...", step="Checkpoint")
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
                    if pts:
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(4)
                        break
                time.sleep(1.5)

            # 6. Event sequence — พฤติกรรมขึ้นกับ EVENT_IMG
            if EVENT_IMG == 1:
                # ─── mode event: กด play22 → play31 ทีละภาพ ───────────────
                for i in range(22, 32):
                    name = f"play{i}.bmp"
                    gui_log(serial, f"Waiting {name}...", step=name)
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, name))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(2.5)
                                break
                        time.sleep(0.5)
                    else:
                        gui_log(serial, f"{name} timeout, skip", step="Skip")

            else:
                # ─── mode no-event: รอ play22 แล้วกด Back รัวๆ จนเจอ cancel ─
                gui_log(serial, "Waiting play22 (no-event mode)...", step="play22")
                deadline = time.time() + 10
                while time.time() < deadline:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "play22.bmp"))
                        if pts:
                            gui_log(serial, "play22 found — pressing Back...", step="Back loop")
                            break
                    time.sleep(0.5)

                # กด Back รัวๆ จนเจอ cancel.bmp
                gui_log(serial, "Spamming Back until cancel.bmp...", step="Cancel")
                while True:
                    check_device_reset(serial, cycle_start)
                    device.shell("input keyevent 4")   # KEYCODE_BACK
                    time.sleep(0.4)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts:
                            x, y = pts[0]
                            gui_log(serial, f"cancel.bmp found — clicking ({x},{y})", step="Click Cancel")
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(1)
                            # กดจนกว่าจะหายไป ไม่เจอครบ 5 วิ ค่อยไปต่อ
                            last_seen = time.time()
                            while time.time() - last_seen < 5:
                                check_device_reset(serial, cycle_start)
                                img2 = get_screen_capture(device)
                                if img2 is not None:
                                    pts2 = img_search(img2, os.path.join(IMG_DIR, "cancel.bmp"))
                                    if pts2:
                                        x2, y2 = pts2[0]
                                        device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                                        gui_log(serial, "cancel still visible, clicking again...", step="Cancel")
                                        time.sleep(1)
                                        last_seen = time.time()
                                time.sleep(0.5)
                            gui_log(serial, "cancel.bmp gone for 5s, moving on", step="Cancel OK")
                            break

            # 7. Box Sequence (Optional)
            if DO_BOX == 1:
                gui_log(serial, "Box sequence started...", step="Box Mode", status="working")
                box2_found = False
                while not box2_found:
                    check_device_reset(serial, cycle_start)
                    # play26 - play31 (リードアップ)
                    for i in range(26, 32):
                        name = f"play{i}.bmp"
                        gui_log(serial, f"Waiting {name} (Box path)...", step=name)
                        deadline = time.time() + 4
                        while time.time() < deadline:
                            check_device_reset(serial, cycle_start)
                            img = get_screen_capture(device)
                            if img is not None:
                                pts = img_search(img, os.path.join(IMG_DIR, name))
                                if pts:
                                    x, y = pts[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    time.sleep(2.5)
                                    break
                            time.sleep(0.5)
                    
                    # box1
                    gui_log(serial, "Waiting box1.bmp...", step="box1")
                    start_box = time.time()
                    box1_found = False
                    while time.time() - start_box < 15:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "box1.bmp"))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(4)
                                box1_found = True
                                break
                        time.sleep(1.2)
                    
                    if not box1_found:
                        gui_log(serial, "box1.bmp not found, retrying sequence", step="Retry")
                        continue

                    # box2
                    gui_log(serial, "Waiting box2.bmp...", step="box2")
                    start_box = time.time()
                    while time.time() - start_box < 15:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "box2.bmp"))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(4)
                                box2_found = True
                                break
                        time.sleep(1.2)
                
                # box3 (กดเรื่อยๆ จนไม่เจอครบ 10s ค่อยไป box4)
                gui_log(serial, "Waiting box3.bmp...", step="box3")
                last_seen = time.time()
                while time.time() - last_seen < 10:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "box3.bmp"))
                        if pts:
                            x, y = pts[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(serial, "box3.bmp clicked!", step="box3")
                            time.sleep(4)
                            last_seen = time.time()  # รีเซ็ตนับใหม่
                            continue
                    time.sleep(1)
                gui_log(serial, "box3 not seen for 10s, moving to box4", step="box3-done")

                # box4
                gui_log(serial, "Waiting box4.bmp...", step="box4")
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "box4.bmp"))
                        if pts:
                            x, y = pts[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(4)
                            break
                    time.sleep(1)

            # 7.4 Check Coin Sequence (Optional)
            DEVICE_DISABLE_FIXEVENT[serial] = True
            if CHECK_COIN == 1:
                if check_coin_mode(device, cycle_start, serial, original_name, file_path):
                    continue  # Start next file immediately

            # 7.5 Find Hero Sequence (Optional)
            if FIND_HERO == 1 and GACHA_CHECK != 1:
                if find_hero_mode(device, cycle_start, serial, original_name, file_path):
                    continue  # Start next file immediately

            # 7.6 Gacha Free Sequence (Optional)
            if GACHA_FREE == 1 or GACHA_CHECK == 1:
                if gacha_free_mode(device, cycle_start, serial, original_name, file_path):
                    continue  # Start next file immediately

            # 8. Gacha Sequence (Optional)
            gacha_hero_found = None
            if DO_GACHA == 1:
                gui_log(serial, "Gacha sequence started...", step="Gacha Mode", status="working")
                
                # gacha1 -> gacha2
                for i in range(1, 3):
                    name = f"gacha{i}.bmp"
                    gui_log(serial, f"Waiting {name}...", step=name)
                    while True:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, name))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(4)
                                break
                        time.sleep(1)

                # swipe until gacha3
                gui_log(serial, "Swiping from 618,308 to 54,306 for gacha3...", step="Swipe Gacha")
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "gacha3.bmp"))
                        if pts:
                            x, y = pts[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(4)
                            break
                    # Swipe (drag) action
                    device.shell("input swipe 618 308 54 306 3000")
                    time.sleep(2)

                # gacha4
                found_g4 = False
                gui_log(serial, "Waiting gacha4.bmp (10s)...", step="Gacha4")
                deadline_g4 = time.time() + 10
                while time.time() < deadline_g4:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "gacha4.bmp"))
                        if pts:
                            x, y = pts[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(4)
                            found_g4 = True
                            break
                        
                        # เช็ค nocions ระหว่างรอ
                        if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                            found_g4 = "nocoin"
                            break
                    time.sleep(1)

                if not found_g4:
                    # ไม่เจอ gacha4 ใน 10s -> แวะเช็ค nocions ต่ออีก 10s
                    gui_log(serial, "gacha4 not found, checking nocions (10s)...", step="Check-NC")
                    deadline_nc = time.time() + 10
                    while time.time() < deadline_nc:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                                found_g4 = "nocoin"
                                break
                        time.sleep(1)
                
                # จัดการกรณีเจอ nocions.bmp (ไม่ว่าจะเจอตอนไหน)
                if found_g4 == "nocoin":
                    gui_log(serial, "nocions.bmp detected! Scanning screen...", step="No-Coins")
                    img = get_screen_capture(device)
                    if img is not None:
                        gacha_region = Region(68, 28, 579, 57)
                        ocr_text = read_screen_text(img, region=gacha_region, serial=serial)
                        gui_log(serial, f"OCR Result (at No-Coins): {ocr_text}", step="OCR Done")
                        for h in HERO_LIST:
                            if is_hero_match(h, ocr_text):
                                gacha_hero_found = h.strip()
                                break
                    # จบรอบนี้ทันที
                    found_g4 = False 
                else:
                    # ถ้าผ่าน nocions มาได้ (ไม่เจอ) หรือเจอ gacha4 ไปแล้ว -> ไป gacha5 ต่อ
                    gui_log(serial, "Proceeding to Gacha5...", step="G5-Flow")
                    while True:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "gacha5.bmp"))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(4)
                                found_g4 = True # ติ๊กให้ทำ checkpointgacha ต่อ
                                break
                            
                            if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                                # กรณีเจอตอนรอ gacha5
                                gui_log(serial, "nocions.bmp detected during Gacha5!", step="No-Coins")
                                # (ทำ OCR เหมือนด้านบนถ้าต้องการ แต่เพื่อความสั้นจะขอ break เลย)
                                found_g4 = False
                                break
                        time.sleep(1)
                # checkpointgacha -> OCR (ข้ามถ้าไม่เจอ gacha4)
                if found_g4:
                    gui_log(serial, "Waiting checkpointgacha or fixcheckpointgacha (OCR)...", step="OCR Wait")
                    deadline_ocr = time.time() + 60
                    while time.time() < deadline_ocr:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            # 1. เช็ค checkpointgacha ปกติ
                            pts = img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp"))
                            if pts:
                                time.sleep(1.2)  # ให้หน้าจอและตัวหนังสือเฟดอินจนเสร็จเรียบร้อย ป้องกันภาพเบลอ
                                img = get_screen_capture(device)
                                # ใช้พิกัด Region(68, 28, 579, 57) ตามตัวอย่าง
                                gacha_region = Region(68, 28, 579, 57)
                                ocr_text = read_screen_text(img, region=gacha_region, serial=serial)
                                display_text = ocr_text if ocr_text else "<EMPTY>"
                                gui_log(serial, f"OCR Result: {display_text}", step="OCR Done")
                                print(f"[{serial}] Gacha OCR: {display_text}")
                                
                                for h in HERO_LIST:
                                    if is_hero_match(h, ocr_text):
                                        gacha_hero_found = h.strip()
                                        break
                                break
                            
                            # 2. เช็ค fixcheckpointgacha
                            pts_fix = img_search(img, os.path.join(IMG_DIR, "fixcheckpointgacha.bmp"))
                            if pts_fix:
                                gui_log(serial, "fixcheckpointgacha detected! Searching fixlocked...", step="Fix CP")
                                pts_fl = img_search(img, os.path.join(IMG_DIR, "fixlocked.bmp"))
                                if pts_fl:
                                    x_fl, y_fl = pts_fl[0]
                                    device.shell(f"input swipe {x_fl} {y_fl} {x_fl} {y_fl} 100")
                                    time.sleep(2)
                                break

                            # 3. เช็ค nocions.bmp ด้วย
                            pts_no = img_search(img, os.path.join(IMG_DIR, "nocions.bmp"))
                            if pts_no:
                                gui_log(serial, "nocions.bmp detected!", step="No-Coins")
                                break
                        time.sleep(1)

            # 9. Done & File Sorting
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            clean_orig = original_name
            if "+" in clean_orig: clean_orig = clean_orig.split("+")[-1]
            elif "-" in clean_orig: clean_orig = clean_orig.split("-")[-1]

            if DO_GACHA == 1:
                if gacha_hero_found:
                    dest_dir = os.path.join(BACKUP_ID_DIR, "hero1")
                    os.makedirs(dest_dir, exist_ok=True)
                    final_name = f"{gacha_hero_found}-{clean_orig}"
                    gui_log(serial, f"⭐ HERO MATCH: {gacha_hero_found}", step=f"⭐ {gacha_hero_found}")
                else:
                    dest_dir = NO_HERO_DIR
                    final_name = clean_orig
                    gui_log(serial, "No hero match found.", step="No Match")
            else:
                dest_dir = LOGIN_SUCCESS_DIR
                final_name = clean_orig

            dest = os.path.join(dest_dir, final_name)
            if os.path.exists(file_path):
                # ให้เวลาไฟล์คลายตัวเล็กน้อยก่อนย้าย
                time.sleep(2)
                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                    # ใช้ copy + remove แทน move เพื่อความชัวร์บน Windows
                    shutil.copy2(file_path, dest)
                    os.remove(file_path)
                    gui_log(serial, f"✅ Sorted: {original_name} -> {dest_dir}",
                            step="Sorted", status="working")
                except Exception as me:
                    gui_log(serial, f"⚠️ Sort failed: {me}", step="Sort Error")
                
                dur = time.time() - cycle_start
                dur_s = f"{dur/60:.1f}m" if dur >= 60 else f"{dur:.0f}s"
                if gui_instance:
                    gui_instance.login_times.append(dur)

            release_file(original_name)

        except DeviceResetException:
            release_file(original_name)
            gui_log(serial, "🛑 Manual reset", step="Reset", status="stuck")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

        except SellScreenException:
            release_file(original_name)
            gui_log(serial, "🛑 Sell screen detected - force closing app and ending cycle", step="Sell Reset", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)



        except Exception as e:
            release_file(original_name)
            gui_log(serial, f"❌ Error: {e}", status="stuck")
            time.sleep(5)
        finally:
            # Safe, non-disruptive memory optimization at the end of each account cycle
            try:
                device.shell("pm trim-caches 9999999999G")
                device.shell("su -c 'sync && echo 3 > /proc/sys/vm/drop_caches'")
            except Exception:
                pass
            try:
                import gc
                gc.collect()
            except Exception:
                pass

# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════
def main():
    if GUI_ENABLED:
        LoginBotGUI().mainloop()
    else:
        if not find_adb_executable():
            print(f"{Fore.RED}[ERROR] adb.exe not found.{Style.RESET_ALL}")
            return
        connect_known_ports()
        devices = get_connected_devices()
        if not devices:
            print(f"{Fore.RED}[ERROR] No devices found.{Style.RESET_ALL}")
            return
        global bot_running
        bot_running = True
        client = AdbClient(host="127.0.0.1", port=5037)
        for serial in devices:
            device = client.device(serial)
            threading.Thread(target=process_device_login,
                             args=(device,), daemon=True).start()
            time.sleep(1)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
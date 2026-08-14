import os
import sys
import socket
socket.setdefaulttimeout(15.0)  # ป้องกันปัญหาระบบค้างใน socket ระดับล่างแบบถาวร
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

class ResetGachaException(Exception):
    pass

in_new_gacha_loop = False

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
    # ปิด warning "pin_memory ... no accelerator" ของ torch (รันบน CPU ไม่มีผลอะไร)
    import warnings as _warnings
    _warnings.filterwarnings("ignore", message=".*pin_memory.*")
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
    from config import GACHA_FIND
except ImportError:
    GACHA_FIND = 0
try:
    from config import list_find_hero
except ImportError:
    list_find_hero = HERO_LIST
# EXTAR_FIND — ฮีโร่ที่ต้องยืนยันด้วยรูปซ้ำอีกชั้น (รับชื่อตัวเล็ก extar_find ด้วย เผื่อพิมพ์คนละแบบ)
try:
    from config import EXTAR_FIND
except ImportError:
    try:
        from config import extar_find as EXTAR_FIND
    except ImportError:
        EXTAR_FIND = {}
try:
    from config import EXTAR_FIND_THRESHOLD
except ImportError:
    EXTAR_FIND_THRESHOLD = 0.8
EXTAR_SUBDIR = "extar"   # โฟลเดอร์รูปของ EXTAR_FIND → img/extar/
# ── Auto restart เครื่องที่ adb หลุด (offline ค้าง) ──
try:
    from config import AUTO_RESTART_OFFLINE
except ImportError:
    AUTO_RESTART_OFFLINE = 1
try:
    from config import OFFLINE_RESTART_AFTER
except ImportError:
    OFFLINE_RESTART_AFTER = 90
try:
    from config import OFFLINE_BOOT_WAIT
except ImportError:
    OFFLINE_BOOT_WAIT = 240
try:
    from config import OFFLINE_RESTART_COOLDOWN
except ImportError:
    OFFLINE_RESTART_COOLDOWN = 600
# ── โหลดที่ยิงใส่ adb (กัน adb server ล้นจนจอหลุด) ──
try:
    from config import SCREENCAP_MAX_CONCURRENT
except ImportError:
    SCREENCAP_MAX_CONCURRENT = 12
try:
    from config import SCREENCAP_INTERVAL
except ImportError:
    SCREENCAP_INTERVAL = 0.25
# ── ROI cache: จำตำแหน่งปุ่ม ไม่ต้องกวาดทั้งจอทุกรอบ ──
try:
    from config import IMG_ROI_CACHE
except ImportError:
    IMG_ROI_CACHE = 1
try:
    from config import IMG_ROI_PAD
except ImportError:
    IMG_ROI_PAD = 40
try:
    from config import AUTORUN
except ImportError:
    AUTORUN = 0
try:
    from config import SILENT_UPDATE_MODE
except ImportError:
    SILENT_UPDATE_MODE = "keep"
try:
    from config import OVERWRITE_CONFIG_ON_UPDATE
except ImportError:
    OVERWRITE_CONFIG_ON_UPDATE = True
try:
    from config import GETCODE
except ImportError:
    GETCODE = 0
try:
    from config import GETCODE_TEXT
except ImportError:
    GETCODE_TEXT = "eFCONNECT"
try:
    from config import GETQUEST
except ImportError:
    GETQUEST = 0
try:
    from config import GETQUEST_IMG_DIR
except ImportError:
    GETQUEST_IMG_DIR = "img/getquest"
try:
    from config import LOGIN_FAST
except ImportError:
    LOGIN_FAST = 0
try:
    from config import GACHA_MIN_COIN
except ImportError:
    GACHA_MIN_COIN = 100
try:
    from config import DEBUG_CONSOLE
except ImportError:
    DEBUG_CONSOLE = 0
try:
    from config import CUSTOM_GACHA
except ImportError:
    CUSTOM_GACHA = 0
try:
    from config import NEW_GACHA
except ImportError:
    NEW_GACHA = 0
try:
    from config import NEW_GACHA_SWIPE
except ImportError:
    NEW_GACHA_SWIPE = 1
try:
    from config import GACHA_LOOP_LIMIT
except ImportError:
    GACHA_LOOP_LIMIT = 0
try:
    from config import GACHA500
except ImportError:
    GACHA500 = 0
try:
    from config import COIN_GACHA_THRESHOLD
except ImportError:
    COIN_GACHA_THRESHOLD = 700
try:
    from config import ONE_GACHA500
except ImportError:
    ONE_GACHA500 = 0


def cprint(*args, **kwargs):
    """print ลง console เฉพาะตอน DEBUG_CONSOLE=1 (รันจริงปิดไว้ กัน cmd ค้าง + เบาเครื่อง)"""
    if DEBUG_CONSOLE:
        print(*args, **kwargs)
try:
    from config import MOVE_LS_ENABLE
except ImportError:
    MOVE_LS_ENABLE = 0
try:
    from config import MOVE_LS_TIME
except ImportError:
    MOVE_LS_TIME = "09:00"

try:
    from config import USE_MUMU_ROOT
except ImportError:
    USE_MUMU_ROOT = True
try:
    from config import MUMU_MANAGER
except ImportError:
    MUMU_MANAGER = r"D:\Program Files\Netease\MuMuPlayerGlobal-12.0\nx_main\MuMuManager.exe"
try:
    from config import MUMU_INDEX
except ImportError:
    MUMU_INDEX = "1"
try:
    from config import USE_SU
except ImportError:
    USE_SU = True
try:
    from config import ROOT_TOGGLE_WAIT
except ImportError:
    ROOT_TOGGLE_WAIT = 3


REMOTE_AUTH_DIR   = "/data/data/jp.konami.pesam/files/SaveData/AUTH"
REMOTE_DAT_FILE   = f"{REMOTE_AUTH_DIR}/online_user_id_data.dat"

IMAGE_CACHE          = {}
_image_cache_lock    = threading.Lock()
DEVICE_RESET_FLAGS   = {}
DEVICE_FILE_ASSIGNMENTS = {}
DEVICE_DISABLE_FIXEVENT = {}
DEVICE_IN_GACHA      = {}     # serial -> True ระหว่างอยู่ใน sequence กาชา → เปิดหา ad-rewardfix1 แบบลอยๆ ทุกเฟรม
DEVICE_IN_NEWSTAGE   = {}     # serial -> True ระหว่างทำ new-stageplay8 อยู่ (กัน floating check เรียกซ้ำซ้อนตัวเอง)
DEVICE_NEWSTAGE_DONE = {}     # serial -> True ถ้าอีเวนต์ new stage ถูกจัดการไปแล้วใน cycle นี้ (ข้ามการรอซ้ำ)
DEVICE_CYCLE_START   = {}     # serial -> เวลาเริ่ม cycle ปัจจุบัน (ให้ floating check ใช้เช็ค timeout รวมได้)
DEVICE_LAST_GAME_CHECK  = {}  # throttle: เช็คเกมออนทุก 30 วิ
DEVICE_REENTER_FILE  = {}     # serial -> (file_path, original_name) ไฟล์ที่ต้อง "เข้าใหม่" (fixclear)
DEVICE_REENTER_COUNT = {}     # serial -> (original_name, count) นับจำนวนครั้งที่ re-enter
FIXCLEAR_MAX_REENTER = 1      # เจอ fixclear → เข้าใหม่ได้กี่ครั้งก่อนยอมแพ้ส่ง file-error (1 = เข้าใหม่ 1 ครั้ง เจออีกค่อยส่ง)
DEVICE_RESTART_PLAY8 = {}     # serial -> (file_path, original_name) เริ่มใหม่ "ตั้งแต่ play8" (เปิดเกมเดิม ไม่ล้าง AUTH ไม่ push ซ้ำ = เก็บ login เดิมไว้)
DEVICE_RESTART_PLAY8_COUNT = {}  # serial -> (original_name, count) นับจำนวนครั้งที่ restart-play8 ต่อไฟล์ (กันวนไม่จบ)
MAX_RESTART_PLAY8 = 2         # restart-play8 ได้ไม่เกินกี่ครั้งต่อไฟล์ ก่อนยอมแพ้ → ส่ง file-error แล้วหยิบไฟล์ใหม่
DEVICE_PAST_LOGIN    = {}     # serial -> bool ผ่านหน้า login (checkpoint) แล้วหรือยัง → ใช้ตัดสิน fixclear ว่าจะ restart-play8 หรือ re-enter (push ใหม่)
DEVICE_FIXOUT_CANCEL_DONE = {}  # serial -> True เมื่อ fixout→Back spam→กด cancel สำเร็จ (ลูป play8 ใช้ break ข้ามไป step ถัดไปเลย)
DEVICE_DISABLE_FIXOUT = {}      # serial -> True = ปิด floating fixout check (ตั้งตอนเข้า sequence กาชา — หน้ากาชามีปุ่มคล้าย fixout จับผิดบ่อย)
_FIXOUT_LAST_DONE = {}          # serial -> เวลาที่ fixout→cancel ทำงานล่าสุด (cooldown กันกดซ้ำรัวๆ — กดรอบเดียวแล้วเว้น)
FIXOUT_COOLDOWN = 60            # วินาที — หลัง fixout→cancel สำเร็จ 1 ครั้ง ห้ามยิงซ้ำภายในเวลานี้
DEVICE_OFFLINE_SINCE = {}       # serial -> เวลาที่เริ่ม offline (นานเกินกำหนด → restart MuMu เฉพาะเครื่องนั้น)

# ── Performance ───────────────────────────────────────────────────────────────
SCREENCAP_SCALE = 1.0  # 1.0 = full resolution (ป้องกัน template quality loss)

# Pre-compute paths — ไม่สร้าง string ใหม่ทุก frame
_P = {
    'fixnet':    os.path.join(IMG_DIR, "fixnet.bmp"),
    'fixnet1':   os.path.join(IMG_DIR, "fixnet1.bmp"),
    'fixload':   os.path.join(IMG_DIR, "fixloading.bmp"),
    'fixload2':  os.path.join(IMG_DIR, "fixload2.bmp"),
    'fixlg3':    os.path.join(IMG_DIR, "fixlg3.bmp"),
    'fixclear':  os.path.join(IMG_DIR, "fixclear.bmp"),
    'fix0':      os.path.join(IMG_DIR, "fix0%.png"),      # เกมค้าง 0% → ปิดแอพเข้าใหม่
    'fixupdate': os.path.join(IMG_DIR, "fixupdate.png"),  # ขึ้นให้อัปเดต → ปิดแอพเข้าใหม่
    'fixevent':  os.path.join(IMG_DIR, "fixevent.bmp"),
    'fixalert1': os.path.join(IMG_DIR, "fixalert1.bmp"),
    'fixalert2': os.path.join(IMG_DIR, "fixalert2.bmp"),
    'fixalert3': os.path.join(IMG_DIR, "fixalert3.bmp"),
    'cancel':    os.path.join(IMG_DIR, "cancel.bmp"),
}
_QUESTFIVE_PATHS = (
    [os.path.join(GETQUEST_IMG_DIR, f"questfive{i}.bmp") for i in range(1, 15) if i not in (4, 5, 10, 13)] +
    [os.path.join(GETQUEST_IMG_DIR, f"getquest{i}.bmp") for i in range(11, 16)]
)

file_pick_lock = threading.Lock()
ocr_lock       = threading.Lock()   # ป้องกัน OCR หลาย device พร้อมกัน (ลด CPU spike)
in_use_files   = set()   # filenames currently being processed
_gui_last_update = {}    # throttle GUI text updates per-device

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

os.makedirs(INPUT_DIR, exist_ok=True)
# โฟลเดอร์ผลลัพธ์ไม่สร้างล่วงหน้า — จะถูกสร้างตอนเขียนไฟล์จริง (กันโฟลเดอร์ว่างรกตอนรันครั้งแรก)
BACKUP_ID_DIR = "backup-id"
NO_HERO_DIR   = "no-hero"
FOUND_HERO_DIR = "found-hero"
TIMEOUT_DIR   = "timeout"
FAST_RANDOM_DIR = "fast-random"
FILE_ERROR_DIR = "file-error"
RUN_FILE_DIR = "run-file"
RANDOM_FAIL_DIR = "random-fail"
LOGIN_FAILED_DIR = "login-failed"

# ── Exceptions ────────────────────────────────────────────────────────────────
class DeviceResetException(Exception):  pass
class FixClearReenterException(Exception): pass
class CycleTimeoutException(Exception): pass
class SellScreenException(Exception):  pass
class RestartFromQuest8Exception(Exception): pass
class RestartFromPlay8Exception(Exception): pass
class GachaCoinCollectedException(Exception): pass  # coin >= เกณฑ์ ใน custom gacha → เก็บไฟล์แล้วจบรอบ
GQ_ACTIVE = False

# ═════════════════════════════════════════════════════════════════════════════
# GUI
# ═════════════════════════════════════════════════════════════════════════════
if GUI_ENABLED:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class DeviceMonitorWidget(ctk.CTkFrame):
        def __init__(self, parent, device_id, index):
            super().__init__(parent, fg_color="#343841", corner_radius=6, height=32)
            self.device_id = device_id
            self.pack_propagate(False)

            self.chk = ctk.CTkCheckBox(self, text="", width=20, height=20,
                                   checkbox_width=16, checkbox_height=16)
            self.chk.pack(side="left", padx=(6, 2))
            self.chk.select()

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

            # (Disabled lbl_file to improve performance)
            self.lbl_file = None

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
            # (Disabled step text update to improve performance)
            pass

    # ─────────────────────────────────────────────────────────────────────────
    class LoginBotGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            global gui_instance
            gui_instance = self
            self.title("🔑 loginสะสม PES")
            self.geometry("780x500")
            self.minsize(770, 420)
            self.adb_connected = False
            self.device_monitors  = {}
            self.threads          = []
            self.is_started       = False
            self.stat_labels      = {}
            self.stat_rows        = {}
            from collections import deque
            self.login_times      = deque(maxlen=500)  # cap — ป้องกัน sum() ช้าเมื่อรันนานๆ
            self._log_buffer      = []     # batch log lines
            self._prev_stats      = {}     # cache previous stat counts to skip no-op updates
            self.current_filter   = ""
            self._last_stats_data = (0, 0, 0, {}, 0, 0)
            self.autorun_triggered = False
            self.setup_ui()
            self.after(500,  self.connect_adb)
            self.after(2000, self.update_realtime_stats)
            self.after(10000, self.auto_scan_devices)
            self.after(200,   self._process_gui_queue)   # queue poller — 200ms
            self.after(500,   self._periodic_log_flush)  # log flush — 500ms
            self.after(120000, self._periodic_gc)        # GC every 2 min — ป้องกัน memory leak
            self.after(30000, self._check_move_schedule) # ตรวจเวลาย้าย login-success → input-id ทุก 30 วิ
            threading.Thread(target=_sync_net_time, daemon=True).start()  # sync เวลาโลก (internet) ตอนเริ่ม
            self.update_check_seconds = 60
            self.after(1000, self.tick_update_timer)
            self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # ── UI build ──────────────────────────────────────────────────────
        def setup_ui(self):
            from datetime import datetime
            self.configure(fg_color="#1e2025")   # พื้นหลังหน้าต่าง (โทน dark อมน้ำเงินนิด ๆ ให้กลมกลืน)

            # ── Top toolbar (สไตล์ CookieRun): Select All · dropdown · Start/Stop · settings ──
            toolbar = ctk.CTkFrame(self, height=46, fg_color="#282b31", corner_radius=0)
            toolbar.pack(fill="x")
            toolbar.pack_propagate(False)

            # Select All — เลือก/ยกเลิกทุกเครื่องในลิสต์
            ctk.CTkButton(toolbar, text="☑ Select All", width=96, height=28, corner_radius=8,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          fg_color="#3d7fff", hover_color="#2f66d8",
                          command=self.select_all_devices).pack(side="left", padx=(10, 6), pady=9)

            # Dropdown เลือกหัวข้อ: 📊 Stats หรือหมวด config (เลือกแล้วช่องขวาเปลี่ยน)
            self.tool_menu = ctk.CTkOptionMenu(toolbar, width=168, height=28,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          fg_color="#33363d", button_color="#4a4a4a",
                          button_hover_color="#5a5a5a", dropdown_fg_color="#2a2d33",
                          values=["📊 Stats", "⚙️ General", "🎰 Gacha", "🆓 Gacha Free",
                                  "🎁 Get-Code", "🔍 Find Hero", "🔧 Setting"],
                          command=self.on_category_select)
            self.tool_menu.set("📊 Stats")
            self.tool_menu.pack(side="left", padx=6, pady=9)

            # Start Bot / Stop (แยกปุ่มเขียว-แดง)
            self.btn_start = ctk.CTkButton(toolbar, text="▶ Start Bot", width=98, height=28,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          fg_color="#2cc985", hover_color="#229f69",
                          command=self.start_bot)
            self.btn_start.pack(side="left", padx=(8, 4), pady=9)
            self.btn_stop = ctk.CTkButton(toolbar, text="⏹ Stop", width=82, height=28,
                          font=ctk.CTkFont(size=12, weight="bold"),
                          fg_color="#6b2f2e", hover_color="#c62828",
                          command=self.stop_bot)
            self.btn_stop.pack(side="left", padx=4, pady=9)

            # ── ขวา: license badge · settings(🔑) · logs · status ──
            self.lbl_license = ctk.CTkLabel(toolbar, text="🎫 PES Bot",
                          font=ctk.CTkFont(size=12, weight="bold"),
                          fg_color="#2a2f3a", corner_radius=13,
                          text_color="#ffd36a", width=78, height=26)
            self.lbl_license.pack(side="right", padx=(6, 12), pady=9)
            ctk.CTkButton(toolbar, text="🔑", width=34, height=28,
                          font=ctk.CTkFont(size=14),
                          fg_color="#33363d", hover_color="#4a4a4a",
                          command=self.open_config_dialog).pack(side="right", padx=4, pady=9)
            ctk.CTkButton(toolbar, text="📋 Logs", width=62, height=28,
                          font=ctk.CTkFont(size=11),
                          fg_color="#3a3e46", hover_color="#666666",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_DIR)}"')
                          ).pack(side="right", padx=4, pady=9)
            self.lbl_status = ctk.CTkLabel(toolbar, text="● OFFLINE",
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color="#888")
            self.lbl_status.pack(side="right", padx=10, pady=9)

            # Main content
            main_frame = ctk.CTkFrame(self, fg_color="transparent")
            main_frame.grid_columnconfigure(0, weight=3)
            main_frame.grid_columnconfigure(1, weight=2)
            main_frame.grid_rowconfigure(0, weight=1)

            left_frame = ctk.CTkFrame(main_frame, fg_color="#2a2d33", corner_radius=8)
            left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
            hdr = ctk.CTkFrame(left_frame, fg_color="#30333a", corner_radius=0, height=28)
            hdr.pack(fill="x")
            ctk.CTkLabel(hdr, text="   DEVICES",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#cccccc", anchor="w").pack(side="left")
            self.dev_scroll = ctk.CTkScrollableFrame(left_frame, fg_color="transparent")
            self.dev_scroll.pack(fill="both", expand=True, padx=3, pady=3)

            right_frame = ctk.CTkFrame(main_frame, fg_color="#2a2d33", corner_radius=8)
            right_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
            rhdr = ctk.CTkFrame(right_frame, fg_color="#30333a", corner_radius=0, height=28)
            rhdr.pack(fill="x")
            # header เปลี่ยนข้อความได้ (STATS ↔ CONFIG · หัวข้อ)
            self.rhdr_label = ctk.CTkLabel(rhdr, text="   🏆 SUMMARY STATS",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#f2c94c", anchor="w")
            self.rhdr_label.pack(side="left")

            # ── ช่องขวาสลับ 2 มุมมอง: STATS (เดิม) / CONFIG (checkbox ตามหัวข้อ dropdown) ──
            self.stats_view  = ctk.CTkFrame(right_frame, fg_color="transparent")
            self.config_view = ctk.CTkScrollableFrame(right_frame, fg_color="transparent")
            self.stats_view.pack(fill="both", expand=True)   # ค่าเริ่มต้น = STATS

            # Search / Filter Bar for Summary Stats (Multi-tag enabled)
            search_bar = ctk.CTkFrame(self.stats_view, fg_color="transparent", height=32)
            search_bar.pack(fill="x", padx=6, pady=4)
            self.txt_filter = ctk.CTkEntry(search_bar, placeholder_text="พิมพ์ชื่อนักเตะแล้วกด Enter...",
                                           font=ctk.CTkFont(size=11), height=24)
            self.txt_filter.pack(side="left", fill="x", expand=True, padx=(0, 4))
            self.txt_filter.bind("<Return>", lambda event: self.add_filter_tag())

            self.btn_clear_filter = ctk.CTkButton(search_bar, text="ล้างทั้งหมด", width=65, height=24,
                                                  font=ctk.CTkFont(size=11), fg_color="#e53935",
                                                  hover_color="#c62828",
                                                  command=self.clear_stats_filter)
            self.btn_clear_filter.pack(side="right")

            # Sub-frame to display active search pills/tags
            self.tags_frame = ctk.CTkFrame(self.stats_view, fg_color="transparent")
            self.tags_frame.pack(fill="x", padx=6, pady=(0, 4))

            self.result_scroll = ctk.CTkScrollableFrame(self.stats_view, fg_color="transparent")
            self.result_scroll.pack(fill="both", expand=True, padx=3, pady=3)

            # Log
            log_frame = ctk.CTkFrame(self, fg_color="#191b1f", corner_radius=6, height=80)
            log_frame.pack_propagate(False)
            self.log_text = ctk.CTkTextbox(log_frame,
                                           font=ctk.CTkFont(family="Consolas", size=10),
                                           text_color="#8b949e", fg_color="#191b1f")
            self.log_text.pack(fill="both", expand=True, padx=2, pady=2)
            self.log_text.configure(state="disabled")

            # ── Bottom bar (สไตล์ CookieRun): ADB controls (ซ้าย) + counters/version (ขวา) ──
            base_path  = os.path.dirname(os.path.abspath(__file__))
            bottom_bar = ctk.CTkFrame(self, height=40, fg_color="#282b31", corner_radius=0)
            bottom_bar.pack_propagate(False)

            ctk.CTkButton(bottom_bar, text="◉ Start ADB", width=92, height=26,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          fg_color="#2cc985", hover_color="#229f69",
                          command=self.start_adb).pack(side="left", padx=(8, 3), pady=6)
            ctk.CTkButton(bottom_bar, text="✕ Kill ADB", width=84, height=26,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          fg_color="#e53935", hover_color="#c62828",
                          command=self.kill_adb).pack(side="left", padx=3, pady=6)
            ctk.CTkButton(bottom_bar, text="🔌 Connect", width=80, height=26,
                          font=ctk.CTkFont(size=10), fg_color="#4caf50",
                          hover_color="#3d8b40",
                          command=self.connect_missing_devices).pack(side="left", padx=3, pady=6)
            ctk.CTkButton(bottom_bar, text="📂 input-id", width=72, height=26,
                          font=ctk.CTkFont(size=10), fg_color="#3a3e46",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(base_path, INPUT_DIR)}"')
                          ).pack(side="left", padx=3, pady=6)
            ctk.CTkButton(bottom_bar, text="✅ login-success", width=98, height=26,
                          font=ctk.CTkFont(size=10), fg_color="#3a3e46",
                          command=lambda: subprocess.Popen(
                              f'explorer "{os.path.join(base_path, LOGIN_SUCCESS_DIR)}"')
                          ).pack(side="left", padx=3, pady=6)

            # Read version dynamically from version.txt
            version_str = "v1.0"
            try:
                version_file = os.path.join(base_path, "version.txt")
                if os.path.exists(version_file):
                    with open(version_file, "r", encoding="utf-8") as f:
                        raw_ver = f.read().strip()
                        version_str = raw_ver if raw_ver.lower().startswith("v") else f"v{raw_ver}"
            except Exception:
                pass

            ctk.CTkLabel(bottom_bar, text=version_str,
                         font=ctk.CTkFont(size=10), text_color="#888888"
                         ).pack(side="right", padx=(4, 10), pady=6)

            # counters (ย้ายมาจาก toolbar เดิม) — ชื่อ attr ต้องคงเดิม (มีโค้ดอื่นอัปเดต)
            counter_frame = ctk.CTkFrame(bottom_bar, fg_color="transparent")
            counter_frame.pack(side="right", padx=6, pady=6)
            self.lbl_file_count = ctk.CTkLabel(counter_frame, text="📁 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#aaaaaa", cursor="hand2")
            self.lbl_file_count.pack(side="left", padx=7)
            # กดตัวเลขไฟล์ → เปิดโฟลเดอร์ input-id
            self.lbl_file_count.bind("<Button-1>", lambda e: subprocess.Popen(
                f'explorer "{os.path.join(base_path, INPUT_DIR)}"'))
            self.lbl_succ_count = ctk.CTkLabel(counter_frame, text="✅ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#4caf50")
            self.lbl_succ_count.pack(side="left", padx=7)
            self.lbl_hero_count = ctk.CTkLabel(counter_frame, text="⭐ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#ffc107")
            self.lbl_hero_count.pack(side="left", padx=7)
            self.lbl_fast_count = ctk.CTkLabel(counter_frame, text="⚡ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#00e5ff", cursor="hand2")
            self.lbl_fast_count.pack(side="left", padx=7)
            # กดตัวเลข ⚡ → เปิดโฟลเดอร์ fast-random
            self.lbl_fast_count.bind("<Button-1>", lambda e: subprocess.Popen(
                f'explorer "{os.path.join(base_path, FAST_RANDOM_DIR)}"'))
            self.lbl_fail_count = ctk.CTkLabel(counter_frame, text="❌ 0",
                                               font=ctk.CTkFont(size=12, weight="bold"),
                                               text_color="#ff5555")
            self.lbl_fail_count.pack(side="left", padx=7)
            self.lbl_update_timer = None  # removed — UI update every 1s was causing lag

            # ตั้งสถานะปุ่ม Start/Stop เริ่มต้น (Stop เป็น disabled ตอนยังไม่รัน)
            self._refresh_run_buttons()

            # Pack the main frames in the correct order to prevent layout clipping
            bottom_bar.pack(side="bottom", fill="x")
            log_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 4))
            main_frame.pack(side="top", fill="both", expand=True, padx=6, pady=4)

        def add_filter_tag(self):
            val = self.txt_filter.get().strip().lower()
            if val:
                if not hasattr(self, 'active_filters'):
                    self.active_filters = []
                if val not in self.active_filters:
                    self.active_filters.append(val)
                self.txt_filter.delete(0, 'end')
                self.render_filter_tags()
                if hasattr(self, '_last_stats_data'):
                    self._apply_stats_ui(*self._last_stats_data)

        def remove_filter_tag(self, tag):
            if hasattr(self, 'active_filters') and tag in self.active_filters:
                self.active_filters.remove(tag)
            self.render_filter_tags()
            if hasattr(self, '_last_stats_data'):
                self._apply_stats_ui(*self._last_stats_data)

        def clear_stats_filter(self):
            self.txt_filter.delete(0, 'end')
            self.active_filters = []
            self.render_filter_tags()
            if hasattr(self, '_last_stats_data'):
                self._apply_stats_ui(*self._last_stats_data)

        def render_filter_tags(self):
            for widget in self.tags_frame.winfo_children():
                widget.destroy()
            filters = getattr(self, 'active_filters', [])
            if not filters:
                self.tags_frame.pack_forget()
                return
            self.tags_frame.pack(fill="x", padx=6, pady=(0, 4))
            for tag in filters:
                pill = ctk.CTkFrame(self.tags_frame, fg_color="#1565c0", corner_radius=12, height=20)
                pill.pack(side="left", padx=2, pady=1)
                ctk.CTkLabel(pill, text=f" {tag} ", font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="white").pack(side="left", padx=(4, 2))
                btn_del = ctk.CTkButton(pill, text="×", width=14, height=14,
                                        font=ctk.CTkFont(size=9, weight="bold"),
                                        fg_color="#e53935", hover_color="#c62828",
                                        corner_radius=7,
                                        command=lambda t=tag: self.remove_filter_tag(t))
                btn_del.pack(side="right", padx=(2, 4), pady=2)

        # ── Helpers ─────────────────────────────────────────────────
        def open_config_dialog(self):
            import importlib, config as cfg
            importlib.reload(cfg)   # อ่านค่าล่าสุดจากไฟล์

            win = ctk.CTkToplevel(self)
            win.title("⚙️ Config")
            win.geometry("420x650")
            win.minsize(380, 400)
            win.resizable(True, True)
            win.grab_set()   # modal

            ctk.CTkLabel(win, text="Bot Configuration",
                         font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 8))

            # ── Scrollable frame for all config rows ──────
            scroll_cfg = ctk.CTkScrollableFrame(win, fg_color="transparent")
            scroll_cfg.pack(fill="both", expand=True, padx=6, pady=(0, 4))

            # _cur[0] = พาเรนต์ปัจจุบันที่ row ต่าง ๆ จะ pack ลง (body ของ section ที่กำลังสร้าง)
            _cur = [scroll_cfg]

            # ── helpers: หัวข้อหมวดแบบ "พับ/กางได้" (accordion) — กดหัวข้อเพื่อเปิด/ปิด ให้ config สั้นลง ──
            def _section(title, start_open=False):
                state = {"open": start_open}
                body = ctk.CTkFrame(scroll_cfg, fg_color="transparent")
                def _toggle():
                    state["open"] = not state["open"]
                    arrow = "▼" if state["open"] else "▶"
                    btn.configure(text=f"{arrow}  {title}")
                    if state["open"]:
                        body.pack(fill="x", padx=2, pady=(0, 4), after=btn)
                    else:
                        body.pack_forget()
                arrow0 = "▼" if start_open else "▶"
                btn = ctk.CTkButton(scroll_cfg, text=f"{arrow0}  {title}",
                                    font=ctk.CTkFont(size=13, weight="bold"),
                                    fg_color="#242424", hover_color="#282b31",
                                    text_color="#4caf50", anchor="w", height=32,
                                    corner_radius=6, command=_toggle)
                btn.pack(fill="x", padx=6, pady=(6, 0))
                if start_open:
                    body.pack(fill="x", padx=2, pady=(0, 4))
                _cur[0] = body
                return body

            def _toggle_row(text, var, command=None):
                r = ctk.CTkFrame(_cur[0], fg_color="transparent")
                r.pack(fill="x", padx=14, pady=3)
                ctk.CTkLabel(r, text=text, font=ctk.CTkFont(size=12)).pack(side="left")
                kw = {"command": command} if command else {}
                ctk.CTkSwitch(r, text="", variable=var, onvalue=1, offvalue=0, **kw).pack(side="right")

            def _entry_row(text, value, width=50):
                r = ctk.CTkFrame(_cur[0], fg_color="transparent")
                r.pack(fill="x", padx=14, pady=3)
                ctk.CTkLabel(r, text=text,
                             font=ctk.CTkFont(size=11, slant="italic")).pack(side="left", padx=(10, 0))
                e = ctk.CTkEntry(r, width=width, height=20, justify="center")
                e.insert(0, str(value))
                e.pack(side="right")
                return e

            def _combo_row(text, targets):
                # สวิตช์รวม (preset): เปิด → ติดทุกตัวใน targets , ปิด → ปิดทุกตัว
                cv = ctk.IntVar(value=1 if all(t.get() == 1 for t in targets) else 0)
                def _cmd(cv=cv, targets=targets):
                    v = cv.get()
                    for t in targets:
                        t.set(v)
                _toggle_row(text, cv, command=_cmd)
                return cv

            # ════════ General ════════
            _section("⚙️ General", start_open=True)
            var_box = ctk.IntVar(value=cfg.DO_BOX)
            _toggle_row("รับของ (1-4)", var_box)
            var_find_hero = ctk.IntVar(value=getattr(cfg, 'FIND_HERO', 0))
            _toggle_row("หาตัวนักเตะ", var_find_hero)
            var_check_coin = ctk.IntVar(value=getattr(cfg, 'CHECK_COIN', 0))
            _toggle_row("Check Coin Mode", var_check_coin)
            entry_min_coin = _entry_row("  └─ Min coin to gacha (น้อยกว่านี้ข้ามสุ่ม)", getattr(cfg, 'GACHA_MIN_COIN', 100), width=70)
            var_login_fast = ctk.IntVar(value=getattr(cfg, 'LOGIN_FAST', 0))
            _toggle_row("Login Fast (เจอ login แล้วจบรอบทันที)", var_login_fast)

            # ════════ Gacha Mode ════════
            _section("🎰 Gacha Mode")
            var_gacha = ctk.IntVar(value=cfg.DO_GACHA)
            _toggle_row("Gacha Mode", var_gacha)
            var_new_gacha = ctk.IntVar(value=getattr(cfg, 'NEW_GACHA', 0))
            _toggle_row("New Gacha Mode (new-gacha1 -> new-gacha1)", var_new_gacha)
            var_ng_swipe = ctk.IntVar(value=getattr(cfg, 'NEW_GACHA_SWIPE', 1))
            _toggle_row("  └─ Swipe (เลื่อนหน้าจอหา new-gacha1)", var_ng_swipe)
            var_custom_gacha = ctk.IntVar(value=getattr(cfg, 'CUSTOM_GACHA', 0))
            _toggle_row("สุ่มจน coin หมด", var_custom_gacha)
            entry_gacha_limit = _entry_row("  └─ Custom จำกัดรอบ (0 = สุ่มจนหมด)", getattr(cfg, 'GACHA_LOOP_LIMIT', 0), width=70)
            var_gacha_find = ctk.IntVar(value=getattr(cfg, 'GACHA_FIND', 0))
            def _sync_gacha_find():
                # Gacha+Find ต้องอาศัย DO_GACHA + Check Coin → เปิดให้อัตโนมัติ
                if var_gacha_find.get() == 1:
                    var_gacha.set(1)
                    var_check_coin.set(1)
            _toggle_row("Gacha + Find + Check Coin", var_gacha_find, command=_sync_gacha_find)
            _combo_row("Box + Gacha + Check Coin + Find", [var_box, var_gacha, var_gacha_find, var_check_coin])

            # ════════ Gacha Free ════════
            _section("🆓 Gacha Free")
            var_gacha_free = ctk.IntVar(value=getattr(cfg, 'GACHA_FREE', 0))
            _toggle_row("Gacha Free Mode", var_gacha_free)
            entry_gfree_loops = _entry_row("  └─ Loops count", getattr(cfg, 'GACHA_FREE_LOOPS', 2))
            var_gacha_check = ctk.IntVar(value=getattr(cfg, 'GACHA_CHECK', 0))
            def _sync_gacha_check():
                # Gacha Free + Check + Find ต้องอาศัย Gacha Free + Check Coin → เปิดให้อัตโนมัติ
                if var_gacha_check.get() == 1:
                    var_gacha_free.set(1)
                    var_check_coin.set(1)
            _toggle_row("Gacha Free + Check Coin + Find", var_gacha_check, command=_sync_gacha_check)
            _combo_row("Box + Gacha Free + Check Coin + Find", [var_box, var_gacha_free, var_gacha_check, var_check_coin])

            # ════════ Get-Code / Quest ════════
            _section("🎁 Get-Code / Quest")
            var_getcode = ctk.IntVar(value=getattr(cfg, 'GETCODE', 0))
            _toggle_row("Get Code Mode (ใส่โค้ดก่อน Box)", var_getcode)
            entry_getcode_txt = _entry_row("  └─ Code Text", getattr(cfg, 'GETCODE_TEXT', 'eFCONNECT'), width=120)
            var_getquest = ctk.IntVar(value=getattr(cfg, 'GETQUEST', 0))
            _toggle_row("Get Quest Mode (เก็บเควสก่อน Box)", var_getquest)
            _combo_row("Box + Get Quest", [var_box, var_getquest])

            # ════════ Find Hero ════════
            _section("🔍 Find Hero")
            _toggle_row("หาตัวนักเตะ", var_find_hero)
            var_find_cc = ctk.IntVar(value=1 if (var_find_hero.get() == 1 and var_check_coin.get() == 1) else 0)
            def _sync_find_cc():
                # Find + Check Coin: เปิด → ติดทั้ง Find Mode + Check Coin , ปิด → ปิด Check Coin
                if var_find_cc.get() == 1:
                    var_find_hero.set(1)
                    var_check_coin.set(1)
                else:
                    var_check_coin.set(0)
            _toggle_row("Find + Check Coin", var_find_cc, command=_sync_find_cc)
            _combo_row("Box + Find + Check Coin", [var_box, var_find_hero, var_check_coin])

            # ════════ Setting ════════
            _section("🔧 Setting")
            var_autorun = ctk.IntVar(value=getattr(cfg, 'AUTORUN', 0))
            _toggle_row("Auto Run on Launch (รันอัตโนมัติเมื่อเปิด)", var_autorun)
            var_debug_console = ctk.IntVar(value=getattr(cfg, 'DEBUG_CONSOLE', 0))
            def _on_toggle_debug_console():
                global DEBUG_CONSOLE
                DEBUG_CONSOLE = var_debug_console.get()
                try:
                    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    import re
                    if re.search(r"^DEBUG_CONSOLE\s*=\s*\d", content, flags=re.MULTILINE):
                        content = re.sub(r"^DEBUG_CONSOLE\s*=\s*\d", f"DEBUG_CONSOLE = {DEBUG_CONSOLE}",
                                         content, flags=re.MULTILINE)
                    else:
                        content += f"\nDEBUG_CONSOLE = {DEBUG_CONSOLE}\n"
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    import importlib
                    importlib.reload(cfg)
                except Exception:
                    pass
            _toggle_row("Debug Console (โชว์ log ลง cmd — ปิดไว้ตอนรันจริง)", var_debug_console, command=_on_toggle_debug_console)
            var_event = ctk.IntVar(value=cfg.EVENT_IMG)
            _toggle_row("Event Image (play22→play31)", var_event)
            var_noscan = ctk.IntVar(value=getattr(cfg, 'NOSCAN', 0))
            _toggle_row("No Scan Mode (ข้ามสแกน → fast-random)", var_noscan)
            var_skipanim = ctk.IntVar(value=getattr(cfg, 'SKIPANIMATION', 0))
            _toggle_row("Skip Animation (Fast Taps)", var_skipanim)
            var_timeout = ctk.IntVar(value=getattr(cfg, 'TIMEOUT_ENABLE', 1))
            _toggle_row("Timeout Mode (กันค้าง)", var_timeout)
            entry_timeout = _entry_row("  ↳ เวลาสูงสุด (Minutes)", getattr(cfg, 'TIMEOUT_MINUTES', 10))
            var_overwrite_cfg = ctk.IntVar(value=1 if getattr(cfg, 'OVERWRITE_CONFIG_ON_UPDATE', True) else 0)
            _toggle_row("Sync Config (อัปเดตตั้งค่าตามเครื่องแม่)", var_overwrite_cfg)
            # Silent Update Mode (segmented)
            row_update = ctk.CTkFrame(_cur[0], fg_color="transparent")
            row_update.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row_update, text="Silent Update Mode",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var_update_mode = ctk.StringVar(value=getattr(cfg, 'SILENT_UPDATE_MODE', 'keep'))
            ctk.CTkSegmentedButton(row_update, values=["keep", "clean"],
                                   variable=var_update_mode).pack(side="right")

            # ════════ Move login-success → input-id (ตั้งเวลา) ════════
            _section("📤 Move login-success → input-id")
            var_move_ls = ctk.IntVar(value=getattr(cfg, 'MOVE_LS_ENABLE', 0))
            _toggle_row("Auto-move ทุกวันตามเวลา", var_move_ls)
            entry_move_time = _entry_row("  ↳ เวลา (24h หรือ AM/PM)", getattr(cfg, 'MOVE_LS_TIME', '09:00'), width=80)
            # ── นับถอยหลังสด (อิงเวลาโลก internet ถ้า sync ได้) ──
            lbl_countdown = ctk.CTkLabel(_cur[0], text="",
                                         font=ctk.CTkFont(size=12, weight="bold"), text_color="#ffa726")
            lbl_countdown.pack(fill="x", padx=18, pady=(0, 0))
            def _update_countdown():
                try:
                    if not lbl_countdown.winfo_exists():
                        return
                    if var_move_ls.get() == 1:
                        from datetime import timedelta
                        now = real_now()
                        hhmm = parse_time_to_hhmm(entry_move_time.get())
                        if hhmm:
                            sh, sm = [int(x) for x in hhmm.split(":")]
                            sched = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                            src = "🌐net" if _NET_TIME_SYNCED else "🖥local"
                            nxt = sched if now < sched else sched + timedelta(days=1)
                            rem = max(0, int((nxt - now).total_seconds()))
                            hh, rr = divmod(rem, 3600); mm, ss = divmod(rr, 60)
                            lbl_countdown.configure(text=f"⏳ อีก {hh:02d}:{mm:02d}:{ss:02d} → {hhmm}  ({src} {now.strftime('%H:%M:%S')})")
                        else:
                            lbl_countdown.configure(text="⚠️ เวลาไม่ถูกต้อง (เช่น 21:46 หรือ 9:46PM)")
                    else:
                        lbl_countdown.configure(text="(ปิด auto-move อยู่)")
                    win.after(1000, _update_countdown)
                except Exception:
                    pass
            _update_countdown()
            lbl_move = ctk.CTkLabel(_cur[0], text="ย้ายไฟล์ทั้งหมด login-success → input-id",
                                    font=ctk.CTkFont(size=11, slant="italic"), text_color="gray")
            lbl_move.pack(fill="x", padx=18, pady=(0, 2))
            def _move_now():
                moved = move_login_success_to_input()
                lbl_move.configure(text=f"📤 ย้าย {moved} ไฟล์แล้ว (login-success → input-id)", text_color="#4caf50")
                self.log(f"Move now: {moved} files login-success → input-id")
            ctk.CTkButton(_cur[0], text="📤 ย้ายตอนนี้ (login-success → input-id)",
                          command=_move_now, height=30).pack(fill="x", padx=14, pady=(2, 6))

            # ════════ Import Zip → input-id ════════
            _section("📦 Import Zip → input-id")
            lbl_zip = ctk.CTkLabel(_cur[0], text="เอา .zip ไปวางในโฟลเดอร์ zip/ แล้วกดปุ่ม → แตกเข้า input-id",
                                   font=ctk.CTkFont(size=11, slant="italic"), text_color="gray")
            lbl_zip.pack(fill="x", padx=18, pady=(0, 2))

            def _import_zip():
                import zipfile, glob as _glob
                base_dir = os.path.dirname(os.path.abspath(__file__))
                zip_dir  = os.path.join(base_dir, "zip")
                dest_dir = os.path.join(base_dir, INPUT_DIR)
                os.makedirs(zip_dir, exist_ok=True)    # ไม่มี zip/ → สร้าง
                os.makedirs(dest_dir, exist_ok=True)   # ไม่มี input-id → สร้าง
                zips = _glob.glob(os.path.join(zip_dir, "*.zip"))
                if not zips:
                    lbl_zip.configure(text="⚠️ ไม่พบไฟล์ .zip ในโฟลเดอร์ zip/", text_color="#e53935")
                    return
                count = 0
                nzip = 0
                try:
                    for zpath in zips:
                        with zipfile.ZipFile(zpath, 'r') as zf:
                            for info in zf.infolist():
                                if info.is_dir():
                                    continue
                                fname = os.path.basename(info.filename)
                                if not fname:
                                    continue
                                # แตกไฟล์มาวางใน input-id (เอาเฉพาะชื่อไฟล์ ไม่เอาโครงสร้างโฟลเดอร์)
                                with zf.open(info) as src, open(os.path.join(dest_dir, fname), 'wb') as out:
                                    shutil.copyfileobj(src, out)
                                count += 1
                        nzip += 1
                    lbl_zip.configure(text=f"✅ แตก {count} ไฟล์ จาก {nzip} zip เข้า input-id แล้ว", text_color="#4caf50")
                    self.log(f"Import Zip: {count} files from {nzip} zip(s) → {INPUT_DIR}")
                except Exception as e:
                    lbl_zip.configure(text=f"⚠️ ผิดพลาด: {e}", text_color="#e53935")
                    self.log(f"Import Zip failed: {e}")

            def _clear_input():
                from tkinter import messagebox
                base_dir = os.path.dirname(os.path.abspath(__file__))
                dest_dir = os.path.join(base_dir, INPUT_DIR)
                files = [f for f in glob.glob(os.path.join(dest_dir, "*")) if os.path.isfile(f)]
                if not files:
                    lbl_zip.configure(text="input-id ว่างอยู่แล้ว (ไม่มีไฟล์ให้ลบ)", text_color="gray")
                    return
                if not messagebox.askyesno("ยืนยันลบไฟล์",
                                           f"ลบไฟล์ทั้งหมด {len(files)} ไฟล์ใน input-id?\n(ลบแล้วกู้คืนไม่ได้)"):
                    return
                deleted = 0
                for f in files:
                    try:
                        os.remove(f)
                        deleted += 1
                    except Exception:
                        pass
                lbl_zip.configure(text=f"🗑️ ลบ {deleted} ไฟล์ใน input-id แล้ว", text_color="#e53935")
                self.log(f"Cleared input-id: deleted {deleted} files")

            btn_zip_row = ctk.CTkFrame(_cur[0], fg_color="transparent")
            btn_zip_row.pack(fill="x", padx=14, pady=(2, 6))
            ctk.CTkButton(btn_zip_row, text="📂 แตก zip → input-id",
                          command=_import_zip, height=30).pack(side="left", expand=True, fill="x", padx=(0, 4))
            ctk.CTkButton(btn_zip_row, text="🗑️ ลบไฟล์ใน input-id",
                          command=_clear_input, height=30,
                          fg_color="#c0392b", hover_color="#a93226").pack(side="left", expand=True, fill="x", padx=(4, 0))

            def _clear_folders():
                # ล้างโฟลเดอร์ผลลัพธ์ทั้งหมด (เหมือน clear-folders.bat) + เคลียร์ไฟล์ใน input-id
                from tkinter import messagebox
                base_dir = os.path.dirname(os.path.abspath(__file__))
                folders = ["backup", "backup-id", "found-hero", "no-hero", "login-success",
                           "login-failed", "random-fail", "fast-random", "file-error",
                           "run-file", "timeout", "logs", "check-coin", "debug-ocr"]
                if not messagebox.askyesno("ยืนยันล้างโฟลเดอร์ทั้งหมด",
                                           "ลบโฟลเดอร์ผลลัพธ์ทั้งหมด + เคลียร์ไฟล์ใน input-id?\n"
                                           "(backup, found-hero, no-hero, logs ฯลฯ — กู้คืนไม่ได้)"):
                    return
                removed = 0
                for fo in folders:
                    p = os.path.join(base_dir, fo)
                    if os.path.isdir(p):
                        try:
                            shutil.rmtree(p)
                            removed += 1
                        except Exception:
                            pass
                in_dir = os.path.join(base_dir, INPUT_DIR)
                cleared = 0
                if os.path.isdir(in_dir):
                    for f in glob.glob(os.path.join(in_dir, "*")):
                        if os.path.isfile(f):
                            try:
                                os.remove(f)
                                cleared += 1
                            except Exception:
                                pass
                lbl_zip.configure(text=f"🧹 ล้าง {removed} โฟลเดอร์ + {cleared} ไฟล์ input-id แล้ว", text_color="#e53935")
                self.log(f"Clear folders: removed {removed} folders, cleared {cleared} input-id files")

            ctk.CTkButton(_cur[0], text="🧹 ล้างโฟลเดอร์ทั้งหมด (clear-folders)",
                          command=_clear_folders, height=30,
                          fg_color="#8e1e1e", hover_color="#6e1515").pack(fill="x", padx=14, pady=(0, 6))

            # ── Save button (pinned at bottom, outside scrollable area) ───
            def _save():
                global EVENT_IMG, DO_BOX, DO_GACHA, FIND_HERO, GACHA_FREE, CHECK_COIN, GACHA_FREE_LOOPS, NOSCAN, SKIPANIMATION, GACHA_CHECK, GACHA_FIND, AUTORUN, SILENT_UPDATE_MODE, OVERWRITE_CONFIG_ON_UPDATE, GETCODE, GETCODE_TEXT, GETQUEST, LOGIN_FAST, GACHA_MIN_COIN, DEBUG_CONSOLE, MOVE_LS_ENABLE, MOVE_LS_TIME, CUSTOM_GACHA, NEW_GACHA, NEW_GACHA_SWIPE, GACHA_LOOP_LIMIT
                new_event = var_event.get()
                new_box   = var_box.get()
                new_gacha = var_gacha.get()
                new_new_gacha = var_new_gacha.get()
                new_ng_swipe = var_ng_swipe.get()
                new_find  = var_find_hero.get()
                new_gfree = var_gacha_free.get()
                new_ccoin = var_check_coin.get()
                new_noscan = var_noscan.get()
                new_skipanim = var_skipanim.get()
                new_gacha_check = var_gacha_check.get()
                new_gacha_find = var_gacha_find.get()
                # Gacha+Find ต้องทำ gacha ปกติ (gacha1→2→3→4→5) ก่อน → บังคับเปิด DO_GACHA
                if new_gacha_find == 1:
                    new_gacha = 1
                new_timeout = var_timeout.get()
                new_autorun = var_autorun.get()
                try:
                    new_timeout_mins = int(entry_timeout.get())
                except ValueError:
                    new_timeout_mins = 10
                try:
                    new_gfree_loops = int(entry_gfree_loops.get())
                except ValueError:
                    new_gfree_loops = 2
                try:
                    new_min_coin = int(entry_min_coin.get())
                except ValueError:
                    new_min_coin = 100

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
                if re.search(r"^GACHA_FIND\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_FIND\s*=\s*\d", f"GACHA_FIND = {new_gacha_find}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_FIND = {new_gacha_find}\n"

                if re.search(r"^TIMEOUT_ENABLE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^TIMEOUT_ENABLE\s*=\s*\d", f"TIMEOUT_ENABLE = {new_timeout}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nTIMEOUT_ENABLE = {new_timeout}\n"

                if re.search(r"^TIMEOUT_MINUTES\s*=\s*\d+", content, flags=re.MULTILINE):
                    content = re.sub(r"^TIMEOUT_MINUTES\s*=\s*\d+", f"TIMEOUT_MINUTES = {new_timeout_mins}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nTIMEOUT_MINUTES = {new_timeout_mins}\n"

                if re.search(r"^AUTORUN\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^AUTORUN\s*=\s*\d", f"AUTORUN = {new_autorun}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nAUTORUN = {new_autorun}\n"

                new_update_mode = var_update_mode.get()
                if re.search(r"^SILENT_UPDATE_MODE\s*=\s*['\"].*['\"]", content, flags=re.MULTILINE):
                    content = re.sub(r"^SILENT_UPDATE_MODE\s*=\s*['\"].*['\"]", f"SILENT_UPDATE_MODE = '{new_update_mode}'",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nSILENT_UPDATE_MODE = '{new_update_mode}'\n"

                new_overwrite_cfg = True if var_overwrite_cfg.get() == 1 else False
                if re.search(r"^OVERWRITE_CONFIG_ON_UPDATE\s*=\s*(True|False)", content, flags=re.MULTILINE):
                    content = re.sub(r"^OVERWRITE_CONFIG_ON_UPDATE\s*=\s*(True|False)", f"OVERWRITE_CONFIG_ON_UPDATE = {new_overwrite_cfg}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nOVERWRITE_CONFIG_ON_UPDATE = {new_overwrite_cfg}\n"

                new_getcode = var_getcode.get()
                new_getcode_txt = entry_getcode_txt.get().strip() or "eFCONNECT"
                if re.search(r"^GETCODE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^GETCODE\s*=\s*\d", f"GETCODE = {new_getcode}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGETCODE = {new_getcode}\n"
                if re.search(r'^GETCODE_TEXT\s*=\s*["\'].*["\']', content, flags=re.MULTILINE):
                    content = re.sub(r'^GETCODE_TEXT\s*=\s*["\'].*["\']', f'GETCODE_TEXT = "{new_getcode_txt}"',
                                     content, flags=re.MULTILINE)
                else:
                    content += f'\nGETCODE_TEXT = "{new_getcode_txt}"\n'

                new_getquest = var_getquest.get()
                if re.search(r"^GETQUEST\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^GETQUEST\s*=\s*\d", f"GETQUEST = {new_getquest}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGETQUEST = {new_getquest}\n"

                new_login_fast = var_login_fast.get()
                if re.search(r"^LOGIN_FAST\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^LOGIN_FAST\s*=\s*\d", f"LOGIN_FAST = {new_login_fast}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nLOGIN_FAST = {new_login_fast}\n"

                if re.search(r"^GACHA_MIN_COIN\s*=\s*\d+", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_MIN_COIN\s*=\s*\d+", f"GACHA_MIN_COIN = {new_min_coin}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_MIN_COIN = {new_min_coin}\n"

                new_move_ls = var_move_ls.get()
                # parse เวลา (รองรับ 24h และ AM/PM เช่น 9:46PM) → HH:MM ; ผิดรูปแบบ → คงค่าเดิม
                new_move_time = parse_time_to_hhmm(entry_move_time.get()) or (str(getattr(cfg, 'MOVE_LS_TIME', '09:00')).strip() or "09:00")
                if re.search(r"^MOVE_LS_ENABLE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^MOVE_LS_ENABLE\s*=\s*\d", f"MOVE_LS_ENABLE = {new_move_ls}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nMOVE_LS_ENABLE = {new_move_ls}\n"
                if re.search(r'^MOVE_LS_TIME\s*=\s*["\'].*["\']', content, flags=re.MULTILINE):
                    content = re.sub(r'^MOVE_LS_TIME\s*=\s*["\'].*["\']', f'MOVE_LS_TIME = "{new_move_time}"',
                                     content, flags=re.MULTILINE)
                else:
                    content += f'\nMOVE_LS_TIME = "{new_move_time}"\n'

                new_debug_console = var_debug_console.get()
                if re.search(r"^DEBUG_CONSOLE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^DEBUG_CONSOLE\s*=\s*\d", f"DEBUG_CONSOLE = {new_debug_console}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nDEBUG_CONSOLE = {new_debug_console}\n"

                new_custom_gacha = var_custom_gacha.get()
                if re.search(r"^CUSTOM_GACHA\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^CUSTOM_GACHA\s*=\s*\d", f"CUSTOM_GACHA = {new_custom_gacha}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nCUSTOM_GACHA = {new_custom_gacha}\n"

                try:
                    new_gacha_limit = max(0, int(entry_gacha_limit.get()))
                except ValueError:
                    new_gacha_limit = 0
                if re.search(r"^GACHA_LOOP_LIMIT\s*=\s*\d+", content, flags=re.MULTILINE):
                    content = re.sub(r"^GACHA_LOOP_LIMIT\s*=\s*\d+", f"GACHA_LOOP_LIMIT = {new_gacha_limit}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nGACHA_LOOP_LIMIT = {new_gacha_limit}\n"

                if re.search(r"^NEW_GACHA\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^NEW_GACHA\s*=\s*\d", f"NEW_GACHA = {new_new_gacha}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nNEW_GACHA = {new_new_gacha}\n"

                if re.search(r"^NEW_GACHA_SWIPE\s*=\s*\d", content, flags=re.MULTILINE):
                    content = re.sub(r"^NEW_GACHA_SWIPE\s*=\s*\d", f"NEW_GACHA_SWIPE = {new_ng_swipe}",
                                     content, flags=re.MULTILINE)
                else:
                    content += f"\nNEW_GACHA_SWIPE = {new_ng_swipe}\n"

                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(content)
                # อัปเดต runtime ด้วย
                CUSTOM_GACHA = new_custom_gacha
                GACHA_LOOP_LIMIT = new_gacha_limit
                NEW_GACHA = new_new_gacha
                NEW_GACHA_SWIPE = new_ng_swipe
                EVENT_IMG  = new_event
                DO_BOX     = new_box
                DO_GACHA   = new_gacha
                FIND_HERO  = new_find
                GACHA_FREE = new_gfree
                GACHA_FREE_LOOPS = new_gfree_loops
                CHECK_COIN = new_ccoin
                NOSCAN     = new_noscan
                GACHA_CHECK = new_gacha_check
                GACHA_FIND = new_gacha_find
                AUTORUN    = new_autorun
                SILENT_UPDATE_MODE = new_update_mode
                OVERWRITE_CONFIG_ON_UPDATE = new_overwrite_cfg
                GETCODE = new_getcode
                GETCODE_TEXT = new_getcode_txt
                GETQUEST = new_getquest
                LOGIN_FAST = new_login_fast
                GACHA_MIN_COIN = new_min_coin
                MOVE_LS_ENABLE = new_move_ls
                MOVE_LS_TIME = new_move_time
                DEBUG_CONSOLE = new_debug_console
                importlib.reload(cfg)
                label_status.configure(text=f"✅ Saved!",
                                       text_color="#4caf50")
                self.log(f"Config saved: EVENT={new_event}, BOX={new_box}, GACHA={new_gacha}, HERO={new_find}, GFREE={new_gfree}({new_gfree_loops} loops), COIN={new_ccoin}(min {new_min_coin}), NOSCAN={new_noscan}, GACHACHECK={new_gacha_check}, GACHAFIND={new_gacha_find}, AUTORUN={new_autorun}, GETCODE={new_getcode}, GETCODE_TEXT={new_getcode_txt}, GETQUEST={new_getquest}")

            ctk.CTkButton(win, text="💾 Save", fg_color="#2cc985",
                          hover_color="#229f69", command=_save).pack(pady=8)
            label_status = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
            label_status.pack()

        # ── Helpers ───────────────────────────────────────────────────────
        def log(self, msg):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            if len(self._log_buffer) > 80:
                self._log_buffer = self._log_buffer[-40:]  # ตัดทิ้งกัน queue ล้น
            self._log_buffer.append(f"[{ts}] {msg}\n")
            # ไม่ flush ที่นี่ — _periodic_log_flush จัดการทุก 500ms เพื่อป้องกัน text widget ops กลาง queue drain

        def _flush_log_buffer(self):
            if not self._log_buffer:
                return
            lines = self._log_buffer[:25]
            self._log_buffer = self._log_buffer[25:]
            try:
                self.log_text.configure(state="normal")
                try:
                    total = int(self.log_text.index("end-1c").split(".")[0])
                    if total > 500:
                        self.log_text.delete("1.0", f"{total - 300}.0")
                except Exception:
                    pass
                self.log_text.insert("end", "".join(lines))
                # see("end") removed — blocked click/drag events every 100ms
                self.log_text.configure(state="disabled")
            except Exception:
                pass

        def _periodic_log_flush(self):
            try:
                self._flush_log_buffer()
            except Exception:
                pass
            finally:
                self.after(500, self._periodic_log_flush)

        def _periodic_gc(self):
            # drain queue ที่ค้างบน main thread (เร็ว)
            try:
                drained = 0
                while _gui_queue.qsize() > 300 and drained < 200:
                    try:
                        _gui_queue.get_nowait()
                        drained += 1
                    except Exception:
                        break
                if drained:
                    self.log(f"[GC] Drained {drained} stale queue items")
            except Exception:
                pass
            # gc.collect() ใน background thread — ไม่บล็อก main thread
            def _bg_gc():
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
            threading.Thread(target=_bg_gc, daemon=True).start()
            self.after(120000, self._periodic_gc)

        def _check_move_schedule(self):
            # ย้าย login-success → input-id อัตโนมัติ เมื่อถึงเวลา MOVE_LS_TIME (วันละครั้ง)
            # + log นับถอยหลังว่าใกล้ถึงเวลายัง
            try:
                # re-sync เวลาโลก (internet) ทุก ~1 ชม. แบบ background
                if time.time() - _net_time_last_sync > 3600:
                    threading.Thread(target=_sync_net_time, daemon=True).start()
                if MOVE_LS_ENABLE == 1:
                    from datetime import timedelta
                    now = real_now()   # อิงเวลาโลก (internet) ถ้า sync ได้ ไม่งั้นเวลาเครื่อง
                    try:
                        sh, sm = [int(x) for x in str(MOVE_LS_TIME).strip().split(":")[:2]]
                    except Exception:
                        sh, sm = 9, 0
                    sched = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                    today = now.strftime("%Y-%m-%d")
                    # กันย้ายซ้ำ "ต่อ (วัน+เวลาที่ตั้ง)" → เปลี่ยนเวลาใหม่ = ได้ย้ายใหม่
                    move_key = (today, f"{sh:02d}:{sm:02d}")
                    already = (getattr(self, "_last_move_key", None) == move_key)

                    # edge-trigger: ย้ายเฉพาะตอน "นาฬิกาเดินข้ามเวลาที่ตั้ง" ขณะโปรแกรมรันอยู่
                    #   รอบแรกหลังเปิดโปรแกรม (prev = None) จะไม่ย้าย → กันย้ายเองตอนเพิ่งเปิด/เวลาเพิ่งผ่าน
                    prev = getattr(self, "_sched_prev_now", None)
                    self._sched_prev_now = now
                    crossed = (prev is not None and prev < sched <= now)

                    if crossed and not already:
                        self._last_move_key = move_key
                        self._last_cd_min = None
                        moved = move_login_success_to_input()
                        self.log(f"⏰ Auto-move {moved} files: login-success → input-id (at {MOVE_LS_TIME})")
                    else:
                        # นับถอยหลังถึงรอบถัดไป (ถ้าเลยเวลา/ย้ายแล้ววันนี้ → พรุ่งนี้)
                        nxt = sched if (now < sched and not already) else sched + timedelta(days=1)
                        mins = max(0, int((nxt - now).total_seconds()) // 60)
                        last = getattr(self, "_last_cd_min", None)
                        # ใกล้ (<=60 นาที) log ทุกนาที , ไกล log ทุก 30 นาที
                        if last != mins and (mins <= 60 or mins % 30 == 0):
                            self._last_cd_min = mins
                            h, m = divmod(mins, 60)
                            self.log(f"⏳ Move login-success in {h}h {m:02d}m (at {MOVE_LS_TIME})")
            except Exception as e:
                self.log(f"Move schedule error: {e}")
            self.after(30000, self._check_move_schedule)

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
                    connect_known_ports(quiet=False, kill_server=False)
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

            # Trigger auto-run if enabled (only once on startup, even if 0 devices are found at first)
            global AUTORUN
            if AUTORUN == 1 and not getattr(self, 'autorun_triggered', False):
                self.autorun_triggered = True
                self.log("🚀 [AUTORUN] Auto-start enabled! Starting bot in 3 seconds...")
                self.after(3000, self.toggle_bot)

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
                # DO NOT scan/connect all 100 ports in a background thread every 10 seconds! That spikes CPU and freezes the system.
                # Just call get_connected_devices() which is one fast call to see what is already connected.
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
            # เผื่อโค้ดเก่า/auto-start ยังเรียก toggle_bot — route ไป start/stop
            if not bot_running:
                self.start_bot()
            else:
                self.stop_bot()

        def start_bot(self):
            global bot_running
            if bot_running:
                return
            bot_running = True
            self.is_started = True
            self._refresh_run_buttons()
            self.start_bot_threads()

        def stop_bot(self):
            global bot_running
            if not bot_running:
                return
            bot_running = False
            self._refresh_run_buttons()
            self.log("Bot stopped by user.")

        def _refresh_run_buttons(self):
            # อัปเดตสี/สถานะปุ่ม Start Bot / Stop ตามว่ากำลังรันอยู่ไหม
            try:
                if bot_running:
                    self.btn_start.configure(state="disabled", fg_color="#1f6f4a")
                    self.btn_stop.configure(state="normal", fg_color="#e53935")
                else:
                    self.btn_start.configure(state="normal", fg_color="#2cc985")
                    self.btn_stop.configure(state="disabled", fg_color="#6b2f2e")
            except Exception:
                pass

        def select_all_devices(self):
            # กดครั้งเดียว = เลือกทุกเครื่อง; ถ้าเลือกครบอยู่แล้ว = ยกเลิกทั้งหมด
            try:
                rows = list(self.device_monitors.values())
                if not rows:
                    return
                all_on = all(getattr(r, 'chk', None) is not None and r.chk.get() == 1 for r in rows)
                for r in rows:
                    chk = getattr(r, 'chk', None)
                    if chk is None:
                        continue
                    chk.deselect() if all_on else chk.select()
            except Exception:
                pass

        def start_adb(self):
            self.log("Start ADB: starting server + scanning ports...")
            def _bg():
                try:
                    connect_known_ports(quiet=True, kill_server=False)
                    self.after(0, self.connect_missing_devices)
                except Exception as e:
                    self.log(f"Start ADB error: {e}")
            threading.Thread(target=_bg, daemon=True).start()

        def kill_adb(self):
            self.log("Kill ADB: stopping adb server...")
            def _bg():
                try:
                    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
                    subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=6, **kwargs)
                    self.log("adb server killed.")
                except Exception as e:
                    self.log(f"Kill ADB error: {e}")
            threading.Thread(target=_bg, daemon=True).start()

        def _config_categories(self):
            # หมวด → รายการ (kind, label, VAR)  kind: 'chk'=สวิตช์ 0/1 · 'ent'=เลขจำนวนเต็ม · 'ents'=ข้อความ
            return {
                "⚙️ General": [
                    ("chk", "รับของ (1-4)",              "DO_BOX"),
                    ("chk", "หาตัวนักเตะ",            "FIND_HERO"),
                    ("chk", "Check Coin Mode",           "CHECK_COIN"),
                    ("chk", "Login Fast (เจอ login จบทันที)", "LOGIN_FAST"),
                    ("ent", "Min coin to gacha",         "GACHA_MIN_COIN"),
                ],
                "🎰 Gacha": [
                    ("chk", "Gacha Mode",                "DO_GACHA"),
                    ("chk", "New Gacha Mode",            "NEW_GACHA"),
                    ("chk", "└ Swipe (เลื่อนหาจอ)",       "NEW_GACHA_SWIPE"),
                    ("chk", "สุ่มจน coin หมด",           "CUSTOM_GACHA"),
                    ("ent", "└ Custom จำกัดรอบ (0=จนหมด)", "GACHA_LOOP_LIMIT"),
                    ("chk", "└ Gacha500 (step1 coin + step2)", "GACHA500"),
                    ("ent", "  └ Coin เก็บ (>= → coin+)",  "COIN_GACHA_THRESHOLD"),
                    ("chk", "  └ One Gacha500 (รอบเดียวจบ)", "ONE_GACHA500"),
                    ("chk", "Gacha + Find + Check Coin", "GACHA_FIND"),
                ],
                "🆓 Gacha Free": [
                    ("chk", "Gacha Free Mode",           "GACHA_FREE"),
                    ("chk", "Gacha Free + Check + Find", "GACHA_CHECK"),
                    ("ent", "Loops count",               "GACHA_FREE_LOOPS"),
                ],
                "🎁 Get-Code": [
                    ("chk", "Get Code Mode",             "GETCODE"),
                    ("ents", "Code Text",                "GETCODE_TEXT"),
                    ("chk", "Get Quest Mode",            "GETQUEST"),
                ],
                "🔍 Find Hero": [
                    ("chk", "หาตัวนักเตะ",                 "FIND_HERO"),
                    ("chk", "Check Coin",                "CHECK_COIN"),
                ],
                "🔧 Setting": [
                    ("chk", "No Scan (→ fast-random)",   "NOSCAN"),
                    ("chk", "Skip Animation",            "SKIPANIMATION"),
                    ("chk", "Event Image (play22→31)",   "EVENT_IMG"),
                    ("chk", "Auto Run on Launch",        "AUTORUN"),
                    ("chk", "Timeout Mode (กันค้าง)",     "TIMEOUT_ENABLE"),
                    ("ent", "Timeout (นาที)",            "TIMEOUT_MINUTES"),
                ],
            }

        def _write_config_var(self, var, value, is_string=False):
            # เขียนค่าเดียวลง config.py แล้ว reload (บอท hot-reload รอบถัดไป)
            import re, importlib
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    content = f.read()
                newval = f'"{value}"' if is_string else f'{value}'
                if re.search(rf'^{re.escape(var)}\s*=', content, flags=re.MULTILINE):
                    if is_string:
                        content = re.sub(rf'^({re.escape(var)}\s*=\s*).*$', rf'\g<1>{newval}',
                                         content, count=1, flags=re.MULTILINE)
                    else:
                        content = re.sub(rf'^({re.escape(var)}\s*=\s*)\S+', rf'\g<1>{newval}',
                                         content, count=1, flags=re.MULTILINE)
                else:
                    content += f'\n{var} = {newval}\n'
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(content)
                import config as _c
                importlib.reload(_c)
                self.log(f"Config: {var} = {newval} (saved)")
            except Exception as e:
                self.log(f"Config save error ({var}): {e}")

        def on_category_select(self, choice):
            # 📊 Stats → โชว์สรุปผล ; หัวข้ออื่น → โชว์ checkbox config ของหัวข้อนั้น
            try:
                if choice.startswith("📊"):
                    self.config_view.pack_forget()
                    self.stats_view.pack(fill="both", expand=True)
                    self.rhdr_label.configure(text="   🏆 SUMMARY STATS", text_color="#f2c94c")
                    return
                items = self._config_categories().get(choice)
                if items is None:
                    return
                self.stats_view.pack_forget()
                self.config_view.pack(fill="both", expand=True, padx=3, pady=3)
                self.rhdr_label.configure(text=f"   ⚙️ CONFIG · {choice}", text_color="#a996ff")
                for w in self.config_view.winfo_children():
                    w.destroy()
                import importlib, config as _c
                importlib.reload(_c)
                for kind, label, var in items:
                    row = ctk.CTkFrame(self.config_view, fg_color="#343841", corner_radius=6)
                    row.pack(fill="x", padx=4, pady=3)
                    ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12),
                                 anchor="w").pack(side="left", padx=(10, 4), pady=7)
                    if kind == "chk":
                        v = ctk.IntVar(value=int(getattr(_c, var, 0) or 0))
                        def _cmd(vr=var, vv=v):
                            self._write_config_var(vr, vv.get())
                        ctk.CTkSwitch(row, text="", variable=v, onvalue=1, offvalue=0,
                                      command=_cmd).pack(side="right", padx=10, pady=6)
                    else:
                        is_str = (kind == "ents")
                        cur = getattr(_c, var, "" if is_str else 0)
                        e = ctk.CTkEntry(row, width=(120 if is_str else 60), height=24, justify="center")
                        e.insert(0, str(cur))
                        e.pack(side="right", padx=10, pady=6)
                        def _save(ev=None, vr=var, ent=e, s=is_str):
                            val = ent.get().strip()
                            if not s:
                                try:
                                    val = int(val)
                                except ValueError:
                                    return
                            self._write_config_var(vr, val, is_string=s)
                        e.bind("<Return>", _save)
                        e.bind("<FocusOut>", _save)
            except Exception as e:
                self.log(f"on_category_select error: {e}")

        def start_bot_threads(self):
            devices = list(self.device_monitors.keys())
            if not devices:
                self.log("No devices loaded yet! Running ADB scan in background...")
                def _bg():
                    connect_known_ports(quiet=False, kill_server=False)
                    devs = get_connected_devices()
                    _gui_queue.put(('adb_ready', devs))
                    # Schedule start_bot_threads on the main thread after a short delay
                    self.after(1000, self.start_bot_threads)
                threading.Thread(target=_bg, daemon=True).start()
                return

            if not devices:
                self.log("ERROR: Still no devices found!")
                return

            client = AdbClient(host="127.0.0.1", port=5037)
            start_cpu_balancer()   # เกลี่ย CPU ของ MuMu ข้าม socket (กันโหลดกอง group เดียวจนค้าง)
            refresh_serial_index_map()   # จำ serial -> MuMu index ไว้ตอนทุกเครื่องยังปกติ (ไว้สั่ง restart ตอนหลุด)
            self.log(f"Starting threads for {len(devices)} devices...")

            def launch_device(index):
                if not bot_running:
                    return  # หยุดการรันถ้าผู้ใช้กด STOP ระหว่างทาง
                if index >= len(devices):
                    self.log("All devices successfully started!")
                    return

                serial = devices[index]
                device = client.device(serial)
                if device is None:
                    self.log(f"ERROR: Cannot get device {serial} from ADB!")
                    launch_device(index + 1)
                    return

                self.log(f"✅ Started bot on {serial}")
                t = threading.Thread(target=process_device_login,
                                     args=(device,), daemon=True)
                t.start()
                self.threads.append(t)

                if index < len(devices) - 1:
                    self.log(f"Waiting 10 seconds before starting the next device...")
                    # ใช้ self.after แทน time.sleep เพื่อไม่ให้เธรด GUI ค้าง (Not Responding)
                    self.after(10000, lambda: launch_device(index + 1))

            launch_device(0)

        def update_device(self, serial, **kwargs):
            if serial in self.device_monitors:
                self.device_monitors[serial].update_state(**kwargs)

        def update_realtime_stats(self):
            def _bg_scan():
                try:
                    input_count   = len(glob.glob(os.path.join(INPUT_DIR, "*.dat")))
                    success_count = len(glob.glob(os.path.join(LOGIN_SUCCESS_DIR, "*.dat")))
                    
                    # Scan all subfolders inside found-hero and backup-id recursively using os.walk
                    found_files = []
                    for root, dirs, files in os.walk(FOUND_HERO_DIR):
                        for file in files:
                            if file.lower().endswith(".dat"):
                                found_files.append(os.path.join(root, file))
                                
                    for root, dirs, files in os.walk(BACKUP_ID_DIR):
                        for file in files:
                            if file.lower().endswith(".dat"):
                                found_files.append(os.path.join(root, file))

                    hero_count  = len(found_files)
                    fail_count  = len(glob.glob(os.path.join(FILE_ERROR_DIR, "*.dat")))
                    fast_count  = len(glob.glob(os.path.join(FAST_RANDOM_DIR, "*.dat")))
                    
                    hero_counts = {}
                    for fpath in found_files:
                        fname = os.path.basename(fpath)
                        parts = fname.split('+')
                        if len(parts) > 1:
                            h_key = "+".join(parts[:-1]).strip()
                            if h_key:
                                hero_counts[h_key] = hero_counts.get(h_key, 0) + 1
                    
                    _gui_queue.put(('stats', (input_count, success_count, hero_count, hero_counts, fail_count, fast_count)))
                except Exception:
                    pass

            t = threading.Thread(target=_bg_scan, daemon=True)
            t.start()
            self.after(30000, self.update_realtime_stats)

        def _apply_stats_ui(self, input_count, success_count, hero_count, hero_counts, fail_count=0, fast_count=0):
            try:
                self._last_stats_data = (input_count, success_count, hero_count, hero_counts, fail_count, fast_count)
                
                # Check for active search filters
                active_filts = getattr(self, 'active_filters', [])
                
                def is_matched(name):
                    if not active_filts:
                        return True
                    name_lower = name.lower()
                    return any(f in name_lower for f in active_filts)

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
                if hasattr(self, 'lbl_fail_count') and prev.get('fail') != fail_count:
                    self.lbl_fail_count.configure(text=f"❌ {fail_count}")
                    prev['fail'] = fail_count
                if hasattr(self, 'lbl_fast_count') and prev.get('fast') != fast_count:
                    self.lbl_fast_count.configure(text=f"⚡ {fast_count}")
                    prev['fast'] = fast_count

                # Build desired stat rows with multi-tag filter applied
                desired = {}
                if success_count and is_matched("login สำเร็จ"):
                    desired["✅ login สำเร็จ"] = (success_count, False)
                for h_name, count in hero_counts.items():
                    if is_matched(h_name):
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
                    
            except Exception:
                pass

        def _process_gui_queue(self):
            """Central poller: drain _gui_queue and apply updates. Runs every 200ms."""
            try:
                processed = 0
                while processed < 50:
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
                    elif kind == 'silent_update':
                        self.perform_silent_update()
            except Exception:
                pass
            finally:
                self.after(200, self._process_gui_queue)

        def check_background_updates(self):
            def _thread():
                try:
                    # Ensure script directory is in sys.path for background imports
                    base = os.path.dirname(os.path.abspath(__file__))
                    if base not in sys.path:
                        sys.path.insert(0, base)
                    
                    import auto_update
                    _gui_queue.put(('log', "🔍 [Update Checker] Checking for new updates..."))
                    latest_version, zip_url = auto_update.get_latest_release()
                    local_version = auto_update.get_local_version() or ""
                    
                    if not latest_version:
                        _gui_queue.put(('log', "⚠️ [Update Checker] Could not fetch latest version (GitHub error or offline)."))
                        return

                    _gui_queue.put(('log', f"🔍 [Update Checker] Check complete. Local: {local_version}, Latest: {latest_version}"))
                    
                    if latest_version != local_version:
                        _gui_queue.put(('log', f"🔔 [UPDATE] New version {latest_version} detected! Auto-updating silently in 5s..."))
                        time.sleep(5)
                        global bot_running
                        bot_running = False
                        _gui_queue.put(('silent_update', None))
                except Exception as e:
                    _gui_queue.put(('log', f"❌ [Update Checker] Error: {e}"))
                    print(f"[Update Checker] Error: {e}")

            threading.Thread(target=_thread, daemon=True).start()

        def tick_update_timer(self):
            if not hasattr(self, 'update_check_seconds'):
                self.update_check_seconds = 60

            if self.update_check_seconds <= 0:
                self.update_check_seconds = 60
                self.check_background_updates()
            
            self.update_check_seconds -= 1
            self.after(1000, self.tick_update_timer)

        def perform_silent_update(self):
            self.log("🚀 Running silent auto-updater...")
            self.destroy() # Close GUI
            
            # Spawn auto_update.py in silent mode
            base = os.path.dirname(os.path.abspath(__file__))
            updater_script = os.path.join(base, "auto_update.py")
            
            kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
            subprocess.Popen([sys.executable, updater_script, "--silent"], **kwargs)
            os._exit(12)

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

class DeviceTimeoutException(Exception): pass

def check_device_reset(serial, cycle_start=None):
    if DEVICE_RESET_FLAGS.get(serial):
        DEVICE_RESET_FLAGS[serial] = False
        raise DeviceResetException(serial)
        
    try:
        from config import TIMEOUT_ENABLE, TIMEOUT_MINUTES
        if TIMEOUT_ENABLE == 1 and cycle_start is not None:
            if time.time() - cycle_start > TIMEOUT_MINUTES * 60:
                raise DeviceTimeoutException(serial)
    except (ImportError, AttributeError):
        # Config not found — use fallback 10 min timeout
        if cycle_start is not None:
            if time.time() - cycle_start > 600:
                raise DeviceTimeoutException(serial)

def update_gui(serial, **kwargs):
    """Queue a device update — never call GUI directly from worker threads."""
    if gui_instance:
        if _gui_queue.qsize() < 400:  # drop เมื่อ queue เริ่มล้น ป้องกัน Not Responding
            _gui_queue.put(('device_update', (serial, kwargs)))

_GUI_LOG_INTERVAL = 5
_gui_last_step = {}

def gui_log(serial, msg, step=None, status=None):
    cprint(f"{Fore.CYAN}[{serial}] {msg}{Style.RESET_ALL}")
    now = time.time()
    last = _gui_last_update.get(serial, 0)
    last_step = _gui_last_step.get(serial, None)
    
    step_changed = step and (step != last_step)
    if step_changed:
        _gui_last_step[serial] = step
        
    if status or step_changed or (now - last >= _GUI_LOG_INTERVAL):
        _gui_last_update[serial] = now
        update_gui(serial, log=msg, step=step, status=status)
        # บันทึก log ลงไฟล์เฉพาะรอบที่ส่ง GUI update (ลด file I/O 50 จอ)
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

def connect_known_ports(quiet=False, kill_server=False):
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

def _device_boot_id(serial):
    """อ่าน boot_id ของเครื่อง (unique ต่อ VM/instance ต่อการบูต 1 ครั้ง)
    ไว้จับคู่ว่า serial 2 ตัว (คนละ port) จริงๆ แล้วเป็นเครื่องเดียวกันหรือไม่"""
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        r = subprocess.run([adb_path, "-s", serial, "shell", "cat /proc/sys/kernel/random/boot_id"],
                           capture_output=True, text=True, timeout=3, **kwargs)
        v = r.stdout.strip()
        if v and len(v) >= 16 and " " not in v and "no such" not in v.lower():
            return v
    except Exception:
        pass
    return None

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
        # Normalize emulator-XXXX → 127.0.0.1:(XXXX+1) so all devices use IP:port format
        final = []
        for serial in port_map.values():
            if "emulator-" in serial:
                try:
                    adb_port = int(serial.split("-")[1]) + 1
                    ip_serial = f"127.0.0.1:{adb_port}"
                    subprocess.run([adb_path, "connect", ip_serial],
                                   capture_output=True, timeout=2, shell=(os.name == 'nt'))
                    final.append(ip_serial)
                except Exception:
                    final.append(serial)
            else:
                final.append(serial)

        # ── Dedup: เครื่องเดียวกันโผล่หลาย port (เช่น 127.0.0.1:5563 กับ 127.0.0.1:16512) ──
        #    จับคู่ด้วย boot_id (unique ต่อ instance) → เก็บไว้ port เดียว โดยเลือกช่วง 55xx ก่อน
        if len(final) > 1:
            def _is_55xx(s):
                try:
                    return 5555 <= int(s.split(":")[1]) <= 5755
                except Exception:
                    return False
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
                    boot_ids = list(ex.map(_device_boot_id, final))
                chosen = {}   # boot_id -> ตำแหน่งใน result
                result = []
                for serial, bid in zip(final, boot_ids):
                    if not bid:
                        result.append(serial)   # อ่าน boot_id ไม่ได้ → เก็บไว้ตามเดิม (ไม่เสี่ยงตัดเครื่องจริงทิ้ง)
                        continue
                    if bid not in chosen:
                        chosen[bid] = len(result)
                        result.append(serial)
                    elif _is_55xx(serial) and not _is_55xx(result[chosen[bid]]):
                        result[chosen[bid]] = serial   # ซ้ำกัน → เลือกตัวที่เป็น port 55xx
                final = result
            except Exception:
                pass

        return final
    except: return []

def is_device_online(device):
    """เช็คเร็วๆ ว่า device ยัง online จริงไหม (adb get-state == 'device')."""
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        r = subprocess.run([adb_path, "-s", device.serial, "get-state"],
                           capture_output=True, text=True, timeout=5, **kwargs)
        return r.stdout.strip() == "device"
    except Exception:
        return False

def try_reconnect_device(serial):
    """พยายาม adb connect กลับ (เผื่อ MuMu ฟื้นจาก offline/ANR)."""
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        subprocess.run([adb_path, "connect", serial],
                       capture_output=True, text=True, timeout=5, **kwargs)
    except Exception:
        pass

# ── Root Toggle Helpers (ported from cookie-run) ──────────────────────
SERIAL_TO_INDEX = {}

def find_mumu_manager():
    """หา path ของ MuMuManager.exe — ลอง config ก่อน แล้วค่อยไล่หา/glob ตาม install ทั่วไป"""
    if MUMU_MANAGER and os.path.exists(MUMU_MANAGER):
        return MUMU_MANAGER
    bases = [r"C:\Program Files\Netease", r"C:\Program Files (x86)\Netease",
             r"D:\Program Files\Netease", r"E:\Program Files\Netease"]
    subs = [r"MuMuPlayer\nx_main\MuMuManager.exe",
            r"MuMuPlayerGlobal-12.0\nx_main\MuMuManager.exe",
            r"MuMuPlayer-12.0\nx_main\MuMuManager.exe",
            r"MuMuPlayerGlobal-12.0\shell\MuMuManager.exe",
            r"MuMu Player 12\shell\MuMuManager.exe",
            r"MuMuPlayer\shell\MuMuManager.exe"]
    for b in bases:
        for s in subs:
            p = os.path.join(b, s)
            if os.path.exists(p):
                return p
    for b in bases:
        if os.path.isdir(b):
            try:
                for r, _dirs, files in os.walk(b):
                    if "MuMuManager.exe" in files:
                        return os.path.join(r, "MuMuManager.exe")
            except Exception:
                pass
    return None

def _mumu(args, timeout=60):
    exe = find_mumu_manager() or MUMU_MANAGER
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    try:
        return subprocess.run([exe] + args, capture_output=True,
                              text=True, timeout=timeout, **kwargs)
    except Exception as e:
        cprint(f"{Fore.RED}[MuMu] error: {e}{Style.RESET_ALL}")
        return None

def get_mumu_instances():
    """
    อ่าน MuMuManager info -v all → คืน list ของ (index, serial) เฉพาะ instance ที่รันอยู่
    """
    import json
    r = _mumu(["info", "-v", "all"])
    if r is None:
        cprint(f"{Fore.RED}[MuMu] เรียก MuMuManager ไม่ได้ (เช็ค MUMU_MANAGER path){Style.RESET_ALL}")
        return []
    raw = (r.stdout or "").strip()
    if not raw:
        cprint(f"{Fore.RED}[MuMu] info ไม่มี output. stderr={ (r.stderr or '').strip()[:200] }{Style.RESET_ALL}")
        return []
    try:
        data = json.loads(raw)
    except Exception as e:
        cprint(f"{Fore.RED}[MuMu] parse info error: {e} | raw={raw[:200]}{Style.RESET_ALL}")
        return []
    if "index" in data and "adb_port" in data:
        data = {str(data.get("index", "0")): data}
    out, skipped = [], []
    for key, inf in data.items():
        if not isinstance(inf, dict):
            continue
        idx = str(inf.get("index", key))
        if inf.get("is_android_started") and inf.get("adb_port"):
            ip = inf.get("adb_host_ip", "127.0.0.1")
            out.append((idx, f"{ip}:{inf['adb_port']}"))
        else:
            skipped.append(idx)
    return out

def mumu_set_root(index, on):
    """ตั้ง root_permission ของ MuMu instance ตาม index — มีผลทันที (live) ไม่ต้อง restart"""
    _mumu(["setting", "-v", str(index), "-k", "root_permission",
           "-val", "true" if on else "false"])

# ── Auto restart MuMu instance ที่ adb หลุด (offline ค้าง) ────────────────
_MUMU_RESTART_LOCK  = threading.Lock()   # รีสตาร์ททีละเครื่อง — กันหลายตัวบูตพร้อมกันจนโฮสต์แขวน
_MUMU_LAST_RESTART  = {}                 # serial -> เวลาที่สั่ง restart ล่าสุด (cooldown)
_MUMU_LAST_BOOT_TS  = [0.0]              # เวลาที่ instance ล่าสุดถูกสั่งบูต (เว้นระยะระหว่างเครื่อง)
_MUMU_COOLDOWN_LOGGED = {}               # serial -> เวลา restart ที่เคย log cooldown ไปแล้ว (กัน log ซ้ำทุก 10 วิ)
_MIN_RESTART_GAP    = 30.0               # วินาที — เว้นระยะขั้นต่ำระหว่างการบูต instance แต่ละตัว

def mumu_running_indexes():
    """คืน list ของ index ที่ instance กำลังรันอยู่ (อ่านจาก MuMuManager info -v all)"""
    import json
    r = _mumu(["info", "-v", "all"])
    if r is None:
        return []
    try:
        data = json.loads((r.stdout or "").strip())
    except Exception:
        return []
    if "index" in data and not any(isinstance(v, dict) for v in data.values()):
        data = {str(data.get("index", "0")): data}
    out = []
    for key, inf in data.items():
        if isinstance(inf, dict) and inf.get("is_android_started"):
            out.append(str(inf.get("index", key)))
    return out

def mumu_adb_endpoint(index):
    """ถาม MuMuManager ตรงๆ ว่า instance นี้ใช้ adb host:port ไหน (สั่ง connect ให้ในตัวด้วย)
    แม่นกว่าอ่านจาก info เพราะบาง version ไม่ใส่ adb_port มาใน info"""
    import json
    r = _mumu(["adb", "-v", str(index), "-c", "connect"], timeout=25)
    if r is None:
        return None
    try:
        data = json.loads((r.stdout or "").strip())
        if isinstance(data, dict):
            if data.get("adb_port"):
                return f"{data.get('adb_host', '127.0.0.1')}:{data['adb_port']}"
            for v in data.values():   # เผื่อคืนเป็น dict ซ้อนราย index
                if isinstance(v, dict) and v.get("adb_port"):
                    return f"{v.get('adb_host', '127.0.0.1')}:{v['adb_port']}"
    except Exception:
        pass
    return None

def refresh_serial_index_map(force=False):
    """สร้างแมพ serial -> MuMu index — เรียกตอนบอทเริ่ม (ตอนที่ทุกเครื่องยังปกติ)

    ทำไมต้องทำล่วงหน้า: instance ที่ "ดับไปแล้ว" จะไม่มี adb port ให้ถามอีก
    → ถ้าไม่มีแมพไว้ก่อน จะสั่ง restart ไม่ได้ (และห้ามเดา เดี๋ยวไปดับจอที่ยังดีอยู่)

    ทำไมต้องจับคู่ด้วย boot_id: instance เดียวกันมองเห็นได้หลาย port
    (เช่น 127.0.0.1:5557 กับ 127.0.0.1:16416 = เครื่องเดียวกัน) — บอทใช้ port 55xx
    แต่ MuMuManager รายงานอีก port หนึ่ง เทียบ string ตรงๆ จะไม่เจอกัน
    """
    try:
        # 1) ทางลัด — info ใส่ adb_port มาให้เลย (MuMu บาง version)
        idx_ep = {}
        try:
            for idx, s in get_mumu_instances():
                idx_ep[str(idx)] = s
                if force or s not in SERIAL_TO_INDEX:
                    SERIAL_TO_INDEX[s] = str(idx)
        except Exception:
            pass

        # 2) index ที่รันอยู่แต่ยังไม่รู้ port → ถาม MuMuManager ตรงๆ (ขนานกัน)
        missing = [i for i in mumu_running_indexes() if i not in idx_ep]
        if missing:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                for idx, ep in zip(missing, ex.map(mumu_adb_endpoint, missing)):
                    if ep:
                        idx_ep[str(idx)] = ep
                        if force or ep not in SERIAL_TO_INDEX:
                            SERIAL_TO_INDEX[ep] = str(idx)

        # 3) serial ที่บอทใช้จริงอาจเป็นคนละ port กับที่ MuMuManager บอก → จับคู่ด้วย boot_id
        serials = [s for s in get_connected_devices() if force or s not in SERIAL_TO_INDEX]
        if serials and idx_ep:
            idx_list = list(idx_ep.keys())
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
                ep_boot  = list(ex.map(_device_boot_id, [idx_ep[i] for i in idx_list]))
                ser_boot = list(ex.map(_device_boot_id, serials))
            boot_to_idx = {b: i for i, b in zip(idx_list, ep_boot) if b}
            for s, b in zip(serials, ser_boot):
                if b and b in boot_to_idx:
                    SERIAL_TO_INDEX[s] = boot_to_idx[b]
    except Exception as e:
        cprint(f"{Fore.YELLOW}[MuMu] สร้างแมพ serial→index ไม่สำเร็จ: {e}{Style.RESET_ALL}")
    return SERIAL_TO_INDEX

def mumu_index_for_serial(serial):
    """หา MuMu index ของ serial นี้ — ต้องรู้ index จริงเท่านั้น (ไม่เดาจากเลข port)
    หาไม่เจอ → None เพื่อกัน 'รีสตาร์ทผิดเครื่อง' ไปดับจอที่ยังทำงานดีอยู่"""
    idx = SERIAL_TO_INDEX.get(serial)
    if idx is not None:
        return idx
    refresh_serial_index_map()
    return SERIAL_TO_INDEX.get(serial)

def mumu_control(index, action, timeout=120):
    """สั่ง MuMuManager control -v <index> <action>   (launch / shutdown / restart)
    คืน (ok, ข้อความ)"""
    r = _mumu(["control", "-v", str(index), action], timeout=timeout)
    if r is None:
        return False, "เรียก MuMuManager ไม่ได้"
    out = ((r.stdout or "") + " " + (r.stderr or "")).strip()
    return (r.returncode == 0), out

def wait_device_online(serial, timeout=240, poll=3.0, mumu_index=None):
    """รอจนเครื่องกลับมา online จริง (adb get-state = device + sys.boot_completed = 1)
    ระหว่างรอจะ adb connect ให้เป็นระยะ — ถ้าส่ง mumu_index มาด้วย จะให้ MuMuManager
    สั่ง connect ฝั่งตัวมันเองเป็นระยะด้วย (เผื่อ adb ฝั่งเราต่อไม่ติดหลังบูตใหม่)"""
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    deadline = time.time() + timeout
    rounds = 0
    while time.time() < deadline:
        try_reconnect_device(serial)
        rounds += 1
        if mumu_index is not None and rounds % 5 == 1:
            try:
                mumu_adb_endpoint(mumu_index)
            except Exception:
                pass
        try:
            r = subprocess.run([adb_path, "-s", serial, "get-state"],
                               capture_output=True, text=True, timeout=5, **kwargs)
            if r.stdout.strip() == "device":
                b = subprocess.run([adb_path, "-s", serial, "shell", "getprop sys.boot_completed"],
                                   capture_output=True, text=True, timeout=8, **kwargs)
                if b.stdout.strip() == "1":
                    return True
        except Exception:
            pass
        time.sleep(poll)
    return False

def restart_mumu_instance(serial):
    """MuMu instance ของ serial นี้ค้าง/ดับไปเอง → สั่งปิด-เปิด "เฉพาะตัวนี้ตัวเดียว"
    แล้วรอจนบูตกลับมา online (เครื่องอื่นไม่โดนแตะ)

    คืน True = กลับมาใช้งานได้แล้ว (ให้ worker เริ่ม cycle ใหม่ตั้งแต่ต้นได้เลย)
    """
    now = time.time()
    last = _MUMU_LAST_RESTART.get(serial, 0.0)
    if now - last < OFFLINE_RESTART_COOLDOWN:
        # log ครั้งเดียวต่อรอบ cooldown (ไม่งั้นจะขึ้นซ้ำทุก 10 วิ)
        if _MUMU_COOLDOWN_LOGGED.get(serial) != last:
            _MUMU_COOLDOWN_LOGGED[serial] = last
            gui_log(serial, f"รีสตาร์ทไปแล้วแต่ยังไม่กลับมา — รอ cooldown "
                            f"{OFFLINE_RESTART_COOLDOWN}s ก่อนสั่งใหม่", step="Restart Cooldown")
        return False

    idx = mumu_index_for_serial(serial)
    if idx is None:
        gui_log(serial, "❌ หา MuMu index ของเครื่องนี้ไม่เจอ — ไม่สั่ง restart "
                        "(กันรีสตาร์ทผิดเครื่อง) เช็ค MuMuManager info -v all",
                step="Restart Fail", status="error")
        return False

    with _MUMU_RESTART_LOCK:
        gap = _MIN_RESTART_GAP - (time.time() - _MUMU_LAST_BOOT_TS[0])
        if gap > 0:
            time.sleep(gap)   # เว้นระยะจากเครื่องก่อนหน้า — กันบูตพร้อมกันจนโฮสต์แขวน
        _MUMU_LAST_RESTART[serial] = time.time()
        _MUMU_LAST_BOOT_TS[0] = time.time()

        gui_log(serial, f"🔄 offline นานเกิน {OFFLINE_RESTART_AFTER}s → restart MuMu idx={idx} "
                        f"(เฉพาะเครื่องนี้)...", step="MuMu Restart", status="stuck")
        ok_s, out_s = mumu_control(idx, "shutdown")
        gui_log(serial, f"  shutdown → {out_s[:120] if out_s else ('ok' if ok_s else 'fail')}", step="MuMu Restart")
        time.sleep(10)   # ให้ instance ปิดสนิทก่อนเปิดใหม่
        ok_l, out_l = mumu_control(idx, "launch")
        gui_log(serial, f"  launch → {out_l[:120] if out_l else ('ok' if ok_l else 'fail')}", step="MuMu Restart")

    gui_log(serial, f"⏳ รอ {serial} บูตกลับมา (สูงสุด {OFFLINE_BOOT_WAIT}s)...", step="MuMu Boot")
    if not wait_device_online(serial, timeout=OFFLINE_BOOT_WAIT, mumu_index=idx):
        gui_log(serial, "❌ บูตกลับไม่สำเร็จภายในเวลา — จะลองใหม่รอบหน้า", step="MuMu Boot Fail", status="error")
        return False

    # บูตใหม่แล้ว root_permission อาจกลับเป็นค่าเดิม → เปิด root ให้ก่อนเริ่มงาน
    try:
        if USE_MUMU_ROOT:
            mumu_set_root(idx, True)
            time.sleep(2)
    except Exception:
        pass

    gui_log(serial, "✅ MuMu กลับมาแล้ว — เริ่มกระบวนการใหม่ตั้งแต่ต้น", step="MuMu Boot OK", status="working")
    return True

def su_wrap(cmd):
    """wrap คำสั่ง shell ด้วย su -c ถ้าตั้ง USE_SU"""
    return f"su -c '{cmd}'" if USE_SU else cmd

def _adb_host(serial, args, timeout=30):
    """เรียกคำสั่ง adb host-side (เช่น root/unroot/wait-for-device)"""
    kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    cmd = [adb_path, "-s", serial] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, **kwargs)
    except Exception as e:
        gui_log(serial, f"adb {' '.join(args)} error: {e}", step="Root Error")
        return None

def is_root(device):
    """เช็คว่า adb shell เป็น root จริงไหม (uid=0) — ถ้า USE_SU เช็คผ่าน su"""
    try:
        out = device.shell(su_wrap("id") if USE_SU else "id")
        return "uid=0" in out
    except Exception:
        return False

def enable_root(device):
    """เปิด root (MuMu: root_permission=true, live ไม่ต้อง restart)"""
    serial = device.serial
    if USE_MUMU_ROOT:
        # พยายามดึง index จาก instance ที่คุยผ่าน adb port
        if not SERIAL_TO_INDEX:
            try:
                for idx, s in get_mumu_instances():
                    SERIAL_TO_INDEX[s] = idx
            except Exception:
                pass
        idx = SERIAL_TO_INDEX.get(serial, MUMU_INDEX)
        gui_log(serial, f"เปิด root (MuMu idx={idx} root_permission=true)...", step="Root Enable")
        mumu_set_root(idx, True)
        time.sleep(1)
    else:
        gui_log(serial, "เปิด root (adb root)...", step="Root Enable")
        r = _adb_host(serial, ["root"])
        if r is not None:
            msg = (r.stdout or "").strip() or (r.stderr or "").strip()
            if msg:
                gui_log(serial, f"  {msg}", step="Root Msg")
        _adb_host(serial, ["wait-for-device"], timeout=30)
        time.sleep(ROOT_TOGGLE_WAIT)
    if is_root(device):
        gui_log(serial, "  ✓ root พร้อม (uid=0)", step="Root OK")
    else:
        gui_log(serial, "  ✗ su ไม่ทำงาน! (เช็ค MUMU_INDEX / root ของ MuMu)", step="Root Fail")
    return device

def disable_root(device):
    """ปิด root (MuMu: root_permission=false, live ไม่ต้อง restart)"""
    serial = device.serial
    if USE_MUMU_ROOT:
        if not SERIAL_TO_INDEX:
            try:
                for idx, s in get_mumu_instances():
                    SERIAL_TO_INDEX[s] = idx
            except Exception:
                pass
        idx = SERIAL_TO_INDEX.get(serial, MUMU_INDEX)
        gui_log(serial, f"ปิด root (MuMu idx={idx} root_permission=false)...", step="Root Disable")
        mumu_set_root(idx, False)
        time.sleep(1)
    else:
        gui_log(serial, "ปิด root (adb unroot)...", step="Root Disable")
        r = _adb_host(serial, ["unroot"])
        if r is not None:
            msg = (r.stdout or "").strip() or (r.stderr or "").strip()
            if msg:
                gui_log(serial, f"  {msg}", step="Root Msg")
        _adb_host(serial, ["wait-for-device"], timeout=30)
        time.sleep(ROOT_TOGGLE_WAIT)
        if is_root(device):
            gui_log(serial, "  ✗ ยังเป็น root อยู่", step="Root Fail")
        else:
            gui_log(serial, "  ✓ ปิด root แล้ว (uid≠0)", step="Root OK")
    return device

def check_and_click_fixback(device, img, serial, check_g1=True):
    """
    เช็คและกด fixback-gacha1.bmp และ fixback-gacha2.bmp ซ้ำๆ จนกว่าจะหายไป
    คืนค่า (img ล่าสุด, force_gacha4)
    """
    global in_new_gacha_loop
    if in_new_gacha_loop:
        pts_fg = img_search(img, os.path.join(IMG_DIR, "fixgachanew1.bmp"))
        if pts_fg:
            pts_fs = img_search(img, os.path.join(IMG_DIR, "fixswap.bmp"))
            if pts_fs:
                x_click, y_click = pts_fs[0]
                click_name = "fixswap.bmp"
            else:
                x_click, y_click = pts_fg[0]
                click_name = "fixgachanew1.bmp"
            device.shell(f"input swipe {x_click} {y_click} {x_click} {y_click} 100")
            gui_log(serial, f"fixgachanew1.bmp detected! Clicking {click_name} immediately...", step="FixGachaNew Instant")
            time.sleep(4)
            raise ResetGachaException()

    force_gacha4 = False
    if not check_g1:
        return img, force_gacha4

    found_g1 = False
    click_count = 0
    while True:
        pts = img_search(img, os.path.join(IMG_DIR, "fixback-gacha1.bmp"))
        if pts:
            click_count += 1
            if click_count > 2:
                gui_log(serial, "Clicking fixback-gacha1.bmp > 2 times! Forcing Gacha4.", step="FixBack1-Limit")
                force_gacha4 = True
                break
            x, y = pts[0]
            device.shell(f"input swipe {x} {y} {x} {y} 100")
            gui_log(serial, f"Clicking fixback-gacha1.bmp... (count: {click_count})", step="FixBack1")
            time.sleep(0.5)
            found_g1 = True
            img = get_screen_capture(device)
            if img is None:
                break
        else:
            break
            
    # 2. เช็ค fixback-gacha2.bmp (จะเช็ค/กดเฉพาะเมื่อเจอ fixback-gacha1 มาก่อนเท่านั้น และไม่ได้ force_gacha4)
    if found_g1 and not force_gacha4:
        while True:
            pts = img_search(img, os.path.join(IMG_DIR, "fixback-gacha2.bmp"))
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, "Clicking fixback-gacha2.bmp...", step="FixBack2")
                time.sleep(0.5)
                img = get_screen_capture(device)
                if img is None:
                    break
            else:
                break
            
    return img, force_gacha4

# ═════════════════════════════════════════════════════════════════════════════
# Screen / image
# ═════════════════════════════════════════════════════════════════════════════
# Throttle: จำกัดความถี่ screencap ต่อเครื่อง — กัน loop ที่เรียกถี่เกินไปยิงใส่ MuMu
# จนค้าง (ANR). ไม่ว่าจะเรียกถี่แค่ไหน แต่ละเครื่องจะถูกแคปไม่เกิน ~1/_MIN_SCREENCAP_INTERVAL ครั้ง/วิ
_MIN_SCREENCAP_INTERVAL = SCREENCAP_INTERVAL   # วินาที (0.25 ≈ 4 ครั้ง/วิ/เครื่อง) — ปรับได้สดจาก config
_LAST_SCREENCAP_TS = {}

# ── เพดานรวมทั้งระบบ: แคปจอพร้อมกันได้กี่จอ ────────────────────────────
# throttle ข้างบนเป็น "ต่อจอ" — เปิด 72 จอก็ยังยิงพร้อมกันได้ 72 สาย
# 1 เฟรม = raw RGBA ไม่บีบอัด (540x960 ≈ 2 MB) วิ่งผ่าน adb server process เดียว
# → burst พร้อมกันเยอะๆ ทำให้ adb server ตอบไม่ทัน จอโดน mark เป็น offline
# ตัวนี้คุมให้แคปพร้อมกันได้ไม่เกิน N จอ ที่เหลือรอคิว (ปกติรอไม่ถึงวินาที)
class _DynamicGate:
    """จำกัดจำนวนงานที่วิ่งพร้อมกัน — ปรับเพดานได้สดๆ ระหว่างรัน
    (threading.Semaphore ปกติเปลี่ยนค่าไม่ได้ เลยทำเอง)  limit <= 0 = ไม่จำกัด"""
    def __init__(self, limit):
        self._cv = threading.Condition()
        self._limit = int(limit)
        self._active = 0

    def set_limit(self, limit):
        limit = int(limit)
        with self._cv:
            if limit != self._limit:
                self._limit = limit
                self._cv.notify_all()

    def acquire(self, timeout=20.0):
        """คืน True ถ้าจองคิวได้ (ต้อง release), False ถ้ารอนานเกิน timeout
        (รอนานเกิน = ปล่อยผ่านไปเลย ดีกว่าให้บอททั้งตัวค้าง)"""
        deadline = time.time() + timeout
        with self._cv:
            if self._limit <= 0:
                return False   # ไม่จำกัด → ไม่ต้องนับ ไม่ต้อง release
            while self._active >= self._limit:
                remain = deadline - time.time()
                if remain <= 0:
                    return False
                self._cv.wait(remain)
            self._active += 1
            return True

    def release(self):
        with self._cv:
            if self._active > 0:
                self._active -= 1
            self._cv.notify()

_SCREENCAP_GATE = _DynamicGate(SCREENCAP_MAX_CONCURRENT)

# Launch cooldown: ห้าม cold-start เกมถี่เกินไป/เครื่อง — cold-start คือคำสั่งที่หนัก
# ที่สุดสำหรับ MuMu (โหลด asset + init 3D ใหม่) ถ้า relaunch ซ้อนถี่ๆ → ANR
_MIN_LAUNCH_INTERVAL = 20.0             # วินาที — เว้นระยะ cold-start ขั้นต่ำ/เครื่อง
_LAST_LAUNCH_TS = {}

# Global cold-start gate: เว้นระยะ cold-start ระหว่าง "คนละเครื่อง" ด้วย — กันหลาย instance
# บูต/โหลด asset พร้อมกันจน CPU/GPU/RAM ของโฮสต์แขวนทั้งเครื่อง (Windows ANR ทั้งวง)
_MIN_GLOBAL_LAUNCH_GAP = 6.0            # วินาที — ระยะขั้นต่ำระหว่าง cold-start ของทุกเครื่อง
_LAUNCH_GATE_LOCK = threading.Lock()
_GLOBAL_LAST_LAUNCH_TS = [0.0]

def launch_game(device, settle=14.0):
    """Cold-start เกมแบบมี cooldown ต่อเครื่อง + global gate ทั้งระบบ —
    กัน relaunch ซ้อนถี่/หลายเครื่องบูตพร้อมกันจน MuMu ค้าง (ANR)."""
    serial = device.serial
    elapsed = time.time() - _LAST_LAUNCH_TS.get(serial, 0.0)
    if elapsed < _MIN_LAUNCH_INTERVAL:
        wait = _MIN_LAUNCH_INTERVAL - elapsed
        gui_log(serial, f"Launch cooldown — waiting {wait:.0f}s before relaunch...", step="Launch CD")
        time.sleep(wait)
    # global gate: เว้นระยะ cold-start ระหว่างทุกเครื่องอย่างน้อย _MIN_GLOBAL_LAUNCH_GAP วิ
    # (ถือ lock ระหว่างเว้นระยะ → คิว cold-start ของเครื่องอื่นไว้ กันบูตพร้อมกันจนโฮสต์แขวน)
    with _LAUNCH_GATE_LOCK:
        gap = _MIN_GLOBAL_LAUNCH_GAP - (time.time() - _GLOBAL_LAST_LAUNCH_TS[0])
        if gap > 0:
            time.sleep(gap)
        device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
        _GLOBAL_LAST_LAUNCH_TS[0] = time.time()
    now = time.time()
    _LAST_LAUNCH_TS[serial] = now
    DEVICE_LAST_GAME_CHECK[serial] = now
    if settle > 0:
        time.sleep(settle)

def fast_screencap(device):
    return _fast_screencap_raw(device)

def _fast_screencap_raw(device):
    # ── per-device throttle ──
    # (นอนรอ "นอกคิว" — ไม่งั้นจะกินโควตาเพดานรวมทั้งที่ยังไม่ได้ทำอะไร)
    serial = device.serial
    last = _LAST_SCREENCAP_TS.get(serial, 0.0)
    wait = _MIN_SCREENCAP_INTERVAL - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _LAST_SCREENCAP_TS[serial] = time.time()

    # ── เพดานรวมทั้งระบบ: จองคิวก่อนคุยกับ adb จริง ──
    _gate_held = _SCREENCAP_GATE.acquire()
    try:
        return _screencap_io(device)
    finally:
        if _gate_held:
            _SCREENCAP_GATE.release()

def _screencap_io(device):
    """ส่วนที่คุยกับ adb จริง (ถูกคุมด้วย _SCREENCAP_GATE จากตัวเรียก)"""
    conn = None
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
            expected_size = w * h * 4
            if len(raw) >= 12 + expected_size:
                gray = cv2.cvtColor(
                    np.frombuffer(raw, dtype=np.uint8, offset=12, count=expected_size).reshape((h, w, 4)),
                    cv2.COLOR_RGBA2GRAY
                )
                if SCREENCAP_SCALE != 1.0:
                    gray = cv2.resize(gray,
                                      (int(w * SCREENCAP_SCALE), int(h * SCREENCAP_SCALE)),
                                      interpolation=cv2.INTER_LINEAR)
                return gray
    except Exception:
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # Fallback
    try:
        raw = device.screencap()
        if raw:
            gray = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
            if gray is not None and SCREENCAP_SCALE != 1.0:
                gray = cv2.resize(gray, None, fx=SCREENCAP_SCALE, fy=SCREENCAP_SCALE,
                                  interpolation=cv2.INTER_LINEAR)
            return gray
    except Exception:
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

FIXCLEAR_FIRST_SEEN = {}

def fixout_back_spam_until_cancel(device, serial):
    """เจอ fixout (popup บังจอ) → กด Back รัวๆ จนกว่าจะเจอ cancel.bmp → คลิก → ค่อยหยุด
    ไม่มี timeout (ทางออกเดียว = เจอ cancel หรือกดปุ่ม reset เอง)
    ใช้ fast_screencap ล้วนๆ — ห้ามเรียก get_screen_capture ในนี้ (กันวนซ้อนตัวเอง)"""
    gui_log(serial, "fixout detected → Spamming Back until cancel.bmp...", step="FixOut Back")
    while True:
        check_device_reset(serial)
        device.shell("input keyevent 4")   # KEYCODE_BACK
        time.sleep(1.0)
        img_bs = fast_screencap(device)
        if img_bs is not None:
            pts_c = img_search(img_bs, os.path.join(IMG_DIR, "cancel.bmp"))
            if pts_c:
                x_c, y_c = pts_c[0]
                device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                gui_log(serial, f"cancel.bmp found — clicked ({x_c},{y_c}), stop Back spam", step="FixOut Cancel")
                time.sleep(1.5)
                # กด cancel แล้ว = อยู่หน้าเมนูหลัก (เลยจุด checkpointlogin ไปแล้ว)
                # → ตั้ง flag ให้ลูป play8 break ข้ามไปทำ step ถัดไปทันที (ไม่ต้องรอ checkpoint ที่ไม่มีวันโผล่)
                DEVICE_FIXOUT_CANCEL_DONE[serial] = True
                _FIXOUT_LAST_DONE[serial] = time.time()   # เริ่ม cooldown — กดรอบเดียวแล้วเว้น ไม่ยิงซ้ำรัวๆ
                return

def trigger_restart_from_play8(device, serial, original_name, reason="stuck"):
    """เริ่มใหม่ "ตั้งแต่ play8" (เปิดเกมเดิม เก็บ login ไม่ push ซ้ำ)
    วนซ้ำไปเรื่อยๆ จนกว่าอาการ (fixclear/ค้าง) จะหายไป — ไม่ส่ง file-error/ไม่ยอมแพ้
    (ฟังก์ชันนี้ 'ไม่ return' เสมอ)."""
    on, cnt = DEVICE_RESTART_PLAY8_COUNT.get(serial, (None, 0))
    cnt = cnt + 1 if on == original_name else 1
    DEVICE_RESTART_PLAY8_COUNT[serial] = (original_name, cnt)
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    if original_name:
        DEVICE_RESTART_PLAY8[serial] = (os.path.join(INPUT_DIR, original_name), original_name)
    gui_log(serial, f"Restarting from play8 (attempt {cnt}, {reason}, keep login, no re-push)...", step="Restart play8", status="working")
    raise RestartFromPlay8Exception(f"restart from play8 — {reason}")

# ═════════════════════════════════════════════════════════════════════════════
# CPU affinity balancer (เครื่อง 2 socket / NUMA / >64 logical processors)
# ─────────────────────────────────────────────────────────────────────────────
# บนเครื่อง 2 socket (เช่น Dual Xeon = 72 logical → Windows แบ่งเป็น 2 processor group)
# Windows จะจับทุก process ไว้ group 0 กลุ่มเดียว → core ของ socket 0 พีค 100% ส่วน
# socket 1 นั่งว่าง → หน้าต่าง MuMu ไม่ได้ CPU ทันจนค้าง (Not Responding) ทั้งที่ CPU
# "รวม" เหลือเพียบ. ตัวนี้เกลี่ย process ของ MuMu แบบ round-robin ข้ามทุก group ให้ใช้
# ทั้ง 2 socket จริงๆ (ทำงานเฉพาะเครื่องที่มี >1 processor group เท่านั้น)
CPU_AFFINITY_BALANCE = True       # เปิด/ปิด (config.py override ได้)
_CPU_BALANCE_INTERVAL = 45.0      # วิ — เกลี่ยซ้ำทุกกี่วิ (จับ instance/threads ที่เพิ่งเกิด)
_cpu_balancer_started = [False]

if os.name == 'nt':
    import ctypes as _ct
    from ctypes import wintypes as _wt

    class _GROUP_AFFINITY(_ct.Structure):
        _fields_ = [("Mask", _ct.c_ulonglong), ("Group", _wt.WORD),
                    ("Reserved", _wt.WORD * 3)]

    class _THREADENTRY32(_ct.Structure):
        _fields_ = [("dwSize", _wt.DWORD), ("cntUsage", _wt.DWORD),
                    ("th32ThreadID", _wt.DWORD), ("th32OwnerProcessID", _wt.DWORD),
                    ("tpBasePri", _wt.LONG), ("tpDeltaPri", _wt.LONG),
                    ("dwFlags", _wt.DWORD)]

    class _PROCESSENTRY32W(_ct.Structure):
        _fields_ = [("dwSize", _wt.DWORD), ("cntUsage", _wt.DWORD),
                    ("th32ProcessID", _wt.DWORD),
                    ("th32DefaultHeapID", _ct.POINTER(_ct.c_ulong)),
                    ("th32ModuleID", _wt.DWORD), ("cntThreads", _wt.DWORD),
                    ("th32ParentProcessID", _wt.DWORD), ("pcPriClassBase", _wt.LONG),
                    ("dwFlags", _wt.DWORD), ("szExeFile", _wt.WCHAR * 260)]

    _k32 = _ct.WinDLL("kernel32", use_last_error=True)
    _k32.CreateToolhelp32Snapshot.restype = _wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [_wt.DWORD, _wt.DWORD]
    _k32.Process32FirstW.argtypes = [_wt.HANDLE, _ct.POINTER(_PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [_wt.HANDLE, _ct.POINTER(_PROCESSENTRY32W)]
    _k32.Thread32First.argtypes = [_wt.HANDLE, _ct.POINTER(_THREADENTRY32)]
    _k32.Thread32Next.argtypes = [_wt.HANDLE, _ct.POINTER(_THREADENTRY32)]
    _k32.OpenThread.restype = _wt.HANDLE
    _k32.OpenThread.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    _k32.OpenProcess.restype = _wt.HANDLE
    _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    _k32.SetThreadGroupAffinity.argtypes = [_wt.HANDLE, _ct.POINTER(_GROUP_AFFINITY),
                                            _ct.POINTER(_GROUP_AFFINITY)]
    _k32.SetThreadGroupAffinity.restype = _wt.BOOL
    _k32.CloseHandle.argtypes = [_wt.HANDLE]
    _k32.GetActiveProcessorGroupCount.restype = _wt.WORD
    _k32.GetActiveProcessorCount.restype = _wt.DWORD
    _k32.GetActiveProcessorCount.argtypes = [_wt.WORD]
    # SetProcessDefaultCpuSetMasks (Win10 1809+) — ให้ thread ใหม่ของ process ไปเกิดถูก group ด้วย
    _has_defcpuset = hasattr(_k32, "SetProcessDefaultCpuSetMasks")
    if _has_defcpuset:
        _k32.SetProcessDefaultCpuSetMasks.argtypes = [_wt.HANDLE,
                                                      _ct.POINTER(_GROUP_AFFINITY), _wt.USHORT]
        _k32.SetProcessDefaultCpuSetMasks.restype = _wt.BOOL

    _TH32CS_SNAPPROCESS = 0x00000002
    _TH32CS_SNAPTHREAD  = 0x00000004
    _INVALID_HANDLE = _wt.HANDLE(-1).value
    _THREAD_SET_INFORMATION = 0x0020
    _THREAD_QUERY_INFORMATION = 0x0040
    _PROCESS_SET_LIMITED_INFORMATION = 0x2000

    def _iter_mumu_pids():
        snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        out = []
        if not snap or snap == _INVALID_HANDLE:
            return out
        try:
            pe = _PROCESSENTRY32W(); pe.dwSize = _ct.sizeof(_PROCESSENTRY32W)
            ok = _k32.Process32FirstW(snap, _ct.byref(pe))
            while ok:
                if pe.szExeFile.lower().startswith("mumu"):
                    out.append(pe.th32ProcessID)
                ok = _k32.Process32NextW(snap, _ct.byref(pe))
        finally:
            _k32.CloseHandle(snap)
        return out

    def _thread_map(pids):
        wanted = set(pids)
        m = {p: [] for p in wanted}
        snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
        if not snap or snap == _INVALID_HANDLE:
            return m
        try:
            te = _THREADENTRY32(); te.dwSize = _ct.sizeof(_THREADENTRY32)
            ok = _k32.Thread32First(snap, _ct.byref(te))
            while ok:
                owner = te.th32OwnerProcessID
                if owner in wanted:
                    m[owner].append(te.th32ThreadID)
                ok = _k32.Thread32Next(snap, _ct.byref(te))
        finally:
            _k32.CloseHandle(snap)
        return m

    def _group_masks():
        n = _k32.GetActiveProcessorGroupCount() or 1
        masks = []
        for g in range(n):
            cnt = _k32.GetActiveProcessorCount(g) or 1
            mask = 0xFFFFFFFFFFFFFFFF if cnt >= 64 else ((1 << cnt) - 1)
            masks.append((g, mask))
        return masks

    def _set_process_default_group(pid, group, mask):
        if not _has_defcpuset:
            return
        h = _k32.OpenProcess(_PROCESS_SET_LIMITED_INFORMATION, False, pid)
        if not h:
            return
        try:
            ga = _GROUP_AFFINITY(); ga.Mask = mask; ga.Group = group
            _k32.SetProcessDefaultCpuSetMasks(h, _ct.byref(ga), 1)
        except Exception:
            pass
        finally:
            _k32.CloseHandle(h)

    def _pin_threads(tids, group, mask):
        pinned = 0
        for tid in tids:
            h = _k32.OpenThread(_THREAD_SET_INFORMATION | _THREAD_QUERY_INFORMATION, False, tid)
            if not h:
                continue
            try:
                ga = _GROUP_AFFINITY(); ga.Mask = mask; ga.Group = group
                if _k32.SetThreadGroupAffinity(h, _ct.byref(ga), None):
                    pinned += 1
            except Exception:
                pass
            finally:
                _k32.CloseHandle(h)
        return pinned

    def balance_mumu_affinity():
        """เกลี่ย process ของ MuMu ข้ามทุก processor group (socket) แบบ round-robin.
        คืน (จำนวน process ที่จัด, จำนวน group). group เดียว = ไม่ทำอะไร."""
        masks = _group_masks()
        if len(masks) <= 1:
            return 0, len(masks)
        pids = sorted(_iter_mumu_pids())
        if not pids:
            return 0, len(masks)
        tmap = _thread_map(pids)
        done = 0
        for i, pid in enumerate(pids):
            group, mask = masks[i % len(masks)]
            _set_process_default_group(pid, group, mask)
            if _pin_threads(tmap.get(pid, ()), group, mask) > 0:
                done += 1
        return done, len(masks)
else:
    def balance_mumu_affinity():
        return 0, 1

def _cpu_balancer_loop():
    try:
        from config import CPU_AFFINITY_BALANCE as _cfg_on
        enabled = bool(_cfg_on)
    except Exception:
        enabled = CPU_AFFINITY_BALANCE
    if not enabled:
        return
    logged = False
    while True:
        try:
            done, groups = balance_mumu_affinity()
            if not logged:
                if groups <= 1:
                    msg = "⚙️ CPU balancer: เครื่องมี processor group เดียว (single socket) — ข้าม"
                else:
                    msg = f"⚙️ CPU balancer: กระจาย MuMu {done} process ข้าม {groups} group/socket (ทุก {int(_CPU_BALANCE_INTERVAL)} วิ)"
                cprint(msg)
                if gui_instance:
                    _gui_queue.put(('log', msg))
                logged = True
                if groups <= 1:
                    return   # single group → เลิกลูป ไม่ต้องวนเปล่าๆ
        except Exception:
            pass
        time.sleep(_CPU_BALANCE_INTERVAL)

def start_cpu_balancer():
    """สตาร์ต daemon เกลี่ย CPU affinity ของ MuMu ข้าม socket (เรียกครั้งเดียวตอนบอทเริ่ม)"""
    if _cpu_balancer_started[0]:
        return
    _cpu_balancer_started[0] = True
    threading.Thread(target=_cpu_balancer_loop, daemon=True).start()

def get_screen_capture(device):
    global in_new_gacha_loop   # ประกาศหัวฟังก์ชัน (มีทั้งจุดอ่าน fixout-skip และจุดใช้ใน fixgachanew)
    try:
        # เช็คเกมออนอยู่หรือไม่ (ทุก 30 วิ)
        if not is_game_running(device):
            # เกมตาย: ถ้าผ่าน login แล้ว (อยู่ช่วง box/gacha) → flow เดิมไม่ตรงกับเกมที่เพิ่งเปิดใหม่
            #   → restart ตั้งแต่ play8 (เก็บ login เดิม ไม่ push ซ้ำ) แทน relaunch แล้ววิ่งต่อผิดเฟสจนค้าง
            _on_gsc = DEVICE_FILE_ASSIGNMENTS.get(device.serial)
            if DEVICE_PAST_LOGIN.get(device.serial) and _on_gsc:
                gui_log(device.serial, "⚠️ เกมไม่รัน (หลัง login) → restart ตั้งแต่ play8", step="Relaunch")
                trigger_restart_from_play8(device, device.serial, _on_gsc, reason="เกมตาย/relaunch หลัง login")
            gui_log(device.serial, "⚠️ Game not running! Relaunching...", step="Relaunch")
            launch_game(device, settle=14)
            DEVICE_LAST_GAME_CHECK[device.serial] = time.time()

        img = fast_screencap(device)
        if img is None:
            return None
        
        if img is not None:
            # === fixnet floating check ===
            fn_pts = img_search(img, _P['fixnet'])
            if fn_pts:
                gui_log(device.serial, "Floating: fixnet.bmp found! Clicking...", step="Fix Net")
                x, y = fn_pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                time.sleep(1)

                gui_log(device.serial, "Waiting for fixnet1.bmp (up to 10s)...", step="Fix Net 1")
                deadline_fn1 = time.time() + 10
                while time.time() < deadline_fn1:
                    img_fn1 = fast_screencap(device)
                    if img_fn1 is not None:
                        fn1_pts = img_search(img_fn1, _P['fixnet1'])
                        if fn1_pts:
                            x_fn1, y_fn1 = fn1_pts[0]
                            device.shell(f"input swipe {x_fn1} {y_fn1} {x_fn1} {y_fn1} 100")
                            gui_log(device.serial, "Clicked fixnet1.bmp!", step="Fix Net 1")
                            time.sleep(1)
                            break
                    time.sleep(0.5)

                img = fast_screencap(device)
                if img is None:
                    return None

            # === fixnet1 standalone floating check ===
            # เจอ fixnet1 ลอยเดี่ยวๆ (ไม่ได้มาจาก flow fixnet ข้างบน หรือกดแล้วไม่หาย)
            # → ปิดแอพแล้วเข้าใหม่ไฟล์เดิมเฉยๆ (ไม่ย้ายไฟล์/ไม่ push ซ้ำ ไม่มีอะไรเพิ่ม)
            if img_search(img, _P['fixnet1']):
                time.sleep(1.5)   # กันจังหวะ popup กำลังปิดตัวเองพอดี → เช็คซ้ำให้ชัวร์ก่อน
                img_fn1re = fast_screencap(device)
                if img_fn1re is not None and img_search(img_fn1re, _P['fixnet1']):
                    serial_fn1 = device.serial
                    original_name = DEVICE_FILE_ASSIGNMENTS.get(serial_fn1)
                    gui_log(serial_fn1, "fixnet1 detected! Closing app & re-entering (same file)...", step="Fix Net 1")
                    if original_name:
                        trigger_restart_from_play8(device, serial_fn1, original_name, reason="fixnet1")
                    device.shell("am force-stop jp.konami.pesam")
                    time.sleep(1)
                    raise DeviceResetException("fixnet1 detected (no file)")
                if img_fn1re is not None:
                    img = img_fn1re

            # === fixneterror floating check ===
            # เจอ fixneterror (เน็ตเออเรอร์) → ปิดแอพแล้วเข้าใหม่ไฟล์เดิมเฉยๆ (แค่นั้น)
            if img_search(img, os.path.join(IMG_DIR, "fixneterror.bmp")):
                time.sleep(1.5)   # กันจังหวะ popup กำลังปิดตัวเองพอดี → เช็คซ้ำให้ชัวร์ก่อน
                img_nere = fast_screencap(device)
                if img_nere is not None and img_search(img_nere, os.path.join(IMG_DIR, "fixneterror.bmp")):
                    serial_ne = device.serial
                    original_name = DEVICE_FILE_ASSIGNMENTS.get(serial_ne)
                    gui_log(serial_ne, "fixneterror detected! Closing app & re-entering (same file)...", step="Fix Net Error")
                    if original_name:
                        trigger_restart_from_play8(device, serial_ne, original_name, reason="fixneterror")
                    device.shell("am force-stop jp.konami.pesam")
                    time.sleep(1)
                    raise DeviceResetException("fixneterror detected (no file)")
                if img_nere is not None:
                    img = img_nere

            # === fixtip floating check ===
            pts1 = img_search(img, os.path.join(GETQUEST_IMG_DIR, "fixtip1.bmp")) if GETQUEST == 1 else None
            if pts1:
                gui_log(device.serial, "fixtip1.bmp detected! Looking for fixtip2.bmp...", step="Fix Tip")
                pts2 = img_search(img, os.path.join(GETQUEST_IMG_DIR, "fixtip2.bmp"))
                if pts2:
                    x2, y2 = pts2[0]
                    device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                    gui_log(device.serial, f"Clicked fixtip2 at ({x2}, {y2})", step="Fix Tip")
                    time.sleep(1.5)
                    img = fast_screencap(device)
                    if img is None:
                        return None

            # === backquest3 floating check ===
            if GQ_ACTIVE and img is not None:
                bq_pts = img_search(img, os.path.join(GETQUEST_IMG_DIR, "backquest3.bmp"))
                if bq_pts:
                    gui_log(device.serial, "backquest3 detected! Performing back-spam rescue...", step="Back Rescue")
                    # Spam back until cancel found
                    while True:
                        device.shell("input keyevent 4")
                        time.sleep(0.4)
                        img_back = fast_screencap(device)
                        if img_back is not None:
                            pts_c = img_search(img_back, os.path.join(IMG_DIR, "cancel.bmp"))
                            if pts_c:
                                xc, yc = pts_c[0]
                                gui_log(device.serial, f"cancel found — clicking ({xc},{yc})", step="Back Rescue")
                                click_cancel_until_gone(device, device.serial, xc, yc, step="Back Rescue")
                                break
                    # After cancel clicked, wait/click fixbackquest1
                    gui_log(device.serial, "Waiting/Clicking fixbackquest1.bmp...", step="Back Rescue")
                    while True:
                        img_fb = fast_screencap(device)
                        if img_fb is not None:
                            pts_fb = img_search(img_fb, os.path.join(GETQUEST_IMG_DIR, "fixbackquest1.bmp"))
                            if pts_fb:
                                xf, yf = pts_fb[0]
                                device.shell(f"input swipe {xf} {yf} {xf} {yf} 100")
                                gui_log(device.serial, "Clicked fixbackquest1.bmp", step="Back Rescue")
                                time.sleep(1.5)
                                break
                        time.sleep(0.5)
                        
                    raise RestartFromQuest8Exception("backquest3 detected")

            # === fixdow1 floating check (download/update popup) ===
            #   เจอ fixdow1 → clear app (force-stop) แล้วเข้าใหม่ (relaunch)
            #   จากนั้นหา fixdow2 ต่อ (timeout 30s) เจอก็คลิก, ไม่เจอข้าม ทำงานต่อปกติ
            fixdow1_pts = img_search(img, os.path.join(IMG_DIR, "fixdow1.bmp"))
            if fixdow1_pts:
                gui_log(device.serial, "Floating: fixdow1 found! Clearing app & relaunching...", step="Fix Download")
                device.shell("am force-stop jp.konami.pesam")
                time.sleep(2)
                launch_game(device, settle=8)

                gui_log(device.serial, "Waiting fixdow2 (up to 30s)...", step="Fix Download 2")
                deadline_fd2 = time.time() + 30
                found_fd2 = False
                while time.time() < deadline_fd2:
                    img_fd2 = fast_screencap(device)
                    if img_fd2 is not None:
                        fd2_pts = img_search(img_fd2, os.path.join(IMG_DIR, "fixdow2.bmp"))
                        if fd2_pts:
                            xd, yd = fd2_pts[0]
                            device.shell(f"input swipe {xd} {yd} {xd} {yd} 100")
                            gui_log(device.serial, f"Clicked fixdow2 at ({xd},{yd})", step="Fix Download 2")
                            time.sleep(2)
                            found_fd2 = True
                            break
                    time.sleep(0.5)
                if not found_fd2:
                    gui_log(device.serial, "fixdow2 not found in 30s — skipping, continue normally.", step="Fix Download Skip")

                img = fast_screencap(device)
                if img is None:
                    return None

            dl_pts = img_search(img, os.path.join(IMG_DIR, "download.bmp"))
            if dl_pts:
                gui_log(device.serial, "Floating: download.bmp found! Clicking...", step="Floating")
                x, y = dl_pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")

            # === download-new floating check (เช็คตลอดทุกเฟรม) ===
            #   เจอ download-new1 (popup ดาวน์โหลด/อัปเดต) → กดปุ่ม download-new2
            if img_search(img, os.path.join(IMG_DIR, "download-new1.bmp")):
                dn2_pts = img_search(img, os.path.join(IMG_DIR, "download-new2.bmp"))
                if dn2_pts:
                    x, y = dn2_pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    gui_log(device.serial, f"download-new1 found! Clicked download-new2 at ({x},{y})", step="Download New")
                    time.sleep(1)

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
                        _safe_copy(file_path, dest_path)
                        os.remove(file_path)
                        gui_log(device.serial, f"✅ Sorted (Sell): {original_name} -> {LOGIN_FAILED_DIR}", step="Sell Sorted")
                
                raise SellScreenException("sell.bmp detected")

            # === failed1/failed2/failed3 floating check ===
            failed1_pts = img_search(img, os.path.join(IMG_DIR, "failed1.bmp"))
            failed2_pts = img_search(img, os.path.join(IMG_DIR, "failed2.bmp"))
            failed3_pts = img_search(img, os.path.join(IMG_DIR, "failed3.bmp"))
            if failed1_pts or failed2_pts or failed3_pts:
                found_name = "failed1.bmp" if failed1_pts else ("failed2.bmp" if failed2_pts else "failed3.bmp")
                gui_log(device.serial, f"🛑 Floating: {found_name} found! Force closing app and moving file to login-failed", step="Failed Detected")
                device.shell("am force-stop jp.konami.pesam")
                time.sleep(1)
                
                original_name = DEVICE_FILE_ASSIGNMENTS.get(device.serial)
                if original_name:
                    file_path = os.path.join(INPUT_DIR, original_name)
                    dest_path = os.path.join(LOGIN_FAILED_DIR, original_name)
                    if os.path.exists(file_path):
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        _safe_copy(file_path, dest_path)
                        os.remove(file_path)
                        gui_log(device.serial, f"✅ Sorted (Failed): {original_name} -> {LOGIN_FAILED_DIR}", step="Failed Sorted")
                
                raise SellScreenException(f"{found_name} detected")

            # เช็คเฉพาะ fixclear1.png (img/ root) เท่านั้น → ไฟล์เสีย ส่ง file-error
            fc_png = img_search(img, os.path.join(IMG_DIR, "fixclear1.png"), threshold=0.8)
            if fc_png:
                serial_fc = device.serial
                original_name = DEVICE_FILE_ASSIGNMENTS.get(serial_fc)

                # ── เจอ fixclear1.png = ไฟล์เสีย → clear app + ล้าง AUTH + ย้ายไป file-error → id ถัดไป ──
                gui_log(serial_fc, "fixclear1.png detected! Clearing app & moving file to file-error, next id...", step="Fix Clear Fail", status="error")
                device.shell("am force-stop jp.konami.pesam")
                device.shell("su -c 'rm -f /data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat'")
                device.shell("su -c 'rm -rf /data/data/jp.konami.pesam/files/SaveData/AUTH/*'")
                DEVICE_RESTART_PLAY8_COUNT.pop(serial_fc, None)
                DEVICE_RESTART_PLAY8.pop(serial_fc, None)
                if original_name:
                    fc_src  = os.path.join(INPUT_DIR, original_name)
                    fc_dest = os.path.join(FILE_ERROR_DIR, original_name)
                    if os.path.exists(fc_src):
                        try:
                            if os.path.exists(fc_dest):
                                os.remove(fc_dest)
                            _safe_copy(fc_src, fc_dest)
                            os.remove(fc_src)
                            gui_log(serial_fc, f"Moved {original_name} to file-error", step="Fix Clear Fail")
                        except Exception as e:
                            gui_log(serial_fc, f"Failed to move {original_name} to file-error: {e}", step="Fix Clear Fail")
                raise DeviceResetException("fixclear1.png — moved to file-error")

            # เช็ค updatenew1 ตลอด (ทุกเฟรม) → เจอ = clear app + ส่งไฟล์ไป file-error → หยิบ id ใหม่เลย
            un1_pts = img_search(img, os.path.join(IMG_DIR, "updatenew1.bmp"), threshold=0.8)
            if un1_pts:
                serial_un = device.serial
                original_name = DEVICE_FILE_ASSIGNMENTS.get(serial_un)
                gui_log(serial_un, "updatenew1 detected! Clearing app & moving file to file-error, next id...", step="UpdateNew Fail", status="error")
                device.shell("am force-stop jp.konami.pesam")
                device.shell("su -c 'rm -f /data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat'")
                device.shell("su -c 'rm -rf /data/data/jp.konami.pesam/files/SaveData/AUTH/*'")
                DEVICE_RESTART_PLAY8_COUNT.pop(serial_un, None)
                DEVICE_RESTART_PLAY8.pop(serial_un, None)
                if original_name:
                    un_src  = os.path.join(INPUT_DIR, original_name)
                    un_dest = os.path.join(FILE_ERROR_DIR, original_name)
                    if os.path.exists(un_src):
                        try:
                            if os.path.exists(un_dest):
                                os.remove(un_dest)
                            _safe_copy(un_src, un_dest)
                            os.remove(un_src)
                            gui_log(serial_un, f"Moved {original_name} to file-error", step="UpdateNew Fail")
                        except Exception as e:
                            gui_log(serial_un, f"Failed to move {original_name} to file-error: {e}", step="UpdateNew Fail")
                raise DeviceResetException("updatenew1 — moved to file-error")

            # fix0%.png / fixupdate.png → เกมค้าง 0% หรือขึ้นให้อัปเดต
            #   → ปิดแอพแล้วเข้าใหม่ด้วย "ไฟล์เดิม" (ไม่ย้ายไฟล์ ไม่ push ซ้ำ)
            fx_name = None
            if img_search(img, _P['fix0'], threshold=0.8):
                fx_name = "fix0%.png"
            elif img_search(img, _P['fixupdate'], threshold=0.8):
                fx_name = "fixupdate.png"
            if fx_name:
                serial_fx = device.serial
                on_fx = DEVICE_FILE_ASSIGNMENTS.get(serial_fx)
                gui_log(serial_fx, f"{fx_name} detected! ปิดแอพแล้วเข้าใหม่...", step="Fix Restart", status="working")
                trigger_restart_from_play8(device, serial_fx, on_fx, reason=f"{fx_name} — ปิดแอพเข้าใหม่")

            # sell-id → ทำงานเหมือน fixclear1 (เช็คควบคู่ทั้ง .png + .bmp ทุกรอบ)
            si_png = img_search(img, os.path.join(IMG_DIR, "sell-id.png"), threshold=0.99)
            si_bmp = img_search(img, os.path.join(IMG_DIR, "sell-id.bmp"), threshold=0.99)
            if si_png or si_bmp:
                gui_log(device.serial, "sell-id detected! Clearing app and moving file to file-error...", step="Sell ID")
                device.shell("am force-stop jp.konami.pesam")
                device.shell("su -c 'rm -f /data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat'")
                device.shell("su -c 'rm -rf /data/data/jp.konami.pesam/files/SaveData/AUTH/*'")

                original_name = DEVICE_FILE_ASSIGNMENTS.get(device.serial)
                if original_name:
                    file_path = os.path.join(INPUT_DIR, original_name)
                    dest_path = os.path.join(FILE_ERROR_DIR, original_name)
                    if os.path.exists(file_path):
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        _safe_copy(file_path, dest_path)
                        os.remove(file_path)
                        gui_log(device.serial, f"Moved {original_name} to file-error", step="Sell ID")

                raise DeviceResetException("sell-id detected")

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
                fe_pts = img_search(img, _P['fixevent'])
                if fe_pts:
                    gui_log(device.serial, "Floating: fixevent.bmp found! Checking if it persists for 5s...", step="Fix Event")
                    persisted = True
                    for _ in range(5):
                        time.sleep(1)
                        img_check = fast_screencap(device)
                        if img_check is None:
                            persisted = False
                            break
                        pts_check = img_search(img_check, _P['fixevent'])
                        if not pts_check:
                            persisted = False
                            break

                    if persisted:
                        gui_log(device.serial, "fixevent.bmp persisted for 5s! Clicking...", step="Fix Event")
                        img_click = fast_screencap(device)
                        if img_click is not None:
                            pts_click = img_search(img_click, _P['fixevent'])
                            if pts_click:
                                x, y = pts_click[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                gui_log(device.serial, f"Clicked fixevent.bmp at ({x}, {y})", step="Fix Event")
                                time.sleep(2)
                        img = fast_screencap(device)

            # fixout floating check — popup บังจอ (เช่น Terms of Use)
            # ยืนยันซ้ำ 1 ครั้ง (~1.2 วิ) กันจับพลาดตอนหน้าจอกำลังเปลี่ยน
            # เจอจริง → กด Back รัวๆ จนเจอ cancel.bmp แล้วคลิก ค่อยกลับมาทำงานต่อ
            # *** ยกเว้น: (1) ช่วง new-gacha/sequence กาชาทั้งหมด — หน้ากาชามีปุ่มคล้าย fixout จับผิดบ่อย
            #             (2) ช่วง cooldown หลังเพิ่งกด cancel ไป — กดรอบเดียวพอ ไม่ยิงซ้ำรัวๆ ***
            if (not in_new_gacha_loop
                    and not DEVICE_DISABLE_FIXOUT.get(device.serial, False)
                    and time.time() - _FIXOUT_LAST_DONE.get(device.serial, 0.0) > FIXOUT_COOLDOWN):
                fo_pts = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.85)
                if fo_pts:
                    gui_log(device.serial, "Floating: fixout found! Confirming (1.2s)...", step="Fix Out")
                    time.sleep(1.2)
                    img_check = fast_screencap(device)
                    pts_check = img_search(img_check, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.85) if img_check is not None else None
                    if pts_check or img_check is None:   # ยังอยู่ (หรือแคปยืนยันไม่ได้ = ถือว่ายังอยู่)
                        fixout_back_spam_until_cancel(device, device.serial)
                        img = fast_screencap(device)
                        if img is None:
                            return None
                    else:
                        gui_log(device.serial, "fixout gone on confirm — skip", step="Fix Out")

            # checkponit-play8.bmp floating check — เจอหน้าอีเวนต์ new stage ตอนไหนก็จัดการทันที
            # *** แทนที่ fixalert1/2/3 เดิม ***
            #     ของเดิมพอเจอ fixalert1 จะวนหา fixalert2 แบบ "ไม่มี timeout" ถ้า fixalert2 ไม่โผล่
            #     = เครื่องนั้นค้างยาวจนกว่าจะกด reset เอง
            # เจอ checkponit-play8 → กด new-stageplay8-1 → -2 → -3 (กดรัวจนแต่ละตัวหายไปจริง)
            if not DEVICE_IN_NEWSTAGE.get(device.serial, False):
                cp8_pts = img_search_best(img, os.path.join(IMG_DIR, "checkponit-play8.bmp"), threshold=0.9)
                if cp8_pts:
                    gui_log(device.serial, "Floating: checkponit-play8 found! เริ่ม new-stageplay8...", step="NewStage")
                    run_new_stage_play8(device, device.serial)
                    img = fast_screencap(device)

            # questfive1-14 floating check — click ทุกรูปจนกว่าจะหายไปทั้งหมด (เฉพาะเมื่อ GETQUEST=1)
            _qf_hit_path = next((p for p in _QUESTFIVE_PATHS if img_search(img, p)), None) if GETQUEST == 1 else None
            if _qf_hit_path:
                gui_log(device.serial, f"Floating: {os.path.basename(_qf_hit_path)} found! Clicking until gone...", step="QuestFive")
                while True:
                    img_qf = fast_screencap(device)
                    if img_qf is None:
                        break

                    # หา questfive ที่เจอตอนนี้
                    _cur_path = None
                    _cur_pts  = None
                    for _qp in _QUESTFIVE_PATHS:
                        _pts = img_search(img_qf, _qp)
                        if _pts:
                            _cur_path = _qp
                            _cur_pts  = _pts
                            break

                    if _cur_path is None:
                        gui_log(device.serial, "questfive: all gone — moving on", step="QuestFive")
                        break

                    # คลิก
                    x, y = _cur_pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    gui_log(device.serial, f"Clicked {os.path.basename(_cur_path)} at ({x},{y})", step="QuestFive")

                    # รอ 5 วิ ให้หน้าจอเปลี่ยน — ถ้าไม่เปลี่ยนให้กดซ้ำ
                    _deadline = time.time() + 15
                    while time.time() < _deadline:
                        time.sleep(0.4)
                        _chk = fast_screencap(device)
                        if _chk is None or not img_search(_chk, _cur_path):
                            break  # หน้าจอเปลี่ยนแล้ว → ไปรอบถัดไป
                    else:
                        gui_log(device.serial, f"questfive: {os.path.basename(_cur_path)} ค้าง 15s → กดซ้ำ", step="QuestFive")
                        # loop จะวนกลับไปคลิกอีกรอบอัตโนมัติ

            # === ad-rewardfix1 floating check (เฉพาะช่วง sequence กาชา) ===
            #     ป็อปอัพรับรางวัลโฆษณาเด้งมาตอนไหนก็กดปิดทันที — หาแบบลอยๆ ทุกเฟรม
            #     ไม่มีการรอ/ไม่บล็อกขั้นตอน ไม่เจอก็ผ่านไปเฉยๆ
            if DEVICE_IN_GACHA.get(device.serial, False) and img is not None:
                pts_adr = img_search(img, os.path.join(IMG_DIR, "ad-rewardfix1.bmp"))
                if pts_adr:
                    x_adr, y_adr = pts_adr[0]
                    device.shell(f"input swipe {x_adr} {y_adr} {x_adr} {y_adr} 100")
                    gui_log(device.serial, f"Floating: ad-rewardfix1 found! Clicked ({x_adr},{y_adr})", step="Ad Reward")
                    time.sleep(1.5)
                    img = fast_screencap(device)

            # === fixgachanew1 -> fixgachanew2 floating check ===
            if in_new_gacha_loop and img is not None:
                pts_fg1 = img_search(img, os.path.join(IMG_DIR, "fixgachanew1.bmp"))
                if pts_fg1:
                    x_fg1, y_fg1 = pts_fg1[0]
                    device.shell(f"input swipe {x_fg1} {y_fg1} {x_fg1} {y_fg1} 100")
                    gui_log(device.serial, "fixgachanew1.bmp detected! Clicking it...", step="FixGachaNew 1")
                    time.sleep(2)

                    # วนกด fixgachanew2.bmp จนกว่าจะหายไป
                    gui_log(device.serial, "Clicking fixgachanew2.bmp until gone...", step="FixGachaNew 2")
                    while True:
                        img_next = fast_screencap(device)
                        if img_next is None:
                            break
                        pts_fg2_loop = img_search(img_next, os.path.join(IMG_DIR, "fixgachanew2.bmp"))
                        if pts_fg2_loop:
                            x_fg2, y_fg2 = pts_fg2_loop[0]
                            device.shell(f"input swipe {x_fg2} {y_fg2} {x_fg2} {y_fg2} 100")
                            gui_log(device.serial, "Clicking fixgachanew2.bmp...", step="FixGachaNew 2")
                            time.sleep(2)
                        else:
                            break

                    # เคลียร์ป็อปอัพเสร็จ → ทำงานต่อจากเดิมเฉยๆ (ไม่ raise/ไม่จบการทำงาน)
                    # การทำงานจะจบก็ต่อเมื่อไปเจอเงื่อนไขจริงๆ (outloop/nocoin/checkpoint) เท่านั้น

            img = fast_screencap(device)

        # (screenshot preview removed — login.py ไม่มี preview widget, ลด GUI lag)
        return img
    except (DeviceResetException, SellScreenException, RestartFromQuest8Exception, ResetGachaException, RestartFromPlay8Exception):
        raise
    except Exception:
        return None

def load_template(path):
    with _image_cache_lock:
        if path in IMAGE_CACHE:
            return IMAGE_CACHE[path]
    t = None
    if os.path.exists(path):
        t = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    else:
        base, ext = os.path.splitext(path)
        for alt in (".bmp", ".png"):
            if alt.lower() != ext.lower():
                alt_path = base + alt
                if os.path.exists(alt_path):
                    t = cv2.imread(alt_path, cv2.IMREAD_GRAYSCALE)
                    if t is not None:
                        break
    if t is not None and SCREENCAP_SCALE != 1.0:
        t = cv2.resize(t,
                       (max(1, int(t.shape[1] * SCREENCAP_SCALE)),
                        max(1, int(t.shape[0] * SCREENCAP_SCALE))),
                       interpolation=cv2.INTER_LINEAR)
    with _image_cache_lock:
        IMAGE_CACHE[path] = t
    return t

def _group_rectangles_compat(rects):
    """รวมกรอบซ้อน/ใกล้กัน — ใช้ cv2.groupRectangles ถ้ามี
    (OpenCV บางเวอร์ชันใหม่ถอดออก → fallback รวมกรอบเองด้วยระยะห่างครึ่ง template)"""
    if hasattr(cv2, "groupRectangles"):
        grouped, _ = cv2.groupRectangles(rects, groupThreshold=1, eps=1)
        return grouped
    out = []
    for (x, y, w, h) in rects:
        for i, (gx, gy, gw, gh) in enumerate(out):
            if abs(x - gx) <= w // 2 and abs(y - gy) <= h // 2:
                out[i] = ((gx + x) // 2, (gy + y) // 2, gw, gh)
                break
        else:
            out.append((x, y, w, h))
    return out

def _match_single(gray_img, find_path, threshold):
    """Match one template, return list of (cx, cy) or []."""
    tmpl = load_template(find_path)
    if tmpl is None:
        return []
    th, tw = tmpl.shape
    if gray_img.shape[0] < th or gray_img.shape[1] < tw:
        return []
    res  = cv2.matchTemplate(gray_img, tmpl, cv2.TM_CCOEFF_NORMED)
    locs = list(zip(*np.where(res >= threshold)[::-1]))
    if not locs:
        return []
    rects = [[x, y, tw, th] for x, y in locs] * 2
    rects = _group_rectangles_compat(rects)
    if not len(rects):
        return []
    inv = 1.0 / SCREENCAP_SCALE if SCREENCAP_SCALE != 1.0 else 1.0
    return [(int((x + tw // 2) * inv), int((y + th // 2) * inv)) for x, y, tw, th in rects]

# ── ROI cache: จำตำแหน่งที่ "เจอรูปนั้นล่าสุด" แล้วรอบถัดไปเทียบเฉพาะบริเวณนั้นก่อน ──
# กวาดเต็มจอ 1 เทมเพลต ≈ 12 ms / เทียบเฉพาะ ROI ≈ 0.3 ms (เร็วขึ้น ~40 เท่า)
# get_screen_capture ยิงหา popup 12-18 เทมเพลตทุกเฟรม → ตรงนี้คือตัวกิน CPU อันดับ 1 ของบอท
#
# เก็บแยกต่อเธรด (= แยกต่อเครื่อง เพราะ 1 worker = 1 จอ) → ไม่ต้องแก้ signature ที่เรียก ~200 จุด
_ROI_TLS = threading.local()

# เทมเพลตที่ตัวเรียก "นับจำนวนจุดที่เจอ" (เช่น len(pts) >= 2) — ห้ามใช้ ROI
# เพราะ ROI คืนจุดเดียวเสมอ จะทำให้การนับผิด
_ROI_CACHE_EXCLUDE = {"verify.png", "verify.bmp",
                      # หน้า Terms of Use — ปุ่ม "Consent" มีคำว่า Consent ในข้อความ
                      # "Consent to All of the Above" อยู่บนจอด้วย (คะแนนเทียบสูงถึง 0.95)
                      # ถ้าใช้ ROI cache จะล็อกไปกดข้อความแทนปุ่มแล้ววนไม่จบ → บังคับกวาดเต็มจอ
                      # (กวาดเต็มจอจะได้ "จุดที่คะแนนสูงสุด" = ปุ่มจริงเสมอ)
                      "checkponit-play8.bmp", "new-stageplay8-1.bmp",
                      "new-stageplay8-2.bmp", "new-stageplay8-3.bmp"}

def _roi_cache():
    c = getattr(_ROI_TLS, "cache", None)
    if c is None:
        c = {}
        _ROI_TLS.cache = c
    return c

def _match_in_roi(gray_img, find_path, threshold, hint):
    """เทียบเทมเพลตเฉพาะกรอบเล็กๆ รอบพิกัดที่จำไว้
    คืน [] ถ้าไม่เจอ → ให้ตัวเรียกถอยไปกวาดเต็มจอตามเดิม

    หมายเหตุ: TM_CCOEFF_NORMED ให้คะแนนเท่าเดิมไม่ว่าจะครอปหรือไม่
    (คะแนนขึ้นกับ template กับ patch ที่ทับอยู่เท่านั้น) → ผลลัพธ์ตรงกับการกวาดเต็มจอ"""
    tmpl = load_template(find_path)
    if tmpl is None:
        return []
    th, tw = tmpl.shape
    H, W = gray_img.shape[0], gray_img.shape[1]
    scale = SCREENCAP_SCALE if SCREENCAP_SCALE != 1.0 else 1.0
    cx, cy = int(hint[0] * scale), int(hint[1] * scale)   # hint เป็นพิกัดจอจริง → กลับเป็นพิกัดในภาพ
    pad = IMG_ROI_PAD
    x0 = max(0, cx - tw // 2 - pad); x1 = min(W, cx + tw // 2 + pad)
    y0 = max(0, cy - th // 2 - pad); y1 = min(H, cy + th // 2 + pad)
    if (x1 - x0) < tw or (y1 - y0) < th:
        return []
    res = cv2.matchTemplate(gray_img[y0:y1, x0:x1], tmpl, cv2.TM_CCOEFF_NORMED)
    _mn, mx, _ml, mloc = cv2.minMaxLoc(res)
    if mx < threshold:
        return []
    inv = 1.0 / scale
    return [(int((x0 + mloc[0] + tw // 2) * inv), int((y0 + mloc[1] + th // 2) * inv))]

def img_search(gray_img, find_path, threshold=0.8):
    """Returns list of (cx, cy) match centers in DEVICE coordinates.
    Tries .bmp first, then .png (or vice versa) automatically."""
    if gray_img is None:
        return []

    use_roi = (IMG_ROI_CACHE and os.path.basename(find_path) not in _ROI_CACHE_EXCLUDE)
    key = (find_path, threshold)
    if use_roi:
        cache = _roi_cache()
        hint = cache.get(key)
        if hint is not None:
            pts = _match_in_roi(gray_img, find_path, threshold, hint)
            if pts:
                return pts          # เจอที่เดิม → จบ ไม่ต้องกวาดทั้งจอ
            cache.pop(key, None)    # ไม่เจอที่เดิม → ลืมทิ้ง แล้วกวาดเต็มจอต่อข้างล่าง

    points = _match_single(gray_img, find_path, threshold)
    if not points:
        base, ext = os.path.splitext(find_path)
        alt_ext = ".png" if ext.lower() == ".bmp" else ".bmp"
        alt_path = base + alt_ext
        if os.path.exists(alt_path):
            points = _match_single(gray_img, alt_path, threshold)
    if use_roi and points:
        _roi_cache()[key] = points[0]   # จำตำแหน่งไว้ใช้รอบหน้า
    return points


def fixout_click_if_stuck(device, serial, img, stuck_since, secs=8.0, step="FixOut", skip_if=None):
    """ค้างอยู่หน้าเดิมครบ `secs` วิ → หา fixout ในภาพ เจอแล้ว "กดเฉยๆ" (ไม่ Back spam ไม่ทำอะไรต่อ)
    แล้วให้ลูปเดิมทำงานตามปกติ. คืนค่า stuck_since ใหม่ (รีเซ็ตนาฬิกาเมื่อครบรอบเช็ค)
    skip_if: path รูป — ถ้าเจอรูปนี้ในเฟรม จะ "ไม่กด fixout" (เช่น checkpoint-gacha4 = หน้าจอถูกต้องแล้ว)"""
    if img is None or time.time() - stuck_since < secs:
        return stuck_since
    if skip_if and img_search(img, skip_if):
        gui_log(serial, f"ค้าง {secs:.0f}s แต่เจอ {os.path.basename(skip_if)} — ไม่กด fixout", step=step)
        return time.time()
    pts_fo = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.85)
    if pts_fo:
        x_fo, y_fo = pts_fo[0]
        device.shell(f"input swipe {x_fo} {y_fo} {x_fo} {y_fo} 100")
        gui_log(serial, f"ค้าง {secs:.0f}s — เจอ fixout กดปิด ({x_fo},{y_fo}) แล้วทำงานต่อ", step=step)
        time.sleep(1.0)
    return time.time()   # เริ่มจับเวลาใหม่ (เช็ครอบถัดไปอีก secs วิ)

def img_search_best(gray_img, find_path, threshold=0.8):
    """คืน "จุดเดียวที่เหมือนที่สุด" ของเทมเพลตนั้น (หรือ [] ถ้าคะแนนไม่ถึงเกณฑ์)

    ต่างจาก img_search: img_search คืน "ทุกจุดที่ผ่านเกณฑ์" (np.where + groupRectangles)
    แล้วตัวเรียกมักหยิบ pts[0] ซึ่งเป็นจุดแรกตามลำดับการจัดกลุ่ม — ไม่ใช่จุดที่คะแนนสูงสุด

    เคสจริงที่พัง: หน้า Terms of Use มีคำว่า "Consent" ในข้อความ "Consent to All of the Above"
    (คะแนน 0.95) อยู่เหนือปุ่ม Consent จริง (0.998) — ผ่านเกณฑ์ทั้งคู่ pts[0] เลยได้ "ข้อความ"
    บอทกดตรงนั้นเท่าไหร่ก็ไม่มีอะไรเกิดขึ้น → ใช้ตัวนี้แทนเมื่อ "ต้องกดให้ตรงปุ่มจริง"
    """
    if gray_img is None:
        return []
    tmpl = load_template(find_path)
    if tmpl is None:
        return []
    th, tw = tmpl.shape
    if gray_img.shape[0] < th or gray_img.shape[1] < tw:
        return []
    res = cv2.matchTemplate(gray_img, tmpl, cv2.TM_CCOEFF_NORMED)
    _mn, mx, _ml, mloc = cv2.minMaxLoc(res)
    if mx < threshold:
        return []
    inv = 1.0 / SCREENCAP_SCALE if SCREENCAP_SCALE != 1.0 else 1.0
    return [(int((mloc[0] + tw // 2) * inv), int((mloc[1] + th // 2) * inv))]


def img_search_any(gray_img, names, threshold=0.8):
    """หา template หลายชื่อในภาพเดียว — เจอตัวไหนก่อนคืนผลตัวนั้นเลย
    (เช่น ["gacha4.bmp", "gacha4v2.bmp"] = เจอเวอร์ชันไหนก็นับว่าเจอ)"""
    for n in names:
        pts = img_search(gray_img, os.path.join(IMG_DIR, n), threshold)
        if pts:
            return pts
    return []


def click_cancel_until_gone(device, serial, x, y, gone_secs=3.0, step="Cancel", timeout=30.0):
    """
    คลิก cancel.bmp ที่ (x,y) แล้วเช็คซ้ำ: ถ้ายังเจอ cancel.bmp อยู่ ให้กดซ้ำเรื่อยๆ
    จนกว่าจะหายไป "ครบ gone_secs วินาทีติดต่อกัน" (default 3 วิ)
    คืนค่า True ถ้า cancel หายครบเวลา, False ถ้า timeout กันค้าง
    """
    cancel_path = os.path.join(IMG_DIR, "cancel.bmp")
    # คลิกครั้งแรกที่จุดที่เจอ
    device.shell(f"input swipe {x} {y} {x} {y} 100")
    time.sleep(0.4)
    gone_since = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        img = get_screen_capture(device)
        pts = img_search(img, cancel_path) if img is not None else None
        if pts:
            cx, cy = pts[0]
            device.shell(f"input swipe {cx} {cy} {cx} {cy} 100")
            gui_log(serial, f"cancel still visible — clicking again ({cx},{cy})...", step=step)
            gone_since = None
            time.sleep(0.4)
        else:
            if gone_since is None:
                gone_since = time.time()
            elif time.time() - gone_since >= gone_secs:
                gui_log(serial, f"cancel gone for {gone_secs:.0f}s — done", step=step)
                return True
            time.sleep(0.3)
    gui_log(serial, f"cancel re-click timeout ({timeout:.0f}s) — moving on", step=step)
    return False

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
    
    # Run OCR sequentially across threads using ocr_lock to prevent CPU spike freezes and deadlocks
    with ocr_lock:
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
            cprint(f"[OCR] [{serial}] Attempting EasyOCR...")
            if _reader is None:
                # verbose=False → ปิดข้อความ "Using CPU. Note: This module is much faster with a GPU."
                _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            
            # Apply bilateral filter to smooth card textures but keep text edges extremely sharp
            cleaned_img = cv2.bilateralFilter(img, 9, 75, 75)
            # Resize 2x using Cubic interpolation for cleaner character strokes
            resized_easy = cv2.resize(cleaned_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            
            results = _reader.readtext(resized_easy, detail=0)
            res = " ".join(results).strip()
            if res:
                cprint(f"[OCR] [{serial}] EasyOCR Result: '{res}'")
                return res
        except Exception as e:
            cprint(f"[OCR] EasyOCR Error: {e}")
            pass

    # 2. Fallback to Pytesseract — Enhanced multi-pass
    if pytesseract is not None:
        try:
            cprint(f"[OCR] Attempting Pytesseract (Enhanced)...")
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
                    cprint(f"[OCR] {label}: '{res}'")
                    all_results.append(res)
            
            combined_result = " | ".join(all_results)
            if combined_result:
                cprint(f"[OCR] ★ Combined Result: '{combined_result}'")
            else:
                cprint(f"[OCR] Pytesseract returned EMPTY string (all methods)")
            return combined_result
        except Exception as e:
            cprint(f"[OCR] Pytesseract Error: {e}")
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
    if len(cleaned_ocr) < 3:
        return False

    # ── หลักการ: match แบบ "ตรงเต็มคำเป๊ะๆ" เท่านั้น (ไม่มี fuzzy/prefix/70%) ──
    #    คำใดคำหนึ่งของชื่อฮีโร่ ตรงกับคำใน OCR แบบเต็มคำ = match
    #    เช่น hero "Erling Haaland" + OCR อ่านได้ "Haaland" → match
    #    (ข้ามคำเชื่อมสั้นๆ เช่น de/van/der กัน match มั่วกับชื่อคนอื่น)
    hero_words = cleaned_hero.split()
    ocr_words = set(cleaned_ocr.split())
    _skip_words = {"de", "van", "der", "dos", "das", "del", "los", "la", "el", "al", "di", "da"}
    for w in hero_words:
        if len(w) < 3 or w in _skip_words:
            continue
        if w in ocr_words:
            return True

    # เผื่อ OCR อ่านชื่อติดกันไม่มีวรรค (เช่น "erlinghaaland") — เช็คชื่อเต็มแบบไม่มีวรรค
    # เฉพาะชื่อหลายคำเท่านั้น (ชื่อคำเดียวใช้กฎเต็มคำข้างบนพอ กัน substring มั่ว เช่น luka ใน lukaku)
    if len(hero_words) > 1:
        if cleaned_hero.replace(" ", "") in cleaned_ocr.replace(" ", ""):
            return True

    return False

def _extar_file_for(hero_name):
    """หาชื่อไฟล์รูปของ EXTAR_FIND จากชื่อฮีโร่ (ไม่สนตัวพิมพ์ใหญ่-เล็ก / ช่องว่างหัวท้าย)
    ไม่ได้อยู่ในลิสต์ → None"""
    if not EXTAR_FIND:
        return None
    key = str(hero_name).strip().lower()
    for k, v in EXTAR_FIND.items():
        if str(k).strip().lower() == key and v:
            return str(v).strip()
    return None

def extar_img_confirm(img, hero_name, serial, step_tag="Extar", cache=None):
    """EXTAR_FIND — ฮีโร่บางคนต้อง "OCR เจอชื่อ" + "เจอรูปในจอ" ถึงจะนับว่าเจอจริง
    (กัน OCR อ่านผิดแล้วนับเกิน)

      - ชื่อไม่ได้อยู่ใน EXTAR_FIND   → True (ใช้ OCR อย่างเดียวเหมือนเดิม)
      - อยู่ในลิสต์ + เจอรูป          → True
      - อยู่ในลิสต์ + ไม่เจอรูป       → False (ไม่นับว่าเจอ)
      - ไฟล์รูปหาย                   → True + log เตือน (ไม่บล็อกการทำงาน)

    cache: dict ว่างๆ ส่งเข้ามาได้ — เฟรมเดียวกันเทียบรูปเดิมซ้ำหลาย lock จะใช้ผลเดิม
    """
    fname = _extar_file_for(hero_name)
    if not fname:
        return True
    if img is None:
        return True

    if cache is not None and fname in cache:
        return cache[fname]

    path = os.path.join(IMG_DIR, EXTAR_SUBDIR, fname)
    base, _ext = os.path.splitext(path)
    if not (os.path.exists(path) or os.path.exists(base + ".png") or os.path.exists(base + ".bmp")):
        gui_log(serial, f"⚠️ EXTAR_FIND: ไม่พบไฟล์รูป {path} — ใช้ผล OCR อย่างเดียว", step=f"{step_tag} No Img")
        return True   # ไม่ cache — เผื่อเพิ่งวางไฟล์รูปทีหลัง

    pts = img_search(img, path, threshold=EXTAR_FIND_THRESHOLD)
    ok = bool(pts)
    if ok:
        gui_log(serial, f"EXTAR ✅ {hero_name}: OCR เจอ + รูป {fname} match ที่ {pts[0]}", step=f"{step_tag} OK")
    else:
        gui_log(serial, f"EXTAR ❌ {hero_name}: OCR เจอ แต่ไม่เจอรูป {fname} → ไม่นับว่าเจอ", step=f"{step_tag} Reject")
    if cache is not None:
        cache[fname] = ok
    return ok

def parse_hero_config(config_list):
    """
    Parses a list of hero configurations.
    Each item can be a string, e.g. "Lamine=x2", "Lamine:2", "Lamine".
    Also supports tuples or lists like ("Lamine", 2) or ["Lamine", "x2"].
    Returns a dict: { hero_name_cleaned: required_count }
    """
    parsed = {}
    for item in config_list:
        if not item:
            continue
        
        if isinstance(item, (list, tuple)):
            if len(item) >= 2:
                name = str(item[0]).strip()
                val = str(item[1]).strip().lower()
                if val.startswith('x'):
                    val = val[1:]
                if val.isdigit():
                    req_count = int(val)
                else:
                    req_count = 1
                parsed[name] = req_count
            elif len(item) == 1:
                name = str(item[0]).strip()
                parsed[name] = 1
            continue
            
        item_str = str(item).strip()
        if not item_str:
            continue
        
        name = item_str
        req_count = 1
        
        for sep in [':', '=']:
            if sep in item_str:
                parts = item_str.split(sep)
                name = parts[0].strip()
                val = parts[1].strip().lower()
                if val.startswith('x'):
                    val = val[1:]
                if val.isdigit():
                    req_count = int(val)
                break
        
        parsed[name] = req_count
    return parsed

# ═════════════════════════════════════════════════════════════════════════════
# File management  ← แก้ตรงนี้
# ═════════════════════════════════════════════════════════════════════════════
_done_cache_names: set  = set()
_done_cache_time: float = 0.0
_DONE_CACHE_TTL         = 3.0  # วินาที — รีเฟรช glob ทุก 3 วิ แทนทุก call

def pick_next_file():
    """
    Thread-safe: pick ONE .dat from input-id that is NOT already in use.
    หมายเหตุ: ไม่ข้ามไฟล์ที่ชื่อซ้ำกับโฟลเดอร์ done อีกแล้ว → ประมวลผลซ้ำได้
    (ผลลัพธ์จะทับไฟล์เดิมที่ชื่อเดียวกัน + อัปเวลาเป็นปัจจุบัน)
    ไม่มีไฟล์เหลือใน input-id → ดึงไฟล์จาก timeout/ กลับมาใส่ input-id แล้วสแกนซ้ำอีกรอบ
    Returns (full_path, basename) or (None, None).
    """
    with file_pick_lock:
        for attempt in (0, 1):
            for f in sorted(glob.glob(os.path.join(INPUT_DIR, "*.dat"))):
                name = os.path.basename(f)
                if name in in_use_files:          # กำลัง process อยู่ในรอบนี้ → ข้าม (กันแย่งไฟล์)
                    continue
                in_use_files.add(name)
                try:
                    _safe_copy(f, os.path.join(RUN_FILE_DIR, name))
                except Exception:
                    pass
                return f, name
            # รอบแรกไม่เจอไฟล์ว่าง → รีไซเคิลไฟล์จาก timeout/ แล้ววนหาใหม่อีกรอบ
            if attempt == 0:
                moved = move_timeout_to_input()
                if not moved:
                    break
                cprint(f"♻️ input-id หมด → ย้าย {moved} ไฟล์จาก {TIMEOUT_DIR}/ กลับเข้า {INPUT_DIR}/")
                if gui_instance:
                    try:
                        gui_instance.log(f"♻️ input-id หมด → ย้าย {moved} ไฟล์จาก {TIMEOUT_DIR}/ กลับเข้า {INPUT_DIR}/")
                    except Exception:
                        pass
        return None, None

def move_timeout_to_input():
    """ย้ายไฟล์ทั้งหมดจาก timeout/ → input-id/ (คืนจำนวนไฟล์ที่ย้าย)
    ใช้ตอน input-id หมด → เอาไฟล์ที่ timeout ไปกลับมาลองใหม่ ไม่ให้ค้างทิ้งไว้เฉยๆ
    *** ต้องเรียกใต้ file_pick_lock เท่านั้น (แตะ in_use_files) ***"""
    moved = 0
    base = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(base, TIMEOUT_DIR)
    dst_dir = os.path.join(base, INPUT_DIR)
    if not os.path.isdir(src_dir):
        return 0
    os.makedirs(dst_dir, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(src_dir, "*.dat"))):
        if not os.path.isfile(f):
            continue
        name = os.path.basename(f)
        if name in in_use_files:      # เครื่องอื่นกำลัง process ชื่อนี้อยู่ → ไม่แตะ
            continue
        dest = os.path.join(dst_dir, name)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(f, dest)
            moved += 1
        except Exception:
            pass
    return moved

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

def _safe_copy(src, dest):
    """copy2 โดยสร้างโฟลเดอร์ปลายทางให้ก่อน (lazy creation — ไม่สร้างโฟลเดอร์ล่วงหน้า)."""
    d = os.path.dirname(dest)
    if d:
        os.makedirs(d, exist_ok=True)
    shutil.copy2(src, dest)

def extract_user_code(dat_path):
    """อ่าน "user_code" จากข้างในไฟล์ .dat (JSON) เช่น {"user_code":"ASCV659902699",...}
    คืน None ถ้าอ่านไม่ได้ (ให้ตัวเรียกไป fallback ใช้ชื่อไฟล์เดิม)"""
    import json
    try:
        with open(dat_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            uc = json.loads(content[s:e + 1]).get("user_code")
            if uc:
                return str(uc).strip()
    except Exception:
        pass
    return None

def export_base_name(file_path, original_name, strip_dash=False):
    """ชื่อไฟล์ที่จะใช้ตอน export — ดึง user_code "จากข้างในไฟล์" มาเป็นชื่อ
    เพราะชื่อไฟล์ขาเข้าอาจไม่ตรงกับ user_code จริงของบัญชีนั้น
    (เก็บ coin tag -[เลข] ที่ติดมากับชื่อเดิมไว้ด้วย)

    อ่าน user_code ไม่ได้ → fallback ตัด prefix จากชื่อเดิมแบบเดิมเป๊ะๆ
    strip_dash: ตัดหลัง '-' ด้วยไหม (บาง flow ตัด, flow ของ find_hero ไม่ตัดเพราะต้องเก็บ coin tag)
    """
    uc = extract_user_code(file_path) if file_path else None
    if uc:
        import re as _re_ex
        m = _re_ex.search(r"-\[\d+\]", os.path.splitext(original_name or "")[0])
        return f"{uc}{m.group(0) if m else ''}.dat"
    clean = original_name
    if "+" in clean:
        clean = clean.split("+")[-1]
    elif strip_dash and "-" in clean:
        clean = clean.split("-")[-1]
    return clean

_NET_TIME_OFFSET   = 0.0     # วินาที = (เวลาโลกจริง) - (เวลาเครื่อง)
_NET_TIME_SYNCED   = False
_net_time_last_sync = 0.0

def _sync_net_time():
    """ดึงเวลาโลกจาก HTTP Date header → คำนวณ offset เทียบเวลาเครื่อง (เงียบ ถ้าเน็ตล่มก็ข้าม)."""
    global _NET_TIME_OFFSET, _NET_TIME_SYNCED, _net_time_last_sync
    import urllib.request, email.utils
    for url in ("https://www.google.com", "https://www.cloudflare.com"):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                date_hdr = r.headers.get("Date")
            if date_hdr:
                real_epoch = email.utils.mktime_tz(email.utils.parsedate_tz(date_hdr))
                _NET_TIME_OFFSET = real_epoch - time.time()
                _NET_TIME_SYNCED = True
                _net_time_last_sync = time.time()
                return True
        except Exception:
            continue
    _net_time_last_sync = time.time()
    return False

def real_now():
    """datetime ปัจจุบันอิงเวลาโลก (internet) ถ้า sync ได้ ไม่งั้น fallback เวลาเครื่อง."""
    from datetime import datetime
    return datetime.fromtimestamp(time.time() + _NET_TIME_OFFSET)

def parse_time_to_hhmm(raw):
    """แปลงเวลาที่พิมพ์ → 'HH:MM' (24 ชม.) รองรับทั้ง 24h และ AM/PM
       เช่น 9:46PM → 21:46 , 9:46 → 09:46 , 946 → 09:46 ; ผิดรูปแบบ → None."""
    import re as _re_t
    s = str(raw).strip().lower().replace(".", ":")
    ampm = None
    if "am" in s:
        ampm = "am"; s = s.replace("am", "")
    elif "pm" in s:
        ampm = "pm"; s = s.replace("pm", "")
    s = s.strip()
    m = _re_t.match(r"^(\d{1,2})\s*:\s*(\d{1,2})$", s)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
    elif _re_t.fullmatch(r"\d{3,4}", s):     # เลขล้วน เช่น 946 / 0946
        s2 = s.zfill(4); h, mm = int(s2[:2]), int(s2[2:])
    else:
        return None
    if ampm == "am" and h == 12:
        h = 0
    elif ampm == "pm" and h != 12:
        h += 12
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return f"{h:02d}:{mm:02d}"
    return None

def move_login_success_to_input():
    """ย้ายไฟล์ทั้งหมดจาก login-success/ → input-id/ (คืนจำนวนไฟล์ที่ย้าย)."""
    moved = 0
    base = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(base, LOGIN_SUCCESS_DIR)
    dst_dir = os.path.join(base, INPUT_DIR)
    if not os.path.isdir(src_dir):
        return 0
    os.makedirs(dst_dir, exist_ok=True)
    for f in glob.glob(os.path.join(src_dir, "*")):
        if not os.path.isfile(f):
            continue
        dest = os.path.join(dst_dir, os.path.basename(f))
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(f, dest)
            moved += 1
        except Exception:
            pass
    return moved

def save_result(src, dest):
    """ย้าย src → dest แบบ 'ทับของเดิมถ้าชื่อซ้ำ' + ตั้งเวลาแก้ไขเป็นปัจจุบัน
    (ใช้แทน shutil.move ตรงๆ เพราะ Windows จะ error ถ้าปลายทางมีไฟล์ชื่อเดียวกันอยู่)."""
    d = os.path.dirname(dest)
    if d:
        os.makedirs(d, exist_ok=True)   # lazy: สร้างโฟลเดอร์ปลายทางตอนเขียนจริง
    try:
        if os.path.exists(dest):
            os.remove(dest)
    except Exception:
        pass
    shutil.move(src, dest)
    try:
        os.utime(dest, None)   # อัปเวลาเป็นปัจจุบัน
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

def find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=None):
    """
    Dedicated function to find heroes with robust checking (Triple Check).
    Checks multiple times to ensure a consistent match and avoid false positives.

    coin_prefix: ถ้าส่งเลขเหรียญมา (จากโหมด Gacha+Find + CHECK_COIN) จะแนบ "[เลข]+"
                 ไว้หน้าชื่อไฟล์ตอน export.
    """
    gui_log(serial, "Find Hero sequence started...", step="Find Hero", status="working")

    # ปิด floating fixout ตลอด sequence fin (fin1..fin13)
    # — หน้า fin มีปุ่มคล้าย fixout จับผิดแล้ว Back spam มั่ว หลุด sequence
    #   (เปิดกลับอัตโนมัติตอนเริ่ม cycle ใหม่ — find_hero_mode จบรอบเสมอ)
    DEVICE_DISABLE_FIXOUT[serial] = True

    def _check_fixteam(img_current):
        pts_team = img_search(img_current, os.path.join(IMG_DIR, "fixteam.bmp"), threshold=0.95)
        if pts_team:
            gui_log(serial, "fixteam.bmp detected! Spamming Back...", step="Fix Team")
            deadline_fixteam = time.time() + 60
            fixteam_cancel_found = False
            while time.time() < deadline_fixteam:
                check_device_reset(serial, cycle_start)
                device.shell("input keyevent 4")
                time.sleep(1.0)
                img_c = get_screen_capture(device)
                if img_c is not None:
                    pts_c = img_search(img_c, os.path.join(IMG_DIR, "cancel.bmp"))
                    if pts_c:
                        x, y = pts_c[0]
                        gui_log(serial, f"cancel.bmp found at ({x},{y})! Clicking and stopping back spam.", step="Fix Team Stop")
                        click_cancel_until_gone(device, serial, x, y, step="Fix Team Stop")
                        fixteam_cancel_found = True
                        break
            if not fixteam_cancel_found:
                gui_log(serial, "Timeout waiting for cancel.bmp in fixteam. Force stopping app...", step="Fix Team Timeout")
                device.shell("am force-stop jp.konami.pesam")
                time.sleep(1)
                raise DeviceResetException("fixteam timeout")
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
        step_start = time.time()   # ใช้จับเวลา "ค้าง" เฉพาะ fin1
        last_countdown = None      # วินาทีล่าสุดที่ log countdown (กัน log รัว)
        fin1_rescue_n = 0          # นับรอบ rescue ของ fin1 — เกิน 2 รอบ → แวะกด next.bmp
        while True:
            check_device_reset(serial, cycle_start)

            # ── Countdown นับถอยหลัง 10 วิ เฉพาะ fin1 (โชว์ว่ายังทำงานอยู่) ──
            if name_curr == "fin1.bmp":
                remaining = int(10.0 - (time.time() - step_start)) + 1
                if remaining > 0 and remaining != last_countdown:
                    last_countdown = remaining
                    gui_log(serial, f"Waiting fin1.bmp... rescue in {remaining}s", step=f"fin1 ⏳{remaining}s")

            img = get_screen_capture(device)
            if img is not None:
                if _check_fixteam(img):
                    continue

                if img_search(img, os.path.join(IMG_DIR, name_next), threshold=0.95):
                    gui_log(serial, f"{name_next} detected! Proceeding to next step.", step=f"{name_next} Seen")
                    break

                # ── ถ้าไปต่อ fin1 ไม่ได้ครบ 10 วิ → กด Back รัวๆ จนเจอ cancel.png แล้วหยุด (แล้วลองรอ fin1 ใหม่) ──
                if name_curr == "fin1.bmp" and (time.time() - step_start) >= 10.0:
                    last_countdown = None
                    gui_log(serial, "fin1.bmp stuck for 10s! Spamming Back until cancel.png...", step="fin1 Rescue")
                    while True:
                        check_device_reset(serial, cycle_start)
                        device.shell("input keyevent 4")  # KEYCODE_BACK
                        time.sleep(0.4)
                        img_b = get_screen_capture(device)
                        if img_b is not None:
                            pts_cb = img_search(img_b, os.path.join(IMG_DIR, "cancel.png"))
                            if pts_cb:
                                xb, yb = pts_cb[0]
                                gui_log(serial, f"cancel.png found at ({xb},{yb}) — clicking & stopping Back spam.", step="fin1 Rescue OK")
                                click_cancel_until_gone(device, serial, xb, yb, step="fin1 Rescue")
                                break

                    # ── rescue เกิน 2 รอบแล้วยังไม่เจอ fin1 → แวะหา next.bmp แล้วกด (หน้าผลสุ่มอาจค้างอยู่) ──
                    fin1_rescue_n += 1
                    if fin1_rescue_n >= 2:
                        gui_log(serial, f"fin1 rescue {fin1_rescue_n} รอบแล้วยังไม่เจอ — แวะหา next.bmp (8s)", step="fin1 Next")
                        dl_fn = time.time() + 8
                        while time.time() < dl_fn:
                            check_device_reset(serial, cycle_start)
                            img_fn = get_screen_capture(device)
                            if img_fn is not None:
                                pts_fn = img_search(img_fn, os.path.join(IMG_DIR, "next.bmp"))
                                if pts_fn:
                                    x_fn, y_fn = pts_fn[0]
                                    gui_log(serial, f"เจอ next.bmp — กด ({x_fn},{y_fn})", step="fin1 Next")
                                    click_next_until_gone(device, cycle_start, serial, x_fn, y_fn, tag="fin1 Next")
                                    break
                            time.sleep(0.3)
                        else:
                            gui_log(serial, "ไม่เจอ next.bmp ใน 8s — รอ fin1 ต่อ", step="fin1 Next Miss")
                        fin1_rescue_n = 0   # เช็คแล้ว → เริ่มนับรอบใหม่

                    step_start = time.time()   # รีเซ็ตนาฬิกาแล้วกลับไปรอ fin1 ใหม่
                    continue
                    
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

                        # ── หลังกด fin2 → แวะหา fixfindnew.png 10 วิ ──
                        #    เจอ → กด แล้วไปต่อ | ไม่เจอครบ 10 วิ → ข้าม ไปต่อตามปกติ (รอ/กด fin3)
                        if name_curr == "fin2.bmp":
                            gui_log(serial, "แวะหา fixfindnew.png (10s)...", step="fixfindnew Wait")
                            ffn_deadline = time.time() + 10.0
                            ffn_clicked  = False
                            while time.time() < ffn_deadline:
                                check_device_reset(serial, cycle_start)
                                img_ffn = get_screen_capture(device)
                                if img_ffn is not None:
                                    pts_ffn = img_search(img_ffn, os.path.join(IMG_DIR, "fixfindnew.png"), threshold=0.8)
                                    if pts_ffn:
                                        x_f, y_f = pts_ffn[0]
                                        device.shell(f"input swipe {x_f} {y_f} {x_f} {y_f} 100")
                                        gui_log(serial, f"Clicked fixfindnew.png at ({x_f},{y_f})", step="fixfindnew Click")
                                        ffn_clicked = True
                                        time.sleep(1.0)
                                        break
                                time.sleep(0.3)
                            if not ffn_clicked:
                                gui_log(serial, "fixfindnew.png ไม่เจอใน 10s — ข้าม ไปต่อ fin3", step="fixfindnew Skip")
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
    target_config = parse_hero_config(target_list)
    target_heroes = list(target_config.keys())

    for pass_num in range(1, 3):
        found_heroes.clear()
        
        # Capture screen once for this pass (maximum speed, zero mismatch)
        img = get_screen_capture(device)
        if img is not None:
            lock1_matches = set()
            lock2_matches = set()
            lock3_matches = set()
            # เฟรมเดียวกันทั้ง 3 lock → เทียบรูป EXTAR_FIND ครั้งเดียวพอ (ใช้ผลซ้ำ)
            extar_cache = {}

            # Lock 1 Scanning
            lock1_region = Region(154, 134, 679, 39)
            lock1_text = read_screen_text(img, region=lock1_region, serial=serial)
            last_lock1_text = lock1_text if lock1_text else ""
            gui_log(serial, f"Lock 1 OCR: {lock1_text if lock1_text else '<EMPTY>'}", step="Scan Lock 1")
            for h in target_heroes:
                if is_hero_match(h, lock1_text):
                    # อยู่ใน EXTAR_FIND → ต้องเจอรูปในจอด้วย ถึงจะนับ
                    if not extar_img_confirm(img, h, serial, step_tag="Extar L1", cache=extar_cache):
                        continue
                    lock1_matches.add(h)
                    gui_log(serial, f"Lock 1 Match: {h}", step=f"⭐ {h}")

            # Lock 2 Scanning
            lock2_region = Region(156, 249, 646, 34)
            lock2_text = read_screen_text(img, region=lock2_region, serial=serial)
            last_lock2_text = lock2_text if lock2_text else ""
            gui_log(serial, f"Lock 2 OCR: {lock2_text if lock2_text else '<EMPTY>'}", step="Scan Lock 2")
            for h in target_heroes:
                if is_hero_match(h, lock2_text):
                    if not extar_img_confirm(img, h, serial, step_tag="Extar L2", cache=extar_cache):
                        continue
                    lock2_matches.add(h)
                    gui_log(serial, f"Lock 2 Match: {h}", step=f"⭐ {h}")

            # Lock 3 Scanning
            lock3_region = Region(157, 360, 658, 34)
            lock3_text = read_screen_text(img, region=lock3_region, serial=serial)
            last_lock3_text = lock3_text if lock3_text else ""
            gui_log(serial, f"Lock 3 OCR: {lock3_text if lock3_text else '<EMPTY>'}", step="Scan Lock 3")
            for h in target_heroes:
                if is_hero_match(h, lock3_text):
                    if not extar_img_confirm(img, h, serial, step_tag="Extar L3", cache=extar_cache):
                        continue
                    lock3_matches.add(h)
                    gui_log(serial, f"Lock 3 Match: {h}", step=f"⭐ {h}")

            # Aggregate matches from the three locks
            from collections import Counter
            pass_matches = list(lock1_matches) + list(lock2_matches) + list(lock3_matches)
            if pass_matches:
                counts = Counter(pass_matches)
                pass_valid_heroes = []
                for h, count in counts.items():
                    req = target_config.get(h, 1)
                    if count >= req:
                        if count > 1:
                            pass_valid_heroes.append(f"{h}x{count}")
                        else:
                            pass_valid_heroes.append(h)
                
                if pass_valid_heroes:
                    found_heroes.extend(pass_valid_heroes)
                    break
            
        # If we failed to find any hero in Pass 1, wait 2s and scan one more time!
        if pass_num == 1:
            gui_log(serial, "No hero found on Pass 1. Retrying in 2s for screen to settle...", step="OCR Retry")
            time.sleep(2.0)

    # 7. Shutdown and Move
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    # ชื่อไฟล์ตอน export = user_code จริงที่อ่านจากข้างในไฟล์ .dat (เก็บ coin tag -[เลข] ไว้)
    #   อ่านไม่ได้ → fallback ตัด hero/coin prefix จากชื่อเดิม (Hero+ID -> ID) แบบเดิม
    clean_orig = export_base_name(file_path, original_name)

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
        
        # ไม่ match hero อะไรเลย → ส่งไป no-hero เสมอ (ไม่ว่าจะ verify empty state ได้หรือไม่)
        dest_dir = NO_HERO_DIR
        final_name = clean_orig
        if is_empty_state:
            gui_log(serial, "No hero match found (Verified empty state).", step="No Match")
        else:
            gui_log(serial, "No hero match found (OCR unverified) → no-hero.", step="No Match")

    # แนบเลขเหรียญที่สแกนสดมา ต่อท้ายชื่อไฟล์ก่อนนามสกุล (เฉพาะกรณีที่ส่ง coin_prefix เข้ามา)
    #   เช่น  Paolo Maldini+ASCV610367086.dat -> Paolo Maldini+ASCV610367086-[300].dat
    if coin_prefix:
        import re as _re_fh
        _b, _e = os.path.splitext(final_name)
        _b = _re_fh.sub(r"-\[\d+\]", "", _b)  # กัน coin ซ้อนถ้าชื่อมี -[เลข] อยู่แล้ว
        final_name = f"{_b}-[{coin_prefix}]{_e}"
        gui_log(serial, f"🪙 Attaching coins to filename: {final_name}", step="Coin Tag")

    dest = os.path.join(dest_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(2)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            _safe_copy(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted: {dest_dir}", step="Sorted", status="working")
        except Exception as me:
            gui_log(serial, f"⚠️ Sort failed: {me}", step="Sort Error")
        
        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    return True

def navigate_home(device, cycle_start, serial):
    """
    กลับหน้า Home: รอ backhome.bmp → คลิก → รอ backhome1.bmp → คลิกจนหาย (ไม่ clear app).
    คืนค่า True ถ้ากด backhome ได้ (ใช้ทั้งตอนไปหาตัวต่อ และตอนสแกนเหรียญก่อนส่งไฟล์ออก).
    """
    # 1. Wait for backhome.bmp with a 45-second timeout to prevent infinite hanging
    clicked_home = False
    deadline_home = time.time() + 45
    while time.time() < deadline_home:
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
        # 1b. Wait for backhome1.bmp with a 30-second timeout, click until gone
        gui_log(serial, "Waiting for backhome1.bmp...", step="Back Home 1 Wait")
        clicked_home1 = False
        deadline_home1 = time.time() + 30
        while time.time() < deadline_home1:
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

    return clicked_home


def navigate_home_then_find_hero(device, cycle_start, serial, original_name, file_path, coin_prefix=None):
    """
    Navigate to Home (backhome -> backhome1) แล้วต่อด้วย find_hero_mode ทันที (ไม่ clear app).
    ใช้ร่วมกันระหว่าง GachaFree+Check (GACHA_CHECK) และ Gacha+Find (GACHA_FIND)
    เพื่อให้ทั้งสองโหมดทำงานเหมือนกันเป๊ะ.
    """
    navigate_home(device, cycle_start, serial)

    # 1c. สแกนเหรียญใหม่อีกรอบก่อนทำ fin (อัปเดตเลขหลังสุ่มไปแล้ว เพราะเหรียญลดลง)
    if CHECK_COIN == 1:
        gui_log(serial, "Re-scanning coins after gacha (updated value)...", step="Coin Re-scan", status="working")
        new_coin = scan_coin_number(device, cycle_start, serial)
        if new_coin is not None:
            coin_prefix = new_coin

    # 2. Run Find Hero sequence continuously! (แนบเลขเหรียญที่สแกนใหม่หลังสุ่มถ้ามี)
    return find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix)


def scan_coin_number(device, cycle_start, serial):
    """
    รอ checkpointcoin.bmp → OCR ที่ Region(52, 10, 106, 41) → คืนค่าเลขเหรียญ (string)
    หรือ None ถ้าหา checkpointcoin ไม่เจอ. (สแกนอย่างเดียว ไม่ย้ายไฟล์/ไม่ปิดแอป)
    """
    import re
    gui_log(serial, "Waiting checkpointcoin (Gacha+Find)...", step="Coin Wait", status="working")
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
        gui_log(serial, "checkpointcoin.bmp not found — skip coin scan.", step="Coin Timeout")
        return None

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

    gui_log(serial, f"🪙 Coins scanned & remembered: {coin_number}", step="Coin Match")
    cprint(f"[{serial}] Gacha+Find Coin Scan: {coin_number}")
    return coin_number


def _read_coin_from_img(img, serial):
    """OCR อ่านเลข coin จากมุมซ้ายบน (region เดิม 52,10,106,41) ของภาพที่ให้มา.
    คืนค่า int (0 ถ้าอ่านไม่ได้) — ใช้ตอน GACHA500 อ่าน coin ที่หน้า checkpoint-gacha4."""
    import re
    try:
        ocr_text = read_screen_text(img, region=Region(52, 10, 106, 41), serial=serial)
        digits = "".join(re.findall(r"\d+", ocr_text or ""))
        return int(digits) if digits else 0
    except Exception:
        return 0


def click_img_until_gone(device, cycle_start, serial, img_path, x, y,
                         stuck_secs=3.0, timeout=60.0, tag="Click", threshold=0.8,
                         label=None, settle=1.5, gone_secs=0.0):
    """กดรูปที่ (x,y) แล้วเฝ้าดู — ถ้ารูปยัง "ค้าง" อยู่เกิน `stuck_secs` วิ ให้กดซ้ำ
    วนจนกว่ารูปจะหายไป (หรือครบ timeout กันค้าง). คืน True ถ้าหายแล้ว
    timeout=None → ไม่ยอมแพ้ กดซ้ำจนกว่ารูปจะหายไปจริงๆ
    gone_secs → ต้องหาไม่เจอ "ติดต่อกันครบ gone_secs วิ" ถึงจะถือว่าหายจริง
                (กัน false-negative จาก animation/กระพริบเฟรมเดียว) — 0 = หายเฟรมเดียวก็ไปต่อ"""
    name = label or os.path.basename(img_path)
    device.shell(f"input swipe {x} {y} {x} {y} 100")
    gui_log(serial, f"กด {name} ({x},{y})", step=tag)
    time.sleep(settle)
    last_click = time.time()
    gone_since = None
    deadline = None if timeout is None else time.time() + timeout
    while deadline is None or time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img_c = get_screen_capture(device)
        if img_c is not None:
            pts_c = img_search(img_c, img_path, threshold=threshold)
            if not pts_c:
                # ไม่เจอรูป — ยืนยันว่าหายจริงเมื่อหาไม่เจอครบ gone_secs วิ
                if gone_secs <= 0:
                    return True   # รูปหายแล้ว → ไปต่อ
                if gone_since is None:
                    gone_since = time.time()
                elif time.time() - gone_since >= gone_secs:
                    gui_log(serial, f"{name} หายครบ {gone_secs:.0f}s — ไปต่อ", step=f"{tag} Gone")
                    return True
                time.sleep(0.3)
                continue
            # ยังเจออยู่ — รีเซ็ตตัวจับเวลา "หาย" + ค้างเกิน stuck_secs → กดซ้ำ
            gone_since = None
            if time.time() - last_click >= stuck_secs:
                x_c, y_c = pts_c[0]
                device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                gui_log(serial, f"{name} ค้างเกิน {stuck_secs:.0f}s — กดซ้ำ ({x_c},{y_c})", step=f"{tag} Retry")
                last_click = time.time()
                time.sleep(settle)
        time.sleep(0.3)
    gui_log(serial, f"{name} ยังไม่หายใน {timeout:.0f}s — ไปต่อ", step=f"{tag} Timeout")
    return False

def run_new_stage_play8(device, serial, cycle_start=None):
    """อีเวนต์ new stage: กด new-stageplay8-1 → -2 → -3 "เรียงตามลำดับเท่านั้น"

    กติกาของขั้นตอนนี้:
      • ไม่มี timeout รายตัว — รอตัวปัจจุบันจนกว่าจะเจอจริง แล้วกดรัวจนหายไปจริง
        ค่อยขยับไปตัวถัดไป (ห้ามข้ามลำดับ ห้ามยอมแพ้กลางคัน)
      • ห้ามมีตัวอื่นมากดแทรกระหว่างนี้ โดยเฉพาะ fixout → Back spam → กด cancel
        จึงใช้ fast_screencap ล้วน (ไม่เรียก get_screen_capture ที่มี floating fixer อยู่)
        และปิดธง fixout ไว้ตลอดช่วงนี้ด้วยกันโดนยิงจากทางอื่น
      • ทางออกถ้าเกมค้างจริง = ปุ่ม ↺ reset หรือ timeout รวมของทั้ง cycle (TIMEOUT_MINUTES)

    เรียกได้ 2 ทาง: หลังกด play8 (ขั้นตอนหลัก) และจาก floating check ตอนเจอ
    checkponit-play8 ลอยๆ — ธง DEVICE_IN_NEWSTAGE กันเรียกซ้อนตัวเอง"""
    if DEVICE_IN_NEWSTAGE.get(serial, False):
        return False
    if cycle_start is None:
        cycle_start = DEVICE_CYCLE_START.get(serial)   # เผื่อ timeout รวมของ cycle ยังทำงานได้

    DEVICE_IN_NEWSTAGE[serial] = True
    _prev_fixout = DEVICE_DISABLE_FIXOUT.get(serial, False)
    DEVICE_DISABLE_FIXOUT[serial] = True   # ห้าม Back spam / กด cancel แทรกระหว่างขั้นตอนนี้

    def _check_fixclearplay8(img_chk, step_no):
        """เจอ fixclearplay8 ระหว่าง step 1/2 → ปิดแอพ เปิดใหม่ เริ่มจาก play8 อีกรอบ
        (trigger_restart_from_play8 จะ force-stop + raise RestartFromPlay8Exception ให้เอง)"""
        if step_no not in (1, 2) or img_chk is None:
            return
        if img_search_best(img_chk, os.path.join(IMG_DIR, "fixclearplay8.bmp"), threshold=0.9):
            on_fc = DEVICE_FILE_ASSIGNMENTS.get(serial)
            gui_log(serial, f"เจอ fixclearplay8 ตอน new-stageplay8-{step_no} → ปิดแอพเปิดใหม่ เริ่มจาก play8",
                    step="FixClearPlay8", status="working")
            trigger_restart_from_play8(device, serial, on_fc,
                                       reason=f"fixclearplay8 ตอน new-stageplay8-{step_no}")

    try:
        for _ns in (1, 2, 3):
            _ns_name = f"new-stageplay8-{_ns}.bmp"
            _ns_path = os.path.join(IMG_DIR, _ns_name)
            # รูปของ step ถัดไป (ตัวที่ 3 ไม่มีถัดไป)
            _nx_name = f"new-stageplay8-{_ns + 1}.bmp" if _ns < 3 else None
            _nx_path = os.path.join(IMG_DIR, _nx_name) if _nx_name else None

            # 1) รอจนเจอตัวนี้ (ไม่มี timeout — หาไปเรื่อยๆ จนกว่าจะเจอ ห้ามยอมแพ้)
            #    เฉพาะตัวที่ 1: แวะเช็ค checkponit-play8 ด้วย (ตัวยืนยันว่าอยู่หน้าอีเวนต์แล้ว)
            #    พอเจอ new-stageplay8-1 แล้ว = เลิกเช็ค checkpoint ที่เหลือไล่ตามลำดับอย่างเดียว
            #    ถ้าเจอ "ตัวถัดไป" ก่อน = ตัวนี้ผ่านไปแล้ว → ไปทำตัวถัดไปทันที (ไม่รอเก้อ)
            gui_log(serial, f"หา {_ns_name} (หาไปเรื่อยๆ จนกว่าจะเจอ)...", step=f"NewStage {_ns}")
            _cp8_logged = False
            _skip_to_next = False
            while True:
                check_device_reset(serial, cycle_start)
                img_ns = fast_screencap(device)
                _check_fixclearplay8(img_ns, _ns)
                if img_ns is not None:
                    if img_search_best(img_ns, _ns_path, threshold=0.9):
                        break
                    if _nx_path and img_search_best(img_ns, _nx_path, threshold=0.9):
                        gui_log(serial, f"เจอ {_nx_name} ก่อน — {_ns_name} ผ่านไปแล้ว ไปตัวถัดไปทันที",
                                step=f"NewStage {_ns}")
                        _skip_to_next = True
                        break
                    if _ns == 1 and not _cp8_logged and img_search_best(img_ns, os.path.join(IMG_DIR, "checkponit-play8.bmp"), threshold=0.9):
                        gui_log(serial, "เจอ checkponit-play8 — อยู่หน้าอีเวนต์แล้ว รอ new-stageplay8-1...", step="NewStage")
                        _cp8_logged = True
                time.sleep(0.4)
            if _skip_to_next:
                continue

            # 2) กดตัวนี้ไปเรื่อยๆ (~2 ครั้ง/วิ) "จนกว่ารูปนี้จะหายไป" ค่อยไปตัวถัดไป
            #    (ยืนยันหายครบ 1 วิ กัน animation กระพริบแล้วเผลอไปต่อทั้งที่ยังอยู่)
            gui_log(serial, f"เจอ {_ns_name} — กดไปเรื่อยๆ จนกว่าจะหาย", step=f"NewStage {_ns}")
            _click_n = 0
            _last_click = 0.0
            _gone_since = None
            while True:
                check_device_reset(serial, cycle_start)
                img_ns = fast_screencap(device)
                _check_fixclearplay8(img_ns, _ns)
                if img_ns is None:
                    time.sleep(0.3)
                    continue
                pts_ns = img_search_best(img_ns, _ns_path, threshold=0.9)
                if pts_ns:
                    _gone_since = None
                    if time.time() - _last_click >= 0.5:
                        x_ns, y_ns = pts_ns[0]
                        device.shell(f"input swipe {x_ns} {y_ns} {x_ns} {y_ns} 100")
                        _last_click = time.time()
                        _click_n += 1
                        if _click_n % 5 == 1:
                            gui_log(serial, f"กด {_ns_name} ({x_ns},{y_ns}) ครั้งที่ {_click_n}", step=f"NewStage {_ns}")
                else:
                    if _gone_since is None:
                        _gone_since = time.time()
                    elif time.time() - _gone_since >= 1.0:
                        gui_log(serial, f"{_ns_name} หายแล้ว (กดไป {_click_n} ครั้ง) → ไปหาตัวถัดไป",
                                step=f"NewStage {_ns} Gone")
                        break
                time.sleep(0.25)

        gui_log(serial, "new-stageplay8 ครบทั้ง 3 ตัวตามลำดับแล้ว → ไปต่อ", step="NewStage Done")
        DEVICE_NEWSTAGE_DONE[serial] = True
        return True
    finally:
        DEVICE_IN_NEWSTAGE[serial] = False
        DEVICE_DISABLE_FIXOUT[serial] = _prev_fixout


def click_next_until_gone(device, cycle_start, serial, x, y, stuck_secs=5.0, timeout=60.0, tag="Next"):
    """กด next.bmp — ค้างเกิน 5 วิ กดซ้ำจนหาย (wrapper ของ click_img_until_gone)"""
    return click_img_until_gone(device, cycle_start, serial,
                                os.path.join(IMG_DIR, "next.bmp"), x, y,
                                stuck_secs=stuck_secs, timeout=timeout, tag=tag)

def find_and_click_optional(device, cycle_start, serial, img_name, secs=5.0,
                            threshold=0.8, tag="Optional", settle=1.0):
    """แวะหารูปนี้ภายใน `secs` วิ — เจอ → กด แล้วไปต่อ | ไม่เจอ → ข้ามไปต่อตามปกติ (ไม่ถือว่าผิด)
    ใช้กับ popup ที่ "บางทีก็โผล่ บางทีก็ไม่โผล่". คืน True ถ้าเจอและกดแล้ว"""
    gui_log(serial, f"แวะหา {img_name} ({secs:.0f}s)...", step=f"{tag} Wait")
    deadline = time.time() + secs
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, img_name), threshold=threshold)
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, f"Clicked {img_name} at ({x},{y})", step=f"{tag} Click")
                time.sleep(settle)
                return True
        time.sleep(0.3)
    gui_log(serial, f"{img_name} ไม่เจอใน {secs:.0f}s — ข้าม ไปต่อ", step=f"{tag} Skip")
    return False

def _g500_checkpoint_then_next(device, cycle_start, serial, cp_secs=30, next_secs=20, tag="G500"):
    """หา checkpointgacha.bmp → เจอแล้วหา next.bmp → กด (ใช้ปิดหน้าผลสุ่มก่อนไป step ต่อไป)
    คืน True ถ้ากด next สำเร็จ / False ถ้าไม่เจอ checkpointgacha หรือ next"""
    gui_log(serial, f"หา checkpointgacha ({cp_secs:.0f}s)...", step=f"{tag} CP")
    found_cp = False
    dl_cp = time.time() + cp_secs
    while time.time() < dl_cp:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None and img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp")):
            found_cp = True
            break
        time.sleep(0.3)
    if not found_cp:
        gui_log(serial, "ไม่เจอ checkpointgacha — ข้ามการกด next", step=f"{tag} CP Miss")
        return False

    gui_log(serial, "เจอ checkpointgacha → หา next.bmp แล้วกด", step=f"{tag} CP")
    dl_next = time.time() + next_secs
    while time.time() < dl_next:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts_n = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
            if pts_n:
                x_n, y_n = pts_n[0]
                # กด next แล้วถ้ายังค้างเกิน 8 วิ กดซ้ำจนหาย
                click_next_until_gone(device, cycle_start, serial, x_n, y_n, tag=f"{tag} Next")
                return True
        time.sleep(0.3)
    gui_log(serial, "ไม่เจอ next.bmp", step=f"{tag} Next Miss")
    return False

def _g500_check_coin_and_collect(device, cycle_start, serial, original_name, file_path, img):
    """GACHA500 step1: สแกน coin จากภาพ img (region 52,10,106,41).
    coin >= COIN_GACHA_THRESHOLD → เก็บไฟล์เข้า coin<threshold>+ (ชื่อ [coin]+เดิม) + release
      แล้ว raise GachaCoinCollectedException (จบบัญชี ไม่สุ่ม)
    coin <  COIN_GACHA_THRESHOLD → return เฉยๆ (ไปสุ่ม loop ต่อ)"""
    import re
    coin_val = _read_coin_from_img(img, serial)
    gui_log(serial, f"🪙 อ่าน coin (ที่ new-gacha1) = {coin_val} | เกณฑ์เก็บ {COIN_GACHA_THRESHOLD}", step="G500-Coin")
    if coin_val < COIN_GACHA_THRESHOLD:
        return
    _m = re.match(r"^\[\d+\]\+(.+)$", original_name)
    base = _m.group(1) if _m else original_name
    final_name = f"[{coin_val}]+{base}"
    coin_dir = f"coin{COIN_GACHA_THRESHOLD}+"
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)
    dest = os.path.join(coin_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(1)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            _safe_copy(file_path, dest)   # สร้างโฟลเดอร์ปลายทางให้เอง
            os.remove(file_path)
            gui_log(serial, f"✅ Coin {coin_val} ≥ {COIN_GACHA_THRESHOLD} → เก็บ {final_name} เข้า {coin_dir}", step="Coin Collected", status="working")
        except Exception as _e:
            gui_log(serial, f"⚠️ เก็บไฟล์ coin ล้มเหลว: {_e}", step="Coin Sort Error")
    release_file(original_name)
    raise GachaCoinCollectedException(f"coin {coin_val} >= {COIN_GACHA_THRESHOLD}")


def gacha_find_navigate_then_find_hero(device, cycle_start, serial, original_name, file_path, coin_prefix=None):
    """
    เส้นทางหลังสุ่ม gacha ปกติ (Gacha+Find) ก่อนเริ่มค้นหา fin1:
      1) เช็คหา next.bmp ก่อน (8 วิ) — เจอ = กดจนกว่าจะหายไป (ปิดหน้าผลสุ่มที่ค้าง)
      2) กด Back รัวๆ จนกว่าจะเจอ cancel.bmp → คลิก (ไม่มี timeout — เจอ cancel เท่านั้นถึงหยุด)
      3) เริ่ม find_hero_mode (fin1...) แล้วแนบเลขเหรียญที่สแกนไว้ "ก่อน" gacha ตอน export
    coin_prefix: เลขเหรียญที่สแกนไว้ตั้งแต่ก่อนเริ่ม gacha (ถ้าเปิด CHECK_COIN)
    """
    # 1. เช็ค next.bmp ก่อน — เจอ = กดจนกว่าจะหายไป แล้วค่อยไปกด Back
    gui_log(serial, "เช็คหา next.bmp ก่อน (8s)...", step="Next Check")
    dl_next_chk = time.time() + 8
    while time.time() < dl_next_chk:
        check_device_reset(serial, cycle_start)
        img_nc = get_screen_capture(device)
        if img_nc is not None:
            pts_nc = img_search(img_nc, os.path.join(IMG_DIR, "next.bmp"))
            if pts_nc:
                x_nc, y_nc = pts_nc[0]
                gui_log(serial, f"เจอ next.bmp — กดจนกว่าจะหาย ({x_nc},{y_nc})", step="Next Check")
                click_next_until_gone(device, cycle_start, serial, x_nc, y_nc,
                                      stuck_secs=3.0, timeout=None, tag="Next Check")
                break
        time.sleep(0.3)
    else:
        gui_log(serial, "ไม่เจอ next.bmp ใน 8s — ไปกด Back เลย", step="Next Check Miss")

    # 2. กด Back รัวๆ จนกว่าจะเจอ cancel.bmp → คลิก แล้วค่อยไปทำ find ต่อ
    gui_log(serial, "Spamming Back until cancel.bmp...", step="Back Spam")
    while True:
        check_device_reset(serial, cycle_start)
        device.shell("input keyevent 4")  # KEYCODE_BACK
        time.sleep(0.6)
        try:
            img = get_screen_capture(device)
        except ResetGachaException:
            # popup กาชาเด้งระหว่างกด Back → get_screen_capture เคลียร์ให้แล้ว กด Back ต่อ
            continue
        if img is not None:
            pts_c = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
            if pts_c:
                x, y = pts_c[0]
                gui_log(serial, f"cancel.bmp found at ({x},{y})! Clicked, stopping Back spam.", step="Cancel OK")
                click_cancel_until_gone(device, serial, x, y, step="Cancel OK")
                break

    # 3. สแกนเหรียญใหม่อีกรอบก่อนทำ fin (อัปเดตเลขหลังสุ่มไปแล้ว เพราะเหรียญลดลง)
    if CHECK_COIN == 1:
        gui_log(serial, "Re-scanning coins after gacha (updated value)...", step="Coin Re-scan", status="working")
        new_coin = scan_coin_number(device, cycle_start, serial)
        if new_coin is not None:
            coin_prefix = new_coin

    # 4. เริ่มค้นหา fin1... (แนบเลขเหรียญที่สแกนใหม่หลังสุ่มตอน export ถ้ามี)
    return find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix)


def check_unlock_hero_before_next(device, cycle_start, serial, loop_num):
    """เจอ next.bmp แล้ว "อย่าเพิ่งกด" — แวะหา unlock-hero1.bmp สูงสุด 8 วิ ก่อน
    (popup ปลดล็อกฮีโร่หลังสุ่ม): เจอ → กดปิด / ไม่เจอครบ 8 วิ → ข้ามไปให้กด next ต่อได้เลย"""
    gui_log(serial, f"[Loop {loop_num}] next found — checking unlock-hero1.bmp (8s) before clicking next...", step="Check-Unlock")
    deadline_unlock = time.time() + 8
    while time.time() < deadline_unlock:
        check_device_reset(serial, cycle_start)
        img_unlock = get_screen_capture(device)
        if img_unlock is not None:
            pts_unlock = img_search(img_unlock, os.path.join(IMG_DIR, "unlock-hero1.bmp"))
            if pts_unlock:
                device.shell("input keyevent 4")
                gui_log(serial, f"[Loop {loop_num}] unlock-hero1.bmp found! Pressed back (once).", step="Unlock-Hero")
                time.sleep(2)
                return True
        time.sleep(0.5)
    return False

def gacha_free_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=None):
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

    def _check_fixgachafree(img_fg=None, cycle_start_time=None):
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
                deadline2 = time.time() + 15
                while time.time() < deadline2:
                    if cycle_start_time is not None:
                        check_device_reset(serial, cycle_start_time)
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
                deadline3 = time.time() + 15
                while time.time() < deadline3:
                    if cycle_start_time is not None:
                        check_device_reset(serial, cycle_start_time)
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
    #    gacha1: หาไปเรื่อยๆ ไม่มี timeout — ไม่เจอครบ 20 วิเมื่อไหร่ กด fixcode ใหม่
    #            แล้วกลับไปเริ่มหา gacha1 ต่อ (นับ 20 วิใหม่ทุกครั้งที่กด)
    #    gacha2: ตามเดิม (รอ 30 วิ)
    for i in range(1, 3):
        name = f"gacha{i}.bmp"
        gui_log(serial, f"Waiting {name}...", step=name)
        deadline = None if i == 1 else time.time() + 30
        no_find_since = time.time()   # เริ่มจับเวลา "หาไม่เจอ" (ใช้เฉพาะ gacha1)
        while deadline is None or time.time() < deadline:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()  # priority #1
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, name))
                if not pts and i == 1 and time.time() - no_find_since >= 20:
                    # ไม่เจอ gacha1 ครบ 20 วิ → กด fixcode ใหม่ (สูงสุด 5 ครั้ง / หยุดเมื่อรูปหาย)
                    gui_log(serial, "ไม่เจอ gacha1 ครบ 20 วิ → กด fixcode ใหม่", step="gacha1 FixCode")
                    fx_n = 0
                    while fx_n < 5:
                        check_device_reset(serial, cycle_start)
                        img_fx = get_screen_capture(device)
                        pts_fx = img_search_best(img_fx, os.path.join(IMG_DIR, "fixcode.bmp"), threshold=0.9) if img_fx is not None else []
                        if not pts_fx:
                            break
                        x_fx, y_fx = pts_fx[0]
                        device.shell(f"input swipe {x_fx} {y_fx} {x_fx} {y_fx} 100")
                        fx_n += 1
                        gui_log(serial, f"กด fixcode ({x_fx},{y_fx}) ครั้งที่ {fx_n}/5", step="gacha1 FixCode")
                        time.sleep(0.6)
                    if fx_n == 0:
                        gui_log(serial, "ไม่เจอ fixcode บนจอ — หา gacha1 ต่อ", step="gacha1 FixCode")
                    no_find_since = time.time()   # เริ่มนับ 20 วิใหม่ แล้วกลับไปหา gacha1 ต่อ
                    time.sleep(1.0)
                    continue
                if pts:
                    x, y = pts[0]
                    if i == 2:
                        # gacha2 — กดซ้ำไปเรื่อยๆ จนกว่าจะหายไปจริง ค่อยไปต่อ
                        click_img_until_gone(device, cycle_start, serial,
                                             os.path.join(IMG_DIR, name),
                                             x, y, stuck_secs=3.0, timeout=60.0, tag="gacha2")
                        # หลัง gacha2 → แวะหา ad-rewardfix1 5 วิ (ไม่เจอ = ข้ามไปต่อ ไม่เป็นไร)
                        find_and_click_optional(device, cycle_start, serial,
                                                "ad-rewardfix1.bmp", secs=5.0, tag="ad-reward")
                    else:
                        # gacha1 — กดซ้ำไปเรื่อยๆ จนกว่าจะหายไป "จริง" (ยืนยันหายครบ 2.5s
                        # กัน animation กระพริบทำให้เผลอไป gacha2 ทั้งที่ยังอยู่) ค่อยไปหา gacha2
                        click_img_until_gone(device, cycle_start, serial,
                                             os.path.join(IMG_DIR, name),
                                             x, y, stuck_secs=3.0, timeout=60.0,
                                             tag="gacha1", gone_secs=2.5)
                    time.sleep(1.2)
                    break
            time.sleep(0.3)

    # 2. ทำลูปสุ่มกาชาฟรีตามจำนวนที่กำหนดใน config
    target_config = parse_hero_config(HERO_LIST_FREE)
    target_heroes = list(target_config.keys())
    raw_found_heroes = []  # เก็บชื่อฮีโร่ที่เจอจากทุก loop
    end_swip_detected = False
    end_gachafree_detected = False  # เจอ endgachafree1 → จบ Gacha Free ทันที

    # ── เลือกว่าจะหา popup ตัวไหน ──────────────────────────────
    #   เปิด GACHA_FREE=1 + FIND_HERO=1 (เปิดหาตัว) → หา no-coingachafree1.bmp
    #        (coin ไม่พอ → กด Back 1 ครั้ง แล้วเลื่อนหาต่อ ไม่จบรอบ)
    #   ไม่เปิดหาตัว → ไม่ต้องหา no-coin เลย ใช้ endgachafree1.bmp แทน (เจอ = จบ Gacha Free ทันที)
    check_nocoin_free = (GACHA_FREE == 1 and FIND_HERO == 1)
    gui_log(serial, f"GachaFree popup mode: {'no-coingachafree1 (find=1)' if check_nocoin_free else 'endgachafree1 (find=0)'}",
            step="Free Mode")

    for loop_num in range(1, GACHA_FREE_LOOPS + 1):
        if end_swip_detected or end_gachafree_detected:
            break
        gui_log(serial, f"=== Gacha Free Loop {loop_num}/{GACHA_FREE_LOOPS} ===", step=f"Loop {loop_num}")

        # 2a. เลื่อนหา gachafree1.bmp (เช็คก่อน → ไม่เจอ → เลื่อน, ครบ 10 รอบ = ข้าม loop นี้)
        gui_log(serial, f"[Loop {loop_num}] Looking for gachafree1.bmp...", step="Swipe Free")
        found_free = False
        miss_count = 0
        max_miss = 10
        next_first_seen = None  # ติดตาม next.bmp ค้าง
        endswip_first_seen = None  # ติดตาม endswip.bmp ค้าง
        nocoin_free_handled = False  # กด Back ปิด no-coingachafree1 ไปแล้วหรือยัง (กดรอบเดียว)

        while miss_count < max_miss:
            check_device_reset(serial, cycle_start)

            img = get_screen_capture(device)
            if img is not None:
                if _check_fixgachafree(img, cycle_start):
                    miss_count = 0  # รีเซ็ตการนับเผื่อให้มันหา gachafree1 ต่อได้โดยไม่หลุด loop
                    continue
                # === Priority: เช็ค endgachafree1.bmp → จบ Gacha Free ทันที ===
                if img_search(img, os.path.join(IMG_DIR, "endgachafree1.bmp"), threshold=0.95):
                    gui_log(serial, f"[Loop {loop_num}] 🛑 เจอ endgachafree1 → จบ Gacha Free ทันที", step="End GachaFree")
                    end_gachafree_detected = True
                    break
                # === Priority: เช็ค no-coingachafree1.bmp (coin ไม่พอ) → กด Back 1 ครั้ง แล้วเลื่อนหาต่อปกติ ===
                #     หาเฉพาะตอนเปิดหาตัว (GACHA_FREE=1 + FIND_HERO=1) เท่านั้น
                if check_nocoin_free:
                    if img_search(img, os.path.join(IMG_DIR, "no-coingachafree1.bmp"), threshold=0.95):
                        if not nocoin_free_handled:
                            device.shell("input keyevent 4")   # Back 1 ครั้ง
                            gui_log(serial, f"[Loop {loop_num}] เจอ no-coingachafree1 → กด Back 1 ครั้ง แล้วเลื่อนหาต่อ", step="NoCoin Free")
                            nocoin_free_handled = True
                            time.sleep(1.5)
                            continue
                    else:
                        nocoin_free_handled = False   # หายแล้ว → เจอใหม่ค่อยกด Back อีกรอบ
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
            device.shell("input swipe 618 308 54 306 6000")
            time.sleep(2.0)

        if not found_free:
            if end_swip_detected or end_gachafree_detected:
                break
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not found after {max_miss} swipes, skipping loop", step="Skip")
            continue  # ข้ามไป loop ถัดไป (หรือจบถ้า loop 2)

        # 2b. รอ gachafree2.bmp → กดจนกว่าจะหายไป (timeout 15s → file-error)
        #     แวะหา no-coingachafree1 ด้วย — เจอ = กด Back 1 ครั้ง แล้วกลับไปเลื่อนหาใหม่ (ไม่ใช่ file-error)
        gui_log(serial, f"[Loop {loop_num}] Waiting gachafree2.bmp...", step="gachafree2")
        deadline_gf2 = time.time() + 15
        clicked_gf2 = False
        nocoin_free_gf2 = False
        while time.time() < deadline_gf2:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()  # priority #1
            img = get_screen_capture(device)
            if img is not None:
                # เจอ endgachafree1 → จบ Gacha Free ทันที (ไม่ส่ง file-error)
                if img_search(img, os.path.join(IMG_DIR, "endgachafree1.bmp"), threshold=0.95):
                    gui_log(serial, f"[Loop {loop_num}] 🛑 เจอ endgachafree1 (ตอนรอ gachafree2) → จบ Gacha Free ทันที", step="End GachaFree")
                    end_gachafree_detected = True
                    break
                # coin ไม่พอ (เฉพาะเปิดหาตัว) → กด Back 1 ครั้ง แล้วเลิกรอ gachafree2 (ไปเลื่อนหา gachafree1 ใหม่)
                if check_nocoin_free and not clicked_gf2 and img_search(img, os.path.join(IMG_DIR, "no-coingachafree1.bmp"), threshold=0.95):
                    device.shell("input keyevent 4")   # Back 1 ครั้ง
                    gui_log(serial, f"[Loop {loop_num}] เจอ no-coingachafree1 (ตอนรอ gachafree2) → กด Back 1 ครั้ง → เลื่อนหาใหม่", step="NoCoin Free")
                    time.sleep(1.5)
                    nocoin_free_gf2 = True
                    break
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

        # เจอ endgachafree1 → จบลูปสุ่มฟรีทั้งหมด ไปขั้นตอนจบรอบ (ต้องเช็คก่อน file-error)
        if end_gachafree_detected:
            break

        # เจอ no-coingachafree1 → ข้าม loop นี้ ไปเลื่อนหา gachafree1 ใหม่ (ไม่ส่ง file-error)
        if nocoin_free_gf2:
            continue

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
                    _safe_copy(file_path, dest)
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
                        cprint(f"[{serial}] GachaFree Loop{loop_num} OCR: {display_text}")
 
                        for h in target_heroes:
                            if is_hero_match(h, ocr_text):
                                h_clean = h.strip()
                                raw_found_heroes.append(h_clean)
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

        # 2e. รอ next.bmp → เจอแล้ว "อย่าเพิ่งกด": แวะหา unlock-hero1 (8 วิ) ก่อน
        #     เจอ popup → กดปิด / ไม่เจอ → ค่อยกลับมากด next (เช็คแค่ครั้งเดียวต่อ loop)
        gui_log(serial, f"[Loop {loop_num}] Waiting next.bmp...", step="Next")
        unlock_checked = False
        if NOSCAN == 1:
            # NOSCAN mode: หา next.bmp ไปเรื่อยๆจนกว่าจะเจอ (ไม่มี timeout)
            while True:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()  # priority #1
                img = get_screen_capture(device)
                if img is not None:
                    pts = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                    if pts:
                        if not unlock_checked:
                            check_unlock_hero_before_next(device, cycle_start, serial, loop_num)
                            unlock_checked = True
                            continue   # แคปใหม่หา next อีกรอบ (พิกัดอาจขยับหลังปิด popup)
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
                        if not unlock_checked:
                            check_unlock_hero_before_next(device, cycle_start, serial, loop_num)
                            unlock_checked = True
                            deadline_next = time.time() + 15   # ต่ออายุ timeout หลังเสียเวลาเช็ค 8 วิ
                            continue   # แคปใหม่หา next อีกรอบ (พิกัดอาจขยับหลังปิด popup)
                        x, y = pts[0]
                        gui_log(serial, f"[Loop {loop_num}] next.bmp found! Clicking ({x},{y})", step="Next OK")
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(1.2)
                        break
                time.sleep(0.3)

    # 3. จบตามลูปที่ตั้งค่า → Sort file
    if GACHA_CHECK == 1:
        gui_log(serial, "GachaFree finished. Gacha+Check mode active: waiting for backhome...", step="GachaFree Done")
        return navigate_home_then_find_hero(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix)

    # ── เปิด Check Coin → กลับหน้า Home แล้วสแกนเหรียญ "ก่อน" ส่งไฟล์ออก ──
    #    (เหรียญเปลี่ยนไปหลังสุ่มฟรี → ต้องอ่านค่าล่าสุด แล้วค่อยแนบเลขไปกับชื่อไฟล์ตอน export)
    if CHECK_COIN == 1:
        gui_log(serial, "CheckCoin → กลับหน้า Home เพื่อสแกนเหรียญก่อนส่งไฟล์ออก...", step="Coin Before Export", status="working")
        # จบเพราะ endgachafree1 และ popup ยังค้างอยู่ → กด Back ปิดก่อน ไม่งั้นหา backhome ไม่เจอ
        if end_gachafree_detected:
            img_end = get_screen_capture(device)
            if img_end is not None and img_search(img_end, os.path.join(IMG_DIR, "endgachafree1.bmp"), threshold=0.95):
                device.shell("input keyevent 4")
                gui_log(serial, "ปิด popup endgachafree1 ก่อนกลับหน้า Home", step="Close Popup")
                time.sleep(1.5)
        navigate_home(device, cycle_start, serial)
        new_coin = scan_coin_number(device, cycle_start, serial)
        if new_coin is not None:
            coin_prefix = new_coin

    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    # ชื่อไฟล์ตอน export = user_code จริงจากข้างในไฟล์ .dat (อ่านไม่ได้ → ใช้ชื่อเดิมแบบเดิม)
    clean_orig = export_base_name(file_path, original_name, strip_dash=True)

    # ถ้า NOSCAN=1 → ส่งไป fast-random/ เสมอ
    if NOSCAN == 1:
        dest_dir = FAST_RANDOM_DIR
        final_name = clean_orig
        gui_log(serial, f"NOSCAN → {dest_dir}/{final_name}", step="Fast Random")
    elif raw_found_heroes:
        from collections import Counter
        counts = Counter(raw_found_heroes)
        found_heroes = []
        for h, count in counts.items():
            req = target_config.get(h, 1)
            if count >= req:
                if count > 1:
                    found_heroes.append(f"{h}x{count}")
                else:
                    found_heroes.append(h)

        if found_heroes:
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
            gui_log(serial, "GachaFree: No hero matched (required counts not met)", step="No Match")
    else:
        # สแกน OCR แล้วแต่ไม่เจอชื่อฮีโร่เลยสักรอบ → random-fail (กันตัวแปรไม่ถูกเซ็ต)
        dest_dir = RANDOM_FAIL_DIR
        final_name = clean_orig
        gui_log(serial, "GachaFree: No hero found in any loop", step="No Match")

    # แนบเลขเหรียญ "ไว้หน้าชื่อไฟล์" แบบเดียวกับโหมด Check Coin (เฉพาะตอนเปิด CHECK_COIN)
    #   เช่น  ASCV610367086.dat -> [500]+ASCV610367086.dat
    if coin_prefix:
        import re as _re_gf
        _base = _re_gf.sub(r"^\[\d+\]\+", "", final_name)   # กัน [เลข]+ ซ้อนถ้าชื่อมีอยู่แล้ว
        _base = _re_gf.sub(r"-\[\d+\]", "", _base)          # กันเลขแบบต่อท้ายเก่าปนมาด้วย
        final_name = f"[{coin_prefix}]+{_base}"
        gui_log(serial, f"🪙 Coins: {coin_prefix} -> {final_name}", step="Coin Match")

    dest = os.path.join(dest_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(1)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            _safe_copy(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted (GachaFree): {dest_dir}", step="Sorted", status="working")
        except Exception as me:
            gui_log(serial, f"⚠️ GachaFree Sort failed: {me}", step="Sort Error")
        
        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    return True

def check_coin_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=None):
    """
    Check Coin sequence:
    1. ใช้เลขเหรียญที่สแกนไว้ "ก่อน" แล้ว (coin_prefix) — ถ้าไม่มีค่อยสแกนสด ณ จุดนี้
    2. Rename file: [digits]+original_name (stripping any old [digits]+ from original name to avoid nesting)
    3. Move file to 'check-coin' directory
    4. Force-stop game and return True
    """
    import re

    # 1. ใช้เลขเหรียญที่สแกนไว้ก่อนหน้า (ถ้ามี) — ไม่ต้องสแกนซ้ำ
    coin_number = coin_prefix

    # 1b. กรณีไม่มีเลขที่สแกนไว้ → สแกนสด ณ จุดนี้ (fallback)
    if not coin_number:
        gui_log(serial, "No pre-scanned coin — waiting checkpointcoin...", step="Coin Wait", status="working")
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
                    _safe_copy(file_path, dest)
                    os.remove(file_path)
                except Exception as e:
                    cprint(f"[{serial}] Failed to move file to random-fail: {e}")
            release_file(original_name)
            return True

        gui_log(serial, "checkpointcoin detected! Scanning coins...", step="Scanning Coin")
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

    # 2. Rename file and strip old [digits]+ prefix
    match = re.match(r"^\[\d+\]\+(.+)$", original_name)
    if match:
        base_name = match.group(1)
    else:
        base_name = original_name

    final_name = f"[{coin_number}]+{base_name}"
    gui_log(serial, f"🪙 Coins: {coin_number} -> {final_name}", step="Coin Match")
    cprint(f"[{serial}] Coin Scan Result: {coin_number} -> file: {final_name}")

    # 3. Move file to 'check-coin' directory
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
            _safe_copy(file_path, dest)
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
            DEVICE_DISABLE_FIXOUT[serial] = False   # เริ่ม cycle ใหม่ → เปิด fixout check กลับ (ช่วง login ต้องใช้)
            DEVICE_IN_GACHA[serial] = False         # เริ่ม cycle ใหม่ → ยังไม่เข้ากาชา (กันค้างจากรอบก่อนที่หลุด exception)
            DEVICE_IN_NEWSTAGE[serial] = False      # เริ่ม cycle ใหม่ → เคลียร์ธงกัน new-stage ซ้อน
            DEVICE_NEWSTAGE_DONE[serial] = False    # ไฟล์ใหม่ = ยังไม่ได้ทำอีเวนต์ new stage ของรอบนี้
            check_device_reset(serial)

            # ── Reload config ต้น cycle (ปกติ config watcher โหลดให้ realtime อยู่แล้ว
            #    อันนี้เป็นตัวกันพลาดเผื่อ watcher ตาย/ไฟล์ mtime ไม่ขยับ) ──
            if not apply_config_now("cycle"):
                gui_log(serial, "⚠️ Config reload failed", step="Reload Error")

            # ── ด่านเช็ค device online ก่อนเริ่ม cycle ──
            # กัน 2 อาการ: (1) spin วน cycle รัวๆ ตอนเครื่องตาย
            #              (2) เริ่มทำงาน/ย้ายไฟล์มั่วบนเครื่องที่ offline/ค้าง
            # ยังไม่ได้ pick file (original_name=None) → continue ปลอดภัย ไม่มีไฟล์ค้าง
            if not is_device_online(device):
                off_since = DEVICE_OFFLINE_SINCE.setdefault(serial, time.time())
                off_for   = time.time() - off_since
                gui_log(serial, f"⚠️ Device OFFLINE — reconnecting & waiting... ({off_for:.0f}s)",
                        step="Offline", status="stuck")
                try_reconnect_device(serial)

                # reconnect ติดเลย → กลับไปทำงานต่อ ไม่ต้องรีสตาร์ทอะไร
                if is_device_online(device):
                    DEVICE_OFFLINE_SINCE.pop(serial, None)
                    gui_log(serial, "✅ กลับมา online แล้ว — เริ่ม cycle ใหม่", step="Online", status="working")
                    continue

                # offline ติดกันนานเกินกำหนด = adb connect ไม่ช่วยแล้ว (instance ค้าง/ดับไปเอง)
                # → ปิด-เปิด MuMu "เฉพาะเครื่องนี้ตัวเดียว" แล้วเริ่มกระบวนการใหม่ตั้งแต่ต้น
                if AUTO_RESTART_OFFLINE and off_for >= OFFLINE_RESTART_AFTER:
                    if restart_mumu_instance(serial):
                        DEVICE_OFFLINE_SINCE.pop(serial, None)
                        continue   # กลับไปต้น while → เช็ค online → เริ่ม cycle ใหม่ตามปกติ

                time.sleep(10)
                continue

            # online อยู่ — ถ้าเพิ่งฟื้นจาก offline ให้ล้างตัวจับเวลาทิ้ง
            if DEVICE_OFFLINE_SINCE.pop(serial, None) is not None:
                gui_log(serial, "✅ กลับมา online แล้ว", step="Online", status="working")

            gui_log(serial, "--- Starting New Cycle ---", step="New Cycle", status="working")

            # เช็ค root ก่อนเข้าเกม (ลบข้อมูล + push + เข้าเกม)
            if not is_root(device):
                gui_log(serial, "root ยังไม่เปิด → เปิด root...", step="Root Check")
                device = enable_root(device)

            # 0. Force-stop
            gui_log(serial, "Force closing app...", step="Cleanup", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            # ── restart-from-play8: เจอ fixclear หลัง login (หรือ box1 หายเกิน 5 ครั้ง) →
            #    เปิดเกมเดิมแล้วไปเริ่มที่ play8 เลย โดย "ไม่ล้าง AUTH / ไม่ push ไฟล์ซ้ำ" (เก็บ login เดิมไว้)
            #    แล้วปล่อยให้วิ่งเข้า launch → loop play8 → เฟสต่อไปตามปกติ ──
            restart_p8 = DEVICE_RESTART_PLAY8.pop(serial, None)
            if restart_p8:
                file_path, original_name = restart_p8
                DEVICE_FILE_ASSIGNMENTS[serial] = original_name
                cycle_start = time.time()
                DEVICE_CYCLE_START[serial] = cycle_start
                DEVICE_PAST_LOGIN[serial] = True   # ผ่าน login แล้ว (ถ้าเจอ fixclear อีกก็ยัง restart-play8 ไม่ login ใหม่)
                gui_log(serial, f"Restart from play8 (same file, keep login, no re-push): {original_name}",
                        step="Restart play8", status="working")
            else:
                DEVICE_RESTART_PLAY8_COUNT.pop(serial, None)   # ไฟล์ใหม่/เข้าใหม่ → รีเซ็ตตัวนับ fixclear-after-login
                # 0.5 ลบ save data เดิมออกก่อนเริ่มวนไฟล์ใหม่ (กันข้อมูล id เก่าค้าง)
                device.shell("su -c 'rm -f /data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat'")
                time.sleep(0.3)

                # 1. Pick file — ถ้ามีไฟล์ค้าง "เข้าใหม่" จาก fixclear → ใช้ไฟล์เดิม (ไม่หยิบใหม่/ไม่ปล่อย lock)
                pending = DEVICE_REENTER_FILE.pop(serial, None)
                if pending:
                    file_path, original_name = pending
                    gui_log(serial, f"Re-entering same file: {original_name}", step="Re-enter", status="working")
                else:
                    DEVICE_REENTER_COUNT.pop(serial, None)   # ไฟล์ใหม่ → รีเซ็ตตัวนับ re-enter
                    file_path, original_name = pick_next_file()
                    if file_path is None:
                        gui_log(serial, "No files left — waiting...", step="No Files", status="idle")
                        time.sleep(3)
                        continue

                gui_log(serial, f"File: {original_name}", step="File OK", status="working")
                DEVICE_FILE_ASSIGNMENTS[serial] = original_name
                cycle_start = time.time()
                DEVICE_CYCLE_START[serial] = cycle_start
                DEVICE_PAST_LOGIN[serial] = False   # ไฟล์ใหม่/เข้าใหม่ → ยังไม่ผ่าน login

                # 2. Push file
                gui_log(serial, "Pushing file...", step="Push")
                if not push_dat_to_device(device, file_path):
                    gui_log(serial, "Push FAILED!", step="Error", status="stuck")
                    release_file(original_name)
                    time.sleep(5)
                    continue

                # delay 5 วิ หลัง push เสร็จ ก่อนเปิดเกม — กันเคสไฟล์ยังเขียนไม่เสร็จ/ไม่เข้าจริง
                gui_log(serial, "Push OK — delaying 5s before launch...", step="Push Settle")
                time.sleep(5)



            # 3. Launch with Black Screen Check (45s check, threshold > 85% dark -> force-stop & relaunch)
            gui_log(serial, "Launching PES...", step="Launch", status="working")
            
            for black_attempt in range(3):
                launch_game(device, settle=0)   # cooldown กัน cold-start ซ้อนถี่ (settle=0 เพราะมี black-check ตามหลังอยู่แล้ว)
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
                    time.sleep(5)   # settle หลัง force-stop เกมหนัก (เดิม 2 วิ) ก่อน relaunch
                else:
                    break
            
            time.sleep(8)

            # 4 & 5. Wait for checkpointlogin (pressing play8/play8fix along the way)
            #    *** ไม่ยอมแพ้: ลูปนี้ออกได้ทางเดียวคือเจอ checkpointlogin เท่านั้น ***
            #    (กด play8 / fallback ไปเรื่อยๆ จนกว่าจะเจอ แล้วค่อยไปขั้นตอนกด Back รัวๆ)
            gui_log(serial, "Waiting checkpointlogin (clicking play8)...", step="play8/Check")
            play8_miss = 0   # นับรอบที่ play8 หาย + ยังไม่เจอ checkpoint (ไว้ทำ fallback กันค้าง)
            play8_click_count = 0   # นับจำนวนครั้งที่กด play8 ติดกัน — ครบ 7 → พัก 8 วิ แล้วเช็คใหม่
            play8_pause_until = 0.0     # ช่วงพักหลังกดครบ 5 ครั้ง (พักแบบไม่หลับ — ลูปยังเช็ค checkpointlogin ตลอด)
            DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None)   # ล้าง flag ค้างจากรอบ/เฟสก่อน กัน break มั่ว
            p8_cancel_done = False      # True = หลุดลูปด้วยทาง fixout→cancel (ข้ามขั้น event/Back spam ได้เลย)
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)

                # fixout→Back spam→cancel เพิ่งทำงานสำเร็จ (จาก floating check ใน get_screen_capture)
                # = อยู่หน้าเมนูหลักแล้ว → break ออกไปทำ step ถัดไปทันที ไม่ต้องรอ checkpointlogin
                if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
                    gui_log(serial, "fixout→cancel done — skipping checkpointlogin, proceeding to next step!", step="Checkpoint Skip")
                    p8_cancel_done = True
                    break

                if img is not None:
                    # --- 1. เช็ค checkpointlogin — เจอเท่านั้นถึงจะหลุดลูปไปเฟสต่อไป ---
                    pts_cp = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
                    # กันจับพลาด: checkpointlogin เป็นไอคอนกลมเล็ก (29x31) ส่วนหน้า title มีฟองกลมสีชมพู
                    # ทรงเหมือนกัน — เทียบแบบ grayscale ได้ถึง 0.97 (ผ่านเกณฑ์) ทำให้บอทนึกว่า login เสร็จ
                    # แล้วลัดไป Back spam/Find Hero ทั้งที่ยังอยู่หน้า title
                    # → ถ้ายังเห็นวงกลม play8/play8fix อยู่บนจอ = ยังอยู่หน้า title แน่นอน ไม่ใช่ของจริง
                    if pts_cp and (img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
                                   or img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))):
                        pts_cp = None
                    if pts_cp:
                        if LOGIN_FAST:
                            gui_log(serial, "LOGIN_FAST: checkpointlogin found — clearing app and moving to next file.", step="Fast Done", status="working")
                            device.shell("am force-stop jp.konami.pesam")
                            time.sleep(0.5)
                            dest = os.path.join(LOGIN_SUCCESS_DIR, original_name)
                            if os.path.exists(file_path):
                                save_result(file_path, dest)
                            release_file(original_name)
                            break

                        x, y = pts_cp[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, "checkpointlogin found & clicked! Proceeding...", step="Checkpoint")
                        time.sleep(4)
                        break

                    # --- 1.5 เจอ checkponit-play8 (หน้า Terms of Use) → "หยุดกด play8"
                    #         แล้วไปทำลำดับ ☐ ติ๊ก → Consent → Confirm ให้จบ ค่อยกลับมากด play8 ต่อ
                    #     *** ตัวเดียวที่ให้หยุดกด play8 ได้คือหน้านี้เท่านั้น ***
                    #     (stopplay8 เดิมที่หยุดกดชั่วคราว 5 วิ ถูกเอาออกแล้ว — ให้กด play8 ตามปกติไปเรื่อยๆ)
                    if img_search_best(img, os.path.join(IMG_DIR, "checkponit-play8.bmp"), threshold=0.9):
                        gui_log(serial, "เจอ checkponit-play8 — หยุดกด play8 ไปทำ Consent/Confirm ก่อน", step="play8 Stop")
                        run_new_stage_play8(device, serial, cycle_start)
                        play8_miss = 0
                        play8_click_count = 0
                        continue

                    # --- 1.7 หา fixout ลอยๆ "ทุกเฟรม" (popup บังจอ เช่น Terms of Use) ---
                    #     เจอ → กด Back รัวๆ จนเจอ cancel.bmp แล้วคลิก → break ไปทำ step ถัดไปเลย
                    pts_fo = img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.85)
                    if pts_fo:
                        fixout_back_spam_until_cancel(device, serial)
                        DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None)   # กันเช็คซ้ำรอบหน้า (break ตรงนี้เลย)
                        gui_log(serial, "fixout→cancel done — skipping checkpointlogin, proceeding to next step!", step="Checkpoint Skip")
                        p8_cancel_done = True
                        break

                    # --- 2. ถ้ายังไม่เจอ Checkpoint ก็หา play8 / play8fix ---
                    pts_8 = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
                    matched_name = "play8"
                    if not pts_8:
                        pts_8 = img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))
                        matched_name = "play8fix"

                    if pts_8:
                        play8_miss = 0   # เจอ play8 แล้ว รีเซ็ตตัวนับ

                        # Prioritize fixlg3
                        pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                        if pts_lg3:
                            gui_log(serial, f"{matched_name} and fixlg3 found! Clicking fixlg3 first", step="play8")
                            x, y = pts_lg3[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(1.0)
                            continue

                        # เจอ play8 = กดเลย แล้วกดไปเรื่อยๆ ไม่มีพัก
                        # (ออกจากลูปได้ทางเดียวคือเจอ checkpointlogin หรือ checkponit-play8 ซึ่งเช็คทุกเฟรมข้างบน)
                        x, y = pts_8[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        play8_click_count += 1
                        if play8_click_count % 5 == 1:   # log ทุก 5 ครั้ง กัน log ถี่เกิน
                            gui_log(serial, f"Found {matched_name}! Clicked. (ครั้งที่ {play8_click_count})", step="play8")
                        time.sleep(0.5)
                        continue

                    # --- 3. play8/play8fix หายแล้วแต่ยังไม่เจอ checkpoint → รอเฉยๆ วนเช็คต่อ ---
                    #     (checkpointlogin/fixout ถูกเช็คทุกเฟรมข้างบนอยู่แล้ว)
                    play8_miss += 1

                time.sleep(0.3)

            # ผ่านหน้า login (เจอ checkpoint) แล้ว → mark ไว้: ถ้าหลังจากนี้เจอ fixclear
            # จะ restart "ตั้งแต่ play8" (เก็บ login เดิม) แทนการ push ไฟล์ + login ใหม่
            DEVICE_PAST_LOGIN[serial] = True

            if LOGIN_FAST:
                if p8_cancel_done:
                    # หลุดลูปทาง fixout→cancel (ยังไม่ได้ sort ไฟล์ในลูปเหมือนทาง checkpoint)
                    # → login ผ่านแล้วเหมือนกัน sort เข้า login-success ให้ครบก่อนเริ่มไฟล์ใหม่
                    gui_log(serial, "LOGIN_FAST: (fixout→cancel) — clearing app and moving to next file.", step="Fast Done", status="working")
                    device.shell("am force-stop jp.konami.pesam")
                    time.sleep(0.5)
                    dest = os.path.join(LOGIN_SUCCESS_DIR, original_name)
                    if os.path.exists(file_path):
                        save_result(file_path, dest)
                    release_file(original_name)
                continue

            # (ไม่มีขั้น checkponit-play8 ตรงนี้แล้ว — เจอ checkpointlogin = ผ่าน login แล้ว
            #  ให้ไป step ถัดไปเลย ลำดับ ☐ ติ๊ก → Consent → Confirm จะถูกทำก็ต่อเมื่อ
            #  "เจอหน้า Terms of Use จริงๆ" เท่านั้น คือในลูป play8 ข้อ 1.5 หรือ floating check)

            # 6. Event sequence — พฤติกรรมขึ้นกับ EVENT_IMG
            # (ถ้าหลุดลูปทาง fixout→cancel = กด Back+cancel ไปแล้ว อยู่หน้าเมนูหลักแล้ว → ข้ามขั้นนี้ทั้งหมด)
            if p8_cancel_done:
                gui_log(serial, "ข้ามขั้น event/Back spam (fixout→cancel ทำไปแล้ว) — ไป step ถัดไปเลย", step="Event Skip")
            elif EVENT_IMG == 1:
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
                skip_cancel_step = False   # True = fixout→cancel กดไปแล้วรอบเดียวพอ → ข้ามขั้นนี้ไป box/step ถัดไปเลย
                gui_log(serial, "Waiting play22 (no-event mode)...", step="play22")
                deadline = time.time() + 10
                while time.time() < deadline:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    # fixout→Back spam→cancel เพิ่งทำงาน (จาก floating check) = กด cancel แล้ว → ข้ามขั้นนี้เลย
                    if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
                        gui_log(serial, "fixout→cancel done — ข้ามขั้น Back/cancel ไป step ถัดไปเลย", step="Cancel Skip")
                        skip_cancel_step = True
                        break
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "play22.bmp"))
                        if pts:
                            gui_log(serial, "play22 found — pressing Back...", step="Back loop")
                            break
                    time.sleep(0.5)

                # กด Back รัวๆ จนกว่าจะเจอ cancel.bmp (ไม่มี timeout → กดไปเรื่อยๆ จนกว่าจะเจอ)
                if not skip_cancel_step:
                    gui_log(serial, "Spamming Back until cancel.bmp...", step="Cancel")
                    while True:
                        check_device_reset(serial, cycle_start)
                        device.shell("input keyevent 4")   # KEYCODE_BACK
                        time.sleep(1.0)
                        try:
                            img = get_screen_capture(device)
                        except ResetGachaException:
                            # fixgachanew เด้งระหว่างกด Back → get_screen_capture เคลียร์ป็อปอัพให้แล้ว
                            # ไม่ต้องหยุด → กด Back ต่อไปเรื่อยๆ จนกว่าจะเจอ cancel.bmp
                            continue
                        # fixout→Back spam→cancel เพิ่งทำงานระหว่างนี้ = กด cancel ไปแล้วรอบเดียวพอ → หยุดเลย
                        if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
                            gui_log(serial, "fixout→cancel done — กดแล้วรอบเดียวพอ หยุด Back spam ไปต่อเลย", step="Cancel Skip")
                            break
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                            if pts:
                                x, y = pts[0]
                                gui_log(serial, f"cancel.bmp found — clicking ({x},{y})", step="Click Cancel")
                                # กดจนกว่าจะหายไปครบ 3 วิ ค่อยไปต่อ
                                click_cancel_until_gone(device, serial, x, y, step="Cancel")
                                break

            # ── Check Coin (สแกนก่อนเสมอ ถ้าเปิด) ──
            #    ถ้าเปิด CHECK_COIN → สแกนเลขเหรียญตั้งแต่อยู่หน้า main menu "ก่อน" ทำงานอื่น
            #    (Box / GetCode / GetQuest / Gacha / Find) แล้วจำไว้แนบชื่อไฟล์ตอนจบ
            coin_prefix = None
            # coin_low = เหรียญที่สแกนได้ "น้อยกว่า" เกณฑ์ GACHA_MIN_COIN → จะใช้ข้ามการสุ่ม
            coin_low = False
            if CHECK_COIN == 1:
                gui_log(serial, "Check Coin enabled → scanning coins first (before other steps)...", step="Coin First", status="working")
                coin_prefix = scan_coin_number(device, cycle_start, serial)
                if coin_prefix is not None:
                    try:
                        coin_low = int(coin_prefix) < int(GACHA_MIN_COIN)
                    except (ValueError, TypeError):
                        coin_low = False
                    if coin_low:
                        gui_log(serial, f"🪙 Coins {coin_prefix} < {GACHA_MIN_COIN} → will SKIP gacha.", step="Low Coin")

            # 6.5 Get Code Sequence (Optional — ก่อน Box)
            if GETCODE == 1:
                gui_log(serial, "Get Code sequence started...", step="GetCode", status="working")
                # Navigate getcode1 → getcode5 (click each, wait for next to appear)
                getcode_nav = [
                    ("getcode1.bmp", "getcode2.bmp"),
                    ("getcode2.bmp", "getcode3.bmp"),
                    ("getcode3.bmp", "getcode4.bmp"),
                    ("getcode4.bmp", "getcode5.bmp"),
                ]
                #   แต่ละตัว "กดซ้ำๆ จนกว่าจะไปรูปถัดไป" (กดรอบเดียวมักไม่ติด)
                #   ใช้ img_search_best = กดจุดที่เหมือนที่สุดจุดเดียว กันกดโดนข้อความ/ปุ่มอื่นที่คล้ายกัน
                for gc_curr, gc_next in getcode_nav:
                    gui_log(serial, f"Waiting for {gc_curr}...", step=f"{gc_curr} Wait")
                    last_gc_click = 0
                    gc_click_n = 0
                    while True:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            if img_search_best(img, os.path.join(IMG_DIR, gc_next), threshold=0.9):
                                gui_log(serial, f"{gc_next} detected! Next step.", step=f"{gc_next} Seen")
                                break
                            pts_gc = img_search_best(img, os.path.join(IMG_DIR, gc_curr), threshold=0.9)
                            if pts_gc:
                                now = time.time()
                                if now - last_gc_click >= 0.6:   # กดรัวๆ ~1.5 ครั้ง/วิ จนกว่ารูปถัดไปจะมา
                                    x, y = pts_gc[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    gc_click_n += 1
                                    if gc_click_n % 5 == 1:      # log ทุก 5 ครั้ง กัน log ถี่
                                        gui_log(serial, f"Clicked {gc_curr} ({x},{y}) ครั้งที่ {gc_click_n}", step=f"{gc_curr} Click")
                                    last_gc_click = now
                        time.sleep(0.3)

                # Wait and click getcode5.bmp — กดไปเรื่อยๆ จนกว่าจะเจอ fixgetcode5
                #   (fixgetcode5 = ช่องกรอกพร้อมรับข้อความแล้ว) ค่อยเริ่มพิมพ์โค้ด
                gui_log(serial, "Waiting for getcode5.bmp...", step="getcode5 Wait")
                gc5_pos = None
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts_gc5 = img_search_best(img, os.path.join(IMG_DIR, "getcode5.bmp"), threshold=0.9)
                        if pts_gc5:
                            x, y = pts_gc5[0]
                            gc5_pos = (x, y)
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            gui_log(serial, f"Clicked getcode5.bmp ({x},{y}) ครั้งที่ 1", step="getcode5 Click")
                            time.sleep(0.8)
                            break
                    time.sleep(0.5)

                # กด getcode5 ไปเรื่อยๆ จนกว่าจะเจอ fixgetcode5 (ไม่มี timeout — ไม่เจอก็กดต่อ)
                #   หาพิกัดใหม่ทุกครั้งเผื่อจอขยับ ไม่เจอในเฟรมนั้นก็กดที่เดิม
                gui_log(serial, "กด getcode5 ต่อจนกว่าจะเจอ fixgetcode5...", step="getcode5 Loop")
                gc5_n = 1
                while True:
                    check_device_reset(serial, cycle_start)
                    img_g5 = fast_screencap(device)
                    if img_g5 is not None:
                        if img_search_best(img_g5, os.path.join(IMG_DIR, "fixgetcode5.bmp"), threshold=0.9):
                            gui_log(serial, f"เจอ fixgetcode5 แล้ว (กด getcode5 ไป {gc5_n} ครั้ง) → เริ่มกรอกโค้ด",
                                    step="fixgetcode5 OK")
                            break
                        pts_g5b = img_search_best(img_g5, os.path.join(IMG_DIR, "getcode5.bmp"), threshold=0.9)
                        if pts_g5b:
                            gc5_pos = pts_g5b[0]
                    if gc5_pos:
                        device.shell(f"input swipe {gc5_pos[0]} {gc5_pos[1]} {gc5_pos[0]} {gc5_pos[1]} 100")
                        gc5_n += 1
                        if gc5_n % 5 == 0:   # log ทุก 5 ครั้ง กัน log ถี่
                            gui_log(serial, f"กด getcode5 ({gc5_pos[0]},{gc5_pos[1]}) ครั้งที่ {gc5_n}", step="getcode5 Click")
                    time.sleep(0.7)

                time.sleep(0.5)   # พักให้ช่องกรอกพร้อมก่อนพิมพ์

                # Type the code text from config
                code_text = GETCODE_TEXT
                gui_log(serial, f"Typing code: {code_text}", step="Type Code")
                device.shell(f"input text '{code_text}'")
                time.sleep(1.5)

                # Click getcode6.bmp — กดซ้ำๆ จนกว่าจะไปหน้าถัดไป (getcode6 หายไป / เจอผล okcode-codesom)
                gui_log(serial, "Waiting for getcode6.bmp...", step="getcode6 Wait")
                gc6_click_n = 0
                gc6_last_click = 0.0
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        # ไปหน้าผลลัพธ์แล้ว → เลิกกด
                        if (img_search_best(img, os.path.join(IMG_DIR, "okcode.bmp"), threshold=0.9)
                                or img_search_best(img, os.path.join(IMG_DIR, "codesom.bmp"), threshold=0.9)):
                            gui_log(serial, f"ไปหน้าผลลัพธ์แล้ว (กด getcode6 ไป {gc6_click_n} ครั้ง)", step="getcode6 Done")
                            break
                        pts_gc6 = img_search_best(img, os.path.join(IMG_DIR, "getcode6.bmp"), threshold=0.9)
                        if pts_gc6:
                            if time.time() - gc6_last_click >= 0.6:
                                x, y = pts_gc6[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                gc6_last_click = time.time()
                                gc6_click_n += 1
                                if gc6_click_n % 5 == 1:
                                    gui_log(serial, f"Clicked getcode6.bmp ({x},{y}) ครั้งที่ {gc6_click_n}", step="getcode6 Click")
                        elif gc6_click_n > 0:
                            # เคยกดแล้วและรูปหายไป = ไปหน้าถัดไปแล้ว
                            gui_log(serial, f"getcode6 หายแล้ว (กดไป {gc6_click_n} ครั้ง) → ไปต่อ", step="getcode6 Done")
                            time.sleep(1.0)
                            break
                    time.sleep(0.3)

                # Wait for result: okcode.bmp or codesom.bmp
                gui_log(serial, "Waiting for okcode or codesom result...", step="Code Result")
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        # Check okcode.bmp first
                        pts_ok = img_search(img, os.path.join(IMG_DIR, "okcode.bmp"), threshold=0.9)
                        if pts_ok:
                            x, y = pts_ok[0]
                            gui_log(serial, f"okcode.bmp found! Clicking ({x},{y})", step="OK Code")
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(1.0)
                            break
                        # Check codesom.bmp
                        pts_som = img_search(img, os.path.join(IMG_DIR, "codesom.bmp"), threshold=0.9)
                        if pts_som:
                            gui_log(serial, "codesom.bmp found! Code already used.", step="Code Som")
                            break
                    time.sleep(0.5)

                # Spam Back until cancel.bmp appears, then click cancel (2 rounds)
                for cancel_round in range(1, 3):
                    gui_log(serial, f"Spamming Back until cancel.bmp (round {cancel_round}/2)...", step=f"GetCode Back R{cancel_round}")
                    while True:
                        check_device_reset(serial, cycle_start)
                        device.shell("input keyevent 4")
                        time.sleep(0.4)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts_cancel = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                            if pts_cancel:
                                x, y = pts_cancel[0]
                                gui_log(serial, f"cancel.bmp found (round {cancel_round}) — clicking ({x},{y})", step=f"GetCode Cancel R{cancel_round}")
                                # กดจนกว่าจะหายไปครบ 3 วิ
                                click_cancel_until_gone(device, serial, x, y, step=f"GetCode Cancel R{cancel_round}")
                                gui_log(serial, f"cancel.bmp gone (round {cancel_round}) — done!", step=f"GetCode Cancel R{cancel_round} OK")
                                break

                # Wait and click fixcode.bmp before proceeding to Box
                #   กดซ้ำ 5 รอบเผื่อกดไม่ติด — ถ้ารูปหายไปก่อนครบ 5 ก็ถือว่าติดแล้ว หยุดกดไปต่อเลย
                gui_log(serial, "Waiting for fixcode.bmp...", step="fixcode Wait")
                fc_clicked = 0
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts_fc = img_search_best(img, os.path.join(IMG_DIR, "fixcode.bmp"), threshold=0.9)
                        if pts_fc:
                            x, y = pts_fc[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            fc_clicked += 1
                            gui_log(serial, f"Clicked fixcode.bmp ({x},{y}) ครั้งที่ {fc_clicked}/5", step="fixcode Click")
                            if fc_clicked >= 5:
                                gui_log(serial, "กด fixcode ครบ 5 ครั้ง → ไปต่อ", step="fixcode Done")
                                time.sleep(1.0)
                                break
                            time.sleep(0.6)
                        elif fc_clicked > 0:
                            # กดไปแล้วและรูปหายไป = ติดแล้ว ไม่ต้องกดให้ครบ 5
                            gui_log(serial, f"fixcode หายแล้ว (กดไป {fc_clicked} ครั้ง) → ไปต่อ", step="fixcode Done")
                            time.sleep(1.0)
                            break
                    time.sleep(0.5)

                gui_log(serial, "GetCode completed!", step="GetCode Done")


            # 6.7 Get Quest Sequence (Optional — ก่อน Box)
            if GETQUEST == 1:
                # Spam Back until cancel.bmp to return to main menu
                gui_log(serial, "Spamming Back until cancel.bmp to return to main menu...", step="GQ Init Back")
                while True:
                    check_device_reset(serial, cycle_start)
                    device.shell("input keyevent 4")
                    time.sleep(0.4)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts_cancel = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts_cancel:
                            x_c, y_c = pts_cancel[0]
                            gui_log(serial, f"cancel.bmp found — clicking ({x_c},{y_c})", step="GQ Init Cancel")
                            # กดซ้ำจนกว่าจะหายไปครบ 3 วิ
                            click_cancel_until_gone(device, serial, x_c, y_c, step="GQ Init Cancel")
                            break

                gui_log(serial, "Get Quest sequence started...", step="GetQuest", status="working")
                GQ_DIR = GETQUEST_IMG_DIR  # img/getquest
                
                global GQ_ACTIVE
                GQ_ACTIVE = True
                try:
                    start_from_gq8 = False
                    while True:
                        try:
                            if not start_from_gq8:
                                # ── Phase 1: getquest1 → getquest5 (คลิกทีละภาพ) ──
                                for gq_i in range(1, 6):
                                    gq_name = f"getquest{gq_i}.bmp"
                                    gui_log(serial, f"Waiting {gq_name}...", step=f"gq{gq_i}")
                                    gq_deadline = time.time() + 10 if gq_i == 5 else None  # getquest5 timeout 10s
                                    gq_found = False
                                    while True:
                                        if gq_deadline and time.time() > gq_deadline:
                                            gui_log(serial, f"{gq_name} timeout 10s — skip", step=f"gq{gq_i} Skip")
                                            break
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            pts = img_search(img, os.path.join(GQ_DIR, gq_name))
                                            if pts:
                                                x, y = pts[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked {gq_name} ({x},{y})", step=f"gq{gq_i} Click")
                                                gq_found = True
                                                time.sleep(1.5)
                                                # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, gq_name)):
                                                        break
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, f"Re-click {gq_name}", step=f"gq{gq_i} Retry")
                                                    time.sleep(1.0)
                                                break
                                        time.sleep(0.8)

                                # ── Phase 2: หลังกด getquest5 → กดตำแหน่งเดิมซ้ำๆ จนกว่าเจอ getquest6 (timeout 10s) ──
                                gui_log(serial, "Spam-clicking last position until getquest6...", step="gq5→gq6")
                                gq5_x, gq5_y = x, y
                                gq6_deadline = time.time() + 10
                                gq6_found = False
                                while time.time() < gq6_deadline:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts6 = img_search(img, os.path.join(GQ_DIR, "getquest6.bmp"))
                                        if pts6:
                                            gui_log(serial, "getquest6 found!", step="gq6 Found")
                                            gq6_found = True
                                            break
                                    device.shell(f"input swipe {gq5_x} {gq5_y} {gq5_x} {gq5_y} 100")
                                    time.sleep(0.5)
                                if not gq6_found:
                                    gui_log(serial, "getquest6 timeout 10s — skip", step="gq6 Skip")

                                # ── Phase 3: กด getquest6 ซ้ำๆ จนกว่าจะหายไป ──
                                gui_log(serial, "Clicking getquest6 until gone...", step="gq6 Click")
                                last_seen_gq6 = time.time()
                                while time.time() - last_seen_gq6 < 8:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts6 = img_search(img, os.path.join(GQ_DIR, "getquest6.bmp"))
                                        if pts6:
                                            x6, y6 = pts6[0]
                                            device.shell(f"input swipe {x6} {y6} {x6} {y6} 100")
                                            last_seen_gq6 = time.time()
                                            time.sleep(0.5)
                                            continue
                                    time.sleep(0.5)
                                gui_log(serial, "getquest6 gone!", step="gq6 Done")

                                # ── Phase 4: getquest7 → กด แล้ว Back รัวๆ จนเจอ cancel (timeout 10s) ──
                                gui_log(serial, "Waiting getquest7...", step="gq7")
                                gq7_deadline = time.time() + 10
                                gq7_found = False
                                while time.time() < gq7_deadline:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts7 = img_search(img, os.path.join(GQ_DIR, "getquest7.bmp"))
                                        if pts7:
                                            x7, y7 = pts7[0]
                                            device.shell(f"input swipe {x7} {y7} {x7} {y7} 100")
                                            gui_log(serial, f"Clicked getquest7 ({x7},{y7})", step="gq7 Click")
                                            gq7_found = True
                                            time.sleep(1.5)
                                            # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "getquest7.bmp")):
                                                    break
                                                device.shell(f"input swipe {x7} {y7} {x7} {y7} 100")
                                                gui_log(serial, "Re-click getquest7", step="gq7 Retry")
                                                time.sleep(1.0)
                                            break
                                    time.sleep(0.8)
                                if not gq7_found:
                                    gui_log(serial, "getquest7 timeout 10s — skip", step="gq7 Skip")

                                # Back รัวๆ จนเจอ cancel แล้วกด
                                gui_log(serial, "Spamming Back until cancel (after gq7)...", step="gq7 Back")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    device.shell("input keyevent 4")
                                    time.sleep(0.4)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts_c = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                                        if pts_c:
                                            xc, yc = pts_c[0]
                                            gui_log(serial, f"cancel found — clicking ({xc},{yc})", step="gq7 Cancel")
                                            click_cancel_until_gone(device, serial, xc, yc, step="gq7 Cancel")
                                            break

                            # ── Phase 5: getquest8 → getquest11 (คลิกทีละภาพ) ──
                            p5_start = 8
                            for gq_i in range(p5_start, 12):
                                gq_name = f"getquest{gq_i}.bmp"
                                thresh = 0.8
                                gq_deadline = time.time() + 15

                                # ── getquest10 ใช้ getquestfix10.png แทนเลย ──
                                if gq_i == 10:
                                    gui_log(serial, "Looking for getquestfix10...", step="gq10 Fix")
                                    fix10_path = os.path.join(GQ_DIR, "getquestfix10.png")
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            pts_fix = img_search(img, fix10_path, threshold=0.8)
                                            if pts_fix:
                                                gui_log(serial, "getquestfix10 found! Tapping [86,413] until getquest11...", step="gq10 Fix Tap")
                                                while True:
                                                    check_device_reset(serial, cycle_start)
                                                    device.shell("input swipe 86 413 86 413 100")
                                                    time.sleep(1.0)
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None:
                                                        pts11 = img_search(img2, os.path.join(GQ_DIR, "getquest11.bmp"), threshold=0.8)
                                                        if pts11:
                                                            gui_log(serial, "getquest11 found — continuing!", step="gq11 Found")
                                                            break
                                                break
                                        time.sleep(0.8)
                                    continue

                                gui_log(serial, f"Waiting {gq_name}...", step=f"gq{gq_i}")
                                found_gq = False
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    if time.time() > gq_deadline:
                                        gui_log(serial, f"{gq_name} timeout 15s — skipping", step=f"gq{gq_i} Skip")
                                        break
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts = img_search(img, os.path.join(GQ_DIR, gq_name), threshold=thresh)
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, f"Clicked {gq_name} ({x},{y})", step=f"gq{gq_i} Click")
                                            time.sleep(1.5)
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, gq_name), threshold=thresh):
                                                    break
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Re-click {gq_name}", step=f"gq{gq_i} Retry")
                                                time.sleep(1.0)
                                            break
                                    time.sleep(0.8)

                            # วิธีที่ 1: ใช้ draganddrop (กดค้างแล้วลาก)
                            # draganddrop จะกดค้างที่จุดแรกสักครู่ แล้วค่อยลากไปยังจุดที่สอง
                            # โดยตัวเลข 5000 คือระยะเวลาในการลาก (5 วินาที)
                            cmd_drag = "input draganddrop 96 124 691 205 5000"
                            gui_log(serial, "Dragging from 96 124 to 691 205...", step="gq Drag")
                            device.shell(cmd_drag)
                            time.sleep(1.5)

                            # Back รัวๆ จนเจอ cancel แล้วกด
                            gui_log(serial, "Spamming Back until cancel (after gq8-11)...", step="gq11 Back")
                            while True:
                                check_device_reset(serial, cycle_start)
                                device.shell("input keyevent 4")
                                time.sleep(0.4)
                                img = get_screen_capture(device)
                                if img is not None:
                                    pts_c = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
                                    if pts_c:
                                        xc, yc = pts_c[0]
                                        gui_log(serial, f"cancel found — clicking ({xc},{yc})", step="gq11 Cancel")
                                        click_cancel_until_gone(device, serial, xc, yc, step="gq11 Cancel")
                                        break

                            # ── Phase 6: getquest12 → getquest14 ──
                            for gq_i in range(12, 15):
                                gq_name = f"getquest{gq_i}.bmp"
                                gui_log(serial, f"Waiting {gq_name}...", step=f"gq{gq_i}")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts = img_search(img, os.path.join(GQ_DIR, gq_name))
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, f"Clicked {gq_name} ({x},{y})", step=f"gq{gq_i} Click")
                                            time.sleep(1.5)
                                            # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, gq_name)):
                                                    break
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Re-click {gq_name}", step=f"gq{gq_i} Retry")
                                                time.sleep(1.0)
                                            break
                                    time.sleep(0.8)

                            # รอเจอ waitquest.bmp
                            gui_log(serial, "Waiting for waitquest.bmp...", step="waitquest")
                            while True:
                                check_device_reset(serial, cycle_start)
                                img = get_screen_capture(device)
                                if img is not None:
                                    pts_wq = img_search(img, os.path.join(GQ_DIR, "waitquest.bmp"))
                                    if pts_wq:
                                        gui_log(serial, "waitquest found!", step="waitquest OK")
                                        time.sleep(1.0)
                                        break
                                time.sleep(1.0)

                            # กด getquest15
                            gui_log(serial, "Waiting getquest15...", step="gq15")
                            while True:
                                check_device_reset(serial, cycle_start)
                                img = get_screen_capture(device)
                                if img is not None:
                                    pts15 = img_search(img, os.path.join(GQ_DIR, "getquest15.bmp"))
                                    if pts15:
                                        x15, y15 = pts15[0]
                                        device.shell(f"input swipe {x15} {y15} {x15} {y15} 100")
                                        gui_log(serial, f"Clicked getquest15 ({x15},{y15})", step="gq15 Click")
                                        time.sleep(1.5)
                                        # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                        retry_end = time.time() + 8
                                        while time.time() < retry_end:
                                            img2 = get_screen_capture(device)
                                            if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "getquest15.bmp")):
                                                break
                                            device.shell(f"input swipe {x15} {y15} {x15} {y15} 100")
                                            gui_log(serial, "Re-click getquest15", step="gq15 Retry")
                                            time.sleep(1.0)
                                        break
                                time.sleep(0.8)

                            # ── Phase 7: Post-GQ15 Quest Five Sequence ──
                            gui_log(serial, "Starting Quest Five sequence...", step="QuestFive Start")
                            
                            def click_until_gone(img_path, label, threshold=0.8):
                                gui_log(serial, f"Waiting for {label}...", step=label)
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts = img_search(img, img_path, threshold=threshold)
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, f"Clicked {label} at ({x}, {y})", step=f"{label} Click")
                                            time.sleep(1.5)
                                            # กดซ้ำจนกว่าจะหาย
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                check_device_reset(serial, cycle_start)
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not img_search(img2, img_path, threshold=threshold):
                                                    break
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Re-clicked {label}", step=f"{label} Retry")
                                                time.sleep(1.0)
                                            break
                                    time.sleep(0.8)

                            while True:
                                check_device_reset(serial, cycle_start)
                                # 1. Delay 10 วินาทีก่อนเริ่มลาก จากนั้นกดค้างที่ 96 124 แล้วลากไป 691 205 (ใช้เวลาลาก 5 วินาที)
                                gui_log(serial, "Waiting 10 seconds delay before dragging...", step="Q5 Drag Delay")
                                time.sleep(10.0)
                                
                                drag_cmd = "input draganddrop 96 124 691 205 5000"
                                gui_log(serial, "Dragging from 96 124 to 691 205...", step="Q5 Drag")
                                device.shell(drag_cmd)
                                time.sleep(0.2) # เริ่มค้นหาต่อทันที
                                
                                # 2. กด questfive1
                                gui_log(serial, "Searching for questfive1.bmp...", step="Q5_1 Search")
                                q5_1_found = False
                                search_start = time.time()
                                while time.time() - search_start < 10: # ให้เวลารอ 10 วิ
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts = img_search(img, os.path.join(GQ_DIR, "questfive1.bmp"))
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, f"Clicked questfive1 at ({x}, {y})", step="Q5_1 Click")
                                            q5_1_found = True
                                            time.sleep(1.5)
                                            # กดซ้ำจนกว่าจะหาย
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                check_device_reset(serial, cycle_start)
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive1.bmp")):
                                                    break
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, "Re-clicked questfive1", step="Q5_1 Retry")
                                                time.sleep(1.0)
                                            break
                                    time.sleep(0.1)
                                    
                                if not q5_1_found:
                                    gui_log(serial, "questfive1.bmp not found! Retrying from drag...", step="Q5_1 Fail")
                                    continue
                                    
                                # 3. เช็ค checkpointquest1
                                gui_log(serial, "Verifying checkpointquest1.bmp...", step="Q5 CP1 Check")
                                time.sleep(2.0) # ให้เวลาโหลดหน้าจอ
                                checkpoint_found = False
                                img = get_screen_capture(device)
                                if img is not None:
                                    pts = img_search(img, os.path.join(GQ_DIR, "checkpointquest1.bmp"))
                                    if pts:
                                        gui_log(serial, "checkpointquest1.bmp FOUND!", step="Q5 CP1 OK")
                                        checkpoint_found = True
                                    else:
                                        gui_log(serial, "checkpointquest1.bmp NOT FOUND!", step="Q5 CP1 Missing")
                                        
                                if not checkpoint_found:
                                    gui_log(serial, "Checkpoint not found, looping back to drag...", step="Q5 CP1 Retry")
                                    continue # กลับไปลากใหม่
                                    
                                # 4. ถ้าเจอ checkpointquest1 -> ไป questfive2 -> questfive3
                                gui_log(serial, "Proceeding to questfive2 -> questfive3...", step="Q5_2->3")
                                # questfive2: reclick ถ้ายังขึ้นอยู่ หรือถ้า questfive2 โผล่กลับมาหลังกด
                                while True:
                                    click_until_gone(os.path.join(GQ_DIR, "questfive2.bmp"), "questfive2.bmp")
                                    # เช็คซ้ำทันทีหลังกด ถ้า questfive2 ยังขึ้นอยู่ → reclick
                                    img = get_screen_capture(device)
                                    if img is not None and img_search(img, os.path.join(GQ_DIR, "questfive2.bmp")):
                                        gui_log(serial, "questfive2 still present after click, retrying...", step="Q5_2 Still Present")
                                        continue
                                    q3_found = False
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            if img_search(img, os.path.join(GQ_DIR, "questfive3.bmp")):
                                                q3_found = True
                                                break
                                            if img_search(img, os.path.join(GQ_DIR, "questfive2.bmp")):
                                                gui_log(serial, "questfive2 reappeared, retrying...", step="Q5_2 Retry")
                                                break
                                        time.sleep(0.5)
                                    if q3_found:
                                        break
                                click_until_gone(os.path.join(GQ_DIR, "questfive3.bmp"), "questfive3.bmp")
                                    
                                # 5. วนกด questfive4 -> questfive5 จนกว่าจะเจอ checkpointquest2
                                gui_log(serial, "Loop clicking questfive4 -> questfive5...", step="Q5_4->5 Loop")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    # เช็ค checkpointquest2 ก่อนเริ่มรอบ
                                    img = get_screen_capture(device)
                                    if img is not None and img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                        gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                        break
                                        
                                    # รอ/กด questfive4
                                    q4_break = False
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            if img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                                gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                                q4_break = True
                                                break
                                            
                                            pts4 = img_search(img, os.path.join(GQ_DIR, "questfive4.bmp"))
                                            if pts4:
                                                x, y = pts4[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked questfive4 at ({x}, {y})", step="Q5_4 Click")
                                                time.sleep(1.5)
                                                # กดซ้ำจนกว่าจะหาย
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    check_device_reset(serial, cycle_start)
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive4.bmp")):
                                                        break
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, "Re-clicked questfive4", step="Q5_4 Retry")
                                                    time.sleep(1.0)
                                                break
                                        time.sleep(0.8)
                                        
                                    if q4_break:
                                        break
                                        
                                    # เช็ค checkpointquest2 อีกรอบก่อนกด questfive5
                                    img = get_screen_capture(device)
                                    if img is not None and img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                        gui_log(serial, "checkpointquest2.bmp FOUND before questfive5! Breaking loop...", step="Q5 CP2 OK")
                                        break
                                        
                                    # รอ/กด questfive5
                                    q5_break = False
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            if img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                                gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                                q5_break = True
                                                break
                                            
                                            pts5 = img_search(img, os.path.join(GQ_DIR, "questfive5.bmp"))
                                            if pts5:
                                                x, y = pts5[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked questfive5 at ({x}, {y})", step="Q5_5 Click")
                                                time.sleep(1.5)
                                                # กดซ้ำจนกว่าจะหาย
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    check_device_reset(serial, cycle_start)
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive5.bmp")):
                                                        break
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, "Re-clicked questfive5", step="Q5_5 Retry")
                                                    time.sleep(1.0)
                                                break
                                        time.sleep(0.8)
                                        
                                    if q5_break:
                                        break
                                        
                                # 6. ถ้าเจอ checkpointquest2 -> กด questfive6 -> questfive9
                                gui_log(serial, "Proceeding to questfive6 -> questfive9...", step="Q5_6->9")
                                for i in range(6, 10):
                                    q_name = f"questfive{i}.bmp"
                                    click_until_gone(os.path.join(GQ_DIR, q_name), q_name)
                                    
                                # 7. วนกดเช็ค questfive10 กดค้าง 5วิ ไปเรื่อยๆ จนกว่าจะเจอ chekcpointquest3
                                gui_log(serial, "Loop checking questfive10...", step="Q5_10 Loop")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        # เช็ค chekcpointquest3.bmp
                                        if img_search(img, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
                                            gui_log(serial, "chekcpointquest3.bmp FOUND!", step="Q5 CP3 OK")
                                            break
                                        
                                        # ค้นหา questfive10.bmp
                                        pts10 = img_search(img, os.path.join(GQ_DIR, "questfive10.bmp"))
                                        if pts10:
                                            x, y = pts10[0]
                                            gui_log(serial, f"Long pressing questfive10 at ({x}, {y})...", step="Q5_10 Click")
                                            device.shell(f"input swipe {x} {y} {x} {y} 5000")
                                            time.sleep(5.5) # รอให้กดค้างเสร็จ
                                            
                                            # เช็ค chekcpointquest3 อีกรอบหลังกดค้างเสร็จ
                                            img_after = get_screen_capture(device)
                                            if img_after is not None and img_search(img_after, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
                                                gui_log(serial, "chekcpointquest3.bmp FOUND after long press!", step="Q5 CP3 OK")
                                                break
                                        else:
                                            gui_log(serial, "questfive10.bmp not found, waiting...", step="Q5_10 Wait")
                                    time.sleep(0.1)
                                    
                                # 8. หลังจากเจอ chekcpointquest3 -> กด questfive11 -> questfive12
                                gui_log(serial, "Proceeding to questfive11 -> questfive12...", step="Q5_11->12")
                                for i in range(11, 13):
                                    q_name = f"questfive{i}.bmp"
                                    click_until_gone(os.path.join(GQ_DIR, q_name), q_name)
                                    
                                # 9. กดรูปค้าง questfive13 7วิ รอให้เจอ checkpointquest4
                                gui_log(serial, "Loop checking questfive13...", step="Q5_13 Loop")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        # เช็ค checkpointquest4.bmp
                                        if img_search(img, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
                                            gui_log(serial, "checkpointquest4.bmp FOUND!", step="Q5 CP4 OK")
                                            break
                                                
                                        # ค้นหา questfive13.bmp
                                        pts13 = img_search(img, os.path.join(GQ_DIR, "questfive13.bmp"))
                                        if pts13:
                                            x, y = pts13[0]
                                            gui_log(serial, f"Long pressing questfive13 at ({x}, {y})...", step="Q5_13 Click")
                                            device.shell(f"input swipe {x} {y} {x} {y} 7000")
                                            time.sleep(7.5) # รอให้กดค้างเสร็จ
                                            
                                            # เช็ค checkpointquest4 อีกรอบหลังกดค้างเสร็จ
                                            img_after = get_screen_capture(device)
                                            if img_after is not None and img_search(img_after, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
                                                gui_log(serial, "checkpointquest4.bmp FOUND after long press!", step="Q5 CP4 OK")
                                                break
                                        else:
                                            gui_log(serial, "questfive13.bmp not found, waiting...", step="Q5_13 Wait")
                                    time.sleep(0.1)
                                    
                                # 10. หลังจากเจอ checkpointquest4 -> กด questfive14 -> กด back รัวๆ จนกว่าจะเจอ cancel.bmp
                                gui_log(serial, "Proceeding to questfive14...", step="Q5_14")
                                click_until_gone(os.path.join(GQ_DIR, "questfive14.bmp"), "questfive14.bmp")
                                
                                gui_log(serial, "Spamming Back key until cancel.bmp...", step="Back Spam")
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts_cancel = img_search(img, "img/cancel.bmp")
                                        if pts_cancel:
                                            x, y = pts_cancel[0]
                                            gui_log(serial, f"Clicked cancel at ({x}, {y})", step="Cancel Click")
                                            # กดซ้ำจนกว่าจะหายไปครบ 3 วิ
                                            click_cancel_until_gone(device, serial, x, y, step="Cancel Click")
                                            break
                                    
                                    # Send Back key
                                    device.shell("input keyevent 4")
                                    gui_log(serial, "Pressed Back key", step="Press Back")
                                    time.sleep(1.0)
                                    
                                break

                            gui_log(serial, "GetQuest completed!", step="GetQuest Done")
                            break
                        except RestartFromQuest8Exception:
                            gui_log(serial, "backquest3 detected! Restarting sequence from getquest8...", step="Restart GQ8")
                            start_from_gq8 = True
                            time.sleep(1.0)
                finally:
                    GQ_ACTIVE = False
            # ── ถ้าเปิดแค่ GETQUEST โดยไม่มี DO_BOX/GACHA/อื่นๆ → จบรอบเลย ──
                if DO_BOX == 0 and DO_GACHA == 0 and GACHA_FREE == 0 and CHECK_COIN == 0 and FIND_HERO == 0 and GACHA_CHECK == 0:
                    gui_log(serial, "GETQUEST only mode — clearing app and finishing cycle.", step="Quest Only Done", status="working")
                    device.shell("am force-stop jp.konami.pesam")
                    time.sleep(1)

                    # ชื่อไฟล์ตอน export = user_code จริงจากข้างในไฟล์ .dat
                    clean_orig = export_base_name(file_path, original_name, strip_dash=True)

                    dest_dir = LOGIN_SUCCESS_DIR
                    dest = os.path.join(dest_dir, clean_orig)
                    if os.path.exists(file_path):
                        time.sleep(2)
                        try:
                            if os.path.exists(dest):
                                os.remove(dest)
                            _safe_copy(file_path, dest)
                            os.remove(file_path)
                            gui_log(serial, f"✅ Sorted: {original_name} -> {dest_dir}", step="Sorted", status="working")
                        except Exception as me:
                            gui_log(serial, f"⚠️ Sort failed: {me}", step="Sort Error")

                        dur = time.time() - cycle_start
                        dur_s = f"{dur/60:.1f}m" if dur >= 60 else f"{dur:.0f}s"
                        if gui_instance:
                            gui_instance.login_times.append(dur)

                    release_file(original_name)
                    continue  # ไปไฟล์ถัดไปทันที

            # 7. Box Sequence (Optional)
            if DO_BOX == 1:
                gui_log(serial, "Box sequence started...", step="Box Mode", status="working")
                box2_found = False
                box1_retry = 0          # นับจำนวนครั้งที่หา box1 ไม่เจอ
                MAX_BOX1_RETRY = 3      # เกิน 3 ครั้ง → เริ่มใหม่ตั้งแต่ play8 (relaunch ไฟล์เดิม)
                while not box2_found:
                    check_device_reset(serial, cycle_start)

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

                                # หลังกด box1 → แวะหา ad-rewardfix1 (5 วิ) เจอแล้วกดก่อนค่อยไปสเต็ปต่อไป
                                gui_log(serial, "Checking ad-rewardfix1 (5s)...", step="box1 AdFix")
                                ad_deadline = time.time() + 5
                                while time.time() < ad_deadline:
                                    check_device_reset(serial, cycle_start)
                                    img_ad = get_screen_capture(device)
                                    if img_ad is not None:
                                        pts_ad = img_search(img_ad, os.path.join(IMG_DIR, "ad-rewardfix1.bmp"))
                                        if pts_ad:
                                            x_ad, y_ad = pts_ad[0]
                                            device.shell(f"input swipe {x_ad} {y_ad} {x_ad} {y_ad} 100")
                                            gui_log(serial, f"ad-rewardfix1 found! Clicked ({x_ad}, {y_ad})", step="box1 AdFix")
                                            time.sleep(2)
                                            break
                                    time.sleep(0.5)

                                box1_found = True
                                break
                        time.sleep(1.2)

                    if not box1_found:
                        box1_retry += 1
                        # หา box1 ไม่เจอเกิน 5 ครั้ง → ปิดแอพ แล้วเริ่มใหม่ตั้งแต่ play8 (ไฟล์เดิม)
                        if box1_retry >= MAX_BOX1_RETRY:
                            gui_log(serial, f"box1.bmp not found {box1_retry}x — restarting from play8 (same file, keep login)...",
                                    step="Restart play8", status="stuck")
                            DEVICE_RESTART_PLAY8[serial] = (file_path, original_name)
                            device.shell("am force-stop jp.konami.pesam")
                            time.sleep(1)
                            raise RestartFromPlay8Exception("box1 not found 5x — restart from play8")
                        gui_log(serial, f"box1.bmp not found, retrying sequence ({box1_retry}/{MAX_BOX1_RETRY})", step="Retry")
                        continue

                    # box2
                    gui_log(serial, "Waiting box2.bmp...", step="box2")
                    start_box = time.time()
                    while time.time() - start_box < 25:  # Increased timeout slightly to account for retries
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "box2.bmp"))
                            if pts:
                                x, y = pts[0]
                                gui_log(serial, f"box2.bmp found at ({x},{y}) — clicking...", step="box2")
                                # Keep clicking if still visible
                                retry_start = time.time()
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    time.sleep(1.5)
                                    img_check = get_screen_capture(device)
                                    if img_check is not None:
                                        pts_check = img_search(img_check, os.path.join(IMG_DIR, "box2.bmp"))
                                        if not pts_check:
                                            gui_log(serial, "box2.bmp gone!", step="box2 OK")
                                            break
                                        else:
                                            if time.time() - retry_start > 5.0:
                                                gui_log(serial, "box2 still visible after 5s — forcing box3", step="box2 Timeout")
                                                break
                                            gui_log(serial, "box2.bmp still visible — clicking again...", step="box2 Retry")
                                    else:
                                        # Capture failed, wait a bit and break/continue
                                        time.sleep(1.0)
                                        break
                                time.sleep(2.5)
                                box2_found = True
                                break
                        time.sleep(1.2)
                
                # box3 (กดเรื่อยๆ จนไม่เจอครบ 5s ค่อยไป box4)
                gui_log(serial, "Waiting box3.bmp...", step="box3")
                last_seen = time.time()
                while time.time() - last_seen < 5:
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
                gui_log(serial, "box3 not seen for 5s, moving to box4", step="box3-done")

                # box4 — เจอแล้ว "กดซ้ำไปเรื่อยๆ จนกว่า box4 จะหายไปจริง" ค่อยไปทำ gacha
                #        (เดิมกดครั้งเดียวแล้วไปต่อเลย → box4 ยังค้างอยู่ แต่ไปเริ่ม gacha แล้ว)
                gui_log(serial, "Waiting box4.bmp...", step="box4")
                while True:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = img_search(img, os.path.join(IMG_DIR, "box4.bmp"))
                        if pts:
                            x, y = pts[0]
                            # ค้างเกิน 3 วิ กดซ้ำ วนจนหาย (90s ยังไม่หาย → log แล้วไปต่อ กันค้างทั้งรอบ)
                            if click_img_until_gone(device, cycle_start, serial,
                                                    os.path.join(IMG_DIR, "box4.bmp"),
                                                    x, y, stuck_secs=3.0, timeout=90.0, tag="box4"):
                                gui_log(serial, "box4.bmp หายแล้ว → ไปทำ gacha ต่อ", step="box4 OK")
                            time.sleep(4)
                            break
                    time.sleep(1)

            DEVICE_DISABLE_FIXEVENT[serial] = True

            # 7.3.5 CheckCoin + FindHero (ไม่มี gacha) → ใช้เลขเหรียญที่สแกนไว้ก่อนแล้ว → หา hero
            #       เลขเหรียญที่สแกนได้จะ "เขียนทับ" เลขเดิมใน -[เลข] (ไม่ต่อเพิ่มจนชื่อยาว)
            #       เจอ → Hero+ชื่อ-[เลขใหม่] , ไม่เจอ → ชื่อ-[เลขใหม่]
            #       *** เปิดกาชาอยู่ (DO_GACHA/NEW_GACHA) → ข้ามไปทำ find "หลังสุ่มเสร็จ" แทน ***
            if (CHECK_COIN == 1 and FIND_HERO == 1
                    and DO_GACHA != 1 and NEW_GACHA != 1 and GACHA_FIND != 1 and GACHA_CHECK != 1):
                gui_log(serial, "CheckCoin+Find mode → using pre-scanned coin, find hero...", step="Coin+Find", status="working")
                if find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                    continue  # Start next file immediately

            # 7.4 Check Coin Sequence (Optional)
            #     ข้าม standalone check-coin ถ้าเปิด Gacha+Find (สแกนเหรียญรวมในเส้นทางนั้นแล้ว)
            #     และข้ามถ้าเปิด FindHero ด้วย (เคสนั้นไปทำในบล็อก 7.3.5 CheckCoin+Find แทน)
            #     และข้ามถ้าเปิด Gacha Free (GACHA_FREE/GACHA_CHECK) — ไปสแกนเหรียญ "ตอนจบ gacha free"
            #     ก่อน export แทน ไม่งั้นจะจบรอบตั้งแต่ยังไม่ได้สุ่มฟรีเลย
            #     และข้ามถ้าเปิดกาชาปกติ (DO_GACHA/NEW_GACHA) — ไปสแกนเหรียญ "ตอนจบสุ่ม" ก่อน export
            #     (บล็อก 9) เหตุผลเดียวกัน: ไม่งั้นเช็คเหรียญเสร็จแล้วปัดไฟล์ทิ้งตั้งแต่ยังไม่ได้สุ่ม
            if (CHECK_COIN == 1 and GACHA_FIND != 1 and FIND_HERO != 1
                    and GACHA_FREE != 1 and GACHA_CHECK != 1
                    and DO_GACHA != 1 and NEW_GACHA != 1):
                if check_coin_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                    continue  # Start next file immediately

            # 7.5 Find Hero Sequence (Optional)
            #     *** ถ้าเปิดกาชาอยู่ (DO_GACHA/NEW_GACHA) → ไม่ทำตรงนี้ ***
            #     ให้ไปทำ find "หลังสุ่มกาชาเสร็จ" (บล็อก 8.5) เพื่อไม่ให้ปิดแอพก่อนสุ่ม
            if (FIND_HERO == 1 and GACHA_CHECK != 1 and GACHA_FIND != 1
                    and DO_GACHA != 1 and NEW_GACHA != 1):
                if find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                    continue  # Start next file immediately

            # 7.6 Gacha Free Sequence (Optional)
            #     ถ้าเปิด Gacha+Find (GACHA_FIND) → ข้าม free-gacha ไปทำ gacha ปกติ (gacha3) แทน
            if (GACHA_FREE == 1 or GACHA_CHECK == 1) and GACHA_FIND != 1:
                # ── เหรียญน้อยกว่าเกณฑ์ → ข้ามการสุ่มฟรี ──
                if coin_low:
                    if GACHA_CHECK == 1:
                        # find เปิดอยู่ → ข้ามสุ่ม ไปทำ fin เลย (เริ่มจากหน้า main menu)
                        gui_log(serial, f"Low coin → skip Gacha Free, go Find Hero...", step="Low Coin → Find")
                        if find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                            continue  # Start next file immediately
                    else:
                        # สุ่มอย่างเดียว → จบรอบ (บันทึกเลขเหรียญลง check-coin)
                        gui_log(serial, f"Low coin → skip Gacha Free, end cycle.", step="Low Coin → End")
                        if check_coin_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                            continue  # Start next file immediately
                elif gacha_free_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                    continue  # Start next file immediately

            # ── เหรียญน้อยกว่าเกณฑ์ + เปิด Gacha mode → ข้ามการสุ่ม ──
            if DO_GACHA == 1 and coin_low:
                if GACHA_FIND == 1:
                    # find เปิดอยู่ → ข้ามสุ่ม ไปทำ fin เลย (เริ่มจากหน้า main menu)
                    gui_log(serial, f"Low coin → skip Gacha, go Find Hero...", step="Low Coin → Find")
                    if find_hero_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                        continue  # Start next file immediately
                else:
                    # สุ่มอย่างเดียว → จบรอบ (บันทึกเลขเหรียญลง check-coin)
                    gui_log(serial, f"Low coin → skip Gacha, end cycle.", step="Low Coin → End")
                    if check_coin_mode(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                        continue  # Start next file immediately

            # 8. Gacha Sequence (Optional)
            gacha_hero_found = None
            if (DO_GACHA == 1 or NEW_GACHA == 1) and not coin_low:
                gui_log(serial, "Gacha sequence started...", step="Gacha Mode", status="working")
                # ปิด floating fixout ตลอด sequence กาชา (new-g1/gacha4/gacha5/OCR ทั้งหมด)
                # — หน้ากาชามีปุ่มคล้าย fixout จับผิดแล้ว Back spam มั่ว (เปิดกลับอัตโนมัติตอนเริ่ม cycle ใหม่)
                DEVICE_DISABLE_FIXOUT[serial] = True
                # เปิดหา ad-rewardfix1 แบบลอยๆ ตลอด sequence กาชา — เจอเมื่อไหร่กดปิดทันที
                DEVICE_IN_GACHA[serial] = True
                
                while True:
                    try:
                        if NEW_GACHA == 1:
                            global in_new_gacha_loop
                            in_new_gacha_loop = True
                            try:
                                while True:
                                    try:
                                        # 1. รอ/คลิก new-gacha1.bmp
                                        gui_log(serial, "Waiting new-gacha1.bmp...", step="new-g1")
                                        new_g1_swipe_count = 0
                                        fixswap_first_seen = None
                                        fixswap_triggered = False
                                        newg1_stuck_since = time.time()   # ค้างครบ 8 วิ → หา fixout กดเฉยๆ
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img = get_screen_capture(device)
                                            if img is not None:
                                                img, _ = check_and_click_fixback(device, img, serial)
                                                if img is None:
                                                    continue

                                                # ค้างหา new-gacha1 ครบ 8 วิ → เจอ fixout ให้กดปิดเฉยๆ แล้วหาต่อตามปกติ
                                                newg1_stuck_since = fixout_click_if_stuck(device, serial, img, newg1_stuck_since, step="NewG FixOut",
                                                                                          skip_if=os.path.join(IMG_DIR, "ch", "checkpoint-gacha4.png"))

                                                # 1. เช็ค fixswap.bmp ก่อน (หาแบบลอยๆ ตลอดเวลา)
                                                pts_fixswap = img_search(img, os.path.join(IMG_DIR, "fixswap.bmp"))
                                                if pts_fixswap:
                                                    if fixswap_triggered:
                                                        x_fs, y_fs = pts_fixswap[0]
                                                        device.shell(f"input swipe {x_fs} {y_fs} {x_fs} {y_fs} 100")
                                                        gui_log(serial, "fixswap.bmp still visible! Re-clicking it immediately...", step="FixSwap ReClick")
                                                        new_g1_swipe_count = 0  # เริ่มลื่นหน้าจอใหม่อีกรอบ
                                                        time.sleep(1.5)
                                                        continue
                                                    else:
                                                        if fixswap_first_seen is None:
                                                            fixswap_first_seen = time.time()
                                                            gui_log(serial, "fixswap.bmp detected, starting 10s timer...", step="FixSwap Timer")
                                                        else:
                                                            elapsed = time.time() - fixswap_first_seen
                                                            if elapsed >= 10.0:
                                                                x_fs, y_fs = pts_fixswap[0]
                                                                device.shell(f"input swipe {x_fs} {y_fs} {x_fs} {y_fs} 100")
                                                                gui_log(serial, f"fixswap.bmp detected for {elapsed:.1f}s. Clicking it!", step="FixSwap Click")
                                                                new_g1_swipe_count = 0  # เริ่มลื่นหน้าจอใหม่อีกรอบ
                                                                time.sleep(1.5)
                                                                fixswap_triggered = True
                                                                continue
                                                else:
                                                    # หากไม่พบ fixswap.bmp ให้รีเซ็ตตัวจับเวลาและสถานะปุ่มกดซ้ำ
                                                    fixswap_first_seen = None
                                                    fixswap_triggered = False

                                                # 1.5 เช็ค fixgachanew1.bmp (หาแบบลอยๆ ตลอดเวลา - เจอให้กด fixswap ทันที)
                                                pts_fixgachanew = img_search(img, os.path.join(IMG_DIR, "fixgachanew1.bmp"))
                                                if pts_fixgachanew:
                                                    pts_fs_fallback = img_search(img, os.path.join(IMG_DIR, "fixswap.bmp"))
                                                    if pts_fs_fallback:
                                                        x_click, y_click = pts_fs_fallback[0]
                                                        click_name = "fixswap.bmp"
                                                    else:
                                                        x_click, y_click = pts_fixgachanew[0]
                                                        click_name = "fixgachanew1.bmp"
                                                    device.shell(f"input swipe {x_click} {y_click} {x_click} {y_click} 100")
                                                    gui_log(serial, f"fixgachanew1.bmp detected! Clicking {click_name} immediately...", step="FixGachaNew Instant")
                                                    new_g1_swipe_count = 0  # เริ่มลื่นหน้าจอใหม่อีกรอบ
                                                    time.sleep(1.5)
                                                    continue

                                                # 2. เช็ค new-gacha1.bmp (หากเจอแล้วจะหลุดลูปและหยุดหา fixswap)
                                                #    (รูปแยกเก็บใน img/ch/ — อยากแก้รูปไปเปลี่ยนที่โฟลเดอร์นั้น)
                                                pts = img_search(img, os.path.join(IMG_DIR, "ch", "new-gacha1.bmp"), threshold=0.95)
                                                if pts:
                                                    # GACHA500 step1: สแกน coin ที่หน้า new-gacha1 (จอนี้ coin อ่านได้ชัด) ก่อนกด
                                                    #   coin >= เกณฑ์ → เก็บเข้า coin<threshold>+ แล้วจบบัญชี | < เกณฑ์ → สุ่มต่อ
                                                    if GACHA500 == 1:
                                                        _g500_check_coin_and_collect(device, cycle_start, serial, original_name, file_path, img)
                                                    x, y = pts[0]
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, f"✅ new-gacha1 found! Clicked ({x},{y})", step="NewG Found")
                                                    time.sleep(1.5)
                                                    break

                                                if NEW_GACHA_SWIPE == 1:
                                                    new_g1_swipe_count += 1
                                                    log_msg = f"new-gacha1 not found (swipe {new_g1_swipe_count}). Swiping 144 243 -> 699 233 (250ms)..."
                                                    gui_log(serial, log_msg, step="Swipe NewG1")
                                                    print(f"[{serial}] {log_msg}")
                                                    res = device.shell("input swipe 144 243 699 233 250")
                                                    print(f"[{serial}] ADB swipe command executed. Result: {res.strip() if res else 'OK'}")
                                                time.sleep(0.1)
                                            time.sleep(0.1)

                                        # 2. หา new-gacha1.bmp — วนหาไปเรื่อยๆ "จนกว่าจะเจอ" (ไม่มีลิมิต ห้ามข้ามไป Gacha4)
                                        gui_log(serial, "Waiting new-gacha1 + checkpoint-gacha4 (until found)...", step="new-g1_step2")
                                        swipe_count = 0
                                        cp_wait_n = 0                     # นับรอบที่เจอ new-gacha1 แต่ยังไม่เจอ checkpoint-gacha4
                                        newg_stuck_since = time.time()   # ค้างครบ 8 วิ → หา fixout กดเฉยๆ
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img = get_screen_capture(device)
                                            if img is not None:
                                                img, _ = check_and_click_fixback(device, img, serial)
                                                if img is None:
                                                    continue
                                                # ค้างหา new-gacha1 ครบ 8 วิ → เจอ fixout ให้กดปิดเฉยๆ แล้วหาต่อตามปกติ
                                                newg_stuck_since = fixout_click_if_stuck(device, serial, img, newg_stuck_since, step="NewG FixOut",
                                                                                skip_if=os.path.join(IMG_DIR, "ch", "checkpoint-gacha4.png"))
                                                # *** เจอ checkpoint-gacha4 = อยู่หน้ากาชาแล้ว → ไป step ถัดไป (gacha4v2/gacha4) ทันที ***
                                                pts_cp4 = img_search(img, os.path.join(IMG_DIR, "ch", "checkpoint-gacha4.png"))
                                                pts = img_search(img, os.path.join(IMG_DIR, "ch", "new-gacha1.bmp"), threshold=0.95)
                                                if pts_cp4:
                                                    if pts:
                                                        x, y = pts[0]   # เจอ new-gacha1 ในเฟรมเดียวกัน → กดก่อนแล้วค่อยไปต่อ
                                                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                        gui_log(serial, f"✅ เจอครบ 2 เงื่อนไข (new-gacha1 + checkpoint-gacha4)! Clicked ({x},{y})", step="NewG Found")
                                                        time.sleep(1.5)
                                                    else:
                                                        gui_log(serial, "✅ เจอ checkpoint-gacha4 แล้ว — ไป step ถัดไป (gacha4v2/gacha4)", step="NewG Found")
                                                    break
                                                if pts:
                                                    # เจอ new-gacha1 แต่ยังไม่เจอ checkpoint-gacha4 →
                                                    #   "กด new-gacha1 ไปก่อน" แต่ยังไม่นับว่าเจอ (ยังไม่ break) วนเช็คต่อ
                                                    x_ng, y_ng = pts[0]
                                                    device.shell(f"input swipe {x_ng} {y_ng} {x_ng} {y_ng} 100")
                                                    cp_wait_n += 1
                                                    if cp_wait_n % 5 == 1:
                                                        gui_log(serial, f"เจอ new-gacha1 → กด ({x_ng},{y_ng}) แต่ยังไม่เจอ checkpoint-gacha4 ({cp_wait_n}) — รอต่อ...", step="NewG Wait CP")
                                                    time.sleep(1.0)
                                                else:
                                                    swipe_count += 1
                                                    if NEW_GACHA_SWIPE == 1:
                                                        # เลื่อนตำแหน่ง 144 243 -> 699 233 แล้วหาต่อ
                                                        log_msg = f"new-gacha1 not found (swipe {swipe_count}). Swiping 144 243 -> 699 233 (250ms)..."
                                                        gui_log(serial, log_msg, step="Swipe NewG")
                                                        print(f"[{serial}] {log_msg}")
                                                        res = device.shell("input swipe 144 243 699 233 250")
                                                        print(f"[{serial}] ADB swipe command executed. Result: {res.strip() if res else 'OK'}")
                                                        time.sleep(0.1)
                                                    else:
                                                        # ปิด swipe อยู่ → รอ 1.5 วิ/รอบ แล้ววนหาต่อจนกว่าจะเจอ
                                                        gui_log(serial, f"new-gacha1 not found (try {swipe_count}) — waiting 1.5s...", step="Wait NewG")
                                                        time.sleep(1.5)
                                            time.sleep(0.1)
                                        break
                                    except ResetGachaException:
                                        gui_log(serial, "Resetting Gacha sequence to step 1 due to fixgachanew1...", step="ResetGacha")
                                        time.sleep(1)
                                        continue
                            finally:
                                in_new_gacha_loop = False
                        else:
                            # gacha1 -> gacha2
                            goto_gacha4 = False
                            for i in range(1, 3):
                                if goto_gacha4:
                                    break
                                name = f"gacha{i}.bmp"
                                gui_log(serial, f"Waiting {name}...", step=name)
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, force_g4 = check_and_click_fixback(device, img, serial)
                                        if force_g4:
                                            goto_gacha4 = True
                                            break
                                        if img is None:
                                            continue
                                        pts = img_search(img, os.path.join(IMG_DIR, name))
                                        if pts:
                                            x, y = pts[0]
                                            if i == 2:
                                                # gacha2 — กดซ้ำไปเรื่อยๆ จนกว่าจะหายไปจริง ค่อยไปต่อ
                                                click_img_until_gone(device, cycle_start, serial,
                                                                     os.path.join(IMG_DIR, name),
                                                                     x, y, stuck_secs=3.0, timeout=60.0, tag="gacha2")
                                                # หลัง gacha2 → แวะหา ad-rewardfix1 5 วิ (ไม่เจอ = ข้ามไปต่อ ไม่เป็นไร)
                                                find_and_click_optional(device, cycle_start, serial,
                                                                        "ad-rewardfix1.bmp", secs=5.0, tag="ad-reward")
                                            else:
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            time.sleep(4)
                                            break
                                    time.sleep(1)

                            # swipe until gacha3
                            if not goto_gacha4:
                                gui_log(serial, "Swiping from 618,308 to 54,306 for gacha3...", step="Swipe Gacha")
                                found_g3 = False
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, force_g4 = check_and_click_fixback(device, img, serial)
                                        if force_g4:
                                            goto_gacha4 = True
                                            break
                                        if img is None:
                                            continue
                                        pts = img_search(img, os.path.join(IMG_DIR, "gacha3.bmp"))
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, "Clicking gacha3.bmp...", step="G3-Click")
                                            time.sleep(2)
                                            found_g3 = True
                                            continue
                                        else:
                                            if found_g3:
                                                break
                                    # Swipe (drag) action
                                    device.shell("input swipe 618 308 54 306 3000")
                                    time.sleep(2)

                        # gacha4
                        if CUSTOM_GACHA == 1 or GACHA500 == 1:
                            # Custom Gacha Loop Mode
                            # *** GACHA500=1 เข้าบล็อกนี้เสมอ (ไม่ต้องเปิด CUSTOM_GACHA) ***
                            #     — step2 (v2/gacha500) อยู่ในนี้ ถ้าไปเข้า Normal flow จะกลายเป็นกด gacha4 แทน
                            # GACHA_LOOP_LIMIT = 0 → สุ่มจนหมด (จนเจอ nocions/outloop) | >0 → สุ่มไม่เกิน N รอบแล้ว break
                            if GACHA_LOOP_LIMIT > 0:
                                gui_log(serial, f"Custom Gacha mode active... (จำกัด {GACHA_LOOP_LIMIT} รอบ)", step="Custom Gacha")
                            else:
                                gui_log(serial, "Custom Gacha mode active... (สุ่มจน coin หมด)", step="Custom Gacha")
                            custom_rounds = 0
                            g500_done = False   # ขั้น gacha500 ทำ "รอบเดียวพอ" ต่อ 1 บัญชี
                            while True:
                                # Custom จำกัดรอบ: ครบตามที่ตั้ง → break ออกเลย ไม่รอ coin หมด
                                if GACHA_LOOP_LIMIT > 0 and custom_rounds >= GACHA_LOOP_LIMIT:
                                    gui_log(serial, f"ครบ {custom_rounds}/{GACHA_LOOP_LIMIT} รอบตามที่ตั้ง — break ออกจากลูปสุ่ม!", step="Custom Limit")
                                    break
                                custom_rounds += 1
                                if GACHA_LOOP_LIMIT > 0:
                                    gui_log(serial, f"สุ่มรอบที่ {custom_rounds}/{GACHA_LOOP_LIMIT}...", step="Custom Round")

                                # ══════════ step2 (GACHA500 = 1) ══════════
                                #  1) หา gacha4v2 (8 วิ)
                                #       เจอ  → กด → หา gacha5v2 → กด (สุ่มปกติ 1 ครั้ง)
                                #              → หา checkpointgacha → กด next → ไปทำ gacha500 ต่อ
                                #       ไม่เจอ → ข้ามไปทำ gacha500 เลย
                                #  2) หา gacha500 → เจอ = กด
                                #       เจอ nocions     → กด Back 1 ครั้ง → skip ไป gacha4
                                #       ไม่เจอ nocions  → หา checkpointgacha → กด next → ไป gacha4
                                #  3) รอบถัดไปใช้ flow gacha4 ปกติ จนครบ GACHA_LOOP_LIMIT
                                #     (ออกจากลูปเมื่อเจอ outloop หรือครบจำนวนรอบใน config)
                                #  *** ONE_GACHA500 = 0 → v2/gacha500 ทำ "รอบเดียว" แล้ววน gacha4 ต่อ
                                #      ONE_GACHA500 = 1 → ทำ "เฉพาะ v2 + gacha500" เท่านั้น ปิด flow gacha4 ทิ้งเลย
                                #                         (จบเมื่อ gacha500 ทำงานได้ / เจอ out900 / ครบจำนวนรอบ) ***
                                if GACHA500 == 1 and (ONE_GACHA500 == 1 or not g500_done):
                                    g500_done = True   # (ONE_GACHA500=0) ทำครั้งเดียว — รอบถัดไปวน gacha4 ปกติ
                                    g500_out900 = False   # เจอ out900 เมื่อไหร่ = ข้าม step ที่เหลือทั้งหมดทันที
                                    g500_worked = False   # gacha500 "กดได้จริง" หรือยัง — ONE_GACHA500 นับจากตัวนี้เท่านั้น
                                                          # (gacha4v2/gacha5v2 ไม่นับ, step1 coin ก็ไม่นับ)
                                    # ── 1) gacha4v2 (8 วิ) ──
                                    gui_log(serial, "Waiting gacha4v2 (8s)...", step="G4v2")
                                    pts_g4v2 = None
                                    dl_g4v2 = time.time() + 8
                                    while time.time() < dl_g4v2:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                            if img is None:
                                                continue
                                            pts_g4v2 = img_search(img, os.path.join(IMG_DIR, "gacha4v2.bmp"))
                                            if pts_g4v2:
                                                break
                                            # เจอ out900 ตั้งแต่ตอนหา gacha4v2 → ข้าม v2/gacha500 ที่เหลือทั้งหมด
                                            if img_search(img, os.path.join(IMG_DIR, "ch", "out900.bmp"), threshold=0.95):
                                                gui_log(serial, "เจอ out900 (ตอนหา gacha4v2) → ข้าม step v2/gacha500", step="G4v2 Out900")
                                                g500_out900 = True
                                                break
                                        time.sleep(0.2)

                                    if pts_g4v2:
                                        # เจอ → กด gacha4v2 (ค้างเกิน 3 วิ กดซ้ำจนหาย) แล้วหา gacha5v2 กดต่อ
                                        x_4v2, y_4v2 = pts_g4v2[0]
                                        gui_log(serial, f"gacha4v2 found! Clicking ({x_4v2},{y_4v2}) — waiting gacha5v2...", step="G4v2-Click")
                                        click_img_until_gone(device, cycle_start, serial,
                                                             os.path.join(IMG_DIR, "gacha4v2.bmp"),
                                                             x_4v2, y_4v2, stuck_secs=3.0, timeout=None, tag="G4v2-Click")

                                        # หา gacha5v2 — วนจนกว่าจะเจอ (ทางออกอื่น: เจอ out900 / รอเกิน 70 วิ)
                                        #   แวะหา next.bmp ด้วย — หน้าผลสุ่มค้างอยู่จะบัง gacha5v2 ไว้
                                        clicked_g5v2 = False
                                        g5v2_wait_start = time.time()
                                        g5v2_last_log = 0.0
                                        G5V2_MAX_WAIT = 70    # รอเกินนี้ = ข้ามไปทำ gacha500 ต่อเลย
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img = get_screen_capture(device)
                                            if img is not None:
                                                img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                                if img is None:
                                                    continue
                                                pts_g5v2 = img_search(img, os.path.join(IMG_DIR, "gacha5v2.bmp"))
                                                if pts_g5v2:
                                                    x_5v2, y_5v2 = pts_g5v2[0]
                                                    gui_log(serial, f"gacha5v2 found! Clicking ({x_5v2},{y_5v2}) — สุ่มปกติ 1 ครั้ง", step="G5v2-Click")
                                                    # ค้างเกิน 3 วิ กดซ้ำจนหาย
                                                    click_img_until_gone(device, cycle_start, serial,
                                                                         os.path.join(IMG_DIR, "gacha5v2.bmp"),
                                                                         x_5v2, y_5v2, stuck_secs=3.0, timeout=None, tag="G5v2-Click")
                                                    clicked_g5v2 = True
                                                    break
                                                # เจอ out900 = ไปต่อไม่ได้ → ข้าม gacha500 ที่เหลือทั้งหมด
                                                if img_search(img, os.path.join(IMG_DIR, "ch", "out900.bmp"), threshold=0.95):
                                                    gui_log(serial, "เจอ out900 ระหว่างรอ gacha5v2 → ข้าม step gacha500", step="G5v2 Out900")
                                                    g500_out900 = True
                                                    break
                                                # แวะหา next.bmp ระหว่างรอ — เจอ = กดจนหาย (หน้าผลสุ่มค้างบัง gacha5v2 อยู่)
                                                pts_nx5 = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                                                if pts_nx5:
                                                    x_nx5, y_nx5 = pts_nx5[0]
                                                    gui_log(serial, f"ระหว่างรอ gacha5v2 — เจอ next.bmp กด ({x_nx5},{y_nx5})", step="G5v2 Next")
                                                    click_next_until_gone(device, cycle_start, serial, x_nx5, y_nx5, tag="G5v2 Next")
                                                    continue
                                            # log ทุก 15 วิ ให้เห็นว่ายังรออยู่ (ไม่ได้ค้างตาย)
                                            waited = time.time() - g5v2_wait_start
                                            if waited >= G5V2_MAX_WAIT:
                                                gui_log(serial, f"รอ gacha5v2 เกิน {G5V2_MAX_WAIT} วิ — ไปทำ gacha500 ต่อเลย", step="G5v2 Timeout")
                                                break
                                            if waited - g5v2_last_log >= 15:
                                                g5v2_last_log = waited
                                                gui_log(serial, f"ยังรอ gacha5v2 อยู่... ({waited:.0f}s)", step="G5v2 Wait")
                                            time.sleep(0.2)
                                        if clicked_g5v2:
                                            # สุ่ม v2 เสร็จ → ปิดหน้าผลสุ่ม: checkpointgacha → next → ค่อยไป gacha500
                                            _g500_checkpoint_then_next(device, cycle_start, serial, tag="G4v2")
                                        elif not g500_out900:
                                            gui_log(serial, "ไม่ได้กด gacha5v2 — ไปต่อ gacha500", step="G5v2 Miss")
                                    elif not g500_out900:
                                        gui_log(serial, "ไม่เจอ gacha4v2 ใน 8 วิ → ไปทำ gacha500 แทน", step="G4v2 Miss")

                                    # ── 2) gacha500 → กด → เช็ค nocions → Back 1 ครั้ง ──
                                    #    หาไปเรื่อยๆ "ไม่มี timeout" (ยังไงก็ต้องเจอ) — กันเคสพลาดแล้วข้ามไป gacha4
                                    #    โดยไม่ได้ทำ gacha500 เลย
                                    if not g500_out900:
                                        gui_log(serial, "Looking for gacha500 (until found)...", step="G500")
                                    pts_g500 = None
                                    g500_wait_start = time.time()
                                    g500_last_log = 0.0
                                    while not g500_out900:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            pts_g500 = img_search(img, os.path.join(IMG_DIR, "ch", "gacha500.png"), threshold=0.95)
                                            if pts_g500:
                                                break
                                            # เจอ out900 (img/ch/) → หยุดหา gacha500 ไปทำ step ต่อไปเลย
                                            if img_search(img, os.path.join(IMG_DIR, "ch", "out900.bmp"), threshold=0.95):
                                                gui_log(serial, "เจอ out900 → หยุดหา gacha500 ไป step ถัดไปเลย", step="G500 Out900")
                                                g500_out900 = True
                                                break
                                            # แวะหา next.bmp ระหว่างรอ — เจอ = กด (หน้าผลสุ่มอาจค้างบัง gacha500 อยู่)
                                            pts_nw = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                                            if pts_nw:
                                                x_nw, y_nw = pts_nw[0]
                                                gui_log(serial, f"ระหว่างรอ gacha500 — เจอ next.bmp กด ({x_nw},{y_nw})", step="G500 Next")
                                                click_next_until_gone(device, cycle_start, serial, x_nw, y_nw, tag="G500 Next")
                                                continue
                                        # log ทุก 15 วิ ให้เห็นว่ายังหาอยู่ (ไม่ได้ค้างตาย)
                                        waited = time.time() - g500_wait_start
                                        if waited - g500_last_log >= 15:
                                            g500_last_log = waited
                                            gui_log(serial, f"ยังหา gacha500 อยู่... ({waited:.0f}s)", step="G500 Wait")
                                        time.sleep(0.3)

                                    if pts_g500:
                                        x_g5, y_g5 = pts_g500[0]
                                        device.shell(f"input swipe {x_g5} {y_g5} {x_g5} {y_g5} 100")
                                        gui_log(serial, f"gacha500 found! Clicked ({x_g5},{y_g5})", step="G500-Click")
                                        g500_worked = True   # ✅ gacha500 ทำงานแล้ว → ONE_GACHA500 ถึงจะนับว่าจบได้
                                        time.sleep(2)

                                        # ── กด gacha500v1 ต่อ (ปุ่มยืนยัน) — หา "พร้อมกับ nocions/out900/gacha500" ──
                                        #    หาไปเรื่อยๆ "ไม่มี timeout" (ยังไงก็ต้องเจอ)
                                        #    เจอ v1 = กด แล้ววนเช็คต่อ — ยังค้างอยู่ก็กดซ้ำ "สูงสุด 5 ครั้ง"
                                        #    ทางออก: v1 หายแล้ว / กดครบ 5 ครั้ง / เจอ nocions / เจอ out900
                                        #    (เจอ gacha500 ซ้ำ = คลิกแรกไม่ติด → กดซ้ำแล้วหา v1 ต่อ)
                                        gui_log(serial, "หา gacha500v1 + nocions + out900 + gacha500 (until found)...", step="G500v1")
                                        clicked_g5v1 = False
                                        g5v1_clicks = 0        # จำนวนครั้งที่กด gacha500v1 (limit 5 กันกดค้างวนไม่จบ)
                                        G5V1_MAX_CLICKS = 5
                                        g500_nocions = False   # เจอ nocions ตั้งแต่ตอนหา v1 → ไม่ต้องวนรอหลัง v1 อีก
                                        g5v1_wait_start = time.time()
                                        g5v1_last_log = 0.0
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img_v1 = get_screen_capture(device)
                                            if img_v1 is not None:
                                                pts_v1 = img_search(img_v1, os.path.join(IMG_DIR, "ch", "gacha500v1.png"), threshold=0.95)
                                                if pts_v1:
                                                    # ยังเจอ v1 อยู่ = ยังกดไม่ติด → กดซ้ำจนกว่าจะหาย (สูงสุด 5 ครั้ง)
                                                    if g5v1_clicks >= G5V1_MAX_CLICKS:
                                                        gui_log(serial, f"กด gacha500v1 ครบ {G5V1_MAX_CLICKS} ครั้งแล้วยังค้าง — ไปเช็ค nocions/checkpointgacha ต่อ", step="G500v1 Limit")
                                                        break
                                                    x_v1, y_v1 = pts_v1[0]
                                                    device.shell(f"input swipe {x_v1} {y_v1} {x_v1} {y_v1} 100")
                                                    g5v1_clicks += 1
                                                    clicked_g5v1 = True
                                                    gui_log(serial, f"gacha500v1 found! Clicked ({x_v1},{y_v1}) [{g5v1_clicks}/{G5V1_MAX_CLICKS}]", step="G500v1-Click")
                                                    time.sleep(2)
                                                    continue   # วนเช็คใหม่ — หายแล้วค่อยไปต่อ, ยังค้างก็กดซ้ำ
                                                # เคยกดไปแล้ว + ตอนนี้ v1 หายแล้ว → สำเร็จ ไปเช็ค nocions/checkpointgacha ต่อ
                                                if clicked_g5v1:
                                                    gui_log(serial, f"gacha500v1 หายแล้ว (กด {g5v1_clicks} ครั้ง) → ไปต่อ", step="G500v1 Gone")
                                                    break
                                                # เจอ nocions (coin ไม่พอ) → v1 ไม่มีวันมา → Back 1 ครั้ง → skip ไป gacha4
                                                if img_search(img_v1, os.path.join(IMG_DIR, "nocions.bmp")):
                                                    device.shell("input keyevent 4")   # Back 1 ครั้ง
                                                    gui_log(serial, "เจอ nocions (ตอนหา gacha500v1) → กด Back 1 ครั้ง → skip ไป gacha4", step="G500v1 NoCoin")
                                                    time.sleep(1.5)
                                                    g500_nocions = True
                                                    break
                                                # เจอ out900 (img/ch/) → ไปต่อไม่ได้แล้ว → หยุดหา gacha500v1
                                                if img_search(img_v1, os.path.join(IMG_DIR, "ch", "out900.bmp"), threshold=0.95):
                                                    gui_log(serial, "เจอ out900 → หยุดหา gacha500v1", step="G500v1 Out900")
                                                    g500_out900 = True
                                                    break
                                                # ยังเจอ gacha500 อยู่ = คลิกแรกไม่ติด (จอไม่เปลี่ยน) → กดซ้ำแล้วหา v1 ต่อ
                                                pts_g500_again = img_search(img_v1, os.path.join(IMG_DIR, "ch", "gacha500.png"), threshold=0.95)
                                                if pts_g500_again:
                                                    x_ga, y_ga = pts_g500_again[0]
                                                    device.shell(f"input swipe {x_ga} {y_ga} {x_ga} {y_ga} 100")
                                                    gui_log(serial, f"ยังเจอ gacha500 อยู่ — กดซ้ำ ({x_ga},{y_ga})", step="G500v1 ReClick")
                                                    time.sleep(2)
                                                    continue
                                            # log ทุก 15 วิ ให้เห็นว่ายังหาอยู่ (ไม่ได้ค้างตาย)
                                            waited = time.time() - g5v1_wait_start
                                            if waited - g5v1_last_log >= 15:
                                                g5v1_last_log = waited
                                                gui_log(serial, f"ยังหา gacha500v1 อยู่... ({waited:.0f}s)", step="G500v1 Wait")
                                            time.sleep(0.3)

                                        # ── หลังกด gacha500v1 → วนเช็ค 2 เงื่อนไข "ไม่มี timeout" ──
                                        #   1) เจอ nocions        → กด Back 1 ครั้ง → skip ไปทำ gacha4 เลย
                                        #   2) เจอ checkpointgacha → กด next.bmp → ไปทำ gacha4 ตามจำนวน loop ใน config
                                        if not (g500_out900 or g500_nocions):
                                            gui_log(serial, "รอ nocions หรือ checkpointgacha (ไม่มี timeout)...", step="G500 Wait")
                                        while not (g500_out900 or g500_nocions):
                                            check_device_reset(serial, cycle_start)
                                            img_w = get_screen_capture(device)
                                            if img_w is not None:
                                                # เจอ out900 → ไปต่อไม่ได้แล้ว → จบลูปสุ่มทันที
                                                if img_search(img_w, os.path.join(IMG_DIR, "ch", "out900.bmp"), threshold=0.95):
                                                    gui_log(serial, "เจอ out900 (หลัง gacha500v1) → จบลูปสุ่มทันที", step="G500 Out900")
                                                    g500_out900 = True
                                                    break
                                                # เงื่อนไข 1 — coin ไม่พอ
                                                if img_search(img_w, os.path.join(IMG_DIR, "nocions.bmp")):
                                                    device.shell("input keyevent 4")   # Back 1 ครั้ง
                                                    gui_log(serial, "เจอ nocions → กด Back 1 ครั้ง → skip ไป gacha4", step="G500 Back")
                                                    time.sleep(1.5)
                                                    break
                                                # เงื่อนไข 2 — สุ่มผ่าน เข้าหน้าผลสุ่ม
                                                if img_search(img_w, os.path.join(IMG_DIR, "checkpointgacha.bmp")):
                                                    gui_log(serial, "เจอ checkpointgacha → หา next.bmp แล้วกด", step="G500 CP")
                                                    dl_next = time.time() + 20
                                                    clicked_next = False
                                                    while time.time() < dl_next:
                                                        check_device_reset(serial, cycle_start)
                                                        img_n = get_screen_capture(device)
                                                        if img_n is not None:
                                                            pts_n = img_search(img_n, os.path.join(IMG_DIR, "next.bmp"))
                                                            if pts_n:
                                                                x_n, y_n = pts_n[0]
                                                                # กด next แล้วถ้ายังค้างเกิน 8 วิ กดซ้ำจนหาย
                                                                click_next_until_gone(device, cycle_start, serial, x_n, y_n, tag="G500 Next")
                                                                clicked_next = True
                                                                break
                                                        time.sleep(0.3)
                                                    if not clicked_next:
                                                        gui_log(serial, "ไม่เจอ next.bmp ใน 20 วิ — ไป gacha4 ต่อ", step="G500 Next Miss")
                                                    break
                                            time.sleep(0.3)
                                    elif not g500_out900:
                                        gui_log(serial, "ไม่เจอ gacha500 — ข้ามไปรอบถัดไป", step="G500 Miss")

                                    # ── เจอ out900 (ตอนหา gacha500 / gacha500v1 หรือหลังกด v1) ──
                                    #    ONE_GACHA500 = 1 → จบลูปสุ่มทันที (ทำรอบเดียวพอ)
                                    #    ONE_GACHA500 = 0 → ข้ามไปวน gacha4 ต่อตาม GACHA_LOOP_LIMIT (เหมือนเคส nocions)
                                    if g500_out900:
                                        if ONE_GACHA500 == 1:
                                            gui_log(serial, "out900 + ONE_GACHA500=1 → จบลูปสุ่ม (Back รัวๆ → ไป find ต่อ)", step="G500 Out900")
                                            found_g4 = False
                                            break
                                        gui_log(serial, "out900 + ONE_GACHA500=0 → ข้ามไปวน gacha4 ต่อ", step="G500 Out900")
                                        continue

                                    # ── ONE_GACHA500 = 1 → จบลูปสุ่มเลย "เฉพาะเมื่อ gacha500 ทำงานได้จริง" ──
                                    #    (gacha4v2/gacha5v2 และ step1 coin ไม่นับ — ทำได้ก็ไม่เป็นไร แต่ยังไม่จบ)
                                    if ONE_GACHA500 == 1:
                                        if g500_worked:
                                            gui_log(serial, "ONE_GACHA500=1 + gacha500 ทำงานแล้ว → จบลูปสุ่มเลย", step="G500 One")
                                            found_g4 = False
                                            break
                                        # ยังไม่ได้ทำ gacha500 → วน "v2/gacha500" ใหม่ (ไม่แตะ flow gacha4 เลย)
                                        gui_log(serial, "ONE_GACHA500=1 ยังไม่ได้ทำ gacha500 (v2 ไม่นับ) — วน v2/gacha500 ใหม่", step="G500 One Retry")
                                        continue

                                    gui_log(serial, "จบขั้น v2/gacha500 (ทำแล้ว 1 รอบ) — รอบถัดไปกลับไปวนคลิก gacha4 ปกติ", step="G500 Done")

                                    # ── 3) วนรอบถัดไป (ตาม GACHA_LOOP_LIMIT) → ใช้ flow gacha4 ปกติ ──
                                    continue

                                # ══════════ สุ่ม loop ปกติ (flow เดิม: gacha4 → gacha5 → loopgacha1) ══════════
                                #   ใช้เมื่อ GACHA500 = 0  หรือ  GACHA500 = 1 แต่ทำ v2/gacha500 ไปแล้ว (รอบ 2 เป็นต้นไป)
                                # 1. Wait/Click gacha4.bmp
                                gui_log(serial, "Waiting gacha4.bmp (Custom)...", step="G4-Custom")
                                found_g4 = False
                                g4_click_count = 0
                                g4_wait_since = time.time()   # ค้างรอ gacha4 เกิน 8 วิ → ลองหา next.bmp แล้วกด
                                fixg1_first_seen = None       # ติดตาม fixgacha1 ค้าง (ครบ 10 วิ = กดปิด)
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                        if img is None:
                                            continue
                                        # (ไม่เช็ค outloop ตรงนี้ — outloop เช็คเฉพาะ "หลังกด gacha5" แล้วเท่านั้น)

                                        # ── fixgacha1 ค้างครบ 10 วิ → กดปิด แล้วกลับไปหา gacha4 ต่อ ──
                                        #    (ต้องค้างจริง 10 วิ กันกดพลาดตอนจอกำลังเปลี่ยน)
                                        pts_fg1 = img_search(img, os.path.join(IMG_DIR, "fixgacha1.bmp"))
                                        if pts_fg1:
                                            if fixg1_first_seen is None:
                                                fixg1_first_seen = time.time()
                                                gui_log(serial, "fixgacha1 detected — เฝ้าดู 10 วิ...", step="FixGacha1")
                                            elif time.time() - fixg1_first_seen >= 10:
                                                x_f1, y_f1 = pts_fg1[0]
                                                device.shell(f"input swipe {x_f1} {y_f1} {x_f1} {y_f1} 100")
                                                gui_log(serial, f"fixgacha1 ค้างครบ 10 วิ → กด ({x_f1},{y_f1}) แล้วกลับไปหา gacha4 ต่อ", step="FixGacha1 Click")
                                                fixg1_first_seen = None
                                                g4_wait_since = time.time()   # เริ่มจับเวลารอ gacha4 ใหม่
                                                time.sleep(1.5)
                                                continue
                                        else:
                                            fixg1_first_seen = None   # หายแล้ว → เจอใหม่ค่อยเริ่มนับ 10 วิใหม่

                                        # ค้างรอ gacha4 เกิน 8 วิ → หน้าผลสุ่มอาจยังค้างอยู่ → ลองหา next.bmp แล้วกด
                                        if time.time() - g4_wait_since > 8:
                                            pts_nx = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                                            if pts_nx:
                                                x_nx, y_nx = pts_nx[0]
                                                device.shell(f"input swipe {x_nx} {y_nx} {x_nx} {y_nx} 100")
                                                gui_log(serial, f"ค้างรอ gacha4 8s — เจอ next.bmp กด ({x_nx},{y_nx})", step="G4 Next")
                                                time.sleep(1.5)
                                            g4_wait_since = time.time()   # เริ่มจับเวลาใหม่ (เจอหรือไม่เจอก็ตาม)
                                            continue

                                        pts = img_search_any(img, ["gacha4.bmp", "gacha4v2.bmp"])
                                        if pts:
                                            gui_log(serial, "gacha4.bmp found! Checking checkpoint-gacha4...", step="G4-Verify")
                                            verified = False
                                            deadline_cp4 = time.time() + 8
                                            while time.time() < deadline_cp4:
                                                check_device_reset(serial, cycle_start)
                                                img_cp4 = get_screen_capture(device)
                                                if img_cp4 is not None:
                                                    pts_cp4 = img_search(img_cp4, os.path.join(IMG_DIR, "ch", "checkpoint-gacha4.png"))
                                                    if pts_cp4:
                                                        verified = True
                                                        pts_fresh = img_search_any(img_cp4, ["gacha4.bmp", "gacha4v2.bmp"])
                                                        if pts_fresh:
                                                            pts = pts_fresh
                                                        break
                                                time.sleep(0.2)
                                            
                                            if verified:
                                                x, y = pts[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                g4_click_count += 1
                                                gui_log(serial, f"Clicking gacha4.bmp... (count: {g4_click_count})", step="G4-Click")
                                                time.sleep(0.8)
                                                found_g4 = True
                                                # กด gacha4 ครบ 5 ครั้งแล้วยังไปต่อไม่ได้ (จอไม่เปลี่ยน)
                                                # → เลิกกดวน ไปทำ step Gacha5/gacha500 ต่อเลย
                                                if g4_click_count >= 5:
                                                    gui_log(serial, "กด gacha4 ครบ 5 ครั้งแล้วไปต่อไม่ได้ — ข้ามไป Gacha5/gacha500 เลย", step="G4-Limit")
                                                    break
                                                continue
                                            else:
                                                gui_log(serial, "checkpoint-gacha4.png not found in 8s! Proceeding to Gacha5...", step="G4-Failed")
                                                # รอหา fixgachanew2.bmp สูงสุด 5 วิ เจอแล้วกดซ้ำจนหายก่อนไปต่อ
                                                fg2_deadline = time.time() + 5
                                                while time.time() < fg2_deadline:
                                                    img_fg2 = fast_screencap(device)
                                                    pts_fg2 = img_search(img_fg2, os.path.join(IMG_DIR, "fixgachanew2.bmp")) if img_fg2 is not None else None
                                                    if pts_fg2:
                                                        x2, y2 = pts_fg2[0]
                                                        device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                                                        gui_log(serial, "Clicked fixgachanew2.bmp", step="G4-Failed")
                                                        time.sleep(1.5)
                                                        continue
                                                    break
                                                # ไปต่อ Gacha5 เลย (ไม่ reset กลับ new-gacha1) — ถ้า gacha5 ค้าง 8 วิ
                                                # watchdog ใน G5 จะสั่ง restart ตั้งแต่ play8 ให้เอง
                                                found_g4 = True
                                                break
                                        # เหรียญไม่พอ — เจอ nocions หรือ not-coin ตัวไหนก็นับว่าเหรียญหมด
                                        if img_search_any(img, ["nocions.bmp", "not-coin.bmp"]):
                                            found_g4 = "nocoin"
                                            break

                                        if found_g4:
                                            break
                                    time.sleep(0.15)

                                if found_g4 in ["nocoin", "outloop"]:
                                    if found_g4 == "nocoin":
                                        gui_log(serial, "เหรียญหมด (nocions/not-coin) detected during Custom Gacha!", step="No-Coins")
                                    else:
                                        gui_log(serial, "outloop.bmp detected during Custom Gacha!", step="Outloop Exit")
                                    break

                                # 2. Wait 10s delay (as requested: "ให้มัน delayด้วยดิ 10วิ")
                                gui_log(serial, "Proceeding to Gacha5 (Custom)... Delaying 10s...", step="G5-Custom")
                                time.sleep(10)

                                # 3. Wait/Click gacha5.bmp
                                #    (โหมด Custom: ไม่มี watchdog restart — ปล่อยให้ loop ทำงานจนเจอ
                                #     loopgacha1/nocions เอง ห้าม clear app กลางคัน)
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                        if img is None:
                                            continue
                                        # (ไม่เช็ค outloop ตรงนี้ — ยังไม่ได้กด gacha5 เช็คที่ step Loop-Check หลังกดแล้ว)

                                        # หากเจอ loopgacha1.bmp แสดงว่าเลย gacha5 ไปแล้ว ให้หลุดลูปทันที
                                        if img_search(img, os.path.join(IMG_DIR, "loopgacha1.bmp")):
                                            gui_log(serial, "loopgacha1.bmp detected during Gacha5 (Custom)! Proceeding.", step="G5-Skip")
                                            break

                                        pts = img_search_any(img, ["gacha5.bmp", "gacha5v2.bmp"])
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, "Clicking gacha5.bmp... (Custom)", step="G5-Click")
                                            time.sleep(1.5)
                                            break

                                        if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                                            found_g4 = "nocoin"
                                            break
                                    time.sleep(0.15)

                                if found_g4 in ["nocoin", "outloop"]:
                                    break

                                # (step2 gacha500 ย้ายไปอยู่ต้นรอบแล้ว — ทำงานเฉพาะ GACHA500=1 ซึ่ง continue ไปก่อนถึงตรงนี้)

                                # 4. Wait for loopgacha1.bmp or outloop.bmp
                                gui_log(serial, "Waiting for loopgacha1.bmp or outloop.bmp...", step="Loop-Check")
                                action_taken = False
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                        if img is None:
                                            continue
                                        if img_search(img, os.path.join(IMG_DIR, "outloop.bmp")):
                                            gui_log(serial, "outloop.bmp detected! Ending Custom Gacha.", step="Outloop Found")
                                            action_taken = "outloop"
                                            break
                                        # coin หมดกลางลูป → จบ custom gacha (กันวนรอ loopgacha1 ที่ไม่มีวันมา)
                                        if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                                            gui_log(serial, "nocions.bmp — coin หมด จบ custom gacha", step="No-Coins")
                                            action_taken = "outloop"
                                            break
                                        pts_loop = img_search(img, os.path.join(IMG_DIR, "loopgacha1.bmp"))
                                        if pts_loop:
                                            x, y = pts_loop[0]

                                            # แวะหา unlock-hero1.bmp 3 วิ
                                            gui_log(serial, "loopgacha1 found! Checking for unlock-hero1.bmp (3s)...", step="Check-Unlock")
                                            print(f"[{serial}] loopgacha1 found! Checking for unlock-hero1.bmp (3s)...")
                                            deadline_unlock = time.time() + 3
                                            while time.time() < deadline_unlock:
                                                check_device_reset(serial, cycle_start)
                                                img_unlock = get_screen_capture(device)
                                                if img_unlock is not None:
                                                    pts_unlock = img_search(img_unlock, os.path.join(IMG_DIR, "unlock-hero1.bmp"))
                                                    if pts_unlock:
                                                        device.shell("input keyevent 4")
                                                        gui_log(serial, "unlock-hero1.bmp found! Pressed back (once).", step="Unlock-Hero")
                                                        print(f"[{serial}] unlock-hero1.bmp found! Pressed back (once).")
                                                        time.sleep(2)
                                                        break
                                                time.sleep(0.5)

                                            # แล้วค่อยกด loopgacha1 ซ้ำๆ จนกว่าจะหายไป
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, f"loopgacha1.bmp found! Clicking ({x},{y}) until gone...", step="LoopGacha1")
                                            print(f"[{serial}] Clicking loopgacha1.bmp at ({x},{y}) until gone...")
                                            time.sleep(0.3)
                                            # กดซ้ำจนกว่า loopgacha1 จะหายไป
                                            retry_end = time.time() + 10
                                            while time.time() < retry_end:
                                                check_device_reset(serial, cycle_start)
                                                img_lp = get_screen_capture(device)
                                                if img_lp is not None:
                                                    pts_lp = img_search(img_lp, os.path.join(IMG_DIR, "loopgacha1.bmp"))
                                                    if not pts_lp:
                                                        gui_log(serial, "loopgacha1.bmp gone!", step="LoopGacha1 Gone")
                                                        break
                                                    x_lp, y_lp = pts_lp[0]
                                                    device.shell(f"input swipe {x_lp} {y_lp} {x_lp} {y_lp} 100")
                                                    gui_log(serial, "loopgacha1 still visible — re-clicking...", step="LoopGacha1 Retry")
                                                time.sleep(0.3)
                                            action_taken = "loop"
                                            continue
                                        else:
                                            if action_taken == "loop":
                                                break
                                    time.sleep(0.15)

                                if action_taken == "outloop":
                                    break
                            found_g4 = False # จบ Custom Gacha ไม่ต้องทำ OCR (ข้าม checkpointgacha)
                        else:
                            # Normal Gacha Flow (CUSTOM_GACHA == 0)
                            found_g4 = False
                            g4_click_count = 0
                            gui_log(serial, "Waiting gacha4.bmp (10s)...", step="Gacha4")
                            deadline_g4 = time.time() + 10
                            fixg1_first_seen = None   # ติดตาม fixgacha1 ค้าง (ครบ 10 วิ = กดปิด)
                            while time.time() < deadline_g4:
                                check_device_reset(serial, cycle_start)
                                img = get_screen_capture(device)
                                if img is not None:
                                    img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                    if img is None:
                                        continue

                                    # ── fixgacha1 ค้างครบ 10 วิ → กดปิด แล้วกลับไปหา gacha4 ต่อ ──
                                    #    ระหว่างเฝ้าดูจะต่ออายุ deadline ให้ ไม่งั้นหมดเวลา 10 วิก่อนจะครบรอบเฝ้าดู
                                    pts_fg1 = img_search(img, os.path.join(IMG_DIR, "fixgacha1.bmp"))
                                    if pts_fg1:
                                        if fixg1_first_seen is None:
                                            fixg1_first_seen = time.time()
                                            gui_log(serial, "fixgacha1 detected — เฝ้าดู 10 วิ...", step="FixGacha1")
                                        elif time.time() - fixg1_first_seen >= 10:
                                            x_f1, y_f1 = pts_fg1[0]
                                            device.shell(f"input swipe {x_f1} {y_f1} {x_f1} {y_f1} 100")
                                            gui_log(serial, f"fixgacha1 ค้างครบ 10 วิ → กด ({x_f1},{y_f1}) แล้วกลับไปหา gacha4 ต่อ", step="FixGacha1 Click")
                                            fixg1_first_seen = None
                                            time.sleep(1.5)
                                            deadline_g4 = time.time() + 10   # ให้เวลาหา gacha4 ใหม่เต็ม 10 วิ
                                            continue
                                        deadline_g4 = max(deadline_g4, time.time() + 12)  # ยังเฝ้าดูอยู่ → อย่าเพิ่งหมดเวลา
                                    else:
                                        fixg1_first_seen = None   # หายแล้ว → เจอใหม่ค่อยเริ่มนับ 10 วิใหม่

                                    # เช็ค outloop.bmp ก่อนเสมอ เจอแล้วจบการทำงานทันที
                                    if img_search(img, os.path.join(IMG_DIR, "outloop.bmp")):
                                        gui_log(serial, "outloop.bmp detected while waiting/clicking gacha4!", step="G4-Outloop")
                                        found_g4 = "outloop"
                                        break

                                    pts = img_search_any(img, ["gacha4.bmp", "gacha4v2.bmp"])
                                    if pts:
                                        gui_log(serial, "gacha4.bmp found! Checking checkpoint-gacha4...", step="G4-Verify")
                                        verified = False
                                        deadline_cp4 = time.time() + 8
                                        while time.time() < deadline_cp4:
                                            check_device_reset(serial, cycle_start)
                                            img_cp4 = get_screen_capture(device)
                                            if img_cp4 is not None:
                                                pts_cp4 = img_search(img_cp4, os.path.join(IMG_DIR, "ch", "checkpoint-gacha4.png"))
                                                if pts_cp4:
                                                    verified = True
                                                    pts_fresh = img_search_any(img_cp4, ["gacha4.bmp", "gacha4v2.bmp"])
                                                    if pts_fresh:
                                                        pts = pts_fresh
                                                    break
                                            time.sleep(0.2)
                                        
                                        if verified:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            g4_click_count += 1
                                            gui_log(serial, f"Clicking gacha4.bmp... (count: {g4_click_count})", step="G4-Click")
                                            time.sleep(0.8)
                                            found_g4 = True
                                            deadline_g4 = time.time() + 10
                                            continue
                                        else:
                                            gui_log(serial, "checkpoint-gacha4.png not found in 8s! Proceeding to Gacha5...", step="G4-Failed")
                                            # รอหา fixgachanew2.bmp สูงสุด 5 วิ เจอแล้วกดซ้ำจนหายก่อนไปต่อ
                                            fg2_deadline = time.time() + 5
                                            while time.time() < fg2_deadline:
                                                img_fg2 = fast_screencap(device)
                                                pts_fg2 = img_search(img_fg2, os.path.join(IMG_DIR, "fixgachanew2.bmp")) if img_fg2 is not None else None
                                                if pts_fg2:
                                                    x2, y2 = pts_fg2[0]
                                                    device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                                                    gui_log(serial, "Clicked fixgachanew2.bmp", step="G4-Failed")
                                                    time.sleep(1.5)
                                                    continue
                                                break
                                            # ไปต่อ Gacha5 เลย (ไม่ reset กลับ new-gacha1) — ถ้า gacha5 ค้าง 8 วิ
                                            # watchdog ใน G5 จะสั่ง restart ตั้งแต่ play8 ให้เอง
                                            found_g4 = True
                                            break
                                    # เช็คเหรียญไม่พอระหว่างรอ (nocions / not-coin เจอตัวไหนก็นับ)
                                    if img_search_any(img, ["nocions.bmp", "not-coin.bmp"]):
                                        found_g4 = "nocoin"
                                        break

                                    if found_g4:
                                        break
                                time.sleep(0.15)

                            if not found_g4:
                                # ไม่เจอ gacha4 ใน 10s -> แวะเช็ค nocions ต่ออีก 10s
                                gui_log(serial, "gacha4 not found, checking nocions/not-coin (10s)...", step="Check-NC")
                                deadline_nc = time.time() + 10
                                while time.time() < deadline_nc:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                        if img is None:
                                            continue
                                        if img_search_any(img, ["nocions.bmp", "not-coin.bmp"]):
                                            found_g4 = "nocoin"
                                            break
                                    time.sleep(0.15)

                            # จัดารกรณีเจอ nocions.bmp หรือ outloop.bmp (ไม่ว่าจะเจอตอนไหน)
                            if found_g4 in ["nocoin", "outloop"]:
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
                                else:
                                    gui_log(serial, "outloop.bmp detected! Ending gacha flow.", step="Outloop Exit")
                                # จบรอบนี้ทันที
                                found_g4 = False 
                            else:
                                # ถ้าผ่าน nocions มาได้ (ไม่เจอ) หรือเจอ gacha4 ไปแล้ว -> ไป gacha5 ต่อ
                                gui_log(serial, "Proceeding to Gacha5...", step="G5-Flow")
                                time.sleep(10) # 10s delay requested by user
                                while True:
                                    check_device_reset(serial, cycle_start)
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                        if img is None:
                                            continue
                                        # เช็ค outloop.bmp ก่อนเสมอ เจอแล้วจบการทำงานทันที
                                        if img_search(img, os.path.join(IMG_DIR, "outloop.bmp")):
                                            gui_log(serial, "outloop.bmp detected during Gacha5!", step="Outloop Exit")
                                            found_g4 = False
                                            break

                                        # หากเจอ checkpointgacha.bmp แสดงว่าเลย gacha5 ไปแล้ว ให้หลุดลูปทันที
                                        if img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp")):
                                            gui_log(serial, "checkpointgacha.bmp detected during Gacha5! Proceeding.", step="G5-Skip")
                                            found_g4 = True
                                            break

                                        pts = img_search_any(img, ["gacha5.bmp", "gacha5v2.bmp"])
                                        if pts:
                                            x, y = pts[0]
                                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                                            gui_log(serial, "Clicking gacha5.bmp...", step="G5-Click")
                                            time.sleep(1.5)
                                            found_g4 = True # ติ๊กให้ทำ checkpointgacha ต่อ
                                            break

                                        if img_search(img, os.path.join(IMG_DIR, "nocions.bmp")):
                                            # กรณีเจอตอนรอ gacha5
                                            gui_log(serial, "nocions.bmp detected during Gacha5!", step="No-Coins")
                                            found_g4 = False
                                            break
                                    time.sleep(0.15)
                        # checkpointgacha -> OCR (ข้ามถ้าไม่เจอ gacha4)
                        # NOSCAN=1 → ข้ามขั้นตอน checkpointgacha/OCR ทั้งหมด (ทำงานเหมือน gachafree)
                        if found_g4 and NOSCAN == 1:
                            gui_log(serial, "NOSCAN=1 → Skipping checkpointgacha/OCR (Gacha)", step="NoScan Skip")
                        elif found_g4:
                            gui_log(serial, "Waiting checkpointgacha or fixcheckpointgacha (OCR)...", step="OCR Wait")
                            deadline_ocr = time.time() + 60
                            while time.time() < deadline_ocr:
                                check_device_reset(serial, cycle_start)
                                img = get_screen_capture(device)
                                if img is not None:
                                    img, _ = check_and_click_fixback(device, img, serial, check_g1=False)
                                    if img is None:
                                        continue
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
                                        cprint(f"[{serial}] Gacha OCR: {display_text}")

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

                        break
                    except ResetGachaException as e:
                        gui_log(serial, f'Resetting Gacha sequence: {str(e)}', step='ResetGacha')
                        time.sleep(1)
                        continue

                # จบ sequence กาชาแล้ว → ปิดการหา ad-rewardfix1 แบบลอยๆ
                DEVICE_IN_GACHA[serial] = False

            # 8.5 Gacha + Find Hero (Optional) — หลังสุ่มกาชาเสร็จ "ไม่ clear app"
            #      next → กด Back รัวๆจนเจอ cancel → คลิก → แล้วค่อยค้นหา fin1
            #      ทำงานเมื่อ: เปิด GACHA_FIND  หรือ  เปิด FIND_HERO (find=1) คู่กับกาชา
            #      → ออกจากลูปสุ่มด้วยเหตุใดก็ตาม (outloop / nocions / ครบจำนวนรอบ) จะ "ไม่ปิดแอพจบรอบ"
            #        แต่ไปทำ find ต่อจนส่งไฟล์ออก แล้วค่อยปิดแอพเริ่มไฟล์ใหม่
            if ((GACHA_FIND == 1 or FIND_HERO == 1)
                    and (DO_GACHA == 1 or NEW_GACHA == 1) and not coin_low):
                gui_log(serial, "Gacha finished → ไม่ปิดแอพ ไปทำ Find Hero ต่อ (next → Back→cancel → fin1)...", step="Gacha+Find")
                if gacha_find_navigate_then_find_hero(device, cycle_start, serial, original_name, file_path, coin_prefix=coin_prefix):
                    continue  # find_hero_mode จัดการปิดแอป + ย้ายไฟล์ + จบรอบให้แล้ว

            # 9. Done & File Sorting
            # ── เปิด Check Coin คู่กับกาชา → กลับหน้า Home สแกนเหรียญ "ก่อน" ปิดแอป/ส่งไฟล์ออก ──
            #    (เหรียญเปลี่ยนไปหลังสุ่ม → ต้องอ่านค่าล่าสุด แล้วค่อยแนบเลขไปกับชื่อไฟล์)
            if CHECK_COIN == 1 and (DO_GACHA == 1 or NEW_GACHA == 1):
                gui_log(serial, "CheckCoin → กลับหน้า Home เพื่อสแกนเหรียญก่อนส่งไฟล์ออก...",
                        step="Coin Before Export", status="working")
                navigate_home(device, cycle_start, serial)
                new_coin = scan_coin_number(device, cycle_start, serial)
                if new_coin is not None:
                    coin_prefix = new_coin

            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            # ชื่อไฟล์ตอน export = user_code จริงจากข้างในไฟล์ .dat
            clean_orig = export_base_name(file_path, original_name, strip_dash=True)

            if DO_GACHA == 1:
                if NOSCAN == 1:
                    # NOSCAN → ไม่สแกน OCR → เก็บลง fast-random/ (เหมือน gachafree)
                    dest_dir = FAST_RANDOM_DIR
                    final_name = clean_orig
                    gui_log(serial, f"NOSCAN → {dest_dir}/{final_name}", step="Fast Random")
                elif gacha_hero_found:
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

            # แนบเลขเหรียญไว้ "หน้าชื่อไฟล์" แบบเดียวกับโหมด Check Coin → [420]+ชื่อเดิม.dat
            if CHECK_COIN == 1 and coin_prefix:
                import re as _re_cc
                _base = _re_cc.sub(r"^\[\d+\]\+", "", final_name)   # กัน [เลข]+ ซ้อน
                _base = _re_cc.sub(r"-\[\d+\]", "", _base)          # กันเลขแบบต่อท้ายเก่าปนมา
                final_name = f"[{coin_prefix}]+{_base}"
                gui_log(serial, f"🪙 Coins: {coin_prefix} -> {final_name}", step="Coin Match")

            dest = os.path.join(dest_dir, final_name)
            if os.path.exists(file_path):
                # ให้เวลาไฟล์คลายตัวเล็กน้อยก่อนย้าย
                time.sleep(2)
                try:
                    if os.path.exists(dest):
                        os.remove(dest)
                    # ใช้ copy + remove แทน move เพื่อความชัวร์บน Windows
                    _safe_copy(file_path, dest)
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

        except GachaCoinCollectedException as e:
            # step1: coin >= เกณฑ์ → ย้ายไฟล์เข้า coin<threshold>+ + release_file เรียบร้อยแล้วใน loop
            gui_log(serial, f"🪙✅ Coin collected — จบรอบ ({e})", step="Coin Done", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)
            continue

        except DeviceTimeoutException:
            gui_log(serial, f"⏱️ Timeout Exceeded! Moving file to timeout...", step="Timeout", status="error")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)
            
            if original_name:
                release_file(original_name)
                try:
                    src_file = os.path.join(INPUT_DIR, original_name)
                    if os.path.exists(src_file):
                        save_result(src_file, os.path.join(TIMEOUT_DIR, original_name))
                        gui_log(serial, f"Moved {original_name} to timeout/", step="Timeout Move")
                except Exception as e:
                    gui_log(serial, f"Failed to move {original_name} to timeout: {e}", step="Timeout Error")
            continue

        except FixClearReenterException:
            # fixclear → เข้าใหม่ไฟล์เดิม: อย่า release_file (เก็บ lock + ไฟล์ไว้ทำต่อ)
            gui_log(serial, "🔁 fixclear re-enter — relaunching same file...", step="Re-enter", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

        except RestartFromPlay8Exception:
            # box1 หาไม่เจอ 5 ครั้ง → เริ่มใหม่ตั้งแต่ play8 ด้วยไฟล์เดิม (อย่า release_file เก็บไฟล์ไว้)
            gui_log(serial, "🔁 Restart from play8 — relaunching same file...", step="Restart play8", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

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
            # คืนไฟล์กลับ input-id เสมอ (ไม่ย้ายไปโฟลเดอร์ผลลัพธ์) → กันส่งไฟล์มั่ว
            release_file(original_name)
            msg = str(e).lower()
            if "offline" in msg or "timed out" in msg or "timeout" in msg or "closed" in msg or "connection" in msg:
                # device หลุด/ค้างกลางคัน → reconnect แล้ว backoff นานขึ้น (อย่า spin)
                gui_log(serial, f"⚠️ Device offline/timeout — reconnecting & backing off...", step="Offline", status="stuck")
                try_reconnect_device(serial)
                time.sleep(10)
            else:
                gui_log(serial, f"❌ Error: {e}", status="stuck")
                time.sleep(5)
        finally:
            # Safe, non-disruptive memory optimization at the end of each account cycle
            try:
                device.shell("pm trim-caches 9999999999G")
                device.shell("su -c 'sync && echo 3 > /proc/sys/vm/drop_caches'")
            except Exception:
                pass
            # Clear remote AUTH directory at the end of the cycle to keep the emulator completely clean and secure
            try:
                device.shell(f"su -c 'rm -rf {REMOTE_AUTH_DIR}/*'")
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
def _disable_console_quickedit():
    """
    ปิด QuickEdit Mode ของ Windows Console กัน cmd "ค้าง" เวลารันนานๆ
    ปัญหา: ถ้าเผลอคลิก/ลากเลือกข้อความในหน้าต่าง cmd → Windows จะหยุด stdout
    ทำให้ thread ที่กำลัง print ค้าง และทุก thread ค้างตามทั้งหมด (บอตหยุดทำงาน)
    แก้โดยลบ flag ENABLE_QUICK_EDIT_MODE ออก (ปลอดภัย, ไม่มีผลบนระบบที่ไม่ใช่ Windows)
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        STD_INPUT_HANDLE = -10
        ENABLE_EXTENDED_FLAGS = 0x0080
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_INSERT_MODE = 0x0020
        hStdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
            new_mode = (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE & ~ENABLE_INSERT_MODE
            kernel32.SetConsoleMode(hStdin, new_mode)
            print(f"{Fore.GREEN}[Console] QuickEdit disabled (ป้องกัน cmd ค้างตอนคลิก/ลากเมาส์){Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.YELLOW}[Console] Could not disable QuickEdit: {e}{Style.RESET_ALL}")


def apply_config_now(reason=""):
    """โหลด config.py ใหม่แล้วอัปเดตตัวแปร runtime ทันที (ใช้ได้ทุกที่ ทุกเวลา)
    คืน True ถ้าสำเร็จ — ตัวนี้คือหัวใจของ 'แก้ config ปุ๊บ มีผลปั๊บ'"""
    global EVENT_IMG, DO_BOX, DO_GACHA, FIND_HERO, GACHA_FREE, CHECK_COIN, GACHA_FREE_LOOPS, NOSCAN, SKIPANIMATION, GACHA_CHECK, GACHA_FIND, AUTORUN, SILENT_UPDATE_MODE, OVERWRITE_CONFIG_ON_UPDATE, GETCODE, GETCODE_TEXT, GETQUEST, LOGIN_FAST, GACHA_MIN_COIN, DEBUG_CONSOLE, MOVE_LS_ENABLE, MOVE_LS_TIME, CUSTOM_GACHA, NEW_GACHA, NEW_GACHA_SWIPE, GACHA_LOOP_LIMIT, GACHA500, COIN_GACHA_THRESHOLD, ONE_GACHA500, HERO_LIST, HERO_LIST_FREE, EXTAR_FIND, EXTAR_FIND_THRESHOLD, AUTO_RESTART_OFFLINE, OFFLINE_RESTART_AFTER, OFFLINE_BOOT_WAIT, OFFLINE_RESTART_COOLDOWN, SCREENCAP_MAX_CONCURRENT, SCREENCAP_INTERVAL, _MIN_SCREENCAP_INTERVAL, IMG_ROI_CACHE, IMG_ROI_PAD
    try:
        import importlib
        import config as cfg
        importlib.reload(cfg)
        EVENT_IMG = getattr(cfg, 'EVENT_IMG', 0)
        DO_BOX = getattr(cfg, 'DO_BOX', 0)
        DO_GACHA = getattr(cfg, 'DO_GACHA', 0)
        FIND_HERO = getattr(cfg, 'FIND_HERO', 0)
        GACHA_FREE = getattr(cfg, 'GACHA_FREE', 0)
        CHECK_COIN = getattr(cfg, 'CHECK_COIN', 0)
        GACHA_FREE_LOOPS = getattr(cfg, 'GACHA_FREE_LOOPS', 2)
        NOSCAN = getattr(cfg, 'NOSCAN', 0)
        SKIPANIMATION = getattr(cfg, 'SKIPANIMATION', 0)
        GACHA_CHECK = getattr(cfg, 'GACHA_CHECK', 0)
        GACHA_FIND = getattr(cfg, 'GACHA_FIND', 0)
        AUTORUN = getattr(cfg, 'AUTORUN', 0)
        SILENT_UPDATE_MODE = getattr(cfg, 'SILENT_UPDATE_MODE', 'normal')
        OVERWRITE_CONFIG_ON_UPDATE = getattr(cfg, 'OVERWRITE_CONFIG_ON_UPDATE', False)
        GETCODE = getattr(cfg, 'GETCODE', 0)
        GETCODE_TEXT = getattr(cfg, 'GETCODE_TEXT', 'eFCONNECT')
        GETQUEST = getattr(cfg, 'GETQUEST', 0)
        LOGIN_FAST = getattr(cfg, 'LOGIN_FAST', 0)
        GACHA_MIN_COIN = getattr(cfg, 'GACHA_MIN_COIN', 100)
        DEBUG_CONSOLE = getattr(cfg, 'DEBUG_CONSOLE', 0)
        MOVE_LS_ENABLE = getattr(cfg, 'MOVE_LS_ENABLE', 0)
        MOVE_LS_TIME = getattr(cfg, 'MOVE_LS_TIME', '09:00')
        CUSTOM_GACHA = getattr(cfg, 'CUSTOM_GACHA', 0)
        NEW_GACHA = getattr(cfg, 'NEW_GACHA', 0)
        NEW_GACHA_SWIPE = getattr(cfg, 'NEW_GACHA_SWIPE', 1)
        GACHA_LOOP_LIMIT = getattr(cfg, 'GACHA_LOOP_LIMIT', 0)
        GACHA500 = getattr(cfg, 'GACHA500', 0)
        COIN_GACHA_THRESHOLD = getattr(cfg, 'COIN_GACHA_THRESHOLD', 700)
        ONE_GACHA500 = getattr(cfg, 'ONE_GACHA500', 0)
        # รายชื่อฮีโร่ก็อัปเดตสดด้วย (แก้ list ใน config แล้วมีผลทันที)
        HERO_LIST = getattr(cfg, 'HERO_LIST', HERO_LIST)
        HERO_LIST_FREE = getattr(cfg, 'HERO_LIST_FREE', HERO_LIST_FREE)
        # EXTAR_FIND (ยืนยันด้วยรูป) — แก้ใน config แล้วมีผลทันทีเหมือนกัน
        EXTAR_FIND = getattr(cfg, 'EXTAR_FIND', getattr(cfg, 'extar_find', {})) or {}
        EXTAR_FIND_THRESHOLD = getattr(cfg, 'EXTAR_FIND_THRESHOLD', 0.8)
        # Auto restart เครื่องที่ adb หลุด
        AUTO_RESTART_OFFLINE = getattr(cfg, 'AUTO_RESTART_OFFLINE', 1)
        OFFLINE_RESTART_AFTER = getattr(cfg, 'OFFLINE_RESTART_AFTER', 90)
        OFFLINE_BOOT_WAIT = getattr(cfg, 'OFFLINE_BOOT_WAIT', 240)
        OFFLINE_RESTART_COOLDOWN = getattr(cfg, 'OFFLINE_RESTART_COOLDOWN', 600)
        # โหลดที่ยิงใส่ adb — ปรับได้สดๆ ระหว่างบอทวิ่ง (ไม่ต้องรีสตาร์ท)
        SCREENCAP_MAX_CONCURRENT = getattr(cfg, 'SCREENCAP_MAX_CONCURRENT', 12)
        SCREENCAP_INTERVAL = getattr(cfg, 'SCREENCAP_INTERVAL', 0.25)
        _MIN_SCREENCAP_INTERVAL = SCREENCAP_INTERVAL
        _SCREENCAP_GATE.set_limit(SCREENCAP_MAX_CONCURRENT)
        IMG_ROI_CACHE = getattr(cfg, 'IMG_ROI_CACHE', 1)
        IMG_ROI_PAD = getattr(cfg, 'IMG_ROI_PAD', 40)
        # TIMEOUT_ENABLE / TIMEOUT_MINUTES ไม่ต้องเก็บเป็น global —
        # check_device_reset อ่านสดจาก config ทุกครั้งอยู่แล้ว
        return True
    except Exception as e:
        cprint(f"{Fore.YELLOW}[Config] reload failed{(' ('+reason+')') if reason else ''}: {e}{Style.RESET_ALL}")
        return False

def config_watcher_loop():
    """เฝ้าไฟล์ config.py — แก้ไฟล์ปุ๊บ (เวลาแก้ไขเปลี่ยน) โหลดใหม่ทันทีภายใน ~1 วิ
    ไม่ต้องรอจบ cycle / ไม่ต้อง restart บอท"""
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    except Exception:
        cfg_path = os.path.abspath("config.py")   # fallback กันเธรดตายตั้งแต่ยังไม่เริ่ม
    last_mtime = None
    try:
        last_mtime = os.path.getmtime(cfg_path)
    except Exception:
        pass
    while True:
        try:
            mtime = os.path.getmtime(cfg_path)
            if last_mtime is None or mtime != last_mtime:
                last_mtime = mtime
                time.sleep(0.2)   # เผื่อ editor เขียนไฟล์ยังไม่เสร็จ
                if apply_config_now("watcher"):
                    msg = (f"⚙️ Config เปลี่ยน → โหลดใหม่แล้ว (realtime) | "
                           f"BOX={DO_BOX} GACHA={DO_GACHA} NEW={NEW_GACHA} CUSTOM={CUSTOM_GACHA} "
                           f"LIMIT={GACHA_LOOP_LIMIT} G500={GACHA500} FREE={GACHA_FREE} FIND={FIND_HERO}")
                    cprint(f"{Fore.GREEN}[Config] {msg}{Style.RESET_ALL}")
                    if gui_instance is not None:
                        try:
                            gui_instance.log(msg)
                        except Exception:
                            pass
        except Exception:
            pass
        time.sleep(1)

def start_config_watcher():
    threading.Thread(target=config_watcher_loop, daemon=True).start()

def download_watcher_loop():
    """เธรดลอยกลาง: สแกนหา download.bmp "ทุกเครื่อง ตลอดเวลา ทุกขั้นตอนการทำงาน"
    เจอเมื่อไหร่กดทันที (ทำงานอิสระจาก worker แต่ละเครื่อง — ต่อให้ worker กำลังหลับ/รออยู่ก็กดให้)"""
    client = None
    while True:
        try:
            if client is None:
                client = AdbClient(host="127.0.0.1", port=5037)
            for serial in get_connected_devices():
                try:
                    dev = client.device(serial)
                    if dev is None:
                        continue
                    img_dl = fast_screencap(dev)
                    if img_dl is None:
                        continue
                    pts_dl = img_search(img_dl, os.path.join(IMG_DIR, "download.bmp"))
                    if pts_dl:
                        x_dl, y_dl = pts_dl[0]
                        dev.shell(f"input swipe {x_dl} {y_dl} {x_dl} {y_dl} 100")
                        gui_log(serial, f"download.bmp found! Clicked ({x_dl},{y_dl})", step="Download")
                        time.sleep(1.5)
                except Exception:
                    pass   # เครื่องนั้นมีปัญหา (offline/ค้าง) → ข้าม ไปเครื่องถัดไป
        except Exception:
            client = None   # adb server สะดุด → สร้าง client ใหม่รอบหน้า
        time.sleep(2)   # สแกนรอบใหม่ทุก 2 วิ (เบาเครื่อง ไม่กวน screencap ของ worker)

def start_download_watcher():
    threading.Thread(target=download_watcher_loop, daemon=True).start()

def main():
    _disable_console_quickedit()
    start_config_watcher()     # เฝ้า config.py — แก้ปุ๊บมีผลปั๊บ (realtime ไม่ต้องรอจบ cycle)
    start_download_watcher()   # เธรดลอยหา download.bmp ตลอด (ทั้งโหมด GUI และ headless)
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
        start_cpu_balancer()   # เกลี่ย CPU ของ MuMu ข้าม socket (กันโหลดกอง group เดียวจนค้าง)
        refresh_serial_index_map()   # จำ serial -> MuMu index ไว้ตอนทุกเครื่องยังปกติ (ไว้สั่ง restart ตอนหลุด)
        client = AdbClient(host="127.0.0.1", port=5037)
        for i, serial in enumerate(devices):
            device = client.device(serial)
            threading.Thread(target=process_device_login,
                             args=(device,), daemon=True).start()
            # ค่อยๆ ทยอยเปิดทีละจอ โดยเว้นระยะ 10 วินาที เพื่อป้องกัน CPU ค้างจากการรันพร้อมกัน
            if i < len(devices) - 1:
                print("Waiting 10 seconds before starting the next device...")
                time.sleep(10.0)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()

import os
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
adb_path      = "adb"
bot_running   = False
gui_instance  = None

# ── โหลด config จาก config.py ──────────────────────────────────────────────
from config import EVENT_IMG, DO_BOX, DO_GACHA, HERO_LIST, IMG_DIR, INPUT_DIR, LOGIN_SUCCESS_DIR, FIND_HERO, HERO_IMG_MAP, GACHA_FREE, HERO_LIST_FREE

REMOTE_AUTH_DIR   = "/data/data/jp.konami.pesam/files/SaveData/AUTH"
REMOTE_DAT_FILE   = f"{REMOTE_AUTH_DIR}/online_user_id_data.dat"

IMAGE_CACHE          = {}
DEVICE_RESET_FLAGS   = {}
DEVICE_FILE_ASSIGNMENTS = {}

file_pick_lock = threading.Lock()
in_use_files   = set()   # filenames currently being processed

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(LOGIN_SUCCESS_DIR, exist_ok=True)
BACKUP_ID_DIR = "backup-id"
NO_HERO_DIR   = "no-hero"
FOUND_HERO_DIR = "found-hero"
os.makedirs(BACKUP_ID_DIR, exist_ok=True)
os.makedirs(NO_HERO_DIR, exist_ok=True)
os.makedirs(FOUND_HERO_DIR, exist_ok=True)
FILE_ERROR_DIR = "file-error"
os.makedirs(FILE_ERROR_DIR, exist_ok=True)
RUN_FILE_DIR = "run-file"
os.makedirs(RUN_FILE_DIR, exist_ok=True)
RANDOM_FAIL_DIR = "random-fail"
os.makedirs(RANDOM_FAIL_DIR, exist_ok=True)

# ── Exceptions ────────────────────────────────────────────────────────────────
class DeviceResetException(Exception):  pass
class CycleTimeoutException(Exception): pass

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
                                         text_color="#aaa", width=120)
            self.lbl_file.pack(side="right", padx=4)

            ctk.CTkButton(self, text="↺", width=22, height=20,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          fg_color="#e53935",
                          command=lambda: trigger_manual_reset(device_id)
                          ).pack(side="right", padx=2)

        def update_state(self, step=None, status=None, **kwargs):
            if status:
                colors = {'working': "#4caf50", 'stuck': "#e53935",
                          'waiting': "#ff9800", 'idle': "#888"}
                self.lbl_status.configure(text=status.upper(),
                                          text_color=colors.get(status.lower(), "#888"))
            if step:
                self.lbl_file.configure(text=step[:20])

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
            self.setup_ui()
            self.after(500,  self.connect_adb)
            self.after(2000, self.update_realtime_stats)
            self.after(10000, self.auto_scan_devices)
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
            ctk.CTkLabel(bottom_bar, text="v1.0",
                         font=ctk.CTkFont(size=10), text_color="#888888"
                         ).pack(side="right", padx=8)

        # ── Helpers ─────────────────────────────────────────────────
        def open_config_dialog(self):
            import importlib, config as cfg
            importlib.reload(cfg)   # อ่านค่าล่าสุดจากไฟล์

            win = ctk.CTkToplevel(self)
            win.title("⚙️ Config")
            win.geometry("340x290")
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

            # ── Save button ───────────────────────────────
            def _save():
                global EVENT_IMG, DO_BOX, DO_GACHA, FIND_HERO, GACHA_FREE
                new_event = var_event.get()
                new_box   = var_box.get()
                new_gacha = var_gacha.get()
                new_find  = var_find_hero.get()
                new_gfree = var_gacha_free.get()
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
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(content)
                # อัปเดต runtime ด้วย
                EVENT_IMG  = new_event
                DO_BOX     = new_box
                DO_GACHA   = new_gacha
                FIND_HERO  = new_find
                GACHA_FREE = new_gfree
                importlib.reload(cfg)
                label_status.configure(text=f"✅ Saved!",
                                       text_color="#4caf50")
                self.log(f"Config saved: EVENT={new_event}, BOX={new_box}, GACHA={new_gacha}, HERO={new_find}, GFREE={new_gfree}")

            ctk.CTkButton(win, text="💾 Save", fg_color="#2cc985",
                          hover_color="#229f69", command=_save).pack(pady=8)
            label_status = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
            label_status.pack()

        # ── Helpers ───────────────────────────────────────────────────────
        def log(self, msg):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

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
                    self.after(0, lambda: self._on_adb_ready(devices))
                else:
                    self.after(0, lambda: self.lbl_status.configure(
                        text="   ● ADB NOT FOUND", text_color="#ff5555"))
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
            connect_known_ports(quiet=False, kill_server=False)
            for dev in get_connected_devices():
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
                    self.after(0, lambda: self._on_auto_scan_result(new_devs))
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
            try:
                input_count   = len(glob.glob(os.path.join(INPUT_DIR, "*.dat")))
                success_count = len(glob.glob(os.path.join(LOGIN_SUCCESS_DIR, "*.dat")))
                
                found_files   = glob.glob(os.path.join(FOUND_HERO_DIR, "*.dat"))
                hero_count    = len(found_files)
                
                self.lbl_file_count.configure(text=f"📁 {input_count}")
                self.lbl_succ_count.configure(text=f"✅ {success_count}")
                if hasattr(self, 'lbl_hero_count'):
                    self.lbl_hero_count.configure(text=f"⭐ {hero_count}")
                    
                if success_count:
                    self.add_stat_row("✅ login สำเร็จ", success_count)
                
                # แยกนับรายชื่อฮีโร่
                hero_counts = {}
                for fpath in found_files:
                    fname = os.path.basename(fpath)
                    parts = fname.split('+')
                    if len(parts) > 1:
                        for h in parts[:-1]:
                            h_key = h.strip()
                            hero_counts[h_key] = hero_counts.get(h_key, 0) + 1
                            
                for h_name, count in hero_counts.items():
                    self.add_stat_row(f"⭐ {h_name}", count)
                if self.login_times:
                    avg = sum(self.login_times) / len(self.login_times)
                    self.lbl_avg_time.configure(
                        text=f"⏱ Avg: {avg/60:.1f}m" if avg >= 60 else f"⏱ Avg: {avg:.0f}s")
            except Exception:
                pass
            self.after(2000, self.update_realtime_stats)

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
    if cycle_start and time.time() - cycle_start > 360:
        raise CycleTimeoutException(serial)

def update_gui(serial, **kwargs):
    if gui_instance:
        gui_instance.after(0, lambda: gui_instance.update_device(serial, **kwargs))

def gui_log(serial, msg, step=None, status=None):
    print(f"{Fore.CYAN}[{serial}] {msg}{Style.RESET_ALL}")
    update_gui(serial, log=msg, step=step, status=status)

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

def get_screen_capture(device):
    try:
        img = fast_screencap(device)
        if img is None:
            return None
        
        if img is not None:
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

        update_gui(device.serial, screenshot=img)
        return img
    except DeviceResetException:
        raise
    except Exception:
        return None

def load_template(path):
    if path not in IMAGE_CACHE:
        t = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if t is not None:
            IMAGE_CACHE[path] = t
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

def read_screen_text(img, region=None):
    """OCR Logic using EasyOCR (priority) or Pytesseract"""
    if img is None: return ""
    
    # Crop region if provided
    if region:
        img = img[region.y : region.y + region.h, region.x : region.x + region.w]
        
        # ตัดขอบซ้าย-ขวาออกอีก 15% เพื่อหลบพวกขอบกรอบ UI (แก้ปัญหาอ่านติด (Bb หรือตัวประหลาด)
        h_tmp, w_tmp = img.shape[:2]
        margin = int(w_tmp * 0.15)
        img = img[:, margin : w_tmp - margin]
        
        # บันทึกภาพที่สแกนล่าสุดออกมาดูเพื่อ debug (ช่วยเรื่องพิกัด)
        cv2.imwrite("debug_ocr_crop.png", img)
    
    # 1. Try EasyOCR
    if easyocr is not None:
        global _reader
        try:
            print(f"[OCR] Attempting EasyOCR...")
            if _reader is None:
                _reader = easyocr.Reader(['en'], gpu=False)
            results = _reader.readtext(img, detail=0)
            res = " ".join(results).strip()
            if res:
                print(f"[OCR] EasyOCR Result: '{res}'")
                return res
        except Exception as e:
            print(f"[OCR] EasyOCR Error: {e}")
            pass

    # 2. Fallback to Pytesseract
    if pytesseract is not None:
        try:
            print(f"[OCR] Attempting Pytesseract...")
            # ตรวจสอบว่าภาพเป็นสีก่อนค่อยเปลี่ยนเป็นเทา
            if len(img.shape) == 3:
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                img_gray = img
                
            # ขยายภาพ 3 เท่าเพื่อให้ตัวหนังสือใหญ่ขึ้น
            img_resized = cv2.resize(img_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            # ลบนอยซ์และแสงเรืองๆ ด้วย Gaussian Blur
            img_blur = cv2.GaussianBlur(img_resized, (3, 3), 0)
            # ใช้ Threshold ค่าสูงหน่อย (200) เพื่อตัดแสงเรืองรอบๆ ตัวหนังสือออก
            _, img_bin = cv2.threshold(img_blur, 200, 255, cv2.THRESH_BINARY)
            
            # ใช้ PSM 7 (Treat the image as a single text line)
            text = pytesseract.image_to_string(img_bin, lang="eng", config="--psm 7")
            res = text.strip()
            if res:
                print(f"[OCR] Pytesseract Result: '{res}'")
            else:
                print(f"[OCR] Pytesseract returned EMPTY string")
            return res
        except Exception as e:
            print(f"[OCR] Pytesseract Error: {e}")
            pass
            
    return ""

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
                      glob.glob(os.path.join(BACKUP_ID_DIR, "*.dat")) +
                      glob.glob(os.path.join(NO_HERO_DIR, "*.dat")) +
                      glob.glob(os.path.join(FOUND_HERO_DIR, "*.dat")))
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
    
    # 1. fin1 -> fin8 navigation
    for i in range(1, 9):
        name = f"fin{i}.bmp"
        gui_log(serial, f"Waiting {name}...", step=name)
        deadline = time.time() + 15
        while time.time() < deadline:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                # fin8 is the most critical confirmation, use higher threshold
                thresh = 0.95 if i == 8 else 0.8
                pts = img_search(img, os.path.join(IMG_DIR, name), threshold=thresh)
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2.5)
                    break
            time.sleep(0.5)

    # 2. Triple Check Scan
    gui_log(serial, "Delay 8s before scanning...", step="Delay 8s")
    time.sleep(8)

    gui_log(serial, "Scanning (Triple Check)...", step="Scan Hero")
    hero_hits = {} # hero_name -> count
    scans_done = 0
    max_attempts = 5
    required_hits = 3
    
    while scans_done < max_attempts:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            found_this_round = set()
            for hero_img, h_name in HERO_IMG_MAP.items():
                pts = img_search(img, os.path.join(IMG_DIR, hero_img), threshold=0.95)
                if pts:
                    found_this_round.add(h_name)
            
            for h_name in found_this_round:
                hero_hits[h_name] = hero_hits.get(h_name, 0) + 1
            
            scans_done += 1
            gui_log(serial, f"Scan {scans_done}/{max_attempts} complete", step="Scanning")
            
            # If we found any hero enough times, we could potentially stop early,
            # but for maximum reliability as requested, we'll finish at least 3 scans
            # or all 5 if some matches are inconsistent.
            if any(count >= required_hits for count in hero_hits.values()) and scans_done >= 3:
                break
        time.sleep(1.2)

    found_heroes = [h for h, count in hero_hits.items() if count >= required_hits]

    # 3. Shutdown and Move
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    if found_heroes:
        dest_dir = FOUND_HERO_DIR
        hero_prefix = "+".join(found_heroes)
        final_name = f"{hero_prefix}+{original_name}"
        gui_log(serial, f"⭐ MATCH: {hero_prefix}", step="Match!")
    else:
        dest_dir = NO_HERO_DIR
        final_name = original_name
        gui_log(serial, "No hero match found.", step="No Match")

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
    Gacha Free mode (2 loops):
    Each loop: swipe to find gachafree1 → click → gachafree2 → click → checkpointgacha → OCR
    Accumulates hero names from both loops.
    - Found heroes → backup-id with hero1+hero2+original.dat
    - No heroes → random-fail with original.dat
    """
    gui_log(serial, "Gacha Free sequence started...", step="GachaFree", status="working")

    # 1. gacha1 → gacha2 (ทำแค่ครั้งเดียวตอนเริ่ม)
    for i in range(1, 3):
        name = f"gacha{i}.bmp"
        gui_log(serial, f"Waiting {name}...", step=name)
        deadline = time.time() + 30
        while time.time() < deadline:
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

    # 2. ทำ 2 loops
    found_heroes = []  # เก็บชื่อฮีโร่ที่เจอจากทุก loop

    for loop_num in range(1, 3):
        gui_log(serial, f"=== Gacha Free Loop {loop_num}/2 ===", step=f"Loop {loop_num}")

        # 2a. เลื่อนหา gachafree1.bmp (เช็คก่อน → ไม่เจอ → เลื่อน, ครบ 10 รอบ = ข้าม loop นี้)
        gui_log(serial, f"[Loop {loop_num}] Looking for gachafree1.bmp...", step="Swipe Free")
        found_free = False
        miss_count = 0
        max_miss = 10

        while miss_count < max_miss:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, "gachafree1.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] gachafree1 found! Clicking ({x},{y})", step="Free Found")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2)
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
                                time.sleep(2)
                            else:
                                break
                        else:
                            break
                    time.sleep(2)
                    break
            miss_count += 1
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not here, swiping... ({miss_count}/{max_miss})", step="Swipe")
            device.shell("input swipe 618 308 54 306 4000")
            time.sleep(2)

        if not found_free:
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not found after 10 swipes, skipping loop", step="Skip")
            continue  # ข้ามไป loop ถัดไป (หรือจบถ้า loop 2)

        # 2b. รอ gachafree2.bmp → กดจนกว่าจะหายไป (timeout 20s → file-error)
        gui_log(serial, f"[Loop {loop_num}] Waiting gachafree2.bmp...", step="gachafree2")
        deadline_gf2 = time.time() + 20
        clicked_gf2 = False
        while time.time() < deadline_gf2:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, "gachafree2.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] gachafree2 found! Clicking ({x},{y})", step="Free2 Found")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2)
                    clicked_gf2 = True
                    deadline_gf2 = time.time() + 10  # ต่อเวลารอหายไป
                elif clicked_gf2:
                    break  # เคยกดแล้ว + หายไปแล้ว → ไปต่อ
            time.sleep(1)

        # ถ้าไม่เจอ gachafree2 เลย → file-error แล้วไปไฟล์ใหม่
        if not clicked_gf2:
            gui_log(serial, f"[Loop {loop_num}] gachafree2 not found in 20s → file-error", step="Error")
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

        # 2c. รอ checkpointgacha.bmp → OCR scan
        gui_log(serial, f"[Loop {loop_num}] Waiting checkpointgacha (OCR)...", step="OCR Wait")
        deadline_cp = time.time() + 30
        while time.time() < deadline_cp:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp"))
                if pts:
                    gacha_region = Region(381, 301, 202, 37)
                    ocr_text = read_screen_text(img, region=gacha_region)
                    display_text = ocr_text if ocr_text else "<EMPTY>"
                    gui_log(serial, f"[Loop {loop_num}] OCR Result: {display_text}", step="OCR Done")
                    print(f"[{serial}] GachaFree Loop{loop_num} OCR: {display_text}")

                    for h in HERO_LIST_FREE:
                        if h and h.strip().lower() in ocr_text.lower():
                            found_heroes.append(h.strip())
                            gui_log(serial, f"[Loop {loop_num}] ⭐ Match: {h.strip()}", step="Match!")
                            break
                    break
            time.sleep(1)

        # 2d. รอ next.bmp → click (จบ loop นี้แล้วค่อยไป loop ถัดไป)
        gui_log(serial, f"[Loop {loop_num}] Waiting next.bmp...", step="Next")
        deadline_next = time.time() + 15
        while time.time() < deadline_next:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts = img_search(img, os.path.join(IMG_DIR, "next.bmp"))
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] next.bmp found! Clicking ({x},{y})", step="Next OK")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(3)
                    break
            time.sleep(1)

    # 3. จบ 2 loops → Sort file
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    if found_heroes:
        dest_dir = BACKUP_ID_DIR
        hero_prefix = "+".join(found_heroes)
        final_name = f"{hero_prefix}+{original_name}"
        gui_log(serial, f"⭐ GACHA FREE RESULT: {hero_prefix}", step="Match!")
    else:
        dest_dir = RANDOM_FAIL_DIR
        final_name = original_name
        gui_log(serial, "No match in both loops → random-fail", step="No Match")

    dest = os.path.join(dest_dir, final_name)
    if os.path.exists(file_path):
        time.sleep(2)
        try:
            if os.path.exists(dest):
                os.remove(dest)
            shutil.copy2(file_path, dest)
            os.remove(file_path)
            gui_log(serial, f"✅ Sorted: {final_name} → {dest_dir}", step="Sorted", status="working")
        except Exception as e:
            gui_log(serial, f"⚠️ Sort failed: {e}", step="Sort Error")

        dur = time.time() - cycle_start
        if gui_instance:
            gui_instance.login_times.append(dur)

    release_file(original_name)
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Main bot loop
# ═════════════════════════════════════════════════════════════════════════════
def process_device_login(device):
    serial = device.serial
    gui_log(serial, "Bot started", step="Init", status="working")

    while bot_running:
        file_path     = None   # ← init ก่อน try เสมอ (แก้ bug scope)
        original_name = None

        try:
            check_device_reset(serial)

            # 0. Force-stop
            gui_log(serial, "Force closing app...", step="Cleanup", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            # 1. Pick file
            file_path, original_name = pick_next_file()
            if file_path is None:
                gui_log(serial, "No files left — waiting...", step="No Files", status="idle")
                time.sleep(10)
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



            # 3. Launch
            gui_log(serial, "Launching PES...", step="Launch", status="working")
            device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
            time.sleep(14)

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
                time.sleep(0.8)

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
                time.sleep(0.8)

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
                        time.sleep(0.8)
                    
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
                        time.sleep(0.8)
                
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

            # 7.5 Find Hero Sequence (Optional)
            if FIND_HERO == 1:
                if find_hero_mode(device, cycle_start, serial, original_name, file_path):
                    continue  # Start next file immediately

            # 7.6 Gacha Free Sequence (Optional)
            if GACHA_FREE == 1:
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
                        gacha_region = Region(381, 301, 202, 37)
                        ocr_text = read_screen_text(img, region=gacha_region)
                        gui_log(serial, f"OCR Result (at No-Coins): {ocr_text}", step="OCR Done")
                        for h in HERO_LIST:
                            if h and h.strip().lower() in ocr_text.lower():
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
                    gui_log(serial, "Waiting checkpointgacha (OCR)...", step="OCR Wait")
                    while True:
                        check_device_reset(serial, cycle_start)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts = img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp"))
                            if pts:
                                # ใช้พิกัด Region(381, 301, 202, 37) ตามตัวอย่าง
                                gacha_region = Region(381, 301, 202, 37)
                                ocr_text = read_screen_text(img, region=gacha_region)
                                display_text = ocr_text if ocr_text else "<EMPTY>"
                                gui_log(serial, f"OCR Result: {display_text}", step="OCR Done")
                                print(f"[{serial}] Gacha OCR: {display_text}")
                                
                                for h in HERO_LIST:
                                    if h and h.strip().lower() in ocr_text.lower():
                                        gacha_hero_found = h.strip()
                                        break
                                break
                            
                            # เช็ค nocions.bmp ด้วย (กรณีเพชรไม่พอในจังหวะนี้)
                            pts_no = img_search(img, os.path.join(IMG_DIR, "nocions.bmp"))
                            if pts_no:
                                gui_log(serial, "nocions.bmp detected! Scanning current screen...", step="No-Coins")
                                gacha_region = Region(381, 301, 202, 37)
                                ocr_text = read_screen_text(img, region=gacha_region)
                                display_text = ocr_text if ocr_text else "<EMPTY>"
                                gui_log(serial, f"OCR Result (at No-Coins): {display_text}", step="OCR Done")
                                print(f"[{serial}] No-Coins OCR: {display_text}")
                                
                                for h in HERO_LIST:
                                    if h and h.strip().lower() in ocr_text.lower():
                                        gacha_hero_found = h.strip()
                                        gui_log(serial, f"Found match even at No-Coins: {gacha_hero_found}", step="Match!")
                                        break
                                break
                        time.sleep(1)

            # 9. Done & File Sorting
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

            if DO_GACHA == 1:
                if gacha_hero_found:
                    dest_dir = BACKUP_ID_DIR
                    final_name = f"{gacha_hero_found}-{original_name}"
                    gui_log(serial, f"⭐ HERO MATCH: {gacha_hero_found}", step="Match!")
                else:
                    dest_dir = NO_HERO_DIR
                    final_name = original_name
                    gui_log(serial, "No hero match found.", step="No Match")
            else:
                dest_dir = LOGIN_SUCCESS_DIR
                final_name = original_name

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

        except CycleTimeoutException:
            release_file(original_name)
            gui_log(serial, "⏳ 6-min timeout", step="Timeout", status="stuck")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)

        except Exception as e:
            release_file(original_name)
            gui_log(serial, f"❌ Error: {e}", status="stuck")
            time.sleep(5)

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
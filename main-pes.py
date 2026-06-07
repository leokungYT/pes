import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except (ImportError, AttributeError):
    pass

import cv2
import numpy as np
import time
import subprocess
import threading
import struct
import shutil
import concurrent.futures
import json
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

# Reduce CPU contention for OpenCV when running multiple instances
cv2.setNumThreads(1)

init(autoreset=True)

# Global ADB path
adb_path = "adb"
bot_running = False
gui_instance = None

if GUI_ENABLED:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class DeviceMonitorWidget(ctk.CTkFrame):
        def __init__(self, parent, serial, index):
            super().__init__(parent)
            self.serial = serial
            self.grid_columnconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=0)
            
            # Info Panel
            info_panel = ctk.CTkFrame(self, fg_color="transparent")
            info_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            
            # Header Line
            header = ctk.CTkFrame(info_panel, fg_color="transparent")
            header.pack(fill="x")
            ctk.CTkLabel(header, text=f"#{index}", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray").pack(side="left")
            ctk.CTkLabel(header, text=f"  {serial}", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
            
            # Reset Button
            self.btn_reset = ctk.CTkButton(header, text="↺ RESET", width=60, height=20, font=ctk.CTkFont(size=10, weight="bold"), fg_color="#ff5555", hover_color="#cc4444", command=lambda: trigger_manual_reset(serial))
            self.btn_reset.pack(side="right", padx=(5, 0))
            
            self.lbl_status = ctk.CTkLabel(header, text="IDLE", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray")
            self.lbl_status.pack(side="right")
            
            self.lbl_step = ctk.CTkLabel(info_panel, text="Step: Initializing", anchor="w")
            self.lbl_step.pack(fill="x", pady=(5,0))
            self.lbl_log = ctk.CTkLabel(info_panel, text="...", font=ctk.CTkFont(size=11), text_color="gray70", anchor="w")
            self.lbl_log.pack(fill="x")

            # Image Preview
            self.img_frame = ctk.CTkFrame(self, width=160, height=90, fg_color="black", corner_radius=5)
            self.img_frame.grid(row=0, column=1, padx=10, pady=10)
            self.img_frame.pack_propagate(False)
            self.img_label = ctk.CTkLabel(self.img_frame, text="NO SIGNAL", text_color="gray")
            self.img_label.pack(fill="both", expand=True)

        def update_state(self, step=None, status=None, log=None, screenshot=None):
            if step: self.lbl_step.configure(text=f"Step: {step}")
            if log: self.lbl_log.configure(text=f"> {log}")
            if status:
                color = "gray"
                if status.lower() == 'working': color = "#2cc985"
                elif status.lower() == 'stuck': color = "#ff5555"
                elif status.lower() == 'waiting': color = "#F2C94C"
                self.lbl_status.configure(text=status.upper(), text_color=color)
            if screenshot is not None:
                try:
                    pil_img = Image.fromarray(cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB))
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 90))
                    self.img_label.configure(image=ctk_img, text="")
                    self.img_label.image = ctk_img
                except: pass

    class ModernBotGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            global gui_instance
            gui_instance = self
            self.title("🎮 PES MOBILE BOT - CONTROL CENTER")
            self.geometry("820x550")
            self.adb_connected = False
            self.device_monitors = {}
            self.threads = []
            self.setup_ui()
            self.after(500, self.connect_adb)
            self.after(2000, self.update_realtime_stats)

        def setup_ui(self):
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)
            
            # Left Panel
            left_panel = ctk.CTkFrame(self, width=220, corner_radius=0)
            left_panel.grid(row=0, column=0, sticky="nsew")
            left_panel.grid_propagate(False)
            
            ctk.CTkLabel(left_panel, text="🤖 PES BOT CONTROL", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(20, 15))
            
            self.btn_start = ctk.CTkButton(left_panel, text="▶ START BOT", font=ctk.CTkFont(size=13, weight="bold"), height=36, fg_color="#2cc985", hover_color="#229f69", command=self.toggle_bot)
            self.btn_start.pack(padx=15, pady=8, fill="x")

            self.btn_config = ctk.CTkButton(left_panel, text="⚙️ Config", font=ctk.CTkFont(size=12, weight="bold"), height=30, fg_color="#1565c0", hover_color="#0d47a1", command=self.open_config_dialog)
            self.btn_config.pack(padx=15, pady=(0, 8), fill="x")
            
            self.lbl_backup_count = ctk.CTkLabel(left_panel, text="Backup: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_backup_count.pack(pady=4)
            
            self.lbl_adb_status = ctk.CTkLabel(left_panel, text="ADB: Connecting...", text_color="#F2C94C")
            self.lbl_adb_status.pack(pady=5)
            
            ctk.CTkLabel(left_panel, text="SYSTEM LOG", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=20, pady=(20, 5))
            self.log_text = ctk.CTkTextbox(left_panel, font=ctk.CTkFont(family="Consolas", size=11))
            self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
            self.log_text.configure(state="disabled")

            # Right Panel
            right_panel = ctk.CTkFrame(self, fg_color="transparent")
            right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
            ctk.CTkLabel(right_panel, text="LIVE DEVICE MONITOR", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 5))
            self.monitor_frame = ctk.CTkScrollableFrame(right_panel, label_text="Connected Devices")
            self.monitor_frame.pack(fill="both", expand=True)

        def update_realtime_stats(self):
            try:
                backup_dir = "backup"
                if os.path.exists(backup_dir):
                    backup_count = len(glob.glob(os.path.join(backup_dir, "*.dat")))
                    self.lbl_backup_count.configure(text=f"✅ Backup Generated: {backup_count}")
            except Exception:
                pass
            self.after(2000, self.update_realtime_stats)

        def open_config_dialog(self):
            import importlib
            import config_gen as cfg
            importlib.reload(cfg)

            win = ctk.CTkToplevel(self)
            win.title("⚙️ Config (config_gen.py)")
            win.geometry("450x580")
            win.resizable(False, False)
            win.grab_set()

            ctk.CTkLabel(win, text="Bot Settings (config_gen.py)",
                          font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 10))

            # Scrollable frame for forms
            form_frame = ctk.CTkFrame(win, fg_color="transparent")
            form_frame.pack(fill="both", expand=True, padx=20)

            # 0. EVENT_IMG Switch
            row_event = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_event.pack(fill="x", pady=4)
            ctk.CTkLabel(row_event, text="Event Image Mode (โหมดมี Event)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_event = ctk.IntVar(value=cfg.EVENT_IMG)
            ctk.CTkSwitch(row_event, text="", variable=var_event, onvalue=1, offvalue=0).pack(side="right")

            # 0.5 GETQUEST Switch
            row_gq = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_gq.pack(fill="x", pady=4)
            ctk.CTkLabel(row_gq, text="Get Quest Sequence (เก็บรางวัลเควส)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_getquest = ctk.IntVar(value=getattr(cfg, 'GETQUEST', 0))
            ctk.CTkSwitch(row_gq, text="", variable=var_getquest, onvalue=1, offvalue=0).pack(side="right")

            # 1. DO_BOX Switch
            row_box = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_box.pack(fill="x", pady=4)
            ctk.CTkLabel(row_box, text="Open Box Sequence (เปิดกล่อง)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_box = ctk.IntVar(value=cfg.DO_BOX)
            ctk.CTkSwitch(row_box, text="", variable=var_box, onvalue=1, offvalue=0).pack(side="right")

            # 2. GACHA_FREE Switch
            row_free = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_free.pack(fill="x", pady=4)
            ctk.CTkLabel(row_free, text="Gacha Free Sequence (กาชาฟรี)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_free = ctk.IntVar(value=cfg.GACHA_FREE)
            ctk.CTkSwitch(row_free, text="", variable=var_free, onvalue=1, offvalue=0).pack(side="right")

            # 3. GACHA_FREE_LOOPS Entry
            row_loops = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_loops.pack(fill="x", pady=4)
            ctk.CTkLabel(row_loops, text="Gacha Free Loops (จำนวนรอบ)", font=ctk.CTkFont(size=12)).pack(side="left")
            entry_loops = ctk.CTkEntry(row_loops, width=60, justify="center")
            entry_loops.insert(0, str(cfg.GACHA_FREE_LOOPS))
            entry_loops.pack(side="right")

            # 4. DEBUG_OCR Switch
            row_debug = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_debug.pack(fill="x", pady=4)
            ctk.CTkLabel(row_debug, text="Debug OCR (บันทึกรูปทดสอบ)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_debug = ctk.IntVar(value=cfg.DEBUG_OCR)
            ctk.CTkSwitch(row_debug, text="", variable=var_debug, onvalue=1, offvalue=0).pack(side="right")

            # 5. NOSCAN Switch
            row_noscan = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_noscan.pack(fill="x", pady=4)
            ctk.CTkLabel(row_noscan, text="No Scan Mode (ข้ามสแกน → fast-random)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_noscan = ctk.IntVar(value=cfg.NOSCAN)
            ctk.CTkSwitch(row_noscan, text="", variable=var_noscan, onvalue=1, offvalue=0).pack(side="right")

            # 5.5 SKIPANIMATION Switch
            row_skipanim = ctk.CTkFrame(form_frame, fg_color="transparent")
            row_skipanim.pack(fill="x", pady=4)
            ctk.CTkLabel(row_skipanim, text="Skip Animation (กด [611,129] ข้ามสปิน)", font=ctk.CTkFont(size=12)).pack(side="left")
            var_skipanim = ctk.IntVar(value=getattr(cfg, 'SKIPANIMATION', 0))
            ctk.CTkSwitch(row_skipanim, text="", variable=var_skipanim, onvalue=1, offvalue=0).pack(side="right")

            # 6. HERO_LIST_FREE Textarea
            ctk.CTkLabel(form_frame, text="Hero Target List (รายชื่อนักเตะ - บรรทัดละคน):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(10, 2))
            txt_heroes = ctk.CTkTextbox(form_frame, height=180, font=ctk.CTkFont(family="Consolas", size=11))
            txt_heroes.pack(fill="both", expand=True, pady=(0, 10))
            
            # Pre-fill textarea
            current_heroes = "\n".join(cfg.HERO_LIST_FREE)
            txt_heroes.insert("1.0", current_heroes)

            def _save():
                global DO_BOX, GACHA_FREE, GACHA_FREE_LOOPS, HERO_LIST_FREE, DEBUG_OCR, EVENT_IMG, NOSCAN, SKIPANIMATION, GETQUEST
                
                val_event = var_event.get()
                val_box = var_box.get()
                val_free = var_free.get()
                
                try:
                    val_loops = int(entry_loops.get().strip())
                except ValueError:
                    val_loops = 6
                    
                val_debug = var_debug.get()
                val_getquest = var_getquest.get()
                val_noscan = var_noscan.get()
                val_skipanim = var_skipanim.get()
                
                # Parse heroes
                raw_heroes = txt_heroes.get("1.0", "end").strip()
                parsed_heroes = []
                for line in raw_heroes.split("\n"):
                    cleaned = line.strip().strip('"').strip("'")
                    if cleaned:
                        parsed_heroes.append(cleaned)

                # Write directly to config_gen.py
                cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_gen.py")
                content = f"""# ═══════════════════════════════════════════════════
#  config_gen.py  —  ตั้งค่าบอทสำหรับ main-pes.py
# ═══════════════════════════════════════════════════

# ── Event Image Mode ───────────────────────────────
# 1  =  มี event (กด play22 → play31 ทีละภาพ)
# 0  =  ไม่มี event (เจอ play22 แล้วกด Back รัวๆ
#        จนเจอ cancel.bmp แล้วคลิก)
EVENT_IMG = {val_event}

# ── Box Sequence (main-pes.py) ────────────────────
# 1 = เปิดกล่อง (ทำ play26-play31 และ box1-box4)
# 0 = ข้ามการเปิดกล่อง (จบที่ play25 แล้วส่งไฟล์เลย)
DO_BOX = {val_box}

# ── Gacha Free Sequence ───────────────────────────
# 1 = ทำ gacha free หลังจบ box (gacha1 → gacha2 → เลื่อนหา gachafree1)
# 0 = ข้าม
GACHA_FREE = {val_free}

# จำนวนลูปย่อยที่ต้องการสุ่มกาชาฟรี (เช่น 2, 3, 6)
GACHA_FREE_LOOPS = {val_loops}

# รายชื่อนักเตะที่ต้องการเก็บ (Gacha Free → found-hero)
HERO_LIST_FREE = {repr(parsed_heroes)}

# ── Path ──────────────────────────────────────────
IMG_DIR = "img"

# ── Debug OCR ─────────────────────────────────────
# 1 = บันทึกภาพที่สแกน OCR ทุกครั้งไว้ในโฟลเดอร์ debug-ocr/
# 0 = ไม่บันทึก
DEBUG_OCR = {val_debug}

# ── Get Quest Sequence ─────────────────────────────
# 1 = ทำขั้นตอน getquest (เก็บรางวัลเควส) ก่อน Box
# 0 = ข้าม
GETQUEST = {val_getquest}

# โฟลเดอร์รูป getquest (อยู่ใน img/getquest/)
GETQUEST_IMG_DIR = "img/getquest"

# ── No Scan Mode ──────────────────────────────────
# 1 = ข้ามขั้นตอน checkpointgacha (ไม่สแกน OCR)
#     ข้ามไปหา next.bmp ต่อเลย
#     ไฟล์จะเก็บในโฟลเดอร์ fast-random/ แทน backup-id/
# 0 = ทำงานปกติ (สแกน OCR ที่ checkpointgacha)
NOSCAN = {val_noscan}

# ── Skip Animation (Gacha Free) ──────────────────
# 1 = หลังกด gachafree2 จะกดตำแหน่ง [611,129] ซ้ำๆเร็วๆ
#     จนกว่าจะเจอ skiphero.bmp แล้วคลิก → ไปหา next ต่อ
# 0 = ทำงานปกติ (ไม่กดข้ามแอนิเมชั่น)
SKIPANIMATION = {val_skipanim}
"""
                try:
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    # Update local/global variables
                    EVENT_IMG = val_event
                    DO_BOX = val_box
                    GACHA_FREE = val_free
                    GACHA_FREE_LOOPS = val_loops
                    HERO_LIST_FREE = parsed_heroes
                    DEBUG_OCR = val_debug
                    NOSCAN = val_noscan
                    SKIPANIMATION = val_skipanim
                    GETQUEST = val_getquest
                    
                    importlib.reload(cfg)
                    label_status.configure(text="✅ Saved settings successfully!", text_color="#2cc985")
                    self.log(f"Config updated: EVENT={val_event}, BOX={val_box}, FREE={val_free}, LOOPS={val_loops}, NOSCAN={val_noscan}, SKIP={val_skipanim}, GETQUEST={val_getquest}, HEROES={len(parsed_heroes)}")
                except Exception as ex:
                    label_status.configure(text=f"❌ Save error: {ex}", text_color="#ff5555")

            ctk.CTkButton(win, text="💾 Save Configuration", font=ctk.CTkFont(size=12, weight="bold"), fg_color="#2cc985",
                          hover_color="#229f69", command=_save).pack(pady=(5, 5))
            label_status = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
            label_status.pack(pady=(0, 5))

        def log(self, msg):
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{timestamp}] {msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        def connect_adb(self):
            self.log("Searching for ADB...")
            def _thread():
                if find_adb_executable():
                    connect_known_ports()
                    devices = get_connected_devices()
                    self.after(0, lambda: self._on_adb_ready(devices))
                else:
                    self.after(0, lambda: self.lbl_adb_status.configure(text="ADB: NOT FOUND", text_color="#ff5555"))
            threading.Thread(target=_thread, daemon=True).start()

        def _on_adb_ready(self, devices):
            self.adb_connected = True
            self.lbl_adb_status.configure(text=f"ADB: ONLINE ({len(devices)} Devices)", text_color="#2cc985")
            for i, serial in enumerate(devices):
                monitor = DeviceMonitorWidget(self.monitor_frame, serial, i+1)
                monitor.pack(fill="x", pady=5, padx=5)
                self.device_monitors[serial] = monitor
            self.log(f"Found {len(devices)} devices.")

        def toggle_bot(self):
            global bot_running
            if not bot_running:
                bot_running = True
                self.btn_start.configure(text="⏹ STOP BOT", fg_color="#ff5555", hover_color="#cc4444")
                self.start_bot_threads()
            else:
                bot_running = False
                self.btn_start.configure(text="▶ START BOT", fg_color="#2cc985", hover_color="#229f69")

        def start_bot_threads(self):
            devices = list(self.device_monitors.keys())
            # If no devices yet, connect ADB first
            if not devices:
                self.log("No devices loaded yet, connecting ADB...")
                connect_known_ports()
                found = get_connected_devices()
                for i, serial in enumerate(found):
                    if serial not in self.device_monitors:
                        m = DeviceMonitorWidget(self.monitor_frame, serial, i+1)
                        m.pack(fill="x", pady=5, padx=5)
                        self.device_monitors[serial] = m
                self.lbl_adb_status.configure(text=f"ADB: ONLINE ({len(self.device_monitors)} Devices)", text_color="#2cc985")
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
                t = threading.Thread(target=process_device, args=(device,), daemon=True)
                t.start()
                self.threads.append(t)
                time.sleep(1)

        def update_device(self, serial, **kwargs):
            if serial in self.device_monitors:
                self.device_monitors[serial].update_state(**kwargs)

DEVICE_RESET_FLAGS = {}

def trigger_manual_reset(serial):
    DEVICE_RESET_FLAGS[serial] = True
    print(f"{Fore.YELLOW}[MANUAL] Reset triggered for {serial}{Style.RESET_ALL}")
    update_gui(serial, status="RESETTING...", log="Manual Reset Pending...")

class DeviceResetException(Exception):
    pass

class RestartFromQuest8Exception(Exception):
    pass

GQ_ACTIVE = {}

class CycleTimeoutException(Exception):
    pass

CYCLE_TIMEOUT = 1800  # 30 minutes in seconds

def check_device_reset(serial, cycle_start=None):
    if DEVICE_RESET_FLAGS.get(serial, False):
        DEVICE_RESET_FLAGS[serial] = False
        raise DeviceResetException(f"Manual Reset for {serial}")
    if cycle_start is not None and (time.time() - cycle_start) > CYCLE_TIMEOUT:
        raise CycleTimeoutException(f"Cycle timeout (30min) for {serial}")

def update_gui(serial, **kwargs):
    if gui_instance:
        gui_instance.after(0, lambda: gui_instance.update_device(serial, **kwargs))

def gui_log(serial, msg, step=None, status=None):
    print(f"{Fore.CYAN}[DEVICE {serial}] {msg}{Style.RESET_ALL}")
    update_gui(serial, log=msg, step=step, status=status)

# --- Configuration ---
from config_gen import DO_BOX, IMG_DIR, GACHA_FREE, GACHA_FREE_LOOPS, HERO_LIST_FREE, DEBUG_OCR, EVENT_IMG, NOSCAN, SKIPANIMATION, GETQUEST, GETQUEST_IMG_DIR
IMAGE_CACHE = {}

BACKUP_ID_DIR = "backup-id"
os.makedirs(BACKUP_ID_DIR, exist_ok=True)

FAST_RANDOM_DIR = "fast-random"
os.makedirs(FAST_RANDOM_DIR, exist_ok=True)

# OCR imports (optional)
try:
    import easyocr
except ImportError:
    easyocr = None
try:
    import pytesseract
    if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except ImportError:
    pytesseract = None

from collections import namedtuple
Region = namedtuple("Region", ["x", "y", "w", "h"])

ocr_lock = threading.Lock()
_reader = None

def find_adb_executable():
    global adb_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    adb_locations = [
        os.path.join(script_dir, "adb", "adb.exe"),
        os.path.join(script_dir, "adb", "adb"),
        "adb",
    ]
    
    for loc in adb_locations:
        if os.path.exists(loc):
            try:
                result = subprocess.run([loc, "version"], capture_output=True, text=True, timeout=5, shell=(os.name == 'nt'))
                if result.returncode == 0:
                    adb_path = loc
                    print(f"{Fore.GREEN}[ADB] Verified: {adb_path}{Style.RESET_ALL}")
                    return True
            except: pass
    
    # Try system PATH
    adb_in_path = shutil.which("adb")
    if adb_in_path:
        adb_path = os.path.abspath(adb_in_path)
        return True
        
    return False

def connect_known_ports():
    """Auto-scan ALL emulator ports, connect everything that responds"""
    try:
        # Kill & start adb server
        subprocess.run([adb_path, "kill-server"], capture_output=True, timeout=5, shell=(os.name == 'nt'))
        time.sleep(1)
        subprocess.run([adb_path, "start-server"], capture_output=True, timeout=5, shell=(os.name == 'nt'))
        time.sleep(1)

        # Scan ports 5555-5755 (odd ports for MuMu)
        ports = list(range(5555, 5756, 2))
        print(f"{Fore.YELLOW}[ADB] Auto-scanning {len(ports)} ports (5555-5755)...{Style.RESET_ALL}")
        
        def try_connect_port(port):
            try:
                addr = f"127.0.0.1:{port}"
                result = subprocess.run([adb_path, "connect", addr], capture_output=True, timeout=2, text=True, shell=(os.name == 'nt'))
                out = result.stdout.lower()
                if ("connected" in out or "already connected" in out) and "cannot" not in out:
                    return addr
            except: pass
            return None

        connected = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(try_connect_port, p): p for p in ports}
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res: connected.append(res)
        
        if connected:
            print(f"{Fore.GREEN}[ADB] Port scan found {len(connected)} device(s): {', '.join(sorted(connected))}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ADB] Port scan error: {e}{Style.RESET_ALL}")

def get_connected_devices():
    """Get online devices from adb devices (filtered and de-duplicated)"""
    try:
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=10, shell=(os.name == 'nt'))
        lines = result.stdout.strip().split("\n")[1:]
        raw_devices = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                raw_devices.append(parts[0])
        
        if not raw_devices: return []
                
        emulator_adb_ports = set()
        for d in raw_devices:
            if d.startswith("emulator-"):
                try:
                    console_port = int(d.replace("emulator-", ""))
                    emulator_adb_ports.add(console_port + 1)
                except: pass
        
        final_devices = []
        seen = set()
        for d in raw_devices:
            if d in seen: continue
            if d.startswith("127.0.0.1:"):
                try:
                    port = int(d.split(":")[1])
                    if port in emulator_adb_ports: continue
                except: pass
            seen.add(d)
            final_devices.append(d)
        return final_devices
    except: return []

def fast_screencap(device):
    """Fast screencap using raw RGBA data — ~30-50ms vs ~200-500ms PNG"""
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
                img_data = raw[12:12+expected_size]
                img = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 4))
                return cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
    except Exception:
        pass
    # Fallback to PNG method
    try:
        raw = device.screencap()
        if raw:
            return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    except:
        pass
    return None

FIXCLEAR_FIRST_SEEN = {}

def get_screen_capture(device):
    """Screencap with global floating checks (namesom, download, fixgoogle)"""
    try:
        img = fast_screencap(device)
        if img is None:
            return None
            
        # Global check for namesom.bmp (Automatic Reset)
        if ImgSearchADB(img, os.path.join(IMG_DIR, "namesom.bmp"), threshold=0.9):
            gui_log(device.serial, "⚠️ NAMESOM DETECTED! Restarting bot...", status="stuck")
            DEVICE_RESET_FLAGS[device.serial] = True

        # === fixtip floating check ===
        pts1 = ImgSearchADB(img, os.path.join(GETQUEST_IMG_DIR, "fixtip1.bmp"))
        if pts1:
            gui_log(device.serial, "fixtip1.bmp detected! Looking for fixtip2.bmp...", step="Fix Tip")
            pts2 = ImgSearchADB(img, os.path.join(GETQUEST_IMG_DIR, "fixtip2.bmp"))
            if pts2:
                x2, y2 = pts2[0]
                device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                gui_log(device.serial, f"Clicked fixtip2 at ({x2}, {y2})", step="Fix Tip")
                time.sleep(1.5)
                img = fast_screencap(device)
                if img is None:
                    return None

        # === backquest3 floating check ===
        if GQ_ACTIVE.get(device.serial, False) and img is not None:
            bq_pts = ImgSearchADB(img, os.path.join(GETQUEST_IMG_DIR, "backquest3.bmp"))
            if bq_pts:
                gui_log(device.serial, "backquest3 detected! Performing back-spam rescue...", step="Back Rescue")
                # Spam back until cancel found
                while True:
                    device.shell("input keyevent 4")
                    time.sleep(0.4)
                    img_back = fast_screencap(device)
                    if img_back is not None:
                        pts_c = ImgSearchADB(img_back, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts_c:
                            xc, yc = pts_c[0]
                            device.shell(f"input swipe {xc} {yc} {xc} {yc} 100")
                            gui_log(device.serial, f"cancel found — clicking ({xc},{yc})", step="Back Rescue")
                            time.sleep(1.5)
                            break
                # After cancel clicked, wait/click fixbackquest1
                gui_log(device.serial, "Waiting/Clicking fixbackquest1.bmp...", step="Back Rescue")
                while True:
                    img_fb = fast_screencap(device)
                    if img_fb is not None:
                        pts_fb = ImgSearchADB(img_fb, os.path.join(GETQUEST_IMG_DIR, "fixbackquest1.bmp"))
                        if pts_fb:
                            xf, yf = pts_fb[0]
                            device.shell(f"input swipe {xf} {yf} {xf} {yf} 100")
                            gui_log(device.serial, "Clicked fixbackquest1.bmp", step="Back Rescue")
                            time.sleep(1.5)
                            break
                    time.sleep(0.5)
                    
                raise RestartFromQuest8Exception("backquest3 detected")

        # === fixclear floating check ===
        pts_fc = ImgSearchADB(img, os.path.join(IMG_DIR, "fixclear.bmp"), threshold=0.99)
        if pts_fc:
            if device.serial not in FIXCLEAR_FIRST_SEEN:
                FIXCLEAR_FIRST_SEEN[device.serial] = time.time()
                gui_log(device.serial, "fixclear.bmp detected! Starting 15s persistent timer...", step="Fix Clear")
            else:
                elapsed = time.time() - FIXCLEAR_FIRST_SEEN[device.serial]
                gui_log(device.serial, f"fixclear.bmp detected for {elapsed:.1f}s / 15s...", step="Fix Clear")
                if elapsed >= 15:
                    gui_log(device.serial, "⚠️ fixclear.bmp persistent for 15s! Deleting save data and restarting...", status="stuck")
                    FIXCLEAR_FIRST_SEEN.pop(device.serial, None)
                    device.shell("am force-stop jp.konami.pesam")
                    device.shell("su -c 'rm -f /data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat'")
                    device.shell("su -c 'rm -rf /data/data/jp.konami.pesam/files/SaveData/AUTH/*'")
                    DEVICE_RESET_FLAGS[device.serial] = True
                    raise DeviceResetException("fixclear persistent reset")
        else:
            FIXCLEAR_FIRST_SEEN.pop(device.serial, None)

        # Global floating checks for download and fixgoogle
        dl_pts = ImgSearchADB(img, os.path.join(IMG_DIR, "download.bmp"))
        if dl_pts:
            gui_log(device.serial, "Floating: download.bmp found! Clicking...", step="Floating")
            x, y = dl_pts[0]
            device.shell(f"input swipe {x} {y} {x} {y} 100")
        
        fg_pts = ImgSearchADB(img, os.path.join(IMG_DIR, "fixgoogle.bmp"))
        if fg_pts:
            gui_log(device.serial, "Floating: fixgoogle.bmp found! Clicking...", step="Floating")
            x, y = fg_pts[0]
            device.shell(f"input swipe {x} {y} {x} {y} 100")

        # Send to GUI for preview (Disabled to prevent GUI lag/freeze)
        # update_gui(device.serial, screenshot=img)
        return img
    except (DeviceResetException, CycleTimeoutException, RestartFromQuest8Exception):
        raise
    except Exception as e:
        return None

def load_template(find_img_path):
    if find_img_path not in IMAGE_CACHE:
        if os.path.exists(find_img_path):
            template = cv2.imread(find_img_path, cv2.IMREAD_GRAYSCALE)
            if template is not None:
                IMAGE_CACHE[find_img_path] = template
                return template
        
        # Try alternate extension (.bmp <-> .png) if not found
        base, ext = os.path.splitext(find_img_path)
        alt_exts = [".bmp", ".png"]
        alt_exts = [e for e in alt_exts if e.lower() != ext.lower()]
        for alt in alt_exts:
            alt_path = base + alt
            if os.path.exists(alt_path):
                template = cv2.imread(alt_path, cv2.IMREAD_GRAYSCALE)
                if template is not None:
                    IMAGE_CACHE[find_img_path] = template
                    return template
                    
    return IMAGE_CACHE.get(find_img_path)

def ImgSearchADB(adb_img, find_img_path, threshold=0.8):
    try:
        if adb_img is None:
            return []
        
        if len(adb_img.shape) == 3:
            img_gray = cv2.cvtColor(adb_img, cv2.COLOR_BGR2GRAY)
        else:
            img_gray = adb_img

        find_img = load_template(find_img_path)
        if find_img is None:
            print(f"{Fore.RED}[ERROR] Image not found: {find_img_path}{Style.RESET_ALL}")
            return []
            
        needle_w = find_img.shape[1]
        needle_h = find_img.shape[0]
        
        result = cv2.matchTemplate(img_gray, find_img, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        locations = list(zip(*locations[::-1]))
        
        rectangles = []
        for loc in locations:
            rect = [int(loc[0]), int(loc[1]), needle_w, needle_h]
            rectangles.append(rect)
            rectangles.append(rect)
            
        if len(rectangles) > 0:
            rectangles, _ = cv2.groupRectangles(rectangles, groupThreshold=1, eps=1)
            
        points = []
        if len(rectangles):
            for (x, y, w, h) in rectangles:
                center_x = x + int(w/2)
                center_y = y + int(h/2)
                points.append((center_x, center_y))
                
        return points
    except Exception as e:
        print(f"Error in ImgSearchADB: {e}")
        return []
def run_back_spam_recovery(device, serial, cycle_start):
    gui_log(serial, "Running recovery: spamming Back until cancel.bmp...", step="Recovery Back")
    cancel_clicked = False
    spam_count = 0
    while not cancel_clicked:
        check_device_reset(serial, cycle_start)
        spam_count += 1
        if spam_count > 20:   # ป้องกันหลุดค้าง
            gui_log(serial, "Recovery timeout: cancel.bmp not found in 20 taps.", step="Recov Timeout")
            break
        # Press back key
        device.shell("input keyevent 4")
        time.sleep(1.5)
        
        # Capture and check for cancel.bmp
        adb_img = get_screen_capture(device)
        if adb_img is not None:
            pts_cancel = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "cancel.bmp"))
            if pts_cancel:
                x_c, y_c = pts_cancel[0]
                gui_log(serial, f"cancel.bmp found! Clicking at ({x_c}, {y_c})...", step="Click Cancel")
                device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                time.sleep(5)
                cancel_clicked = True
                break

# ═══════════════════════════════════════════════════════════════════════════════
# OCR Helper
# ═══════════════════════════════════════════════════════════════════════════════
def read_screen_text(img, region=None, serial="unknown"):
    """OCR using EasyOCR (priority) or Pytesseract"""
    if img is None: return ""
    if region:
        img = img[region.y : region.y + region.h, region.x : region.x + region.w]

    with ocr_lock:
        # 1. Try EasyOCR
        if easyocr is not None:
            global _reader
            try:
                if _reader is None:
                    _reader = easyocr.Reader(['en'], gpu=False)
                
                # Apply bilateral filter to smooth card textures but keep text edges extremely sharp
                cleaned_img = cv2.bilateralFilter(img, 9, 75, 75)
                # Resize 2x using Cubic interpolation for cleaner character strokes
                resized_easy = cv2.resize(cleaned_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                
                results = _reader.readtext(resized_easy, detail=0)
                res = " ".join(results).strip()
                if res:
                    print(f"[OCR] EasyOCR: '{res}'")
                    return res
            except Exception as e:
                print(f"[OCR] EasyOCR Error: {e}")

        # 2. Fallback Pytesseract
        if pytesseract is not None:
            try:
                if len(img.shape) == 3:
                    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                else:
                    img_gray = img
                img_resized = cv2.resize(img_gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                img_blur = cv2.GaussianBlur(img_resized, (3, 3), 0)
                img_adapt = cv2.adaptiveThreshold(
                    img_blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 15, 4
                )
                text = pytesseract.image_to_string(img_adapt, lang="eng", config="--psm 7").strip()
                if text:
                    print(f"[OCR] Pytesseract: '{text}'")
                    return text
            except Exception as e:
                print(f"[OCR] Pytesseract Error: {e}")
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
    
    if not cleaned_hero or not cleaned_ocr:
        return False
        
    if cleaned_hero in cleaned_ocr:
        return True
        
    if cleaned_ocr in cleaned_hero:
        return True
        
    hero_words = cleaned_hero.split()
    if len(hero_words) > 1:
        if all(w in cleaned_ocr for w in hero_words):
            return True
        match_count = sum(1 for w in hero_words if w in cleaned_ocr)
        if match_count >= max(2, len(hero_words) * 0.7):
            return True
            
    for w in hero_words:
        if len(w) >= 5 and w in cleaned_ocr:
            return True
            
    return False

# ═══════════════════════════════════════════════════════════════════════════════
# Gacha Free Mode (main-pes.py version)
# ═══════════════════════════════════════════════════════════════════════════════
def gacha_free_mode_mainpes(device, cycle_start, serial):
    """
    Gacha Free mode for main-pes.py
    Returns list of found hero names (may be empty).
    """
    gui_log(serial, "Gacha Free sequence started...", step="GachaFree", status="working")

    # Helper: fixcoin check → press Back once
    fixcoin_handled = False
    def _check_fixcoin():
        nonlocal fixcoin_handled
        img_fc = get_screen_capture(device)
        if img_fc is not None:
            pts_fc = ImgSearchADB(img_fc, os.path.join(IMG_DIR, "fixcoin.bmp"), threshold=0.95)
            if pts_fc:
                if not fixcoin_handled:
                    gui_log(serial, "fixcoin.bmp detected! Pressing Back (once)...", step="Fix Coin")
                    device.shell("input keyevent 4")
                    time.sleep(2)
                    fixcoin_handled = True
                return True
            else:
                fixcoin_handled = False
        return False

    # 1. gacha1 → gacha2
    for i in range(1, 3):
        name = f"gacha{i}.bmp"
        gui_log(serial, f"Waiting {name}...", step=name)
        deadline = time.time() + 30
        while time.time() < deadline:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()
            img = get_screen_capture(device)
            if img is not None:
                pts = ImgSearchADB(img, os.path.join(IMG_DIR, name))
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(4)
                    break
            time.sleep(1)

    # 2. Gacha free loops
    found_heroes = []

    for loop_num in range(1, GACHA_FREE_LOOPS + 1):
        gui_log(serial, f"=== Gacha Free Loop {loop_num}/{GACHA_FREE_LOOPS} ===", step=f"Loop {loop_num}")

        # 2a. Swipe to find gachafree1
        gui_log(serial, f"[Loop {loop_num}] Looking for gachafree1.bmp...", step="Swipe Free")
        found_free = False
        miss_count = 0
        max_miss = 10
        next_first_seen = None

        while miss_count < max_miss:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()
            img = get_screen_capture(device)
            if img is not None:
                # Check next.bmp stuck
                pts_next = ImgSearchADB(img, os.path.join(IMG_DIR, "next.bmp"))
                if pts_next:
                    if next_first_seen is None:
                        next_first_seen = time.time()
                    elif time.time() - next_first_seen >= 10:
                        gui_log(serial, f"[Loop {loop_num}] next.bmp stuck! Clicking until gone...", step="Next Stuck")
                        while True:
                            check_device_reset(serial, cycle_start)
                            img_n = get_screen_capture(device)
                            if img_n is not None:
                                pts_n = ImgSearchADB(img_n, os.path.join(IMG_DIR, "next.bmp"))
                                if pts_n:
                                    x_n, y_n = pts_n[0]
                                    device.shell(f"input swipe {x_n} {y_n} {x_n} {y_n} 100")
                                    time.sleep(1)
                                else:
                                    break
                            else:
                                break
                        next_first_seen = None
                        miss_count = 0
                        time.sleep(2)
                        continue
                else:
                    next_first_seen = None

                # Find gachafree1
                pts = ImgSearchADB(img, os.path.join(IMG_DIR, "gachafree1.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    gui_log(serial, f"[Loop {loop_num}] gachafree1 found! Clicking ({x},{y})", step="Free Found")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2)
                    found_free = True
                    deadline_gone = time.time() + 15
                    while time.time() < deadline_gone:
                        check_device_reset(serial, cycle_start)
                        img2 = get_screen_capture(device)
                        if img2 is not None:
                            pts2 = ImgSearchADB(img2, os.path.join(IMG_DIR, "gachafree1.bmp"), threshold=0.95)
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
            device.shell("input swipe 618 308 54 306 5000")
            time.sleep(2)
            _check_fixcoin()

        if not found_free:
            gui_log(serial, f"[Loop {loop_num}] gachafree1 not found after {max_miss} swipes, skipping", step="Skip")
            continue

        # 2b. Wait gachafree2
        gui_log(serial, f"[Loop {loop_num}] Waiting gachafree2.bmp...", step="gachafree2")
        deadline_gf2 = time.time() + 15
        clicked_gf2 = False
        while time.time() < deadline_gf2:
            check_device_reset(serial, cycle_start)
            _check_fixcoin()
            img = get_screen_capture(device)
            if img is not None:
                pts = ImgSearchADB(img, os.path.join(IMG_DIR, "gachafree2.bmp"), threshold=0.95)
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2)
                    clicked_gf2 = True
                    deadline_gf2 = time.time() + 10
                elif clicked_gf2:
                    break
            time.sleep(1)

        if not clicked_gf2:
            gui_log(serial, f"[Loop {loop_num}] gachafree2 not found, skipping loop", step="Error")
            continue

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
                    pts_skip = ImgSearchADB(img_skip, os.path.join(IMG_DIR, "skiphero.bmp"))
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
                            pts_check = ImgSearchADB(img_check, os.path.join(IMG_DIR, "skiphero.bmp"))
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
            # 2c. Wait checkpointgacha → click (478,320) → checkpointgacha1
            gui_log(serial, f"[Loop {loop_num}] Waiting checkpointgacha...", step="CP Wait")
            deadline_cp = time.time() + 45
            while time.time() < deadline_cp:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()
                img = get_screen_capture(device)
                if img is not None:
                    pts = ImgSearchADB(img, os.path.join(IMG_DIR, "checkpointgacha.bmp"))
                    if pts:
                        gui_log(serial, f"[Loop {loop_num}] checkpointgacha found! Clicking...", step="Click Loop")
                        click_count = 0
                        while True:
                            check_device_reset(serial, cycle_start)
                            _check_fixcoin()
                            device.shell("input swipe 478 320 478 320 100")
                            click_count += 1
                            time.sleep(0.3)
                            img_check = get_screen_capture(device)
                            if img_check is not None:
                                pts_fl = ImgSearchADB(img_check, os.path.join(IMG_DIR, "fixlocked.bmp"))
                                if pts_fl:
                                    x_fl, y_fl = pts_fl[0]
                                    device.shell(f"input swipe {x_fl} {y_fl} {x_fl} {y_fl} 100")
                                    time.sleep(1)
                                    continue
                                pts_cp1 = ImgSearchADB(img_check, os.path.join(IMG_DIR, "checkpointgacha1.bmp"))
                                if pts_cp1:
                                    gui_log(serial, f"[Loop {loop_num}] checkpointgacha1 found after {click_count} clicks!", step="CP1 Found")
                                    break
                        break

                    pts_fix = ImgSearchADB(img, os.path.join(IMG_DIR, "fixcheckpointgacha.bmp"))
                    if pts_fix:
                        gui_log(serial, f"[Loop {loop_num}] fixcheckpointgacha detected!", step="Fix CP")
                        pts_fl = ImgSearchADB(img, os.path.join(IMG_DIR, "fixlocked.bmp"))
                        if pts_fl:
                            x_fl, y_fl = pts_fl[0]
                            device.shell(f"input swipe {x_fl} {y_fl} {x_fl} {y_fl} 100")
                            time.sleep(2)
                        break
                time.sleep(1)

            # 2c2. Wait checkpointgacha1 → OCR
            gui_log(serial, f"[Loop {loop_num}] Waiting checkpointgacha1 (OCR)...", step="CP1 Wait")
            deadline_cp1 = time.time() + 30
            while time.time() < deadline_cp1:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()
                img = get_screen_capture(device)
                if img is not None:
                    pts = ImgSearchADB(img, os.path.join(IMG_DIR, "checkpointgacha1.bmp"))
                    if pts:
                        gacha_region = Region(68, 28, 579, 57)
                        ocr_text = read_screen_text(img, region=gacha_region, serial=serial)
                        display_text = ocr_text if ocr_text else "<EMPTY>"
                        gui_log(serial, f"[Loop {loop_num}] OCR: {display_text}", step="OCR Done")

                        for h in HERO_LIST_FREE:
                            if is_hero_match(h, ocr_text):
                                found_heroes.append(h.strip())
                                gui_log(serial, f"[Loop {loop_num}] ⭐ Match: {h.strip()}", step="Match!")
                                break
                        break
                time.sleep(1)

            # 2d. Wait scanout
            gui_log(serial, f"[Loop {loop_num}] Waiting scanout.bmp...", step="Scanout")
            deadline_so = time.time() + 15
            while time.time() < deadline_so:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()
                img = get_screen_capture(device)
                if img is not None:
                    pts = ImgSearchADB(img, os.path.join(IMG_DIR, "scanout.bmp"))
                    if pts:
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(3)
                        break
                time.sleep(1)

        # 2e. Wait next
        gui_log(serial, f"[Loop {loop_num}] Waiting next.bmp...", step="Next")
        if NOSCAN == 1:
            # NOSCAN mode: หา next.bmp ไปเรื่อยๆจนกว่าจะเจอ (ไม่มี timeout)
            while True:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()
                img = get_screen_capture(device)
                if img is not None:
                    pts = ImgSearchADB(img, os.path.join(IMG_DIR, "next.bmp"))
                    if pts:
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(3)
                        break
                time.sleep(1)
        else:
            deadline_next = time.time() + 15
            while time.time() < deadline_next:
                check_device_reset(serial, cycle_start)
                _check_fixcoin()
                img = get_screen_capture(device)
                if img is not None:
                    pts = ImgSearchADB(img, os.path.join(IMG_DIR, "next.bmp"))
                    if pts:
                        x, y = pts[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(3)
                        break
                time.sleep(1)

    # 3. Done — report results
    if found_heroes:
        gui_log(serial, f"⭐ GACHA FREE RESULT: {'+'.join(found_heroes)}", step="Match!")
    else:
        gui_log(serial, f"No match in all {GACHA_FREE_LOOPS} loops", step="No Match")

    return found_heroes

def delete_save_data(device):
    """Delete the specific save file before starting"""
    target_file = "/data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat"
    target_folder = "/data/data/jp.konami.pesam/files/SaveData/AUTH"
    
    print(f"{Fore.YELLOW}[DEVICE {device.serial}] Deleting: {target_file}{Style.RESET_ALL}")
    
    device.shell(f"su -c 'rm -f {target_file}'")
    device.shell(f"su -c 'rm -rf {target_folder}/*'")
    
    time.sleep(1)

def backup_uid_file(device, adb_full_path, remote_path, local_path):
    """Copy the UID file from device to local backup using direct binary capture"""
    search_cmd = "su -c 'find /data/data/jp.konami.pesam/ -name \"*online_user_id_data.dat*\"'"
    found_path = device.shell(search_cmd).strip()
    
    if not found_path or "No such file" in found_path:
        return False
        
    actual_remote_path = found_path.split('\n')[0].strip()
    try:
        with open(local_path, "wb") as f:
            cmd = [adb_full_path, "-s", device.serial, "shell", f"su -c 'cat {actual_remote_path}'"]
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, shell=(os.name == 'nt'))
            
        if result.returncode == 0 and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            return True
        else:
            if os.path.exists(local_path):
                os.remove(local_path)
            return False
    except Exception:
        return False

def process_device(serial_or_device):
    if hasattr(serial_or_device, 'serial'):
        serial = serial_or_device.serial
    else:
        serial = str(serial_or_device)
    
    # Create thread-local AdbClient to prevent socket/data sharing between threads
    client = AdbClient(host="127.0.0.1", port=5037)
    device = client.device(serial)
    if device is None:
        gui_log(serial, "ERROR: Thread failed to initialize private AdbClient device", status="stuck")
        return
        
    gui_log(serial, "Starting automation...", step="Initializing", status="working")
    
    while bot_running: # Respect global bot_running flag
        try:
            check_device_reset(serial)
            
            # 0. Force stop before cleanup
            gui_log(serial, "Force closing app before cleanup...", step="Cleanup", status="working")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(2)
            
            # 1. Initialization - START 6min timer here
            gui_log(serial, "Deleting save data...", step="Resetting", status="working")
            delete_save_data(device)
            cycle_start = time.time()
            
            # 2. Launch app
            gui_log(serial, "Launching PES app...", step="Launching", status="working")
            device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
            time.sleep(15)
            
            # 3. Main sequence: play1 - play19
            sequence_1 = [f"play{i}.bmp" for i in range(1, 20)]
            for img_name in sequence_1:
                if img_name == "play19.bmp": break # Handle play19 later after UID
                
                img_path = os.path.join(IMG_DIR, img_name)
                found = False
                img_num = int(img_name.replace("play", "").replace(".bmp", ""))
                has_timeout = img_num >= 13
                start_time = time.time()
                
                while not found:
                    check_device_reset(serial, cycle_start)
                    if has_timeout and (time.time() - start_time > 5):
                        gui_log(serial, f"Timeout for {img_name}.", step="Skipping")
                        break
                    adb_img = get_screen_capture(device)
                    if adb_img is None: continue
                    points = None
                    if img_name == "play1.bmp": points = [(871, 508)]
                    elif img_name == "play10.bmp" or img_name == "play12.bmp": points = [(675, 476)]
                    else: points = ImgSearchADB(adb_img, img_path)
                    if points:
                        x, y = points[0]
                        gui_log(serial, f"Found {img_name} at ({x}, {y})", step=f"Clicking {img_name}")
                        if img_name in ["play10.bmp", "play12.bmp"]:
                            for i in range(3):
                                gui_log(serial, f"Clicking {img_name} ({i+1}/3)...", step="Multi-Click")
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(1)
                        else:
                            device.shell(f"input swipe {x} {y} {x} {y} 100")

                        if img_name == "play8.bmp":
                            while True:
                                check_device_reset(serial, cycle_start)
                                time.sleep(5)
                                p9_img = get_screen_capture(device)
                                if p9_img is not None and ImgSearchADB(p9_img, os.path.join(IMG_DIR, "play9.bmp")): break
                                device.shell(f"input swipe {x} {y} {x} {y} 100")

                        if img_name == "play2.bmp":
                            time.sleep(10)
                            check_device_reset(serial, cycle_start)
                            p2_img = get_screen_capture(device)
                            if p2_img is not None and ImgSearchADB(p2_img, img_path):
                                gui_log(serial, "Still found play2.bmp, clicking again...", step="Retry play2")
                                device.shell(f"input swipe {x} {y} {x} {y} 100")

                        if img_name == "play3.bmp":
                            gui_log(serial, "play3 clicked. Repeating until play4 found...", step="Repeat play3")
                            while True:
                                check_device_reset(serial, cycle_start)
                                time.sleep(0.033)
                                p4_img = get_screen_capture(device)
                                if p4_img is not None and ImgSearchADB(p4_img, os.path.join(IMG_DIR, "play4.bmp")):
                                    gui_log(serial, "play4.bmp found! Moving on.", step="play4 Found")
                                    break
                                device.shell(f"input swipe {x} {y} {x} {y} 100")

                        time.sleep(5)
                        found = True
                    time.sleep(0.01)
            
            # 4. UID Flow (Existing)
            gui_log(serial, "Waiting for UID check screen...", step="UID Backup", status="working")
            while True:
                check_device_reset(serial, cycle_start)
                adb_img = get_screen_capture(device)
                if adb_img is not None and ImgSearchADB(adb_img, os.path.join(IMG_DIR, "uidcheck.bmp")):
                    gui_log(serial, "Found UID check! Capturing data...", step="Extracting UID")
                    device.shell("input swipe 215 369 215 369 5000")
                    time.sleep(2)
                    device.shell("input swipe 81 522 81 522 5000")
                    time.sleep(2)
                    break
                time.sleep(0.01)
                
            uid1_done = False
            while True:
                check_device_reset(serial, cycle_start)
                adb_img = get_screen_capture(device)
                if adb_img is not None:
                    p2 = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "uid2.bmp"))
                    if p2:
                        x, y = p2[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        time.sleep(3)
                        break
                    if not uid1_done:
                        p1 = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "uid1.bmp"))
                        if p1:
                            x, y = p1[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            uid1_done = True
                            time.sleep(3)
                time.sleep(0.01)

            # play19 → spam (815, 355) จนเจอ play21
            gui_log(serial, "Waiting for play19.bmp...", step="Post-UID")
            while True:
                check_device_reset(serial, cycle_start)
                adb_img = get_screen_capture(device)
                if adb_img is not None:
                    p = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "play19.bmp"))
                    if p:
                        x, y = p[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, "play19 clicked. Spamming (815,355) until play21...", step="Play19 Clicked")
                        break
                time.sleep(0.01)

            # Spam (815, 355) จนเจอ play21 (ไม่รอ 20 วิ กดรัวๆ เลย)
            gui_log(serial, "Searching for play21.bmp via (815, 355)...", step="Transition")
            spam_count_p21 = 0
            while True:
                check_device_reset(serial, cycle_start)
                spam_count_p21 += 1
                if spam_count_p21 % 15 == 0:
                    gui_log(serial, f"Still searching for play21.bmp... (Spammed 815,355 x{spam_count_p21})", step="Search Play21")
                device.shell("input swipe 815 355 815 355 100")
                adb_img = get_screen_capture(device)
                if adb_img is not None:
                    p = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "play21.bmp"))
                    if p:
                        x, y = p[0]
                        gui_log(serial, f"Found play21.bmp at ({x}, {y}). Spamming until gone...", step="Spam Play21")
                        while True:
                            check_device_reset(serial, cycle_start)
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(0.5)
                            check_img = get_screen_capture(device)
                            if check_img is not None and not ImgSearchADB(check_img, os.path.join(IMG_DIR, "play21.bmp")):
                                break
                        time.sleep(3)
                        break
            
            # ── Event Image Mode (EVENT_IMG) ──
            if EVENT_IMG == 0:
                gui_log(serial, "Event Image Mode = 0 (No Event). Waiting for play22.bmp...", step="No Event")
                
                # 1. Wait for play22.bmp
                spam_count_p22 = 0
                while True:
                    check_device_reset(serial, cycle_start)
                    adb_img = get_screen_capture(device)
                    if adb_img is not None:
                        if ImgSearchADB(adb_img, os.path.join(IMG_DIR, "play22.bmp")):
                            gui_log(serial, "play22.bmp detected! Starting Back spam...", step="Spamming Back")
                            break
                    # Spam click 815 355 to get to play22 screen if needed
                    spam_count_p22 += 1
                    if spam_count_p22 % 10 == 0:
                        gui_log(serial, f"Still waiting for play22.bmp... (Spammed 815,355 x{spam_count_p22})", step="Wait Play22")
                    device.shell("input swipe 815 355 815 355 100")
                    time.sleep(1)

                # 2. Press Back repeatedly until cancel.bmp is found
                cancel_clicked = False
                while not cancel_clicked:
                    check_device_reset(serial, cycle_start)
                    # Press back key
                    device.shell("input keyevent 4")
                    time.sleep(1.5)
                    
                    # Capture and check for cancel.bmp
                    adb_img = get_screen_capture(device)
                    if adb_img is not None:
                        pts_cancel = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts_cancel:
                            x_c, y_c = pts_cancel[0]
                            gui_log(serial, f"cancel.bmp found! Clicking at ({x_c}, {y_c})...", step="Click Cancel")
                            device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                            time.sleep(5)
                            cancel_clicked = True
                            break
            else:
                # EVENT_IMG == 1 -> Normal Event flow (play22-play25, play26-play31 and Box sequence)
                # play22 - play25
                seq_ext = [f"play{i}.bmp" for i in range(22, 26)]
                for img_name in seq_ext:
                    if img_name == "play22.bmp":
                        gui_log(serial, "Clicking 815 355 until play22/play23...", step="Loop play22")
                        spam_count_p22_event = 0
                        while True:
                            check_device_reset(serial, cycle_start)
                            adb_img = get_screen_capture(device)
                            if adb_img is not None:
                                if ImgSearchADB(adb_img, os.path.join(IMG_DIR, "play23.bmp")):
                                    gui_log(serial, "Found play23.bmp! Proceeding...", step="Found play23")
                                    break
                                p22 = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "play22.bmp"))
                                if p22:
                                    x, y = p22[0]
                                    gui_log(serial, "Clicking play22.bmp again...", step="Repeat play22")
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    time.sleep(3)
                                else:
                                    # Not found play22 or play23, spam click 815 355
                                    spam_count_p22_event += 1
                                    if spam_count_p22_event % 15 == 0:
                                        gui_log(serial, f"Still waiting for play22/play23... (Spammed 815,355 x{spam_count_p22_event})", step="Wait Play22")
                                    device.shell("input swipe 815 355 815 355 100")
                                    time.sleep(0.5)
                            time.sleep(0.05)   # Optimized sleep from 0.01 to 0.05 to save host CPU
                        continue

                    gui_log(serial, f"Waiting for {img_name}...", step=f"Wait {img_name}")
                    wait_count = 0
                    while True:
                        check_device_reset(serial, cycle_start)
                        wait_count += 1
                        if wait_count % 300 == 0:
                            gui_log(serial, f"Still waiting for {img_name}... ({wait_count // 20}s elapsed)", step=f"Wait {img_name}")
                        adb_img = get_screen_capture(device)
                        if adb_img is not None:
                            p = ImgSearchADB(adb_img, os.path.join(IMG_DIR, img_name))
                            if p:
                                x, y = p[0]
                                gui_log(serial, f"Found {img_name} at ({x}, {y})", step=f"Click {img_name}")
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(5)
                                break
                        time.sleep(0.05)   # Optimized sleep from 0.01 to 0.05 to save host CPU

                # ── Get Quest Sequence (เอาระบบในไฟล์ login.py มาใส่ก่อน Box) ──
                if GETQUEST == 1:
                    # Spam Back until cancel.bmp to return to main menu
                    gui_log(serial, "Spamming Back until cancel.bmp to return to main menu...", step="GQ Init Back")
                    while True:
                        check_device_reset(serial, cycle_start)
                        device.shell("input keyevent 4")
                        time.sleep(0.4)
                        img = get_screen_capture(device)
                        if img is not None:
                            pts_cancel = ImgSearchADB(img, os.path.join(IMG_DIR, "cancel.bmp"))
                            if pts_cancel:
                                x_c, y_c = pts_cancel[0]
                                device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                                gui_log(serial, f"cancel.bmp found — clicking ({x_c},{y_c})", step="GQ Init Cancel")
                                time.sleep(1.5)
                                # กดซ้ำจนกว่าจะหาย
                                retry_end = time.time() + 8
                                while time.time() < retry_end:
                                    check_device_reset(serial, cycle_start)
                                    img2 = get_screen_capture(device)
                                    if img2 is not None and not ImgSearchADB(img2, os.path.join(IMG_DIR, "cancel.bmp")):
                                        break
                                    device.shell(f"input swipe {x_c} {y_c} {x_c} {y_c} 100")
                                    time.sleep(1.0)
                                break

                    gui_log(serial, "Get Quest sequence started...", step="GetQuest", status="working")
                    GQ_DIR = GETQUEST_IMG_DIR  # img/getquest
                    
                    GQ_ACTIVE[serial] = True
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
                                                pts = ImgSearchADB(img, os.path.join(GQ_DIR, gq_name))
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
                                                        if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, gq_name)):
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
                                            pts6 = ImgSearchADB(img, os.path.join(GQ_DIR, "getquest6.bmp"))
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
                                            pts6 = ImgSearchADB(img, os.path.join(GQ_DIR, "getquest6.bmp"))
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
                                            pts7 = ImgSearchADB(img, os.path.join(GQ_DIR, "getquest7.bmp"))
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
                                                    if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, "getquest7.bmp")):
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
                                            pts_c = ImgSearchADB(img, os.path.join(IMG_DIR, "cancel.bmp"))
                                            if pts_c:
                                                xc, yc = pts_c[0]
                                                gui_log(serial, f"cancel found — clicking ({xc},{yc})", step="gq7 Cancel")
                                                device.shell(f"input swipe {xc} {yc} {xc} {yc} 100")
                                                time.sleep(1.5)
                                                break

                                # ── Phase 5: getquest8 → getquest11 (คลิกทีละภาพ) ──
                                p5_start = 8
                                for gq_i in range(p5_start, 12):
                                    gq_name = f"getquest{gq_i}.bmp"
                                    gui_log(serial, f"Waiting {gq_name}...", step=f"gq{gq_i}")
                                    thresh = 0.99 if gq_i == 10 else 0.8
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            pts = ImgSearchADB(img, os.path.join(GQ_DIR, gq_name), threshold=thresh)
                                            if pts:
                                                x, y = pts[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked {gq_name} ({x},{y})", step=f"gq{gq_i} Click")
                                                time.sleep(1.5)
                                                # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, gq_name), threshold=thresh):
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
                                        pts_c = ImgSearchADB(img, os.path.join(IMG_DIR, "cancel.bmp"))
                                        if pts_c:
                                            xc, yc = pts_c[0]
                                            gui_log(serial, f"cancel found — clicking ({xc},{yc})", step="gq11 Cancel")
                                            device.shell(f"input swipe {xc} {yc} {xc} {yc} 100")
                                            time.sleep(1.5)
                                            break

                                # ── Phase 6: getquest12 → getquest14 ──
                                for gq_i in range(12, 15):
                                    gq_name = f"getquest{gq_i}.bmp"
                                    gui_log(serial, f"Waiting {gq_name}...", step=f"gq{gq_i}")
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        img = get_screen_capture(device)
                                        if img is not None:
                                            pts = ImgSearchADB(img, os.path.join(GQ_DIR, gq_name))
                                            if pts:
                                                x, y = pts[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked {gq_name} ({x},{y})", step=f"gq{gq_i} Click")
                                                time.sleep(1.5)
                                                # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, gq_name)):
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
                                        pts_wq = ImgSearchADB(img, os.path.join(GQ_DIR, "waitquest.bmp"))
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
                                        pts15 = ImgSearchADB(img, os.path.join(GQ_DIR, "getquest15.bmp"))
                                        if pts15:
                                            x15, y15 = pts15[0]
                                            device.shell(f"input swipe {x15} {y15} {x15} {y15} 100")
                                            gui_log(serial, f"Clicked getquest15 ({x15},{y15})", step="gq15 Click")
                                            time.sleep(1.5)
                                            # กดซ้ำจนรูปหาย (กันกดไม่ติด)
                                            retry_end = time.time() + 8
                                            while time.time() < retry_end:
                                                img2 = get_screen_capture(device)
                                                if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, "getquest15.bmp")):
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
                                            pts = ImgSearchADB(img, img_path, threshold=threshold)
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
                                                    if img2 is not None and not ImgSearchADB(img2, img_path, threshold=threshold):
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
                                            pts = ImgSearchADB(img, os.path.join(GQ_DIR, "questfive1.bmp"))
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
                                                    if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, "questfive1.bmp")):
                                                        break
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, "Re-clicked questfive1", step="Q5_1 Retry")
                                                    time.sleep(1.0)
                                                break
                                        time.sleep(0.8)
                                        
                                    if not q5_1_found:
                                        gui_log(serial, "questfive1.bmp not found! Retrying from drag...", step="Q5_1 Fail")
                                        continue
                                        
                                    # 3. เช็ค checkpointquest1
                                    gui_log(serial, "Verifying checkpointquest1.bmp...", step="Q5 CP1 Check")
                                    time.sleep(2.0) # ให้เวลาโหลดหน้าจอ
                                    checkpoint_found = False
                                    img = get_screen_capture(device)
                                    if img is not None:
                                        pts = ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest1.bmp"))
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
                                    for i in range(2, 4):
                                        q_name = f"questfive{i}.bmp"
                                        click_until_gone(os.path.join(GQ_DIR, q_name), q_name)
                                        
                                    # 5. วนกด questfive4 -> questfive5 จนกว่าจะเจอ checkpointquest2
                                    gui_log(serial, "Loop clicking questfive4 -> questfive5...", step="Q5_4->5 Loop")
                                    while True:
                                        check_device_reset(serial, cycle_start)
                                        # เช็ค checkpointquest2 ก่อนเริ่มรอบ
                                        img = get_screen_capture(device)
                                        if img is not None and ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                            gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                            break
                                            
                                        # รอ/กด questfive4
                                        q4_break = False
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img = get_screen_capture(device)
                                            if img is not None:
                                                if ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                                    gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                                    q4_break = True
                                                    break
                                                
                                                pts4 = ImgSearchADB(img, os.path.join(GQ_DIR, "questfive4.bmp"))
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
                                                        if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, "questfive4.bmp")):
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
                                        if img is not None and ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                            gui_log(serial, "checkpointquest2.bmp FOUND before questfive5! Breaking loop...", step="Q5 CP2 OK")
                                            break
                                            
                                        # รอ/กด questfive5
                                        q5_break = False
                                        while True:
                                            check_device_reset(serial, cycle_start)
                                            img = get_screen_capture(device)
                                            if img is not None:
                                                if ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                                                    gui_log(serial, "checkpointquest2.bmp FOUND! Breaking loop...", step="Q5 CP2 OK")
                                                    q5_break = True
                                                    break
                                                
                                                pts5 = ImgSearchADB(img, os.path.join(GQ_DIR, "questfive5.bmp"))
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
                                                        if img2 is not None and not ImgSearchADB(img2, os.path.join(GQ_DIR, "questfive5.bmp")):
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
                                            if ImgSearchADB(img, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
                                                gui_log(serial, "chekcpointquest3.bmp FOUND!", step="Q5 CP3 OK")
                                                break
                                            
                                            # ค้นหา questfive10.bmp
                                            pts10 = ImgSearchADB(img, os.path.join(GQ_DIR, "questfive10.bmp"))
                                            if pts10:
                                                x, y = pts10[0]
                                                gui_log(serial, f"Long pressing questfive10 at ({x}, {y})...", step="Q5_10 Click")
                                                device.shell(f"input swipe {x} {y} {x} {y} 5000")
                                                time.sleep(5.5) # รอให้กดค้างเสร็จ
                                                
                                                # เช็ค chekcpointquest3 อีกรอบหลังกดค้างเสร็จ
                                                img_after = get_screen_capture(device)
                                                if img_after is not None and ImgSearchADB(img_after, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
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
                                            if ImgSearchADB(img, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
                                                gui_log(serial, "checkpointquest4.bmp FOUND!", step="Q5 CP4 OK")
                                                break
                                                    
                                            # ค้นหา questfive13.bmp
                                            pts13 = ImgSearchADB(img, os.path.join(GQ_DIR, "questfive13.bmp"))
                                            if pts13:
                                                x, y = pts13[0]
                                                gui_log(serial, f"Long pressing questfive13 at ({x}, {y})...", step="Q5_13 Click")
                                                device.shell(f"input swipe {x} {y} {x} {y} 7000")
                                                time.sleep(7.5) # รอให้กดค้างเสร็จ
                                                
                                                # เช็ค checkpointquest4 อีกรอบหลังกดค้างเสร็จ
                                                img_after = get_screen_capture(device)
                                                if img_after is not None and ImgSearchADB(img_after, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
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
                                            pts_cancel = ImgSearchADB(img, "img/cancel.bmp")
                                            if pts_cancel:
                                                x, y = pts_cancel[0]
                                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                gui_log(serial, f"Clicked cancel at ({x}, {y})", step="Cancel Click")
                                                time.sleep(1.5)
                                                # กดซ้ำจนกว่าจะหาย
                                                retry_end = time.time() + 8
                                                while time.time() < retry_end:
                                                    check_device_reset(serial, cycle_start)
                                                    img2 = get_screen_capture(device)
                                                    if img2 is not None and not ImgSearchADB(img2, "img/cancel.bmp"):
                                                        break
                                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                                    gui_log(serial, "Re-clicked cancel", step="Cancel Retry")
                                                    time.sleep(1.0)
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
                        GQ_ACTIVE[serial] = False

                # ── Box Sequence (เอาระบบในไฟล์ login.py มาทดแทนทั้งหมด) ──
                if DO_BOX == 1:
                    gui_log(serial, "Box sequence started...", step="Box Mode", status="working")
                    
                    # play26 - play31 (リードアップ) - ทำเพียงครั้งเดียวตอนเริ่มขั้นตอนกล่อง
                    found_any_play = False
                    for i in range(26, 32):
                        name = f"play{i}.bmp"
                        gui_log(serial, f"Waiting {name} (Box path)...", step=name)
                        deadline = time.time() + 4
                        while time.time() < deadline:
                            check_device_reset(serial, cycle_start)
                            adb_img = get_screen_capture(device)
                            if adb_img is not None:
                                pts = ImgSearchADB(adb_img, os.path.join(IMG_DIR, name))
                                if pts:
                                    x, y = pts[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    found_any_play = True
                                    time.sleep(2.5)
                                    break
                            time.sleep(0.5)
                    
                    # ถ้าระหว่างทางหา play26 - play31 ไม่เจอเลยสักตัว ให้ทำระบบ Recovery: กด Back รัวๆ จนเจอ cancel.bmp
                    if not found_any_play:
                        run_back_spam_recovery(device, serial, cycle_start)
                    
                    # วนหา box1 และ box2
                    box2_found = False
                    while not box2_found:
                        check_device_reset(serial, cycle_start)
                        
                        # box1
                        gui_log(serial, "Waiting box1.bmp...", step="box1")
                        start_box = time.time()
                        box1_found = False
                        while time.time() - start_box < 15:
                            check_device_reset(serial, cycle_start)
                            adb_img = get_screen_capture(device)
                            if adb_img is not None:
                                pts = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "box1.bmp"))
                                if pts:
                                    x, y = pts[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    time.sleep(4)
                                    box1_found = True
                                    break
                            time.sleep(0.8)
                        
                        if not box1_found:
                            gui_log(serial, "box1.bmp not found! Running recovery: spamming Back until cancel.bmp...", step="Retry")
                            run_back_spam_recovery(device, serial, cycle_start)
                            continue

                        # box2
                        gui_log(serial, "Waiting box2.bmp...", step="box2")
                        start_box = time.time()
                        while time.time() - start_box < 15:
                            check_device_reset(serial, cycle_start)
                            adb_img = get_screen_capture(device)
                            if adb_img is not None:
                                pts = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "box2.bmp"))
                                if pts:
                                    x, y = pts[0]
                                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                                    time.sleep(4)
                                    box2_found = True
                                    break
                            time.sleep(0.8)
                            
                        if not box2_found:
                            gui_log(serial, "box2.bmp not found! Running recovery: spamming Back until cancel.bmp...", step="Retry")
                            run_back_spam_recovery(device, serial, cycle_start)
                            continue
                    
                    # box3 (กดเรื่อยๆ จนไม่เจอครบ 10s ค่อยไป box4)
                    gui_log(serial, "Waiting box3.bmp...", step="box3")
                    last_seen = time.time()
                    while time.time() - last_seen < 10:
                        check_device_reset(serial, cycle_start)
                        adb_img = get_screen_capture(device)
                        if adb_img is not None:
                            pts = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "box3.bmp"))
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
                        adb_img = get_screen_capture(device)
                        if adb_img is not None:
                            pts = ImgSearchADB(adb_img, os.path.join(IMG_DIR, "box4.bmp"))
                            if pts:
                                x, y = pts[0]
                                device.shell(f"input swipe {x} {y} {x} {y} 100")
                                time.sleep(4)
                                break
                        time.sleep(1)

            # ── Gacha Free Sequence (ถ้าเปิด GACHA_FREE=1) ──
            gacha_free_result = []
            if GACHA_FREE == 1:
                gacha_free_result = gacha_free_mode_mainpes(device, cycle_start, serial)

            # 5. FINAL BACKUP LOGIC
            gui_log(serial, "Starting final backup sequence...", step="Final Backup")
            backup_dir = "backup"
            if not os.path.exists(backup_dir): os.makedirs(backup_dir)
            safe_serial = serial.replace(".", "_").replace(":", "_")
            temp_local_path = os.path.join(backup_dir, f"temp_uid_{safe_serial}.dat")
            remote_path = "/data/data/jp.konami.pesam/files/SaveData/AUTH/online_user_id_data.dat"
            adb_full_path = adb_path
            
            file_found = False
            for _ in range(15):
                check_device_reset(serial, cycle_start)
                if device.shell(f"su -c 'find /data/data/jp.konami.pesam/files/SaveData/AUTH/ -name \"online_user_id_data.dat\"'").strip():
                    file_found = True
                    break
                time.sleep(0.01)

            success = backup_uid_file(device, adb_full_path, remote_path, temp_local_path)
            gui_log(serial, "Closing app for cleanup...", step="Cleanup")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(2)
            
            if not success:
                success = backup_uid_file(device, adb_full_path, remote_path, temp_local_path)

            if success:
                try:
                    time.sleep(1)
                    user_code = "unknown"
                    with open(temp_local_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        start_idx, end_idx = content.find("{"), content.rfind("}")
                        if start_idx != -1 and end_idx != -1:
                            data = json.loads(content[start_idx:end_idx+1])
                            user_code = data.get("user_code", "unknown")
                    
                    # ถ้า NOSCAN=1 → ส่งไป fast-random/ เสมอ
                    if NOSCAN == 1:
                        final_name = f"{user_code}.dat"
                        dest_dir = FAST_RANDOM_DIR
                        gui_log(serial, f"NOSCAN → {dest_dir}/{final_name}", step="Fast Random")
                    # ถ้ามี gacha free result → ส่งไป backup-id
                    elif GACHA_FREE == 1 and gacha_free_result:
                        hero_prefix = "+".join(gacha_free_result)
                        final_name = f"{hero_prefix}+{user_code}.dat"
                        dest_dir = BACKUP_ID_DIR
                        gui_log(serial, f"⭐ HERO FOUND: {hero_prefix} → {dest_dir}", step="Match!")
                    else:
                        final_name = f"{user_code}.dat"
                        dest_dir = backup_dir

                    final_local_path = os.path.join(dest_dir, final_name)
                    for i in range(5):
                        try:
                            if os.path.exists(final_local_path): os.remove(final_local_path)
                            shutil.move(temp_local_path, final_local_path)
                            gui_log(serial, f"COMPLETE: Saved as {final_name}", step="Finished", status="waiting")
                            break
                        except: time.sleep(2)
                except Exception as e:
                    gui_log(serial, f"Rename error: {e}", status="stuck")
            
            gui_log(serial, "Loop finished. Restarting from scratch...", step="Done", status="waiting")
            time.sleep(3)

        except DeviceResetException:
            gui_log(serial, "🛑 MANUAL RESET TRIGGERED", step="Resetting", status="stuck")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(2)
            continue
        except CycleTimeoutException:
            elapsed = int(time.time() - cycle_start) if 'cycle_start' in dir() else 0
            gui_log(serial, f"⏰ TIMEOUT ({elapsed}s)! Restarting cycle...", step="Timeout Reset", status="stuck")
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(2)
            continue
        except Exception as e:
            gui_log(serial, f"Error: {e}", status="stuck")
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

def main():
    if GUI_ENABLED:
        app = ModernBotGUI()
        app.mainloop()
    else:
        # Fallback to CLI if GUI libs missing
        if not find_adb_executable():
            print(f"{Fore.RED}[ERROR] adb.exe not found.{Style.RESET_ALL}")
            return
        connect_known_ports()
        devices = get_connected_devices()
        if not devices:
            print(f"{Fore.RED}[ERROR] No devices found.{Style.RESET_ALL}")
            return
        client = AdbClient(host="127.0.0.1", port=5037)
        global bot_running
        bot_running = True
        for serial in devices:
            device = client.device(serial)
            t = threading.Thread(target=process_device, args=(device,), daemon=True)
            t.start()
            time.sleep(2)
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
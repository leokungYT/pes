import os
import cv2
import time
import random
import shutil
import threading
import subprocess
import queue as _queue_mod

os.chdir(os.path.dirname(os.path.abspath(__file__)))

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from ppadb.client import Client as AdbClient
from colorama import Fore, Style, init
init(autoreset=True)

import customtkinter as ctk
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from config import IMG_DIR
try:
    from config import SEND_CODE as _CFG_SEND_CODE
except ImportError:
    _CFG_SEND_CODE = "M-CBFTKHBALEF"

from login import (
    gui_log,
    get_screen_capture,
    img_search,
    check_device_reset,
    pick_next_file,
    push_dat_to_device,
    release_file,
    find_adb_executable,
    DEVICE_FILE_ASSIGNMENTS,
    DEVICE_DISABLE_FIXEVENT,
)

# ── Dirs ──────────────────────────────────────────────────────────────────────
SENDCODE_IMG_DIR = os.path.join(IMG_DIR, "setcode")
DONE_CODE_DIR    = "done-code"
SUBMIT_CODE_DIR  = "submit-code"

# ── Exceptions ───────────────────────────────────────────────────────────────
class FixSendCodeException(Exception):
    pass

class BotStoppedException(Exception):
    pass

# ── Globals ───────────────────────────────────────────────────────────────────
_gui_queue  = _queue_mod.Queue()
bot_running = False
gui_instance = None

# ─────────────────────────────────────────────────────────────────────────────
# Bot logic
# ─────────────────────────────────────────────────────────────────────────────

def _sc(name):
    return os.path.join(SENDCODE_IMG_DIR, name)


def _move_file(src, dest_dir, name):
    os.makedirs(dest_dir, exist_ok=True)
    try:
        shutil.move(src, os.path.join(dest_dir, name))
    except Exception as e:
        _gui_queue.put(('log', f"[WARN] move file: {e}"))


def play_start_to_checkpoint(device, serial):
    """
    force-stop → pick file → push → launch game → play8 → checkpointlogin
    คืน (file_path, original_name, cycle_start) หรือ None
    """
    if not bot_running:
        return None

    time.sleep(random.uniform(0.5, 2.0))

    DEVICE_DISABLE_FIXEVENT[serial] = False
    check_device_reset(serial)
    _gui_queue.put(('log', f"[{serial}] --- New Cycle ---"))

    # 0. Force-stop
    device.shell("am force-stop jp.konami.pesam")
    time.sleep(1)

    # 1. Pick file
    file_path, original_name = pick_next_file()
    if file_path is None:
        _gui_queue.put(('log', f"[{serial}] No files left — idle"))
        _gui_queue.put(('status', (serial, 'idle')))
        return None

    _gui_queue.put(('log', f"[{serial}] File: {original_name}"))
    _gui_queue.put(('status', (serial, 'working')))
    DEVICE_FILE_ASSIGNMENTS[serial] = original_name
    cycle_start = time.time()

    # 2. Push file
    _gui_queue.put(('log', f"[{serial}] Pushing file..."))
    if not push_dat_to_device(device, file_path):
        _gui_queue.put(('log', f"[{serial}] Push FAILED!"))
        _gui_queue.put(('status', (serial, 'stuck')))
        release_file(original_name)
        return None

    # เช็คหลัง push (push_dat_to_device อาจรันนานมาก)
    if not bot_running:
        release_file(original_name)
        DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
        return None

    # 3. Launch + Black Screen Check
    _gui_queue.put(('log', f"[{serial}] Launching PES..."))
    for attempt in range(3):
        device.shell("monkey -p jp.konami.pesam -c android.intent.category.LAUNCHER 1")
        t0 = time.time()
        stuck = False
        while time.time() - t0 < 45:
            if not bot_running:
                release_file(original_name)
                DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
                raise BotStoppedException()
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                try:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
                    _, th = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
                    if cv2.countNonZero(th) / (gray.shape[0] * gray.shape[1]) < 0.85:
                        stuck = False
                        break
                    stuck = True
                except Exception:
                    stuck = True
            else:
                stuck = True
            time.sleep(1)
        if stuck:
            _gui_queue.put(('log', f"[{serial}] Black screen! (attempt {attempt+1}/3)"))
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(2)
        else:
            break

    # เช็คหลัง sleep 8s
    if not bot_running:
        release_file(original_name)
        DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
        return None
    time.sleep(8)

    def _chk():
        if not bot_running:
            release_file(original_name)
            DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
            raise BotStoppedException()
        check_device_reset(serial, cycle_start)

    # 4. Wait play8 / play8fix
    _gui_queue.put(('log', f"[{serial}] Waiting play8..."))
    play8_clicked = False
    while True:
        _chk()
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
            mname = "play8"
            if not pts:
                pts = img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))
                mname = "play8fix"
            if pts:
                pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                if pts_lg3:
                    x, y = pts_lg3[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(2)
                    continue
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                _gui_queue.put(('log', f"[{serial}] {mname} clicked"))
                play8_clicked = True
                time.sleep(5)
            elif play8_clicked:
                break
        time.sleep(1.5)

    # 5. Wait checkpointlogin
    _gui_queue.put(('log', f"[{serial}] Waiting checkpointlogin..."))
    while True:
        _chk()
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                _gui_queue.put(('log', f"[{serial}] checkpointlogin ✓"))
                time.sleep(4)
                break
        time.sleep(1.5)

    # 6. กด Back รัวๆ จนเจอ cancel.bmp แล้วคลิกจนหาย
    _gui_queue.put(('log', f"[{serial}] Spamming Back until cancel.bmp..."))
    while True:
        _chk()
        device.shell("input keyevent 4")
        time.sleep(0.4)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                _gui_queue.put(('log', f"[{serial}] cancel.bmp found — clicking until gone"))
                time.sleep(1)
                last_seen = time.time()
                while time.time() - last_seen < 5:
                    _chk()
                    img2 = get_screen_capture(device)
                    if img2 is not None:
                        pts2 = img_search(img2, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts2:
                            x2, y2 = pts2[0]
                            device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
                            time.sleep(1)
                            last_seen = time.time()
                    time.sleep(0.5)
                _gui_queue.put(('log', f"[{serial}] cancel.bmp gone ✓"))
                break

    return file_path, original_name, cycle_start


def sendcode_sequence(device, serial, cycle_start, original_name, file_path, code):
    """sentcode1 → sentcode2(15s) → sentcode3 → sentcode4 → type → sentcode5 → result"""

    _fix_path = os.path.join(SENDCODE_IMG_DIR, "fixsendcode.bmp")

    def _get_img():
        """ดึงภาพ + เช็ค bot stop + fixsendcode ทุกครั้ง (floating check)"""
        if not bot_running:
            raise BotStoppedException()
        img = get_screen_capture(device)
        if img is not None and img_search(img, _fix_path):
            _gui_queue.put(('log', f"[{serial}]   ⚠ fixsendcode detected!"))
            raise FixSendCodeException()
        return img

    def _click_img(bmp_name, label, timeout=30):
        _gui_queue.put(('log', f"[{serial}]   looking for {bmp_name}..."))
        deadline = time.time() + timeout
        while time.time() < deadline:
            check_device_reset(serial, cycle_start)
            img = _get_img()
            if img is not None:
                pts = img_search(img, _sc(bmp_name))
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    _gui_queue.put(('log', f"[{serial}]   ✓ {label} clicked ({x},{y})"))
                    time.sleep(1)
                    return True
            time.sleep(0.5)
        _gui_queue.put(('log', f"[{serial}]   ✗ {label} not found (timeout {timeout}s)"))
        return False

    try:
        # 1. sentcode1
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 1: sentcode1"))
        _click_img("sentcode1.bmp", "sentcode1", timeout=30)

        # 2. sentcode2 — 15s timeout → done-code
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 2: sentcode2 (15s)"))
        found2 = _click_img("sentcode2.bmp", "sentcode2", timeout=15)
        if not found2:
            _gui_queue.put(('log', f"[{serial}] sentcode2 timeout → done-code: {original_name}"))
            device.shell("am force-stop jp.konami.pesam")
            time.sleep(1)
            _move_file(file_path, DONE_CODE_DIR, original_name)
            release_file(original_name)
            _gui_queue.put(('stat', ('done-code', 1)))
            _gui_queue.put(('status', (serial, 'idle')))
            return

        # 3. sentcode3
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 3: sentcode3"))
        _click_img("sentcode3.bmp", "sentcode3", timeout=30)

        # 4. sentcode4 → type code
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 4: sentcode4 → type code"))
        found4 = _click_img("sentcode4.bmp", "sentcode4", timeout=30)
        if found4:
            time.sleep(0.5)
            device.shell(f"input text '{code}'")
            _gui_queue.put(('log', f"[{serial}]   Code typed: {code}"))
            time.sleep(0.5)

        # 5. sentcode5
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 5: sentcode5"))
        _click_img("sentcode5.bmp", "sentcode5", timeout=30)

        # รอผล — เช็ค fixsendcode ตลอด 3 วินาที
        deadline_wait = time.time() + 3
        while time.time() < deadline_wait:
            _get_img()
            time.sleep(0.5)

        # 6. Check result
        _gui_queue.put(('log', f"[{serial}] [SendCode] Step 6: checking result..."))
        img = _get_img()
        dest_dir  = None
        dest_stat = None

        if img is not None:
            if img_search(img, _sc("invitation-code.bmp")):
                dest_dir  = SUBMIT_CODE_DIR
                dest_stat = "submit-code"
                _gui_queue.put(('log', f"[{serial}] ✓ invitation-code → submit-code: {original_name}"))
            elif img_search(img, os.path.join(IMG_DIR, "okcode.bmp")):
                dest_dir  = DONE_CODE_DIR
                dest_stat = "done-code"
                _gui_queue.put(('log', f"[{serial}] ✓ okcode → done-code: {original_name}"))

        if dest_dir is None:
            dest_dir  = DONE_CODE_DIR
            dest_stat = "done-code"
            _gui_queue.put(('log', f"[{serial}] no result img → done-code: {original_name}"))

        device.shell("am force-stop jp.konami.pesam")
        time.sleep(1)
        _move_file(file_path, dest_dir, original_name)
        release_file(original_name)
        _gui_queue.put(('stat', (dest_stat, 1)))
        _gui_queue.put(('status', (serial, 'idle')))

    except BotStoppedException:
        release_file(original_name)
        raise
    except FixSendCodeException:
        _gui_queue.put(('log', f"[{serial}] ⚠ fixsendcode → clear app → submit-code: {original_name}"))
        device.shell("am force-stop jp.konami.pesam")
        time.sleep(1)
        _move_file(file_path, SUBMIT_CODE_DIR, original_name)
        release_file(original_name)
        _gui_queue.put(('stat', ('submit-code', 1)))
        _gui_queue.put(('status', (serial, 'idle')))


def _device_worker(serial, get_code_fn):
    global bot_running
    while bot_running:
        try:
            device = AdbClient(host="127.0.0.1", port=5037).device(serial)
            if device is None:
                _gui_queue.put(('log', f"[{serial}] device lost — retrying..."))
                time.sleep(5)
                continue

            result = play_start_to_checkpoint(device, serial)
            if result is None:
                time.sleep(3)
                continue

            file_path, original_name, cycle_start = result
            code = get_code_fn()
            sendcode_sequence(device, serial, cycle_start, original_name, file_path, code)

        except BotStoppedException:
            DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
            _gui_queue.put(('log', f"[{serial}] Bot stopped — exiting thread"))
            _gui_queue.put(('status', (serial, 'idle')))
            break
        except Exception as e:
            # release ไฟล์ที่อาจค้าง lock อยู่จาก cycle นี้
            held = DEVICE_FILE_ASSIGNMENTS.get(serial)
            if held:
                try:
                    release_file(held)
                except Exception:
                    pass
                DEVICE_FILE_ASSIGNMENTS.pop(serial, None)
            _gui_queue.put(('log', f"[{serial}] ERROR: {e}"))
            _gui_queue.put(('status', (serial, 'stuck')))
            time.sleep(3)


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

class DeviceRow(ctk.CTkFrame):
    _STATUS_COLOR = {
        'working': "#4caf50",
        'idle':    "#888888",
        'stuck':   "#e53935",
        'waiting': "#ff9800",
    }

    def __init__(self, parent, serial, idx):
        super().__init__(parent, fg_color="#2e2e2e", corner_radius=6, height=32)
        self.pack_propagate(False)
        self.serial = serial

        ctk.CTkLabel(self, text=f"  {idx}.", width=24,
                     font=ctk.CTkFont(size=11), text_color="#888").pack(side="left")
        ctk.CTkLabel(self, text=serial,
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#dddddd", anchor="w").pack(side="left", fill="x", expand=True)
        self.lbl_status = ctk.CTkLabel(self, text="IDLE  ",
                                       font=ctk.CTkFont(size=10, weight="bold"),
                                       text_color="#888")
        self.lbl_status.pack(side="right", padx=6)

    def set_status(self, status: str):
        color = self._STATUS_COLOR.get(status.lower(), "#888")
        self.lbl_status.configure(text=status.upper() + "  ", text_color=color)


class PlaycodeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        global gui_instance
        gui_instance = self

        self.title("📨 SendCode — PES")
        self.geometry("820x580")
        self.minsize(820, 580)

        self._device_rows  = {}
        self._stat_counts  = {}
        self._stat_labels  = {}
        self._threads      = []
        self._adb_ready    = False

        self._build_ui()
        self.after(400,  self._connect_adb)
        self.after(100,  self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(self, height=44, fg_color="#1e1e1e", corner_radius=0)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        ctk.CTkLabel(tb, text="  📨 SENDCODE BOT",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f2c94c").pack(side="left", padx=4)

        self.lbl_adb = ctk.CTkLabel(tb, text="  ● OFFLINE",
                                    font=ctk.CTkFont(size=11, weight="bold"),
                                    text_color="#888")
        self.lbl_adb.pack(side="left", padx=8)

        self.btn_start = ctk.CTkButton(
            tb, text="▶  START", width=90, height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2cc985", hover_color="#229f69",
            command=self._toggle_bot)
        self.btn_start.pack(side="left", padx=10)

        self.btn_scan = ctk.CTkButton(
            tb, text="🔍 Scan ADB", width=90, height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#444", hover_color="#555",
            command=self._scan_adb)
        self.btn_scan.pack(side="left", padx=4)

        # file counter
        self.lbl_files = ctk.CTkLabel(tb, text="📁 0",
                                      font=ctk.CTkFont(size=11, weight="bold"),
                                      text_color="#aaa")
        self.lbl_files.pack(side="right", padx=12)

        # ── Body ─────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Left — devices
        left = ctk.CTkFrame(body, fg_color="#252525", corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 3))

        lhdr = ctk.CTkFrame(left, fg_color="#333", corner_radius=0, height=26)
        lhdr.pack(fill="x")
        ctk.CTkLabel(lhdr, text="  DEVICES",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#ccc", anchor="w").pack(side="left")

        self.dev_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.dev_scroll.pack(fill="both", expand=True, padx=3, pady=3)

        # Right — config + stats
        right = ctk.CTkFrame(body, fg_color="#252525", corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        rhdr = ctk.CTkFrame(right, fg_color="#333", corner_radius=0, height=26)
        rhdr.pack(fill="x")
        ctk.CTkLabel(rhdr, text="  ⚙  CONFIG & STATS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#ccc", anchor="w").pack(side="left")

        cfg_body = ctk.CTkFrame(right, fg_color="transparent")
        cfg_body.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(cfg_body, text="Invite Code",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#aaa", anchor="w").pack(fill="x")

        code_row = ctk.CTkFrame(cfg_body, fg_color="transparent")
        code_row.pack(fill="x", pady=(2, 6))

        self.entry_code = ctk.CTkEntry(
            code_row,
            placeholder_text="M-CBFTKHBALEF",
            font=ctk.CTkFont(family="Consolas", size=13),
            height=32, fg_color="#1a1a1a", border_color="#555",
            text_color="#f2c94c")
        self.entry_code.insert(0, _CFG_SEND_CODE)
        self.entry_code.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            code_row, text="💾", width=32, height=32,
            fg_color="#333", hover_color="#444",
            command=self._save_code).pack(side="left")

        # separator
        ctk.CTkFrame(cfg_body, fg_color="#444", height=1).pack(fill="x", pady=6)

        # Stats
        ctk.CTkLabel(cfg_body, text="Results",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#aaa", anchor="w").pack(fill="x")

        self.stats_frame = ctk.CTkScrollableFrame(right, fg_color="transparent", height=160)
        self.stats_frame.pack(fill="both", expand=True, padx=6, pady=4)
        self._add_stat_row("done-code",    "#2196f3", "id ที่กรอกโค้ดแล้ว เก็บไว้ที่นี่")
        self._add_stat_row("submit-code", "#ff9800", "โค้ดผิด / Clear ไม่ครบ / บัค")

        # ── Log ──────────────────────────────────────────────────────────────
        log_wrap = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=6, height=130)
        log_wrap.pack(fill="x", padx=6, pady=4)
        log_wrap.pack_propagate(False)

        log_hdr = ctk.CTkFrame(log_wrap, fg_color="#2a2a2a", corner_radius=0, height=20)
        log_hdr.pack(fill="x")
        ctk.CTkLabel(log_hdr, text="  LOG",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color="#777", anchor="w").pack(side="left")

        self.log_box = ctk.CTkTextbox(
            log_wrap,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#8b949e", fg_color="#1a1a1a",
            state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=2, pady=2)

    def _add_stat_row(self, name, color, desc=""):
        h = 54 if desc else 36
        row = ctk.CTkFrame(self.stats_frame, fg_color="#2a2a2a", corner_radius=6, height=h)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)
        top = ctk.CTkFrame(row, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(6 if desc else 8, 0))
        ctk.CTkLabel(top, text=name,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ccc", anchor="w").pack(side="left", fill="x", expand=True)
        lbl = ctk.CTkLabel(top, text="0",
                           font=ctk.CTkFont(size=15, weight="bold"),
                           text_color=color)
        lbl.pack(side="right")
        if desc:
            ctk.CTkLabel(row, text=f"  {desc}",
                         font=ctk.CTkFont(size=11),
                         text_color="#777", anchor="w").pack(fill="x", padx=10)
        self._stat_labels[name] = lbl
        self._stat_counts[name] = 0

    # ── ADB ───────────────────────────────────────────────────────────────────
    def _connect_adb(self):
        self._log("Searching for ADB...")
        def _t():
            if find_adb_executable():
                from login import adb_path
                subprocess.run([adb_path, "start-server"],
                               capture_output=True, timeout=10,
                               shell=(os.name == "nt"))
                client  = AdbClient(host="127.0.0.1", port=5037)
                serials = [d.serial for d in client.devices()]
                _gui_queue.put(('adb_ready', serials))
            else:
                _gui_queue.put(('log', "ADB not found! ตรวจสอบโฟลเดอร์ adb/"))
        threading.Thread(target=_t, daemon=True).start()

    def _scan_adb(self):
        self._log("Scanning ADB devices...")
        def _t():
            try:
                client  = AdbClient(host="127.0.0.1", port=5037)
                serials = [d.serial for d in client.devices()]
                _gui_queue.put(('adb_ready', serials))
            except Exception as e:
                _gui_queue.put(('log', f"Scan error: {e}"))
        threading.Thread(target=_t, daemon=True).start()

    def _on_adb_ready(self, serials):
        self._adb_ready = True
        # เก็บเฉพาะ emulator-XXXX format — ตัด 127.0.0.1:PORT ออก
        serials = [s for s in serials if s.startswith("emulator-")]
        for i, s in enumerate(serials):
            if s not in self._device_rows:
                row = DeviceRow(self.dev_scroll, s, len(self._device_rows) + 1)
                row.pack(fill="x", pady=1)
                self._device_rows[s] = row
        self.lbl_adb.configure(
            text=f"  ● ONLINE ({len(self._device_rows)})",
            text_color="#4caf50")
        self._update_file_count()
        self._log(f"ADB ready — {len(self._device_rows)} device(s)")

    # ── Bot control ───────────────────────────────────────────────────────────
    def _toggle_bot(self):
        global bot_running
        if not bot_running:
            self._start_bot()
        else:
            self._stop_bot()

    def _start_bot(self):
        global bot_running
        if not self._device_rows:
            self._log("ไม่มี device — กด Scan ADB ก่อน")
            return
        bot_running = True
        self._done_limit_fired = False
        self._threads = []  # clear รายการ thread เก่า
        # reset counters
        for name in list(self._stat_counts.keys()):
            self._stat_counts[name] = 0
            lbl = self._stat_labels.get(name)
            if lbl:
                lbl.configure(text="0")
        self.btn_start.configure(text="■  STOP", fg_color="#e53935", hover_color="#c62828")
        self._log("=== BOT STARTED ===")
        code_fn = self.entry_code.get
        for serial in list(self._device_rows.keys()):
            t = threading.Thread(target=_device_worker, args=(serial, code_fn), daemon=True)
            t.start()
            self._threads.append(t)

    def _stop_bot(self):
        global bot_running
        bot_running = False
        self.btn_start.configure(text="▶  START", fg_color="#2cc985", hover_color="#229f69")
        self._log("=== BOT STOPPED ===")

    # ── Queue poller ──────────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                kind, payload = _gui_queue.get_nowait()
                if kind == 'log':
                    self._log(payload)
                elif kind == 'adb_ready':
                    self._on_adb_ready(payload)
                elif kind == 'status':
                    serial, status = payload
                    if serial in self._device_rows:
                        self._device_rows[serial].set_status(status)
                elif kind == 'stat':
                    name, delta = payload
                    self._inc_stat(name, delta)
        except _queue_mod.Empty:
            pass
        self.after(80, self._poll_queue)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            pass

    def _inc_stat(self, name, delta):
        if name not in self._stat_counts:
            self._add_stat_row(name, "#aaaaaa")
        self._stat_counts[name] = self._stat_counts.get(name, 0) + delta
        lbl = self._stat_labels.get(name)
        if lbl:
            lbl.configure(text=str(self._stat_counts[name]))
        if name == "done-code" and self._stat_counts[name] >= 5:
            if not getattr(self, '_done_limit_fired', False):
                self._done_limit_fired = True
                global bot_running
                bot_running = False  # หยุด global ทันที
                self.after(50, self._on_done_limit)

    def _on_done_limit(self):
        self._stop_bot()  # sync UI button เสมอ (safe ถ้า already stopped)
        self._log("=== done-code ครบ 5 — หยุดการทำงาน ===")

        popup = ctk.CTkToplevel(self)
        popup.title("จบการทำงาน")
        popup.geometry("340x140")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.grab_set()
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width()  - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 140) // 2
        popup.geometry(f"340x140+{x}+{y}")

        ctk.CTkLabel(popup, text="✅  จบการทำงานแล้ว",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#4caf50").pack(pady=(20, 6))
        ctk.CTkLabel(popup, text="กรุณากรอก Code ใหม่แล้วกด START อีกรอบ",
                     font=ctk.CTkFont(size=12),
                     text_color="#aaaaaa").pack()
        ctk.CTkButton(popup, text="  OK  ", width=90, height=30,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color="#2cc985", hover_color="#229f69",
                      command=popup.destroy).pack(pady=14)

    def _update_file_count(self):
        try:
            n = len([f for f in os.listdir("input-id") if f.endswith(".dat")])
            self.lbl_files.configure(text=f"📁 {n}")
        except Exception:
            pass

    def _save_code(self):
        code = self.entry_code.get().strip()
        if not code:
            return
        try:
            import re
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
            with open(cfg_path, "r", encoding="utf-8") as f:
                content = f.read()
            if re.search(r'^SEND_CODE\s*=', content, re.MULTILINE):
                content = re.sub(r'^SEND_CODE\s*=\s*["\'].*["\']',
                                 f'SEND_CODE = "{code}"', content, flags=re.MULTILINE)
            else:
                content += f'\nSEND_CODE = "{code}"\n'
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._log(f"Code saved to config: {code}")
        except Exception as e:
            self._log(f"Save error: {e}")

    def _on_close(self):
        global bot_running
        bot_running = False
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = PlaycodeApp()
    app.mainloop()

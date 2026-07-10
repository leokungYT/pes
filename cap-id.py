# ═══════════════════════════════════════════════════════════════════════════
#  cap-id.py  —  ดึงการทำงานจาก login.py (ส่งไฟล์ → play → checkpointlogin)
#                แล้วต่อด้วย: กด Back รัวๆ → ทำลำดับ img/fin-cap (fin-cap1..9)
#                → แคปทั้งหน้าจอเป็น <user_code>.png + ดึงไฟล์ .dat ชื่อเดียวกัน
#                → clear app แล้วเริ่มรอบใหม่
#
#  *ใช้ helper เดิมทั้งหมดจาก login.py (import เข้ามาใช้ซ้ำ ไม่ก๊อปโค้ด)
#   - import login ทำให้ cwd ถูกย้ายไปโฟลเดอร์ pes ให้อัตโนมัติ (relative path ถูกต้อง)
# ═══════════════════════════════════════════════════════════════════════════
import os
import sys
import time
import json
import shutil
import random
import threading
import subprocess

# บังคับ stdout/stderr เป็น line-buffered — กัน Windows console + colorama บัฟเฟอร์ output
# จน log ไม่โผล่ระหว่างรัน (ทำให้ดูเหมือนโปรแกรมค้าง/ไม่ทำงานทั้งที่จริงๆ รันอยู่)
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# ── ใช้ helper เดิมจาก login.py (import ครั้งเดียวได้ของครบ) ──────────────────
import login
from login import (
    find_adb_executable, connect_known_ports, get_connected_devices,
    is_device_online, try_reconnect_device,
    pick_next_file, release_file,
    push_dat_to_device, launch_game, get_screen_capture, img_search,
    gui_log, check_device_reset, _disable_console_quickedit, click_cancel_until_gone,
    IMG_DIR, INPUT_DIR,
    REMOTE_AUTH_DIR, REMOTE_DAT_FILE,
    DEVICE_FILE_ASSIGNMENTS, DEVICE_REENTER_FILE, DEVICE_DISABLE_FIXEVENT,
    DeviceResetException, DeviceTimeoutException,
    FixClearReenterException, SellScreenException,
)
from ppadb.client import Client as AdbClient
import cv2

# ── GUI (customtkinter) ───────────────────────────────────────────────────────
try:
    import customtkinter as ctk
    GUI_ENABLED = True
except Exception:
    GUI_ENABLED = False

# ── Config ──────────────────────────────────────────────────────────────────
FIN_CAP_DIR    = os.path.join(IMG_DIR, "fin-cap")  # img/fin-cap (fin-cap1..9.bmp)
FIN_CAP_TH     = 0.95                               # threshold การ match ของ fin-cap ทั้งหมด
VERIFY_IMG     = os.path.join(IMG_DIR, "verify.png")  # ใช้ตัวเดียวกับ login.py (img/verify.png)
VERIFY_TH      = 0.9                                # threshold verify (ตรงกับ login.py)
CAP_RESULT_DIR = "cap-id-result"                   # โฟลเดอร์เก็บผล: <uid>.png + <uid>.dat
PKG            = "jp.konami.pesam"

# CAP_ALL: 1 = เก็บไฟล์+รูปลง cap-id-result ตรงๆ (flat) / 0 = แยกโฟลเดอร์ย่อยตามชื่อ .dat
try:
    from config import CAP_ALL
except Exception:
    CAP_ALL = 0
cap_all_mode = bool(CAP_ALL)   # runtime flag — toggle ได้จาก GUI

bot_running = False


def _gui_event(kind, data):
    """ส่ง event เข้า queue ของ GUI (ถ้าเปิด GUI อยู่) — ใช้แจ้งผลแคป/ผิดพลาด"""
    if login.gui_instance is not None:
        try:
            login._gui_queue.put((kind, data))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════
def _adb_kwargs():
    return {'creationflags': 0x08000000} if os.name == 'nt' else {}


def click_until_gone(device, serial, img_path, label, cycle_start, threshold=0.8, step_timeout=None):
    """รอภาพโผล่ → กดซ้ำๆ ที่ตำแหน่งที่เจอ จนกว่าภาพจะหายไป แล้วค่อยไปต่อ (คืน True)
    (พอร์ตจากตรรกะ click_until_gone ใน login.py — ใช้กับ fin-cap1..6)
    ถ้า step_timeout กำหนดไว้ และยังหาภาพไม่เจอภายในเวลานั้น → คืน False (ให้ caller ทำ rescue)"""
    gui_log(serial, f"Waiting for {label}...", step=label)
    deadline = (time.time() + step_timeout) if step_timeout else None
    while True:
        check_device_reset(serial, cycle_start)
        if deadline is not None and time.time() > deadline:
            gui_log(serial, f"{label} not found within {step_timeout:.0f}s", step=f"{label} Stuck")
            return False
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, img_path, threshold=threshold)
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, f"Clicked {label} at ({x},{y})", step=f"{label} Click")
                time.sleep(1.2)
                # กดซ้ำจนกว่าจะหาย (กันค้างไม่เกิน 8 วิ)
                retry_end = time.time() + 8
                while time.time() < retry_end:
                    check_device_reset(serial, cycle_start)
                    img2 = get_screen_capture(device)
                    if img2 is not None and not img_search(img2, img_path, threshold=threshold):
                        gui_log(serial, f"{label} gone", step=f"{label} Done")
                        return True
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    gui_log(serial, f"Re-clicked {label}", step=f"{label} Retry")
                    time.sleep(1.0)
                return True
        time.sleep(0.6)


def wait_and_click(device, serial, img_path, label, cycle_start, appear_timeout=30, threshold=0.8):
    """รอภาพโผล่ (ภายใน appear_timeout วิ) → กด 1 ครั้ง. คืน True ถ้ากดสำเร็จ
    ใช้กับ fin-cap7 / fin-cap8 (fin-cap8 ให้เวลา 30 วิ)"""
    gui_log(serial, f"Waiting {label} (timeout {appear_timeout}s)...", step=label)
    deadline = time.time() + appear_timeout
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, img_path, threshold=threshold)
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, f"Clicked {label} at ({x},{y})", step=f"{label} Click")
                time.sleep(1.5)
                return True
        time.sleep(0.6)
    gui_log(serial, f"{label} timeout ({appear_timeout}s) — skip", step=f"{label} Timeout")
    return False


def wait_for_appear(device, serial, img_path, label, cycle_start, appear_timeout=60, threshold=0.8):
    """รอภาพโผล่อย่างเดียว (ไม่กด) — ใช้เป็นจุดสังเกตว่ามาถึง fin-cap9 แล้ว"""
    gui_log(serial, f"Waiting {label} (timeout {appear_timeout}s)...", step=label)
    deadline = time.time() + appear_timeout
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None and img_search(img, img_path, threshold=threshold):
            gui_log(serial, f"{label} detected!", step=f"{label} Found")
            return True
        time.sleep(0.6)
    gui_log(serial, f"{label} not found within {appear_timeout}s — capturing anyway", step=f"{label} Timeout")
    return False


def spam_back_until(device, serial, target_img, label, cycle_start, timeout=90, threshold=0.8):
    """กด Back (KEYCODE_4) รัวๆ:
       - เจอ cancel.bmp → กดจนหาย (click_cancel_until_gone) แล้วหยุด (วิธีเดียวกับ login.py)
       - หรือเจอ target_img (เช่น fin-cap1) ก่อน → หยุดเลย
       จากนั้นไปทำงาน fin-cap ต่อ (กันค้างด้วย timeout)"""
    cancel_path = os.path.join(IMG_DIR, "cancel.bmp")
    gui_log(serial, f"Spamming Back until cancel/{label}...", step="Back loop")
    deadline = time.time() + timeout
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        device.shell("input keyevent 4")   # KEYCODE_BACK
        time.sleep(0.4)
        img = get_screen_capture(device)
        if img is None:
            continue
        # เจอ cancel → กดที่ cancel จนหายแล้วหยุด back
        pts_c = img_search(img, cancel_path)
        if pts_c:
            x, y = pts_c[0]
            gui_log(serial, f"cancel found — clicking ({x},{y}) until gone", step="Click Cancel")
            click_cancel_until_gone(device, serial, x, y, step="Cancel")
            return True
        # เจอ target (fin-cap1) ก่อน → หยุด back ไปทำ fin-cap เลย
        if img_search(img, target_img, threshold=threshold):
            gui_log(serial, f"{label} appeared — stop Back spam", step="Back Done")
            return True
    gui_log(serial, f"Back spam timeout ({timeout}s) — continue", step="Back Timeout")
    return False


def tap_until_verify(device, serial, x, y, need_count, cycle_start,
                     verify_img=VERIFY_IMG, threshold=VERIFY_TH, search_secs=5.0, timeout=60):
    """กดตำแหน่ง (x,y) แล้วค้นหา verify ภายใน search_secs วิ — ถ้านับได้ >= need_count ถือว่าผ่าน
    ถ้าไม่ครบใน 5 วิ ค่อย "กดตำแหน่งเดิมซ้ำ" แล้วลองใหม่
    (วิธีเดียวกับ login.py: กด 1 ที → สังเกต 5 วิ → ถ้าไม่ครบค่อยกดใหม่ กัน toggle ปิดเอง)"""
    overall_deadline = time.time() + timeout
    while time.time() < overall_deadline:
        check_device_reset(serial, cycle_start)
        gui_log(serial, f"Clicking position ({x},{y}) — need {need_count} verify...", step=f"verify{need_count}")
        device.shell(f"input swipe {x} {y} {x} {y} 100")
        # ค้นหา verify ให้ครบ need_count ภายใน search_secs
        deadline = time.time() + search_secs
        while time.time() < deadline:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                pts_v = img_search(img, verify_img, threshold=threshold)
                if len(pts_v) >= need_count:
                    gui_log(serial, f"Detected {len(pts_v)} verify (>= {need_count})! Verified.", step=f"verify{need_count} OK")
                    return True
            time.sleep(0.5)
        gui_log(serial, f"Failed to find {need_count} verify in {search_secs:.0f}s! Retrying tap...", step=f"verify{need_count} Retry")
    gui_log(serial, f"verify{need_count} timeout ({timeout}s) — continue", step=f"verify{need_count} Timeout")
    return False


def extract_user_code(dat_path):
    """อ่าน user_code จากไฟล์ .dat (JSON) เช่น "user_code":"ASCV592793838"
    ถ้าพังให้ fallback เป็นชื่อไฟล์ (ตัดนามสกุล)"""
    try:
        with open(dat_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            data = json.loads(content[s:e + 1])
            uc = data.get("user_code")
            if uc:
                return str(uc).strip()
    except Exception:
        pass
    return os.path.splitext(os.path.basename(dat_path))[0]


def capture_fullscreen_png(device, out_path):
    """แคปทั้งหน้าจอเป็นไฟล์ PNG สี (ใช้ adb exec-out screencap -p, fallback device.screencap())"""
    serial = device.serial
    # หลัก: adb exec-out screencap -p → binary PNG ตรงๆ (กันปัญหา \r\n)
    try:
        with open(out_path, "wb") as f:
            subprocess.run([login.adb_path, "-s", serial, "exec-out", "screencap", "-p"],
                           stdout=f, stderr=subprocess.PIPE, timeout=25, **_adb_kwargs())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True
    except Exception as ex:
        gui_log(serial, f"exec-out capture failed: {ex}", step="Cap Retry")
    # fallback: ppadb device.screencap() (คืน PNG bytes)
    try:
        raw = device.screencap()
        if raw:
            with open(out_path, "wb") as f:
                f.write(raw)
            if os.path.getsize(out_path) > 0:
                return True
    except Exception:
        pass
    return False


def pull_dat_from_device(device, out_path):
    """ดึงไฟล์ online_user_id_data.dat จากเครื่องมาเก็บเป็น out_path
    (พอร์ตจาก backup_uid_file ใน main-pes.py)"""
    serial = device.serial
    search_cmd = f"su -c 'find /data/data/{PKG}/ -name \"*online_user_id_data.dat*\"'"
    try:
        found = device.shell(search_cmd).strip()
    except Exception:
        found = ""
    if not found or "No such file" in found:
        return False
    actual = found.split("\n")[0].strip()
    try:
        with open(out_path, "wb") as f:
            subprocess.run([login.adb_path, "-s", serial, "shell", f"su -c 'cat {actual}'"],
                           stdout=f, stderr=subprocess.PIPE, timeout=25, **_adb_kwargs())
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return True
    except Exception:
        pass
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except Exception:
            pass
    return False


# ═══════════════════════════════════════════════════════════════════════════
# ขั้นตอนที่ "ดึงมาจาก login.py" (ส่งไฟล์ → launch → play8 → checkpointlogin)
# ═══════════════════════════════════════════════════════════════════════════
def launch_with_black_check(device, serial, cycle_start):
    """Launch เกม + เช็คจอดำ 45 วิ (พอร์ตจาก login.py) — จอดำ >85% = restart (สูงสุด 3 ครั้ง)"""
    gui_log(serial, "Launching PES...", step="Launch", status="working")
    for attempt in range(3):
        launch_game(device, settle=0)
        black_start = time.time()
        is_stuck = False
        while time.time() - black_start < 45:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                try:
                    gray = img if len(img.shape) == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
                    black_ratio = cv2.countNonZero(thresh) / (gray.shape[0] * gray.shape[1])
                    if black_ratio < 0.85:
                        gui_log(serial, "Screen OK! (app loaded)", step="Launch OK")
                        is_stuck = False
                        break
                    is_stuck = True
                except Exception:
                    is_stuck = True
            else:
                is_stuck = True
            time.sleep(1)
        if is_stuck:
            gui_log(serial, f"[BLACK] Dark screen (attempt {attempt + 1}/3) — restarting app...", step="Black Stuck")
            device.shell(f"am force-stop {PKG}")
            time.sleep(5)
        else:
            break
    time.sleep(8)


def wait_play8(device, serial, cycle_start):
    """รอ play8 หรือ play8fix → กดซ้ำจนหาย (พอร์ตจาก login.py)"""
    gui_log(serial, "Waiting play8 or play8fix...", step="play8")
    play8_clicked = False
    absent_count = 0
    loop_count = 0
    while True:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            # ถ้าเจอ checkpointlogin.bmp ถือว่าผ่านมาได้แล้ว ให้หลุดลูปได้เลย
            if img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp")):
                gui_log(serial, "checkpointlogin detected during play8 loop, breaking...", step="play8")
                break

            pts = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
            matched = "play8"
            if not pts:
                pts = img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))
                matched = "play8fix"
            if pts:
                absent_count = 0
                # มี fixlg3 ให้กดก่อน
                pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                if pts_lg3:
                    x, y = pts_lg3[0]
                    gui_log(serial, f"{matched} & fixlg3 found! Clicking fixlg3 first", step="play8")
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(1.0)
                    continue
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, f"Found {matched}! Clicked.", step="play8")
                play8_clicked = True
                time.sleep(0.5)
                continue
            else:
                if play8_clicked:
                    absent_count += 1
                    if absent_count >= 10:  # ต้องไม่พบติดต่อกัน 10 ครั้ง ถึงจะถือว่าหายจริง
                        break
                else:
                    loop_count += 1
                    if loop_count >= 30:  # ~10 วินาที (30 * 0.3s)
                        gui_log(serial, "play8 not matched yet, attempting fallback center click...", step="play8")
                        device.shell("input swipe 480 270 480 270 100")
                        loop_count = 0
        time.sleep(0.3)


def wait_checkpointlogin(device, serial, cycle_start):
    """รอ checkpointlogin → กด แล้วไปต่อ (พอร์ตจาก login.py สาขา non-fast)"""
    gui_log(serial, "Waiting checkpointlogin...", step="Checkpoint")
    while True:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, "checkpointlogin found & clicked!", step="Login OK", status="working")
                time.sleep(4)
                return
        time.sleep(1.5)


# ═══════════════════════════════════════════════════════════════════════════
# Worker หลัก
# ═══════════════════════════════════════════════════════════════════════════
def process_device_capid(device):
    serial = device.serial
    gui_log(serial, "cap-id bot started", step="Init", status="working")

    while bot_running:
        time.sleep(random.uniform(0.5, 2.0))   # jitter กัน ADB ค้าง
        file_path = None
        original_name = None
        try:
            check_device_reset(serial)

            # ── เช็ค device online ก่อนเริ่ม cycle ──
            if not is_device_online(device):
                gui_log(serial, "Device OFFLINE — reconnecting...", step="Offline", status="stuck")
                try_reconnect_device(serial)
                time.sleep(10)
                continue

            gui_log(serial, "--- Starting New Cycle ---", step="New Cycle", status="working")
            DEVICE_DISABLE_FIXEVENT[serial] = False   # เฟส launch/play/checkpointlogin: เปิด fixevent ตามปกติ

            # 0. Force-stop + ลบ save data เดิม
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            device.shell(f"su -c 'rm -f {REMOTE_DAT_FILE}'")
            time.sleep(0.3)

            # 1. หยิบไฟล์ (รองรับ re-enter จาก fixclear)
            pending = DEVICE_REENTER_FILE.pop(serial, None)
            if pending:
                file_path, original_name = pending
                gui_log(serial, f"Re-entering same file: {original_name}", step="Re-enter")
            else:
                file_path, original_name = pick_next_file()
                if file_path is None:
                    gui_log(serial, "No files left — waiting...", step="No Files", status="idle")
                    time.sleep(3)
                    continue

            gui_log(serial, f"File: {original_name}", step="File OK", status="working")
            DEVICE_FILE_ASSIGNMENTS[serial] = original_name
            cycle_start = time.time()

            # 2. ส่งไฟล์ (push .dat)
            gui_log(serial, "Pushing file...", step="Push")
            if not push_dat_to_device(device, file_path):
                gui_log(serial, "Push FAILED!", step="Error", status="stuck")
                release_file(original_name)
                time.sleep(5)
                continue

            # 3. Launch + Black-screen check
            launch_with_black_check(device, serial, cycle_start)

            # 4. play8 / play8fix
            wait_play8(device, serial, cycle_start)

            # 5. checkpointlogin (จุดสิ้นสุดของส่วนที่ดึงมาจาก login.py)
            wait_checkpointlogin(device, serial, cycle_start)

            # *** ปิดการเช็ค fixevent.bmp ตั้งแต่เข้าเฟส fin-cap ***
            #     (ไม่งั้น get_screen_capture จะกด fixevent แล้วปิดเมนูที่เรากำลังทำ fin-cap อยู่)
            DEVICE_DISABLE_FIXEVENT[serial] = True

            # 6. *** ระบบกด Back รัวๆ *** หลังเจอ checkpointlogin
            #    → เจอ cancel กดจนหายแล้วหยุด (หรือเจอ fin-cap1 ก่อนก็หยุด) → ไปทำ fin-cap
            fin_cap1 = os.path.join(FIN_CAP_DIR, "fin-cap1.bmp")
            spam_back_until(device, serial, fin_cap1, "fin-cap1", cycle_start, timeout=90, threshold=FIN_CAP_TH)

            # 7. ลำดับ img/fin-cap
            #    fin-cap1 / fin-cap2 ถ้าไปต่อไม่ได้ครบ 15 วิ → กด Back รัวๆ (จนเจอ cancel)
            #    แล้วเริ่ม fin-cap1 ใหม่อีกรอบ (rescue เหมือน fin1 ใน login.py)
            fin_cap2 = os.path.join(FIN_CAP_DIR, "fin-cap2.bmp")
            rescue_rounds = 0
            MAX_RESCUE = 15
            while True:
                if not click_until_gone(device, serial, fin_cap1, "fin-cap1",
                                        cycle_start, threshold=FIN_CAP_TH, step_timeout=15):
                    rescue_rounds += 1
                    gui_log(serial, f"fin-cap1 stuck 15s — Back rescue & restart (round {rescue_rounds})", step="fin-cap1 Rescue")
                    spam_back_until(device, serial, fin_cap1, "fin-cap1", cycle_start, timeout=90, threshold=FIN_CAP_TH)
                    if rescue_rounds >= MAX_RESCUE:
                        gui_log(serial, "Too many rescues — proceeding best-effort", step="Rescue Giveup")
                        break
                    continue
                if not click_until_gone(device, serial, fin_cap2, "fin-cap2",
                                        cycle_start, threshold=FIN_CAP_TH, step_timeout=15):
                    rescue_rounds += 1
                    gui_log(serial, f"fin-cap2 stuck 15s — Back rescue & restart fin-cap1 (round {rescue_rounds})", step="fin-cap2 Rescue")
                    spam_back_until(device, serial, fin_cap1, "fin-cap1", cycle_start, timeout=90, threshold=FIN_CAP_TH)
                    if rescue_rounds >= MAX_RESCUE:
                        gui_log(serial, "Too many rescues — proceeding best-effort", step="Rescue Giveup")
                        break
                    continue
                break   # ผ่าน fin-cap1 + fin-cap2 แล้ว

            #    fin-cap3..5 → กดซ้ำๆจนหาย (รอปกติ ไม่มี timeout)
            for i in range(3, 6):
                click_until_gone(device, serial,
                                 os.path.join(FIN_CAP_DIR, f"fin-cap{i}.bmp"),
                                 f"fin-cap{i}", cycle_start, threshold=FIN_CAP_TH)
            #    fin-cap6 → เช็คเฉยๆ (ไม่กด) ยืนยันว่ามาถึงหน้านี้
            wait_for_appear(device, serial,
                            os.path.join(FIN_CAP_DIR, "fin-cap6.bmp"),
                            "fin-cap6", cycle_start, appear_timeout=30, threshold=FIN_CAP_TH)

            #    กด 5 ตำแหน่ง ทีละจุด — กดจนกว่าจะนับ verify ได้ครบจำนวนของจุดนั้น (วิธีเดียวกับ login.py)
            #    pos1→1 อัน, pos2→2 อัน, ... pos5→5 อัน (ครบ 5 แล้วไป fin-cap7)
            verify_points = [
                (239, 105, 1),
                (233, 168, 2),
                (235, 228, 3),
                (234, 290, 4),
                (235, 354, 5),
            ]
            for vx, vy, need in verify_points:
                tap_until_verify(device, serial, vx, vy, need, cycle_start)

            #    fin-cap7 → กด 1 ครั้ง
            wait_and_click(device, serial,
                           os.path.join(FIN_CAP_DIR, "fin-cap7.bmp"),
                           "fin-cap7", cycle_start, appear_timeout=30, threshold=FIN_CAP_TH)
            #    fin-cap8 → timeout 30s
            wait_and_click(device, serial,
                           os.path.join(FIN_CAP_DIR, "fin-cap8.bmp"),
                           "fin-cap8", cycle_start, appear_timeout=30, threshold=FIN_CAP_TH)
            #    fin-cap9 → กดก่อน แล้วค่อยแคปหน้าจอ
            wait_and_click(device, serial,
                           os.path.join(FIN_CAP_DIR, "fin-cap9.bmp"),
                           "fin-cap9", cycle_start, appear_timeout=60, threshold=FIN_CAP_TH)
            time.sleep(2)   # รอจอนิ่งหลังกด fin-cap9 ก่อนแคป

            # 8. แคปทั้งหน้าจอ + ตั้งชื่อเป็น <user_code> และดึงไฟล์ .dat ชื่อเดียวกัน
            #    CAP_ALL/cap_all_mode = True  → เก็บลง cap-id-result ตรงๆ (flat)
            #                          = False → แยกโฟลเดอร์ย่อยตามชื่อ .dat เดิม → cap-id-result/<ชื่อ>/
            user_code = extract_user_code(file_path)
            if cap_all_mode:
                out_dir = CAP_RESULT_DIR
                rel = ""
            else:
                folder_name = os.path.splitext(original_name)[0]   # ชื่อไฟล์ .dat เดิม (ตัดนามสกุล)
                out_dir = os.path.join(CAP_RESULT_DIR, folder_name)
                rel = folder_name + "/"
            os.makedirs(out_dir, exist_ok=True)
            png_path = os.path.join(out_dir, f"{user_code}.png")
            dat_out  = os.path.join(out_dir, f"{user_code}.dat")

            cap_ok = capture_fullscreen_png(device, png_path)
            if cap_ok:
                gui_log(serial, f"Saved screenshot: {rel}{user_code}.png", step="Captured", status="working")
            else:
                gui_log(serial, "Screenshot capture FAILED!", step="Cap Fail", status="stuck")

            # ส่งไฟล์ .dat (ชื่อเดิม = user_code) — ดึงจากเครื่อง, ถ้าไม่ได้ใช้ไฟล์ input
            if pull_dat_from_device(device, dat_out):
                gui_log(serial, f"Pulled .dat: {rel}{user_code}.dat", step="DAT OK")
            else:
                try:
                    shutil.copy2(file_path, dat_out)
                    gui_log(serial, f"Copied input .dat: {rel}{user_code}.dat", step="DAT Copy")
                except Exception as e:
                    gui_log(serial, f"DAT save failed: {e}", step="DAT Fail", status="stuck")

            # แจ้งผลไป GUI (นับ ✅/❌)
            _gui_event('capid_done' if cap_ok else 'capid_fail', user_code)

            # 9. Clear app → ลบไฟล์ input ที่ทำเสร็จ → เริ่มรอบใหม่
            #    ลบต้นฉบับใน input-id ก็ต่อเมื่อมีสำเนา .dat อยู่ใน cap-id-result แล้ว (กันข้อมูลหาย)
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            try:
                if os.path.exists(dat_out) and file_path and os.path.exists(file_path):
                    os.remove(file_path)   # ลบไฟล์ต้นฉบับใน input-id (มีสำเนาแล้ว)
                    gui_log(serial, f"Deleted input: {original_name}", step="Deleted")
                elif file_path and os.path.exists(file_path):
                    gui_log(serial, "DAT not saved — keep input (will retry)", step="Keep Input")
            except Exception as e:
                gui_log(serial, f"Delete input failed: {e}", step="Del Fail")
            release_file(original_name)   # ปล่อย lock + เก็บกวาดสำเนาใน run-file
            gui_log(serial, f"Cycle finished for {user_code} — next file", step="Done", status="waiting")
            time.sleep(2)

        except FixClearReenterException:
            # fixclear → เข้าใหม่ไฟล์เดิม: อย่า release (เก็บ lock + ไฟล์ไว้)
            gui_log(serial, "fixclear re-enter — relaunching same file...", step="Re-enter")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
        except (DeviceResetException, DeviceTimeoutException):
            release_file(original_name)
            gui_log(serial, "Reset/Timeout — restarting cycle", step="Reset", status="stuck")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
        except SellScreenException:
            release_file(original_name)
            gui_log(serial, "Sell screen — force closing & ending cycle", step="Sell", status="working")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
        except Exception as e:
            release_file(original_name)
            msg = str(e).lower()
            if any(k in msg for k in ("offline", "timed out", "timeout", "closed", "connection")):
                gui_log(serial, "Device offline/timeout — reconnecting & backing off...", step="Offline", status="stuck")
                try_reconnect_device(serial)
                time.sleep(10)
            else:
                gui_log(serial, f"Error: {e}", status="stuck")
                time.sleep(5)
        finally:
            # ล้าง AUTH ปลายรอบให้เครื่องสะอาด (เหมือน login.py)
            try:
                device.shell(f"su -c 'rm -rf {REMOTE_AUTH_DIR}/*'")
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# GUI (customtkinter) — แบบเดียวกับ login.py แต่เรียบง่าย เข้าใจง่าย
# ═══════════════════════════════════════════════════════════════════════════
if GUI_ENABLED:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class DeviceRow(ctk.CTkFrame):
        """แถวแสดงสถานะ 1 เครื่อง: #ลำดับ | serial | ข้อความล่าสุด | สถานะ"""
        def __init__(self, parent, serial, index):
            super().__init__(parent, fg_color="#383838", corner_radius=6, height=36)
            self.pack_propagate(False)
            ctk.CTkLabel(self, text=f"#{index}", width=34,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ffffff").pack(side="left", padx=(8, 2))
            ctk.CTkLabel(self, text=serial, width=120,
                         font=ctk.CTkFont(family="Consolas", size=11),
                         text_color="#bbbbbb", anchor="w").pack(side="left", padx=(0, 6))
            self.lbl_status = ctk.CTkLabel(self, text="READY", width=82,
                                           font=ctk.CTkFont(size=10, weight="bold"),
                                           text_color="#888")
            self.lbl_status.pack(side="right", padx=8)
            self.lbl_msg = ctk.CTkLabel(self, text="-", anchor="w",
                                        font=ctk.CTkFont(size=11), text_color="#9fb4c7")
            self.lbl_msg.pack(side="left", fill="x", expand=True, padx=6)
            self._last_status = ""

        def update_state(self, log=None, step=None, status=None, **kw):
            txt = log or step
            if txt:
                self.lbl_msg.configure(text=str(txt)[:64])
            if status and status != self._last_status:
                self._last_status = status
                colors = {'working': "#4caf50", 'stuck': "#e53935",
                          'waiting': "#ff9800", 'idle': "#888"}
                self.lbl_status.configure(text=status.upper(),
                                          text_color=colors.get(status.lower(), "#888"))

    class CapIdGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            login.gui_instance = self          # เปิดทาง update_gui → queue
            login._GUI_LOG_INTERVAL = 2         # อัปเดตแถวเครื่องถี่ขึ้น (ทุก 2 วิ)
            self.title("📸 cap-id — Capture ID Bot")
            self.geometry("800x620")
            self.minsize(720, 540)
            self.device_rows = {}
            self.threads = []
            self.captured = 0
            self.failed = 0
            self._log_buffer = []
            self.setup_ui()
            self.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.after(400, self.connect_adb)
            self.after(200, self._process_gui_queue)
            self.after(500, self._periodic_log_flush)

        # ── UI ──
        def setup_ui(self):
            from datetime import datetime

            # Toolbar
            tb = ctk.CTkFrame(self, height=48, fg_color="#2a2d2e", corner_radius=0)
            tb.pack(fill="x"); tb.pack_propagate(False)
            self.lbl_status = ctk.CTkLabel(tb, text="● OFFLINE",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#888")
            self.lbl_status.pack(side="left", padx=12)
            self.btn_start = ctk.CTkButton(tb, text="▶ START", width=100, height=30,
                                           font=ctk.CTkFont(size=13, weight="bold"),
                                           fg_color="#2cc985", hover_color="#229f69",
                                           command=self.toggle_bot)
            self.btn_start.pack(side="left", padx=8)
            self.btn_rescan = ctk.CTkButton(tb, text="🔄 Scan", width=72, height=30,
                                            font=ctk.CTkFont(size=12),
                                            fg_color="#444", hover_color="#555",
                                            command=self.connect_adb)
            self.btn_rescan.pack(side="left", padx=2)

            cf = ctk.CTkFrame(tb, fg_color="transparent"); cf.pack(side="right", padx=12)
            self.lbl_dev = ctk.CTkLabel(cf, text="📱 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#aaaaaa")
            self.lbl_dev.pack(side="left", padx=8)
            self.lbl_captured = ctk.CTkLabel(cf, text="✅ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#4caf50")
            self.lbl_captured.pack(side="left", padx=8)
            self.lbl_failed = ctk.CTkLabel(cf, text="❌ 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ff5555")
            self.lbl_failed.pack(side="left", padx=8)
            ctk.CTkLabel(tb, text=f"⏱ {datetime.now().strftime('%H:%M:%S')}",
                         font=ctk.CTkFont(size=12), text_color="#888").pack(side="right", padx=6)

            # Config bar
            cfg = ctk.CTkFrame(self, height=46, fg_color="#23272a", corner_radius=0)
            cfg.pack(fill="x"); cfg.pack_propagate(False)
            self.sw_all = ctk.CTkSwitch(cfg, text="ALL : รวมไฟล์ + รูป ลง cap-id-result ตรงๆ (ไม่มีโฟลเดอร์ย่อย)",
                                        font=ctk.CTkFont(size=12), command=self._toggle_all)
            self.sw_all.pack(side="left", padx=12, pady=9)
            if cap_all_mode:
                self.sw_all.select()
            ctk.CTkButton(cfg, text="📂 เปิดโฟลเดอร์ผล", width=140, height=28,
                          font=ctk.CTkFont(size=12), fg_color="#3b5bdb", hover_color="#2f48af",
                          command=self._open_result).pack(side="right", padx=12)

            # Devices
            dev_frame = ctk.CTkFrame(self, fg_color="#2b2b2b", corner_radius=8)
            dev_frame.pack(fill="both", expand=True, padx=8, pady=(8, 4))
            hdr = ctk.CTkFrame(dev_frame, fg_color="#383838", corner_radius=0, height=28)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkLabel(hdr, text="   DEVICES", font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#cccccc", anchor="w").pack(side="left")
            self.dev_scroll = ctk.CTkScrollableFrame(dev_frame, fg_color="transparent")
            self.dev_scroll.pack(fill="both", expand=True, padx=4, pady=4)

            # Log
            lf = ctk.CTkFrame(self, fg_color="#1e1e1e", corner_radius=6, height=150)
            lf.pack(fill="x", padx=8, pady=(4, 8)); lf.pack_propagate(False)
            self.log_text = ctk.CTkTextbox(lf, font=ctk.CTkFont(family="Consolas", size=11),
                                           text_color="#8b949e", fg_color="#1e1e1e")
            self.log_text.pack(fill="both", expand=True, padx=2, pady=2)
            self.log_text.configure(state="disabled")
            mode = "ON (flat)" if cap_all_mode else "OFF (subfolder)"
            self.log(f"cap-id GUI พร้อม — ALL mode = {mode} | กด START เพื่อเริ่ม")

        # ── config toggles ──
        def _toggle_all(self):
            global cap_all_mode
            cap_all_mode = bool(self.sw_all.get())
            self.log(f"ALL mode = {'ON → เก็บลง cap-id-result/ ตรงๆ' if cap_all_mode else 'OFF → แยกโฟลเดอร์ย่อยตามชื่อ .dat'}")

        def _open_result(self):
            try:
                os.makedirs(CAP_RESULT_DIR, exist_ok=True)
                os.startfile(os.path.abspath(CAP_RESULT_DIR))
            except Exception as e:
                self.log(f"open folder error: {e}")

        # ── logging ──
        def log(self, msg):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_buffer.append(f"[{ts}] {msg}\n")
            if len(self._log_buffer) > 120:
                self._log_buffer = self._log_buffer[-60:]

        def _periodic_log_flush(self):
            try:
                if self._log_buffer:
                    lines = self._log_buffer[:30]; self._log_buffer = self._log_buffer[30:]
                    self.log_text.configure(state="normal")
                    try:
                        total = int(self.log_text.index("end-1c").split(".")[0])
                        if total > 400:
                            self.log_text.delete("1.0", f"{total-250}.0")
                    except Exception:
                        pass
                    self.log_text.insert("end", "".join(lines))
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
            except Exception:
                pass
            finally:
                self.after(500, self._periodic_log_flush)

        # ── ADB ──
        def connect_adb(self):
            self.log("Searching for ADB & devices...")
            def _t():
                if find_adb_executable():
                    connect_known_ports(quiet=True)
                    devs = get_connected_devices()
                    login._gui_queue.put(('adb_ready', devs))
                else:
                    login._gui_queue.put(('log', '● ADB NOT FOUND'))
            threading.Thread(target=_t, daemon=True).start()

        def _on_adb_ready(self, devices):
            for serial in devices:
                if serial not in self.device_rows:
                    row = DeviceRow(self.dev_scroll, serial, len(self.device_rows) + 1)
                    row.pack(fill="x", pady=2)
                    self.device_rows[serial] = row
            n = len(self.device_rows)
            self.lbl_dev.configure(text=f"📱 {n}")
            if n:
                self.lbl_status.configure(text=f"● ONLINE ({n})", text_color="#4caf50")
            self.log(f"Found {len(devices)} device(s).")

        # ── queue poller ──
        def _process_gui_queue(self):
            try:
                n = 0
                while n < 80:
                    try:
                        kind, data = login._gui_queue.get_nowait()
                    except Exception:
                        break
                    n += 1
                    if kind == 'device_update':
                        serial, kwargs = data
                        row = self.device_rows.get(serial)
                        if row:
                            row.update_state(**kwargs)
                    elif kind == 'log':
                        self.log(data)
                    elif kind == 'adb_ready':
                        self._on_adb_ready(data)
                    elif kind == 'capid_done':
                        self.captured += 1
                        self.lbl_captured.configure(text=f"✅ {self.captured}")
                        self.log(f"✅ Captured: {data}")
                    elif kind == 'capid_fail':
                        self.failed += 1
                        self.lbl_failed.configure(text=f"❌ {self.failed}")
                        self.log(f"❌ Failed: {data}")
            except Exception:
                pass
            finally:
                self.after(200, self._process_gui_queue)

        # ── bot control ──
        def toggle_bot(self):
            global bot_running
            if not bot_running:
                if not self.device_rows:
                    self.log("ยังไม่เจอ device — กำลัง scan ใหม่ แล้วกด START อีกครั้ง")
                    self.connect_adb()
                    return
                bot_running = True
                login.bot_running = True
                self.btn_start.configure(text="⏹ STOP", fg_color="#e53935", hover_color="#c62828")
                self.lbl_status.configure(text=f"● RUNNING ({len(self.device_rows)})", text_color="#4caf50")
                self._start_threads()
            else:
                bot_running = False
                login.bot_running = False
                self.btn_start.configure(text="▶ START", fg_color="#2cc985", hover_color="#229f69")
                self.lbl_status.configure(text="● STOPPED", text_color="#ff9800")
                self.log("STOP — จะหยุดหลังจบรอบปัจจุบันของแต่ละเครื่อง")

        def _start_threads(self):
            devices = list(self.device_rows.keys())
            client = AdbClient(host="127.0.0.1", port=5037)
            self.log(f"Starting {len(devices)} device thread(s)...")

            def launch(i):
                if not bot_running or i >= len(devices):
                    return
                serial = devices[i]
                try:
                    dev = client.device(serial)
                    t = threading.Thread(target=process_device_capid, args=(dev,), daemon=True)
                    t.start()
                    self.threads.append(t)
                    self.log(f"▶ started {serial}")
                except Exception as e:
                    self.log(f"start error {serial}: {e}")
                if i + 1 < len(devices):
                    self.after(8000, lambda: launch(i + 1))   # ทยอยเปิดทีละจอ เว้น 8 วิ

            launch(0)

        def on_closing(self):
            global bot_running
            bot_running = False
            login.bot_running = False
            self.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════
def run_headless():
    """รันแบบไม่มี GUI (ถ้าไม่มี customtkinter) — auto scan + start ทุกเครื่อง"""
    global bot_running
    login.DEBUG_CONSOLE = 1   # โชว์ log ลง console
    if not find_adb_executable():
        print("[ERROR] adb.exe not found.", flush=True)
        return
    print("[*] Scanning ADB devices... (รอสักครู่)", flush=True)
    connect_known_ports()
    devices = get_connected_devices()
    if not devices:
        print("[ERROR] No devices found.", flush=True)
        return
    print(f"[*] Found {len(devices)} device(s): {devices}", flush=True)
    bot_running = True
    login.bot_running = True
    client = AdbClient(host="127.0.0.1", port=5037)
    for i, serial in enumerate(devices):
        device = client.device(serial)
        threading.Thread(target=process_device_capid, args=(device,), daemon=True).start()
        if i < len(devices) - 1:
            print("Waiting 10 seconds before starting the next device...", flush=True)
            time.sleep(10.0)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot_running = False
        login.bot_running = False


def main():
    print("=" * 60, flush=True)
    print(" cap-id.py — capture id bot", flush=True)
    print("=" * 60, flush=True)
    _disable_console_quickedit()
    if GUI_ENABLED:
        CapIdGUI().mainloop()
    else:
        print("[WARN] customtkinter not found — running headless mode.", flush=True)
        run_headless()


if __name__ == "__main__":
    main()

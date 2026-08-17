# ═══════════════════════════════════════════════════════════════════════════
#  checkTH.py — บอทเช็คประเทศของบัญชี (Residence = Thailand หรือไม่)
#
#  ดึงระบบจาก login.py มาใช้ตั้งแต่ต้นจนถึงจุดที่ login เสร็จ (stoplogin)
#  แล้วต่อด้วยลำดับเช็คประเทศ:
#
#      fix-checkth1 (Extras)        → กดซ้ำจนรูปหาย
#      fix-checkth2 (ไอคอนบันทึก)   → กดซ้ำจนรูปหาย
#      fix-checkth3 (User Personal) → กดซ้ำจนรูปหาย
#      check-th (Residence)         → หาไปเรื่อยๆ จนกว่าจะเจอ (ไม่มี timeout)
#      fix-checkth4 (Thailand)      → หาใน 15 วินาที
#          เจอ    → ย้ายไฟล์ .dat ชื่อเดิม เข้าโฟลเดอร์  th-check/
#          ไม่เจอ → ย้ายไฟล์ .dat ชื่อเดิม เข้าโฟลเดอร์  Other countries/
#      แล้วเริ่มไฟล์ถัดไป
#
#  เปิด/ปิดด้วย  CHECK_TH = 1  ใน config.py (ไม่ใส่ = ถือว่าเปิด)
#  รันด้วย:  py checkTH.py
#
#  *** ไฟล์นี้แยกจาก login.py — ไม่แตะ flow เดิม ใช้แค่ helper ร่วมกัน ***
# ═══════════════════════════════════════════════════════════════════════════
import os
import time
import random
import shutil
import threading

import cv2

import login
from login import (
    find_adb_executable, connect_known_ports, get_connected_devices,
    is_device_online, try_reconnect_device, is_root, enable_root,
    pick_next_file, release_file, _safe_copy, export_base_name,
    push_dat_to_device, launch_game, get_screen_capture, fast_screencap,
    img_search, img_search_best, click_img_until_gone,
    run_new_stage_play8, fixout_back_spam_until_cancel, click_cancel_until_gone,
    gui_log, check_device_reset, _disable_console_quickedit,
    EVENT_IMG, ResetGachaException,
    IMG_DIR, INPUT_DIR, REMOTE_DAT_FILE,
    DEVICE_FILE_ASSIGNMENTS, DEVICE_REENTER_FILE, DEVICE_REENTER_COUNT,
    DEVICE_DISABLE_FIXEVENT, DEVICE_FIXOUT_CANCEL_DONE, DEVICE_OFFLINE_SINCE,
    DEVICE_RESTART_PLAY8, DEVICE_RESTART_PLAY8_COUNT,
    DEVICE_PAST_LOGIN, DEVICE_CYCLE_START,
    DeviceResetException, DeviceTimeoutException,
    FixClearReenterException, SellScreenException, RestartFromPlay8Exception,
)
from ppadb.client import Client as AdbClient

# ── Config ──────────────────────────────────────────────────────────────────
PKG = "jp.konami.pesam"

TH_DIR    = "th-check"           # เจอ Thailand
OTHER_DIR = "Other countries"    # ไม่เจอ Thailand

# รูปที่ใช้ในลำดับนี้ (อยู่ในโฟลเดอร์ img/)
IMG_FIX1   = os.path.join(IMG_DIR, "fix-checkth1.bmp")   # Extras
IMG_FIX2   = os.path.join(IMG_DIR, "fix-checkth2.bmp")   # ไอคอนบันทึก
IMG_FIX3   = os.path.join(IMG_DIR, "fix-checkth3.bmp")   # User Personal
IMG_CHECK  = os.path.join(IMG_DIR, "check-th.bmp")       # Residence
IMG_TH     = os.path.join(IMG_DIR, "fix-checkth4.bmp")   # Thailand

TH_FIND_SECS = 15.0      # หา Thailand กี่วินาทีก่อนตัดสินว่าไม่ใช่ไทย
MATCH_TH     = 0.9       # เกณฑ์ match ของรูปชุดนี้

# CHECK_TH = 1 เปิดลำดับเช็คประเทศ / 0 = ข้าม (ไฟล์เข้า login-success ตามปกติ)
try:
    from config import CHECK_TH
except Exception:
    CHECK_TH = 1

bot_running = False


# ═══════════════════════════════════════════════════════════════════════════
#  ตัวช่วย
# ═══════════════════════════════════════════════════════════════════════════
def _login_marker():
    """รูปที่ใช้ตัดสินว่า 'login เสร็จแล้ว'

    ผู้ใช้เรียกจุดนี้ว่า stoplogin — ถ้ามีไฟล์ img/stoplogin.bmp ให้ใช้ตัวนั้น
    ยังไม่มีก็ถอยไปใช้ checkpointlogin.bmp ซึ่งเป็นจุดเดียวกันใน login.py
    """
    p = os.path.join(IMG_DIR, "stoplogin.bmp")
    if os.path.exists(p):
        return p, "stoplogin"
    return os.path.join(IMG_DIR, "checkpointlogin.bmp"), "checkpointlogin"


def _click_step(device, serial, cycle_start, img_path, label,
                next_path=None, next_label="", max_clicks=5, find_timeout=90.0):
    """กดรูปของ step นี้ แล้วไปต่อเมื่อเข้าเงื่อนไขข้อใดข้อหนึ่ง:

        1. รูปนี้หายไปจากจอ (ยืนยันหายครบ 1 วิ)
        2. เจอรูปของ step ถัดไปแล้ว  ← ไปต่อทันที ไม่ต้องรอรูปนี้หาย
        3. กดครบ max_clicks ครั้ง (ดีฟอลต์ 5)  ← กันวนกดไม่จบ

    เคสจริง: fix-checkth1 (Extras) เป็นแท็บที่ยังค้างอยู่บนจอหลังกด รูปเลยไม่มีวันหาย
    ของเดิมใช้ click_img_until_gone จึงกดวนไปเรื่อยๆ ไม่ยอมไป step ถัดไป

    คืน True ถ้าได้กด / False ถ้าหารูปไม่เจอเลยจนหมดเวลา
    """
    # 1) รอให้เจอรูปก่อน (ถ้าเจอ step ถัดไปอยู่แล้ว = ข้าม step นี้ไปเลย)
    gui_log(serial, f"หา {label} ...", step=label)
    found = None
    deadline = time.time() + find_timeout
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None:
            if next_path and img_search_best(img, next_path, threshold=MATCH_TH):
                gui_log(serial, f"เจอ {next_label} อยู่แล้ว — ข้าม {label} ไปต่อ", step=f"{label} Skip")
                return True
            pts = img_search_best(img, img_path, threshold=MATCH_TH)
            if pts:
                found = pts[0]
                break
        time.sleep(0.4)

    if not found:
        gui_log(serial, f"ไม่เจอ {label} ใน {find_timeout:.0f} วิ — ข้ามไปขั้นถัดไป", step=f"{label} Skip")
        return False

    # 2) กดสูงสุด max_clicks ครั้ง
    x, y = found
    clicks = 0
    gone_since = None
    last_click = 0.0
    gui_log(serial, f"เจอ {label} ({x},{y}) — กดได้สูงสุด {max_clicks} ครั้ง", step=label)
    while True:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)

        if img is not None:
            # ไปต่อทันทีถ้า step ถัดไปโผล่แล้ว
            if next_path and img_search_best(img, next_path, threshold=MATCH_TH):
                gui_log(serial, f"เจอ {next_label} แล้ว (กด {label} ไป {clicks} ครั้ง) → ไปต่อ",
                        step=f"{label} → next")
                return True

            pts = img_search_best(img, img_path, threshold=MATCH_TH)
            if pts:
                gone_since = None
                x, y = pts[0]
                if clicks >= max_clicks:
                    gui_log(serial, f"กด {label} ครบ {max_clicks} ครั้งแล้วรูปยังอยู่ — ลองไป {next_label or 'ขั้นถัดไป'} ต่อ",
                            step=f"{label} Max")
                    return True
                if time.time() - last_click >= 1.0:
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    last_click = time.time()
                    clicks += 1
                    gui_log(serial, f"กด {label} ({x},{y}) ครั้งที่ {clicks}/{max_clicks}", step=label)
            else:
                # รูปหายแล้ว — ยืนยันครบ 1 วิ ค่อยไปต่อ (กัน animation กระพริบ)
                if gone_since is None:
                    gone_since = time.time()
                elif time.time() - gone_since >= 1.0:
                    gui_log(serial, f"{label} หายแล้ว (กดไป {clicks} ครั้ง) → ไปต่อ", step=f"{label} Gone")
                    return True
        time.sleep(0.3)


def _wait_for(device, serial, cycle_start, img_path, label, timeout=None):
    """รอจนกว่าจะเจอรูป — timeout=None คือรอไปเรื่อยๆ ไม่ยอมแพ้
    คืน True ถ้าเจอ / False ถ้าหมดเวลา"""
    gui_log(serial, f"รอ {label} ...", step=label)
    deadline = None if timeout is None else time.time() + timeout
    while deadline is None or time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None and img_search_best(img, img_path, threshold=MATCH_TH):
            gui_log(serial, f"เจอ {label} แล้ว", step=f"{label} OK")
            return True
        time.sleep(0.4)
    return False


def _sort_file(serial, file_path, original_name, dest_dir, reason):
    """ย้ายไฟล์ .dat (ชื่อเดิม) เข้าโฟลเดอร์ปลายทาง"""
    os.makedirs(dest_dir, exist_ok=True)
    final_name = export_base_name(file_path, original_name, strip_dash=True)
    dest = os.path.join(dest_dir, final_name)
    if not os.path.exists(file_path):
        gui_log(serial, f"ไม่พบไฟล์ต้นทาง {original_name} — ข้ามการย้าย", step="Sort Skip")
        return
    try:
        if os.path.exists(dest):
            os.remove(dest)
        _safe_copy(file_path, dest)
        os.remove(file_path)
        gui_log(serial, f"✅ {reason} → {dest_dir}/{final_name}", step="Sorted", status="working")
    except Exception as e:
        gui_log(serial, f"⚠️ ย้ายไฟล์ไม่สำเร็จ: {e}", step="Sort Error")


# ═══════════════════════════════════════════════════════════════════════════
#  ลำดับเช็คประเทศ (หลัง login เสร็จ)
# ═══════════════════════════════════════════════════════════════════════════
def run_check_th(device, serial, cycle_start, file_path, original_name):
    """fix-checkth1 → 2 → 3 → รอ check-th → หา Thailand 15 วิ → ย้ายไฟล์"""
    gui_log(serial, "เริ่มลำดับเช็คประเทศ (Check TH)", step="CheckTH", status="working")

    # 1-3) กดทีละรูปตามลำดับ — แต่ละตัวกดได้สูงสุด 5 ครั้ง
    #      เจอรูปของ step ถัดไปเมื่อไหร่ = ไปต่อทันที (บาง step รูปไม่หายจากจอ เช่นแท็บ Extras)
    _click_step(device, serial, cycle_start, IMG_FIX1, "fix-checkth1",
                next_path=IMG_FIX2, next_label="fix-checkth2")
    _click_step(device, serial, cycle_start, IMG_FIX2, "fix-checkth2",
                next_path=IMG_FIX3, next_label="fix-checkth3")
    _click_step(device, serial, cycle_start, IMG_FIX3, "fix-checkth3",
                next_path=IMG_CHECK, next_label="check-th")

    # 4) รอหน้าโปรไฟล์ (Residence) — หาไปเรื่อยๆ จนกว่าจะเจอ
    _wait_for(device, serial, cycle_start, IMG_CHECK, "check-th", timeout=None)

    # 5) หา Thailand ภายใน 15 วินาที
    gui_log(serial, f"หา fix-checkth4 (Thailand) ภายใน {TH_FIND_SECS:.0f} วิ...", step="CheckTH TH")
    found_th = False
    deadline = time.time() + TH_FIND_SECS
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if img is not None and img_search_best(img, IMG_TH, threshold=MATCH_TH):
            found_th = True
            break
        time.sleep(0.3)

    device.shell(f"am force-stop {PKG}")
    time.sleep(1)

    if found_th:
        gui_log(serial, "🇹🇭 เจอ Thailand", step="CheckTH = TH", status="working")
        _sort_file(serial, file_path, original_name, TH_DIR, "บัญชีไทย")
    else:
        gui_log(serial, f"ไม่เจอ Thailand ใน {TH_FIND_SECS:.0f} วิ", step="CheckTH = Other", status="working")
        _sort_file(serial, file_path, original_name, OTHER_DIR, "ไม่ใช่บัญชีไทย")


# ═══════════════════════════════════════════════════════════════════════════
#  ขั้นตอนที่ดึงมาจาก login.py — ส่งไฟล์ → launch → play8 → stoplogin
# ═══════════════════════════════════════════════════════════════════════════
def launch_with_black_check(device, serial, cycle_start):
    """เปิดเกม + เช็คจอดำ (พอร์ตจาก login.py ข้อ 3)
       จอดำเกิน 85% นาน 45 วิ = ค้าง → force-stop แล้วเปิดใหม่ (ลองได้ 3 รอบ)"""
    gui_log(serial, "Launching PES...", step="Launch", status="working")
    for black_attempt in range(3):
        launch_game(device, settle=0)
        black_start = time.time()
        is_stuck = False
        while time.time() - black_start < 45:
            check_device_reset(serial, cycle_start)
            img = get_screen_capture(device)
            if img is not None:
                try:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
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
            gui_log(serial, f"[BLACK] Dark screen detected! (attempt {black_attempt+1}/3) Restarting app...",
                    step="Black Stuck")
            device.shell(f"am force-stop {PKG}")
            time.sleep(5)
        else:
            break
    time.sleep(8)


def wait_login_done(device, serial, cycle_start):
    """ลูป play8 เต็มรูปแบบจาก login.py — ออกได้ทางเดียวคือผ่าน login

    ยกมาครบทั้ง:
      • กัน checkpointlogin จับพลาดที่หน้า title (ถ้ายังเห็นวงกลม play8 = ยังไม่ผ่าน)
      • เจอ checkponit-play8 (หน้า Terms of Use) → ทำ ☐ ติ๊ก → Consent → Confirm ให้จบก่อน
      • fixout ลอยๆ → กด Back รัวจนเจอ cancel → ถือว่าอยู่หน้าเมนูแล้ว
      • fixlg3 มาก่อน play8 เสมอ
    คืน True ถ้าผ่านทาง checkpointlogin / False ถ้าออกทาง fixout→cancel
    """
    gui_log(serial, "Waiting checkpointlogin (clicking play8)...", step="play8/Check")
    play8_miss = 0
    play8_click_count = 0
    DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None)
    p8_cancel_done = False

    while True:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)

        # fixout→Back spam→cancel เพิ่งทำงานจาก floating check ใน get_screen_capture
        if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
            gui_log(serial, "fixout→cancel done — ข้ามการรอ checkpointlogin", step="Checkpoint Skip")
            p8_cancel_done = True
            break

        if img is not None:
            # 1. checkpointlogin (กันจับพลาดที่หน้า title)
            pts_cp = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
            if pts_cp and (img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
                           or img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))):
                pts_cp = None
            if pts_cp:
                x, y = pts_cp[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                gui_log(serial, "checkpointlogin found & clicked! Proceeding...", step="Checkpoint")
                time.sleep(4)
                break

            # 1.5 หน้า Terms of Use → ☐ ติ๊ก → Consent → Confirm
            if img_search_best(img, os.path.join(IMG_DIR, "checkponit-play8.bmp"), threshold=0.9):
                gui_log(serial, "เจอ checkponit-play8 — หยุดกด play8 ไปทำ Consent/Confirm ก่อน", step="play8 Stop")
                run_new_stage_play8(device, serial, cycle_start)
                play8_miss = 0
                play8_click_count = 0
                continue

            # 1.7 fixout ลอยๆ ทุกเฟรม
            if img_search(img, os.path.join(IMG_DIR, "fixout.bmp"), threshold=0.85):
                fixout_back_spam_until_cancel(device, serial)
                DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None)
                gui_log(serial, "fixout→cancel done — ข้ามการรอ checkpointlogin", step="Checkpoint Skip")
                p8_cancel_done = True
                break

            # 2. กด play8 / play8fix (fixlg3 มาก่อน)
            pts_8 = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
            matched_name = "play8"
            if not pts_8:
                pts_8 = img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))
                matched_name = "play8fix"

            if pts_8:
                play8_miss = 0
                pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                if pts_lg3:
                    gui_log(serial, f"{matched_name} and fixlg3 found! Clicking fixlg3 first", step="play8")
                    x, y = pts_lg3[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    time.sleep(1.0)
                    continue

                x, y = pts_8[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                play8_click_count += 1
                if play8_click_count % 5 == 1:
                    gui_log(serial, f"Found {matched_name}! Clicked. (ครั้งที่ {play8_click_count})", step="play8")
                time.sleep(0.5)
                continue

            # 3. play8 หายแต่ยังไม่เจอ checkpoint → วนเช็คต่อ
            play8_miss += 1

        time.sleep(0.3)

    DEVICE_PAST_LOGIN[serial] = True
    return not p8_cancel_done


def pass_event_screens(device, serial, cycle_start, p8_cancel_done):
    """ปิดหน้า Login Bonus / event หลัง login ให้ถึงหน้าเมนูหลัก (บล็อก 6 ของ login.py)

    EVENT_IMG = 1 → กด play22 → play31 ทีละภาพ
    EVENT_IMG = 0 → รอ play22 แล้วกด Back รัวๆ จนเจอ cancel.bmp แล้วกดจนหาย
    (หลุดมาทาง fixout→cancel แล้ว = อยู่หน้าเมนูหลักอยู่แล้ว ข้ามทั้งขั้น)
    """
    if p8_cancel_done:
        gui_log(serial, "ข้ามขั้น event/Back spam (fixout→cancel ทำไปแล้ว)", step="Event Skip")
        return

    if EVENT_IMG == 1:
        # ─── mode event: กด play22 → play31 ทีละภาพ ───
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
        return

    # ─── mode no-event: รอ play22 แล้วกด Back รัวๆ จนเจอ cancel ───
    skip_cancel_step = False
    gui_log(serial, "Waiting play22 (no-event mode)...", step="play22")
    deadline = time.time() + 10
    while time.time() < deadline:
        check_device_reset(serial, cycle_start)
        img = get_screen_capture(device)
        if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
            gui_log(serial, "fixout→cancel done — ข้ามขั้น Back/cancel", step="Cancel Skip")
            skip_cancel_step = True
            break
        if img is not None and img_search(img, os.path.join(IMG_DIR, "play22.bmp")):
            gui_log(serial, "play22 found — pressing Back...", step="Back loop")
            break
        time.sleep(0.5)

    if skip_cancel_step:
        return

    # กด Back รัวๆ จนกว่าจะเจอ cancel.bmp (ไม่มี timeout)
    gui_log(serial, "Spamming Back until cancel.bmp...", step="Cancel")
    while True:
        check_device_reset(serial, cycle_start)
        device.shell("input keyevent 4")   # KEYCODE_BACK
        time.sleep(1.0)
        try:
            img = get_screen_capture(device)
        except ResetGachaException:
            continue
        if DEVICE_FIXOUT_CANCEL_DONE.pop(serial, None):
            gui_log(serial, "fixout→cancel done — หยุด Back spam", step="Cancel Skip")
            break
        if img is not None:
            pts = img_search(img, os.path.join(IMG_DIR, "cancel.bmp"))
            if pts:
                x, y = pts[0]
                gui_log(serial, f"cancel.bmp found — clicking ({x},{y})", step="Click Cancel")
                click_cancel_until_gone(device, serial, x, y, step="Cancel")
                break


def process_device_checkth(device):
    """หนึ่งเธรดต่อหนึ่งเครื่อง — ส่วนหน้ายกมาจาก login.py ทั้งชุด แล้วต่อด้วย Check TH"""
    serial = device.serial
    gui_log(serial, "checkTH bot started", step="Init", status="working")

    while bot_running:
        time.sleep(random.uniform(0.5, 2.0))   # jitter กัน ADB ค้าง
        file_path = None
        original_name = None
        try:
            DEVICE_DISABLE_FIXEVENT[serial] = False
            check_device_reset(serial)

            # ── เช็ค device online ──
            if not is_device_online(device):
                gui_log(serial, "⚠️ Device OFFLINE — reconnecting & waiting...", step="Offline", status="stuck")
                try_reconnect_device(serial)
                time.sleep(10)
                continue
            if DEVICE_OFFLINE_SINCE.pop(serial, None) is not None:
                gui_log(serial, "✅ กลับมา online แล้ว", step="Online", status="working")

            gui_log(serial, "--- Starting New Cycle ---", step="New Cycle", status="working")

            # ── เช็ค root ก่อนเข้าเกม ──
            if not is_root(device):
                gui_log(serial, "root ยังไม่เปิด → เปิด root...", step="Root Check")
                device = enable_root(device)

            # ── 0. Force-stop ──
            gui_log(serial, "Force closing app...", step="Cleanup", status="working")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)

            # ── restart-from-play8 (เข้าเกมเดิม ไม่ล้าง AUTH ไม่ push ซ้ำ) ──
            restart_p8 = DEVICE_RESTART_PLAY8.pop(serial, None)
            if restart_p8:
                file_path, original_name = restart_p8
                DEVICE_FILE_ASSIGNMENTS[serial] = original_name
                cycle_start = time.time()
                DEVICE_CYCLE_START[serial] = cycle_start
                DEVICE_PAST_LOGIN[serial] = True
                gui_log(serial, f"Restart from play8 (same file, keep login, no re-push): {original_name}",
                        step="Restart play8", status="working")
            else:
                DEVICE_RESTART_PLAY8_COUNT.pop(serial, None)
                # 0.5 ลบ save data เดิม
                device.shell(f"su -c 'rm -f {REMOTE_DAT_FILE}'")
                time.sleep(0.3)

                # 1. หยิบไฟล์ (รองรับ re-enter จาก fixclear)
                pending = DEVICE_REENTER_FILE.pop(serial, None)
                if pending:
                    file_path, original_name = pending
                    gui_log(serial, f"Re-entering same file: {original_name}", step="Re-enter", status="working")
                else:
                    DEVICE_REENTER_COUNT.pop(serial, None)
                    file_path, original_name = pick_next_file()
                    if file_path is None:
                        gui_log(serial, "No files left — waiting...", step="No Files", status="idle")
                        time.sleep(3)
                        continue

                gui_log(serial, f"File: {original_name}", step="File OK", status="working")
                DEVICE_FILE_ASSIGNMENTS[serial] = original_name
                cycle_start = time.time()
                DEVICE_CYCLE_START[serial] = cycle_start
                DEVICE_PAST_LOGIN[serial] = False

                # 2. Push file
                gui_log(serial, "Pushing file...", step="Push")
                if not push_dat_to_device(device, file_path):
                    gui_log(serial, "Push FAILED!", step="Error", status="stuck")
                    release_file(original_name)
                    time.sleep(5)
                    continue

                gui_log(serial, "Push OK — delaying 5s before launch...", step="Push Settle")
                time.sleep(5)

            # ── 3. เปิดเกม + เช็คจอดำ ──
            launch_with_black_check(device, serial, cycle_start)

            # ── 4. ลูป play8 จนผ่าน login ──
            passed_checkpoint = wait_login_done(device, serial, cycle_start)

            # ── 5. ปิดหน้า Login Bonus / event ให้ถึงหน้าเมนูหลักก่อน ──
            pass_event_screens(device, serial, cycle_start, not passed_checkpoint)

            # ── 6. ลำดับเช็คประเทศ ──
            if CHECK_TH == 1:
                run_check_th(device, serial, cycle_start, file_path, original_name)
            else:
                gui_log(serial, "CHECK_TH = 0 — ข้ามการเช็คประเทศ", step="CheckTH Off")
                device.shell(f"am force-stop {PKG}")
                time.sleep(1)
                _sort_file(serial, file_path, original_name, "login-success", "login ผ่าน")

            release_file(original_name)
            gui_log(serial, f"จบรอบของ {original_name}", step="Done")

        except DeviceResetException:
            gui_log(serial, "🔄 Reset — เริ่มไฟล์ใหม่", step="Reset", status="working")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            if original_name:
                release_file(original_name)
            continue
        except DeviceTimeoutException:
            gui_log(serial, "⏱️ Timeout — คืนไฟล์กลับ input-id", step="Timeout", status="error")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            if original_name:
                release_file(original_name)
            continue
        except RestartFromPlay8Exception:
            # login.py จะเก็บไฟล์ไว้ใน DEVICE_RESTART_PLAY8 ให้แล้ว — ห้าม release_file
            gui_log(serial, "🔁 restart จาก play8 — เข้าเกมเดิมอีกรอบ", step="Restart play8", status="working")
            continue
        except FixClearReenterException:
            gui_log(serial, "🔁 fixclear — เข้าไฟล์เดิมใหม่", step="Re-enter", status="working")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            continue
        except SellScreenException:
            gui_log(serial, "🛑 เจอหน้าขาย/ล็อกอินล้มเหลว — เริ่มไฟล์ใหม่", step="Sell/Failed", status="error")
            device.shell(f"am force-stop {PKG}")
            time.sleep(1)
            if original_name:
                release_file(original_name)
            continue
        except Exception as e:
            gui_log(serial, f"❌ Error: {e}", step="Error", status="error")
            if original_name:
                release_file(original_name)   # ไม่รู้สาเหตุ = คืนไฟล์ ไม่ตัดสินว่าไทย/ไม่ไทย
            time.sleep(3)
            continue


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════
def main():
    global bot_running
    print("=" * 62, flush=True)
    print(" checkTH.py — เช็คประเทศบัญชี (Residence = Thailand ?)", flush=True)
    print("=" * 62, flush=True)
    _disable_console_quickedit()

    marker_path, marker_name = _login_marker()
    print(f"[*] จุดตัดสินว่า login เสร็จ: {marker_name} ({marker_path})", flush=True)
    print(f"[*] CHECK_TH = {CHECK_TH}", flush=True)
    print(f"[*] เจอ Thailand → {TH_DIR}/   ไม่เจอ → {OTHER_DIR}/", flush=True)

    missing = [p for p in (IMG_FIX1, IMG_FIX2, IMG_FIX3, IMG_CHECK, IMG_TH) if not os.path.exists(p)]
    if missing:
        print("[ERROR] ไม่พบไฟล์รูปเหล่านี้: " + ", ".join(missing), flush=True)
        return

    find_adb_executable()
    connect_known_ports()
    devices = get_connected_devices()
    if not devices:
        print("[ERROR] ไม่พบเครื่องที่เชื่อมต่อ", flush=True)
        return
    print(f"[*] เจอ {len(devices)} เครื่อง: {devices}", flush=True)

    bot_running = True
    login.bot_running = True
    client = AdbClient(host="127.0.0.1", port=5037)
    for i, serial in enumerate(devices):
        device = client.device(serial)
        threading.Thread(target=process_device_checkth, args=(device,), daemon=True).start()
        if i < len(devices) - 1:
            print("รอ 10 วิ ก่อนเริ่มเครื่องถัดไป...", flush=True)
            time.sleep(10.0)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        bot_running = False
        login.bot_running = False
        print("\n[*] หยุดบอทแล้ว", flush=True)


if __name__ == "__main__":
    main()

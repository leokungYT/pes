# -*- coding: utf-8 -*-
"""
test-coin-scan.py — เทสระบบสแกนเหรียญ (Check Coin) แบบเห็นภาพ
  1) แคปหน้าจอจากเครื่อง (เปิดเกมค้างไว้หน้าที่ต้องการเทสก่อน)
  2) ตีกรอบสีแดงตรง Region ที่บอทใช้สแกน แล้วเซฟรูปเต็มจอ
  3) ครอปเฉพาะกรอบ + OCR แบบเดียวกับบอท ให้ดูว่าอ่านได้อะไร

ผลลัพธ์เซฟใน debug-ocr/:
  coin-test_<serial>_full.png = เต็มจอ + กรอบแดง (ดูว่ากรอบทับตรงเลขเหรียญไหม)
  coin-test_<serial>_crop.png = ภาพที่ส่งเข้า OCR จริง

วิธีใช้:
  py test-coin-scan.py                              -> เครื่องแรกที่เจอ + region เดิมของบอท (52 10 106 41)
  py test-coin-scan.py 127.0.0.1:5563               -> ระบุเครื่อง
  py test-coin-scan.py 127.0.0.1:5563 52 10 106 41  -> ลอง region ใหม่ (x y w h) จนกว่ากรอบจะตรง
"""
import os
import re
import sys
import subprocess

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cv2
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)


def find_adb():
    for p in [os.path.join(BASE, "adb", "adb.exe"), "adb"]:
        try:
            subprocess.run([p, "version"], capture_output=True, timeout=5)
            return p
        except Exception:
            continue
    return None


adb = find_adb()
if not adb:
    print("[ERROR] adb.exe not found (ต้องมีโฟลเดอร์ adb/ หรือ adb ใน PATH)")
    sys.exit(1)

# ── อ่าน arguments ──
serial = None
region = (52, 10, 106, 41)   # (x, y, w, h) — ค่าเดียวกับที่บอทใช้สแกนเหรียญ
args = sys.argv[1:]
if args and not args[0].isdigit():
    serial = args[0]
    args = args[1:]
if len(args) >= 4:
    region = tuple(int(a) for a in args[:4])

# ── หาเครื่องอัตโนมัติถ้าไม่ระบุ ──
if serial is None:
    r = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10)
    for line in r.stdout.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            break
    if serial is None:
        print("[ERROR] ไม่เจอเครื่องเลย — เปิด emulator แล้ว adb connect ก่อน")
        sys.exit(1)

x, y, rw, rh = region
print(f"[INFO] device = {serial}")
print(f"[INFO] region (x={x}, y={y}, w={rw}, h={rh})")

# ── แคปหน้าจอ ──
r = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"],
                   capture_output=True, timeout=15)
img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
if img is None:
    print("[ERROR] แคปหน้าจอไม่สำเร็จ")
    sys.exit(1)
h, w = img.shape[:2]
print(f"[INFO] screen = {w}x{h}")

if y + rh > h or x + rw > w:
    print(f"[WARN] region เกินขอบจอ! (จอ {w}x{h}) — ครอปเท่าที่ได้")

crop = img[y:y + rh, x:x + rw]
if crop.size == 0:
    print("[ERROR] region อยู่นอกจอทั้งหมด — แก้พิกัดแล้วลองใหม่")
    sys.exit(1)

# ── เซฟรูปให้ดู ──
os.makedirs("debug-ocr", exist_ok=True)
safe = serial.replace(":", "_").replace(".", "_")
full_path = os.path.join("debug-ocr", f"coin-test_{safe}_full.png")
crop_path = os.path.join("debug-ocr", f"coin-test_{safe}_crop.png")

annotated = img.copy()
cv2.rectangle(annotated, (x, y), (x + rw, y + rh), (0, 0, 255), 2)
cv2.imwrite(full_path, annotated)
cv2.imwrite(crop_path, crop)
print(f"[SAVED] {full_path}   <- เต็มจอ + กรอบแดง = จุดที่บอทสแกน")
print(f"[SAVED] {crop_path}   <- ภาพที่ส่งเข้า OCR จริง")

# ── OCR แบบเดียวกับบอท (EasyOCR ก่อน + preprocess เหมือนกัน) ──
gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
text = ""
try:
    import warnings
    warnings.filterwarnings("ignore", message=".*pin_memory.*")
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    # แบบเดียวกับบอทเป๊ะ: grayscale + ขยาย 3 เท่าแบบสะอาด (resize อย่างเดียว) + allowlist 0-9
    big = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    text = " ".join(reader.readtext(big, detail=0)).strip()
    print(f"[OCR] EasyOCR (ทั่วไป)   : '{text}'")
    digits_read = "".join(ch for ch in "".join(reader.readtext(big, detail=0, allowlist='0123456789')) if ch.isdigit())
    print(f"[OCR] EasyOCR (เลขล้วน) : '{digits_read}'")
    if digits_read:
        text = digits_read
except Exception as e:
    print(f"[OCR] EasyOCR ใช้ไม่ได้ ({e}) — ลอง Pytesseract...")
    try:
        import pytesseract
        if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        big = cv2.resize(gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
        text = pytesseract.image_to_string(big, lang="eng", config="--psm 7").strip()
        print(f"[OCR] Pytesseract: '{text}'")
    except Exception as e2:
        print(f"[OCR] Pytesseract ก็ไม่ได้: {e2}")

digits = "".join(re.findall(r"\d+", text))
print()
print(f"[RESULT] ข้อความที่อ่านได้ : '{text}'")
print(f"[RESULT] เลขที่บอทจะใช้    : '{digits or '0'}'")
print()
print("เปิดรูป _full.png ดู: ถ้ากรอบแดงไม่ทับเลขเหรียญ ให้ลองพิกัดใหม่:")
print(f"  py test-coin-scan.py {serial} <x> <y> <w> <h>")
print("พอได้พิกัดที่ตรงแล้ว บอกพิกัดมา เดี๋ยวแก้ Region ในบอทให้")

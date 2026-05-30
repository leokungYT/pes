import cv2
import os
import sys
import glob
import subprocess
import time
import shutil
import numpy as np
import concurrent.futures

# Set up paths and imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

try:
    from ppadb.client import Client as AdbClient
except ImportError:
    AdbClient = None

class Region:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

_reader = None
adb_path = "adb"

def find_adb_executable():
    global adb_path
    base = os.path.dirname(os.path.abspath(__file__))
    for loc in [os.path.join(base, "adb", "adb.exe"),
                os.path.join(base, "adb", "adb"), "adb"]:
        if os.path.exists(loc):
            adb_path = loc
            return True
    found = shutil.which("adb")
    if found:
        adb_path = os.path.abspath(found)
        return True
    return False

def connect_known_ports():
    try:
        subprocess.run([adb_path, "start-server"], capture_output=True, timeout=5, shell=(os.name == 'nt'))
        ports = range(5555, 5756, 2)
        print(f"[ADB] Scanning {len(ports)} emulator ports...")
        
        def _try(port):
            try:
                addr = f"127.0.0.1:{port}"
                subprocess.run([adb_path, "connect", addr], capture_output=True, timeout=2, shell=(os.name == 'nt'))
            except:
                pass
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            ex.map(_try, ports)
    except Exception as e:
        print(f"[ADB] Connect error: {e}")

def get_connected_devices():
    try:
        kwargs = {'creationflags': 0x08000000} if os.name == 'nt' else {}
        result = subprocess.run([adb_path, "devices"], capture_output=True, text=True, timeout=5, **kwargs)
        lines = result.stdout.strip().split("\n")[1:]
        raw_list = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                raw_list.append(parts[0])
        return raw_list
    except:
        return []

def ocr_region_test(img, region, label="Region"):
    global _reader
    if img is None:
        return ""

    # Crop the region
    crop_img = img[region.y : region.y + region.h, region.x : region.x + region.w].copy()
    
    # Create debug folder
    debug_dir = "debug-test-ocr"
    os.makedirs(debug_dir, exist_ok=True)
    cv2.imwrite(os.path.join(debug_dir, f"{label}_raw.png"), crop_img)
    print(f"\n--- [{label}] Saved raw crop to {debug_dir}/{label}_raw.png ({crop_img.shape[1]}x{crop_img.shape[0]}) ---")

    # 1. EasyOCR (with Bilateral Filtering + 2x Resize)
    if easyocr is not None:
        try:
            print(f"[{label}] 1. Running EasyOCR (with Bilateral Filter + 2x Cubic Resize)...")
            if _reader is None:
                _reader = easyocr.Reader(['en'], gpu=False)
            
            # Apply bilateral filter to smooth card textures but keep text edges extremely sharp
            cleaned_img = cv2.bilateralFilter(crop_img, 9, 75, 75)
            cv2.imwrite(os.path.join(debug_dir, f"{label}_easy_bilateral.png"), cleaned_img)
            
            # Resize 2x using Cubic interpolation for cleaner character strokes
            resized_easy = cv2.resize(cleaned_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(os.path.join(debug_dir, f"{label}_easy_resized2x.png"), resized_easy)
            
            results = _reader.readtext(resized_easy, detail=0)
            res = " ".join(results).strip()
            print(f"*** [{label}] EasyOCR Result: '{res}'")
        except Exception as e:
            print(f"[{label}] EasyOCR Error: {e}")

    # 2. Pytesseract (with original multi-pass)
    if pytesseract is not None:
        try:
            print(f"[{label}] 2. Running Pytesseract (Enhanced Multi-pass)...")
            if len(crop_img.shape) == 3:
                img_gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            else:
                img_gray = crop_img
                
            img_resized = cv2.resize(img_gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            
            cv2.imwrite(os.path.join(debug_dir, f"{label}_tess_raw.png"), img_resized)
            
            all_results = []
            configs = [
                (img_resized, "--psm 7", "Raw-psm7"),
            ]
            
            for proc_img, psm, label_cfg in configs:
                text = pytesseract.image_to_string(
                    proc_img, lang="eng",
                    config=f"{psm}"
                )
                txt = text.strip()
                if txt:
                    # ป้องกันข้อความที่มีสัญลักษณ์พิเศษ (เช่น ©, \xa9) แล้วปริ้นออก Console Windows ไม่ผ่าน
                    try:
                        enc = sys.stdout.encoding or 'utf-8'
                        safe_txt = txt.encode(enc, errors='replace').decode(enc)
                    except:
                        safe_txt = txt.encode('utf-8', errors='replace').decode('utf-8', errors='ignore')
                    print(f"   - Tesseract {label_cfg}: '{safe_txt}'")
                    all_results.append(txt)
            
            combined_result = " | ".join(all_results)
            try:
                enc = sys.stdout.encoding or 'utf-8'
                safe_combined = combined_result.encode(enc, errors='replace').decode(enc)
            except:
                safe_combined = combined_result.encode('utf-8', errors='replace').decode('utf-8', errors='ignore')
            print(f"*** [{label}] Pytesseract Combined: '{safe_combined}'")
        except Exception as e:
            print(f"[{label}] Pytesseract Error: {e}")

def main():
    print("==================================================")
    print("   PES Mobile - Live ADB OCR Test Script         ")
    print("==================================================")
    
    img = None
    filename = None
    
    # 1. Try to connect to ADB device live
    find_adb_executable()
    connect_known_ports()
    devices = get_connected_devices()
    
    if devices and AdbClient is not None:
        serial = devices[0]
        print(f"[ADB] Connected to live emulator/device: {serial}")
        try:
            client = AdbClient(host="127.0.0.1", port=5037)
            device = client.device(serial)
            print("[ADB] Capturing live screenshot from device...")
            raw = device.screencap()
            if raw:
                img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                debug_dir = "debug-test-ocr"
                os.makedirs(debug_dir, exist_ok=True)
                filename = os.path.join(debug_dir, "adb_live_screenshot.png")
                cv2.imwrite(filename, img)
                print(f"[ADB] Live screenshot saved to {filename}")
        except Exception as e:
            print(f"[ADB] Failed to capture live screenshot: {e}")
            img = None

    # 2. Fallback to local files if ADB failed or no device connected
    if img is None:
        print("\n[ADB] No live device found or screenshot failed. Falling back to local files...")
        
        # Check coordinates inside current directory or parent directory
        candidate_files = [
            "screen_coord.png", "screen-5556.png", "debug_ocr_crop.png", "debugtest.png",
            "pes/screen_coord.png", "pes/screen-5556.png", "pes/debug_ocr_crop.png"
        ]
        # Check top-level or relative paths
        base = os.path.dirname(os.path.abspath(__file__))
        for f in candidate_files:
            loc = f if os.path.isabs(f) else os.path.join(base, f)
            if os.path.exists(loc):
                filename = loc
                break
                
        if not filename:
            old_files = glob.glob(os.path.join(base, "old", "screen*.png"))
            if old_files:
                filename = old_files[0]

        if not filename:
            print("\n[ERROR] No screenshot file found to test!")
            print("Please make sure your emulator is running, or place a screen_coord.png in d:/bot/pes/")
            return

        print(f"Using local test screenshot: {filename}")
        img = cv2.imread(filename)
        if img is None:
            print(f"[ERROR] Could not read image: {filename}")
            return

    # Lock Regions (3 horizontal rows)
    lock1_region = Region(154, 134, 679, 39)
    lock2_region = Region(156, 249, 646, 34)
    lock3_region = Region(157, 360, 658, 34)

    ocr_region_test(img, lock1_region, label="Lock1")
    ocr_region_test(img, lock2_region, label="Lock2")
    ocr_region_test(img, lock3_region, label="Lock3")
    
    print("\n==================================================")
    print("Processing complete! Images saved to 'debug-test-ocr/'")
    print("==================================================")

if __name__ == "__main__":
    main()

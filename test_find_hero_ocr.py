import cv2
import os
import sys
import glob

# ─────────────────────────────────────────────
# Set up paths and imports
# ─────────────────────────────────────────────
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

# Region Helper
class Region:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

_reader = None

def ocr_region(img, region, label="Region", serial="test"):
    global _reader
    if img is None:
        return ""

    # Crop the region
    crop_img = img[region.y : region.y + region.h, region.x : region.x + region.w]
    
    # Save debug raw crop
    os.makedirs("debug-ocr-test", exist_ok=True)
    cv2.imwrite(f"debug-ocr-test/{label}_raw.png", crop_img)
    print(f"[{label}] Saved debug-ocr-test/{label}_raw.png ({crop_img.shape[1]}x{crop_img.shape[0]})")

    # 1. EasyOCR (Deep Learning)
    if easyocr is not None:
        try:
            print(f"[{label}] Scanning with EasyOCR...")
            if _reader is None:
                _reader = easyocr.Reader(['en'], gpu=False)
            
            # Resize 2x for better accuracy
            resized_easy = cv2.resize(crop_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            results = _reader.readtext(resized_easy, detail=0)
            res = " ".join(results).strip()
            if res:
                print(f"[{label}] EasyOCR Result: '{res}'")
                return res
        except Exception as e:
            print(f"[{label}] EasyOCR Error: {e}")

    # 2. Pytesseract Fallback
    if pytesseract is not None:
        try:
            print(f"[{label}] Scanning with Pytesseract...")
            if len(crop_img.shape) == 3:
                gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            else:
                gray = crop_img
            
            # Resize 4x for Tesseract text size optimization
            resized = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
            
            # Preprocessing Method A: Adaptive Threshold
            blur_a = cv2.GaussianBlur(resized, (3, 3), 0)
            adapt = cv2.adaptiveThreshold(
                blur_a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 4
            )
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            clean_a = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, kernel)
            cv2.imwrite(f"debug-ocr-test/{label}_processed.png", clean_a)

            # Try Tesseract PSM 7 and 6
            best_res = ""
            for psm in ["7", "6"]:
                text = pytesseract.image_to_string(
                    clean_a, lang="eng",
                    config=f"--psm {psm}"
                )
                txt = text.strip()
                if txt and len(txt) > len(best_res):
                    best_res = txt
            
            print(f"[{label}] Pytesseract Result: '{best_res}'")
            return best_res
        except Exception as e:
            print(f"[{label}] Pytesseract Error: {e}")

    return ""

def main():
    print("=== PES Mobile - Find Hero OCR Test Tool ===")
    
    # 1. Load config
    try:
        import config
        from config import HERO_LIST
        print(f"Loaded HERO_LIST from config.py: {HERO_LIST}")
    except Exception as e:
        print(f"Could not load config.py: {e}")
        HERO_LIST = ["Gareth Bale", "Aubameyang", "Marcelo", "Nico Paz", "Federico Dimarco", "Luka", "rgson", "Arribas", "Ramedhan Saifullah", "Chrigor"]
        print(f"Using fallback HERO_LIST: {HERO_LIST}")

    # Clean empty strings from list
    target_heroes = [h.strip() for h in HERO_LIST if h and h.strip()]
    print(f"Targeting Heroes for search: {target_heroes}")

    # 2. Find screenshot to test
    filename = None
    candidate_files = ["screen_coord.png", "screen-5556.png", "debug_ocr_crop.png", "debugtest.png"]
    # Check if any exist
    for f in candidate_files:
        if os.path.exists(f):
            filename = f
            break
            
    # Try parent directory or old/ directory
    if not filename:
        old_files = glob.glob("old/screen*.png")
        if old_files:
            filename = old_files[0]

    if not filename:
        print("\n[ERROR] No test screenshot found! Please capture a screenshot using get_coords.py first.")
        print("Expected one of: screen_coord.png, screen-5556.png, debugtest.png")
        return

    print(f"\nUsing test screenshot: {filename}")
    img = cv2.imread(filename)
    if img is None:
        print(f"[ERROR] Could not read image: {filename}")
        return

    # Lock Regions
    lock1_region = Region(58, 122, 351, 343)
    lock2_region = Region(503, 116, 341, 338)

    print("\n--- Scanning Lock 1 ---")
    lock1_text = ocr_region(img, lock1_region, label="Lock1")
    
    print("\n--- Scanning Lock 2 ---")
    lock2_text = ocr_region(img, lock2_region, label="Lock2")

    # Match Heroes
    found_heroes = []
    
    # Check Lock 1
    print("\n--- Matching Lock 1 Results ---")
    lock1_found = None
    for h in target_heroes:
        if h.lower() in lock1_text.lower():
            lock1_found = h
            found_heroes.append(h)
            print(f"⭐ MATCH Lock 1: {h}")
            break
    if not lock1_found:
        print("No hero matched in Lock 1.")

    # Check Lock 2
    print("\n--- Matching Lock 2 Results ---")
    lock2_found = None
    for h in target_heroes:
        if h.lower() in lock2_text.lower():
            lock2_found = h
            found_heroes.append(h)
            print(f"⭐ MATCH Lock 2: {h}")
            break
    if not lock2_found:
        print("No hero matched in Lock 2.")

    print("\n=== FINAL RESULTS ===")
    if found_heroes:
        hero_prefix = "+".join(found_heroes)
        original_name = "test_file.dat"
        final_name = f"{hero_prefix}+{original_name}"
        print(f"Status: Found Heroes!")
        print(f"Prefix: {hero_prefix}")
        print(f"Final filename will be: {final_name}")
        print(f"Target Folder: found-hero/")
    else:
        print("Status: No heroes found.")
        print("Final filename will be: test_file.dat")
        print("Target Folder: no-hero/")

if __name__ == "__main__":
    main()

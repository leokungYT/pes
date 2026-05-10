import cv2
import os
import numpy as np

# พยายาม Import OCR engines
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

_reader = None

def test_read_ocr(image_path):
    global _reader
    if not os.path.exists(image_path):
        print(f"Error: File '{image_path}' not found!")
        return

    print(f"\n--- Testing OCR on: {image_path} ---")
    img = cv2.imread(image_path)
    if img is None:
        print("Error: Could not load image (None)")
        return

    # ตัดขอบซ้าย-ขวาออก 15% (เลียนแบบ login.py เพื่อความแม่นยำ)
    h_tmp, w_tmp = img.shape[:2]
    margin = int(w_tmp * 0.15)
    img = img[:, margin : w_tmp - margin]
    cv2.imwrite("debug_test_trimmed.png", img)

    # 1. Try EasyOCR
    if easyocr is not None:
        try:
            print("[OCR] Attempting EasyOCR...")
            if _reader is None:
                _reader = easyocr.Reader(['en'], gpu=False)
            results = _reader.readtext(img, detail=0)
            res = " ".join(results).strip()
            print(f"[OCR] EasyOCR Result: '{res}'")
        except Exception as e:
            print(f"[OCR] EasyOCR Error: {e}")
    else:
        print("[OCR] EasyOCR not installed.")

    # 2. Try Pytesseract
    if pytesseract is not None:
        try:
            print("[OCR] Attempting Pytesseract...")
            img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # ขยายภาพ 3 เท่า
            img_resized = cv2.resize(img_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            # ลบนอยซ์
            img_blur = cv2.GaussianBlur(img_resized, (3, 3), 0)
            # ตัดสีที่สว่างกว่า 200 (ตัวหนังสือสีขาว)
            _, img_bin = cv2.threshold(img_blur, 200, 255, cv2.THRESH_BINARY)
            
            # Save the processed image to see what Tesseract sees
            cv2.imwrite("debug_test_processed.png", img_bin)
            print("[OCR] Saved 'debug_test_processed.png' for verification.")

            text = pytesseract.image_to_string(img_bin, lang="eng", config="--psm 7")
            res = text.strip()
            print(f"[OCR] Pytesseract Result: '{res}'")
        except Exception as e:
            print(f"[OCR] Pytesseract Error: {e}")
    else:
        print("[OCR] Pytesseract not installed.")

if __name__ == "__main__":
    # เปลี่ยนชื่อไฟล์ที่ต้องการทดสอบที่นี่
    test_read_ocr("debugtest.png")
    # แถม: ทดสอบไฟล์ที่บอทเซฟออกมาด้วย
    if os.path.exists("debug_ocr_crop.png"):
        test_read_ocr("debug_ocr_crop.png")

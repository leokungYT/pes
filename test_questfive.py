import os
import cv2
import numpy as np
import time
from ppadb.client import Client as AdbClient

IMAGE_CACHE = {}

def load_template(path):
    if path not in IMAGE_CACHE:
        if os.path.exists(path):
            t = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if t is not None:
                IMAGE_CACHE[path] = t
                return t
        
        # Try alternate extension (.bmp <-> .png) if not found
        base, ext = os.path.splitext(path)
        alt_exts = [".bmp", ".png"]
        alt_exts = [e for e in alt_exts if e.lower() != ext.lower()]
        for alt in alt_exts:
            alt_path = base + alt
            if os.path.exists(alt_path):
                t = cv2.imread(alt_path, cv2.IMREAD_GRAYSCALE)
                if t is not None:
                    IMAGE_CACHE[path] = t
                    return t
                    
    return IMAGE_CACHE.get(path)

def img_search(gray_img, find_path, threshold=0.8):
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
            expected_size = w * h * 4
            if len(raw) >= 12 + expected_size:
                img_data = raw[12:12+expected_size]
                img = np.frombuffer(img_data, dtype=np.uint8).reshape((h, w, 4))
                return cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
    except Exception:
        pass

    try:
        raw = device.screencap()
        if raw:
            return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
    except:
        pass
    return None

def check_and_handle_fixtip(device, img):
    gq_dir = "img/getquest"
    pts1 = img_search(img, os.path.join(gq_dir, "fixtip1.bmp"))
    if pts1:
        print("fixtip1.bmp detected! Looking for fixtip2.bmp...")
        pts2 = img_search(img, os.path.join(gq_dir, "fixtip2.bmp"))
        if pts2:
            x2, y2 = pts2[0]
            device.shell(f"input swipe {x2} {y2} {x2} {y2} 100")
            print(f"Clicked fixtip2 at ({x2}, {y2})")
            time.sleep(1.5)
            return True
        else:
            print("fixtip2.bmp not found on screen yet.")
    return False

def get_screen_capture_with_check(device):
    img = fast_screencap(device)
    if img is not None:
        check_and_handle_fixtip(device, img)
    return img

def click_until_gone(device, img_path, label, threshold=0.8):
    print(f"Waiting for {label}...")
    while True:
        img = get_screen_capture_with_check(device)
        if img is not None:
            pts = img_search(img, img_path, threshold=threshold)
            if pts:
                x, y = pts[0]
                device.shell(f"input swipe {x} {y} {x} {y} 100")
                print(f"Clicked {label} at ({x}, {y})")
                time.sleep(1.5)
                # Retry loop to verify if it is gone
                retry_end = time.time() + 8
                while time.time() < retry_end:
                    img2 = get_screen_capture_with_check(device)
                    if img2 is not None and not img_search(img2, img_path, threshold=threshold):
                        break
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    print(f"Re-clicked {label}")
                    time.sleep(1.0)
                break
        time.sleep(0.8)

def main():
    print("Connecting to ADB...")
    client = AdbClient(host="127.0.0.1", port=5037)
    devices = client.devices()
    if not devices:
        print("No devices found via ppadb.")
        return
    
    device = devices[0]
    print(f"Testing on device: {device.serial}")
    
    GQ_DIR = "img/getquest"
    
    while True:
        # 1. Delay 10 วินาทีก่อนเริ่มลาก จากนั้นกดค้างที่ 152 343 แล้วลากไป 310 304 (ใช้เวลาลาก 2 วินาที)
        print(f"\n[Step 1] Waiting 10 seconds delay before dragging...")
        time.sleep(10.0)
        
        drag_cmd = "input draganddrop 152 343 310 304 3000"
        print(f"Executing: adb shell {drag_cmd}")
        device.shell(drag_cmd)
        time.sleep(0.2) # เริ่มค้นหาต่อทันที
        print("Drag completed.")
        
        # 2. กด questfive1
        print("[Step 2] Searching for questfive1.bmp...")
        q5_1_found = False
        search_start = time.time()
        while time.time() - search_start < 10: # ให้เวลารอ 10 วิ
            img = get_screen_capture_with_check(device)
            if img is not None:
                pts = img_search(img, os.path.join(GQ_DIR, "questfive1.bmp"))
                if pts:
                    x, y = pts[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    print(f"Clicked questfive1 at ({x}, {y})")
                    q5_1_found = True
                    time.sleep(1.5)
                    # กดซ้ำจนกว่าจะหาย
                    retry_end = time.time() + 8
                    while time.time() < retry_end:
                        img2 = get_screen_capture_with_check(device)
                        if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive1.bmp")):
                            break
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        print("Re-clicked questfive1")
                        time.sleep(1.0)
                    break
            time.sleep(0.8)
            
        if not q5_1_found:
            print("questfive1.bmp not found! Retrying from step 1...")
            continue
            
        # 3. เช็ค checkpointquest1
        print("[Step 3] Verifying checkpointquest1.bmp...")
        time.sleep(2.0) # ให้เวลาโหลดหน้าจอ
        checkpoint_found = False
        img = get_screen_capture_with_check(device)
        if img is not None:
            pts = img_search(img, os.path.join(GQ_DIR, "checkpointquest1.bmp"))
            if pts:
                print("checkpointquest1.bmp FOUND!")
                checkpoint_found = True
            else:
                print("checkpointquest1.bmp NOT FOUND!")
                
        if not checkpoint_found:
            print("Checkpoint not found, going back to drag again...")
            continue # กลับไปลากใหม่
            
        # 4. ถ้าเจอ checkpointquest1 -> ไป questfive2 -> questfive3
        print("[Step 4] Proceeding to questfive2 -> questfive3...")
        for i in range(2, 4):
            q_name = f"questfive{i}.bmp"
            click_until_gone(device, os.path.join(GQ_DIR, q_name), q_name)
            
        # 5. วนกด questfive4 -> questfive5 จนกว่าจะเจอ checkpointquest2
        print("[Step 5] Loop clicking questfive4 -> questfive5 until checkpointquest2.bmp is found...")
        while True:
            # เช็ค checkpointquest2 ก่อนเริ่มรอบ
            img = get_screen_capture_with_check(device)
            if img is not None and img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                print("checkpointquest2.bmp FOUND! Breaking loop...")
                break
                
            # รอ/กด questfive4
            print("Waiting/Clicking questfive4...")
            q4_break = False
            while True:
                img = get_screen_capture_with_check(device)
                if img is not None:
                    if img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                        print("checkpointquest2.bmp FOUND during questfive4 check! Breaking loop...")
                        q4_break = True
                        break
                    
                    pts4 = img_search(img, os.path.join(GQ_DIR, "questfive4.bmp"))
                    if pts4:
                        x, y = pts4[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        print(f"Clicked questfive4 at ({x}, {y})")
                        time.sleep(1.5)
                        # กดซ้ำจนกว่าจะหาย
                        retry_end = time.time() + 8
                        while time.time() < retry_end:
                            img2 = get_screen_capture_with_check(device)
                            if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive4.bmp")):
                                break
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            print("Re-clicked questfive4")
                            time.sleep(1.0)
                        break
                time.sleep(0.8)
                
            if q4_break:
                break
                
            # เช็ค checkpointquest2 อีกรอบก่อนกด questfive5
            img = get_screen_capture_with_check(device)
            if img is not None and img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                print("checkpointquest2.bmp FOUND before questfive5! Breaking loop...")
                break
                
            # รอ/กด questfive5
            print("Waiting/Clicking questfive5...")
            q5_break = False
            while True:
                img = get_screen_capture_with_check(device)
                if img is not None:
                    if img_search(img, os.path.join(GQ_DIR, "checkpointquest2.bmp")):
                        print("checkpointquest2.bmp FOUND during questfive5 check! Breaking loop...")
                        q5_break = True
                        break
                    
                    pts5 = img_search(img, os.path.join(GQ_DIR, "questfive5.bmp"))
                    if pts5:
                        x, y = pts5[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        print(f"Clicked questfive5 at ({x}, {y})")
                        time.sleep(1.5)
                        # กดซ้ำจนกว่าจะหาย
                        retry_end = time.time() + 8
                        while time.time() < retry_end:
                            img2 = get_screen_capture_with_check(device)
                            if img2 is not None and not img_search(img2, os.path.join(GQ_DIR, "questfive5.bmp")):
                                break
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            print("Re-clicked questfive5")
                            time.sleep(1.0)
                        break
                time.sleep(0.8)
                
            if q5_break:
                break
                
        # 6. ถ้าเจอ checkpointquest2 -> กด questfive6 -> questfive9
        print("[Step 6] Proceeding to questfive6 -> questfive9...")
        for i in range(6, 10):
            q_name = f"questfive{i}.bmp"
            click_until_gone(device, os.path.join(GQ_DIR, q_name), q_name)
            
        # 7. วนกดเช็ค questfive10 กดค้าง 5วิ ไปเรื่อยๆ จนกว่าจะเจอ chekcpointquest3
        print("[Step 7] Loop checking questfive10 (long press 5s) until chekcpointquest3.bmp is found...")
        while True:
            # เช็ค chekcpointquest3.bmp
            img = get_screen_capture_with_check(device)
            if img is not None:
                if img_search(img, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
                    print("chekcpointquest3.bmp FOUND! Ending sequence...")
                    break
            
            # ค้นหา questfive10.bmp
            img = get_screen_capture_with_check(device)
            if img is not None:
                pts10 = img_search(img, os.path.join(GQ_DIR, "questfive10.bmp"))
                if pts10:
                    x, y = pts10[0]
                    print(f"questfive10.bmp found! Long pressing at ({x}, {y}) for 5 seconds...")
                    device.shell(f"input swipe {x} {y} {x} {y} 5000")
                    time.sleep(5.5) # รอให้กดค้างเสร็จ
                    
                    # เช็ค chekcpointquest3 อีกรอบหลังกดค้างเสร็จ
                    img_after = get_screen_capture_with_check(device)
                    if img_after is not None and img_search(img_after, os.path.join(GQ_DIR, "chekcpointquest3.bmp")):
                        print("chekcpointquest3.bmp FOUND after long press! Ending sequence...")
                        break
                else:
                    print("questfive10.bmp not found on screen, waiting...")
            time.sleep(1.0)
            
        # 8. หลังจากเจอ chekcpointquest3 -> กด questfive11 -> questfive12
        print("[Step 8] Proceeding to questfive11 -> questfive12...")
        for i in range(11, 13):
            q_name = f"questfive{i}.bmp"
            click_until_gone(device, os.path.join(GQ_DIR, q_name), q_name)
            
        # 9. กดรูปค้าง questfive13 7วิ รอให้เจอ checkpointquest4
        print("[Step 9] Loop checking questfive13 (long press 7s) until checkpointquest4.bmp is found...")
        while True:
            # เช็ค checkpointquest4.bmp
            img = get_screen_capture_with_check(device)
            if img is not None:
                if img_search(img, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
                    print("checkpointquest4.bmp FOUND! Proceeding...")
                    break
                    
            # ค้นหา questfive13.bmp
            img = get_screen_capture_with_check(device)
            if img is not None:
                pts13 = img_search(img, os.path.join(GQ_DIR, "questfive13.bmp"))
                if pts13:
                    x, y = pts13[0]
                    print(f"questfive13.bmp found! Long pressing at ({x}, {y}) for 7 seconds...")
                    device.shell(f"input swipe {x} {y} {x} {y} 7000")
                    time.sleep(7.5) # รอให้กดค้างเสร็จ
                    
                    # เช็ค checkpointquest4 อีกรอบหลังกดค้างเสร็จ
                    img_after = get_screen_capture_with_check(device)
                    if img_after is not None and img_search(img_after, os.path.join(GQ_DIR, "checkpointquest4.bmp")):
                        print("checkpointquest4.bmp FOUND after long press! Proceeding...")
                        break
                else:
                    print("questfive13.bmp not found on screen, waiting...")
            time.sleep(1.0)
            
        # 10. หลังจากเจอ checkpointquest4 -> กด questfive14 -> กด back รัวๆ จนกว่าจะเจอ cancel.bmp
        print("[Step 10] Proceeding to questfive14...")
        click_until_gone(device, os.path.join(GQ_DIR, "questfive14.bmp"), "questfive14.bmp")
        
        print("Spamming Back key until cancel.bmp is found...")
        while True:
            img = get_screen_capture_with_check(device)
            if img is not None:
                pts_cancel = img_search(img, "img/cancel.bmp")
                if pts_cancel:
                    x, y = pts_cancel[0]
                    device.shell(f"input swipe {x} {y} {x} {y} 100")
                    print(f"Clicked cancel at ({x}, {y})")
                    time.sleep(1.5)
                    # กดซ้ำจนกว่าจะหาย
                    retry_end = time.time() + 8
                    while time.time() < retry_end:
                        img2 = get_screen_capture_with_check(device)
                        if img2 is not None and not img_search(img2, "img/cancel.bmp"):
                            break
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        print("Re-clicked cancel")
                        time.sleep(1.0)
                    break
            
            # Send Back key
            device.shell("input keyevent 4")
            print("Pressed Back key")
            time.sleep(1.0)
            
        print("\nAll steps completed successfully!")
        break

if __name__ == "__main__":
    main()

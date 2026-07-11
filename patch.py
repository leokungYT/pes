import re
import os

filepath = r"c:\Users\Administrator\Downloads\pes-new\pes\login.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

start_marker = "            # 4. Wait for play8 or play8fix"
end_marker = "                time.sleep(1.5)"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx != -1 and end_idx != -1:
    new_content = """            # 4 & 5. Wait for checkpointlogin (pressing play8/play8fix along the way)
            gui_log(serial, "Waiting checkpointlogin (clicking play8)...", step="play8/Check")
            while True:
                check_device_reset(serial, cycle_start)
                img = get_screen_capture(device)
                if img is not None:
                    # --- 1. เช็ค Checkpoint ก่อน ถ้าเจอคือหลุดลูปไปเฟสต่อไป ---
                    pts_cp = img_search(img, os.path.join(IMG_DIR, "checkpointlogin.bmp"))
                    if pts_cp:
                        if LOGIN_FAST:
                            gui_log(serial, "LOGIN_FAST: checkpointlogin found — clearing app and moving to next file.", step="Fast Done", status="working")
                            device.shell("am force-stop jp.konami.pesam")
                            time.sleep(0.5)
                            dest = os.path.join(LOGIN_SUCCESS_DIR, original_name)
                            if os.path.exists(file_path):
                                save_result(file_path, dest)
                            release_file(original_name)
                            break
                        
                        x, y = pts_cp[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, "checkpointlogin found & clicked! Proceeding...", step="Checkpoint")
                        time.sleep(4)
                        break
                    
                    if img_search(img, os.path.join(IMG_DIR, "checkpointgacha.bmp")):
                        gui_log(serial, "checkpointgacha detected! Entering checkpoint phase.", step="Checkpoint")
                        break
                    if img_search(img, os.path.join(IMG_DIR, "checkpointcoin.bmp")):
                        gui_log(serial, "checkpointcoin detected! Entering checkpoint phase.", step="Checkpoint")
                        break

                    # --- 2. ถ้ายังไม่เจอ Checkpoint ก็หา play8 / play8fix ---
                    pts_8 = img_search(img, os.path.join(IMG_DIR, "play8.bmp"))
                    matched_name = "play8"
                    if not pts_8:
                        pts_8 = img_search(img, os.path.join(IMG_DIR, "play8fix.bmp"))
                        matched_name = "play8fix"

                    if pts_8:
                        # Prioritize fixlg3
                        pts_lg3 = img_search(img, os.path.join(IMG_DIR, "fixlg3.bmp"))
                        if pts_lg3:
                            gui_log(serial, f"{matched_name} and fixlg3 found! Clicking fixlg3 first", step="play8")
                            x, y = pts_lg3[0]
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(1.0)
                            continue

                        x, y = pts_8[0]
                        device.shell(f"input swipe {x} {y} {x} {y} 100")
                        gui_log(serial, f"Found {matched_name}! Clicked.", step="play8")
                        time.sleep(0.5)
                        continue

                time.sleep(0.3)"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content[:start_idx] + new_content + content[end_idx:])
    print("Patch successful.")
else:
    print("Markers not found.")

import os
import time

with open('main-pes.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1
for i, l in enumerate(lines):
    if '# play22 - play25' in l:
        start_idx = i
    if '# 5. FINAL BACKUP LOGIC' in l:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    old_block = lines[start_idx:end_idx]
    
    new_block = []
    new_block.append('            if EVENT_IMG == 1:\n')
    for l in old_block:
        new_block.append('    ' + l if l.strip() else l)
    
    else_block = """            else:
                # ─── mode no-event: รอ play22 แล้วกด Back รัวๆ จนเจอ cancel ─
                gui_log(serial, "Waiting play22 (no-event mode)...", step="play22")
                deadline = time.time() + 10
                while time.time() < deadline:
                    check_device_reset(serial, cycle_start)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = ImgSearchADB(img, os.path.join(IMG_DIR, "play22.bmp"))
                        if pts:
                            gui_log(serial, "play22 found — pressing Back...", step="Back loop")
                            break
                    time.sleep(0.01)

                gui_log(serial, "Spamming Back until cancel.bmp...", step="Cancel")
                while True:
                    check_device_reset(serial, cycle_start)
                    device.shell("input keyevent 4")
                    time.sleep(0.4)
                    img = get_screen_capture(device)
                    if img is not None:
                        pts = ImgSearchADB(img, os.path.join(IMG_DIR, "cancel.bmp"))
                        if pts:
                            x, y = pts[0]
                            gui_log(serial, f"cancel.bmp found — clicking ({x},{y})", step="Click Cancel")
                            device.shell(f"input swipe {x} {y} {x} {y} 100")
                            time.sleep(1)
                            break
"""
    new_block.append(else_block)
    
    lines = lines[:start_idx] + new_block + lines[end_idx:]
    with open('main-pes.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Successfully updated main-pes.py')
else:
    print('Markers not found')

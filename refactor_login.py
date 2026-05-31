import sys
import os

with open("d:/bot/pes/login.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

out_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 1. Replace nav_steps list
    if line.strip() == "nav_steps = [":
        out_lines.append("    nav_steps_1 = [\n")
        out_lines.append("        (\"fin1.bmp\", \"fin2.bmp\"),\n")
        out_lines.append("        (\"fin2.bmp\", \"fin3.bmp\"),\n")
        out_lines.append("        (\"fin3.bmp\", \"fin4.bmp\"),\n")
        out_lines.append("        (\"fin4.bmp\", \"fin5.bmp\"),\n")
        out_lines.append("        (\"fin5.bmp\", \"fin6.bmp\"),\n")
        out_lines.append("    ]\n")
        out_lines.append("    for name_curr, name_next in nav_steps_1:\n")
        out_lines.append("        gui_log(serial, f\"Waiting for {name_curr}...\", step=f\"{name_curr} Waiting\")\n")
        out_lines.append("        deadline = time.time() + 60\n")
        out_lines.append("        last_click_time = 0\n")
        out_lines.append("        while time.time() < deadline:\n")
        out_lines.append("            check_device_reset(serial, cycle_start)\n")
        out_lines.append("            img = get_screen_capture(device)\n")
        out_lines.append("            if img is not None:\n")
        out_lines.append("                if img_search(img, os.path.join(IMG_DIR, name_next)):\n")
        out_lines.append("                    gui_log(serial, f\"{name_next} detected! Proceeding to next step.\", step=f\"{name_next} Seen\")\n")
        out_lines.append("                    break\n")
        out_lines.append("                pts = img_search(img, os.path.join(IMG_DIR, name_curr))\n")
        out_lines.append("                if pts:\n")
        out_lines.append("                    now = time.time()\n")
        out_lines.append("                    if now - last_click_time >= 5.0:\n")
        out_lines.append("                        x, y = pts[0]\n")
        out_lines.append("                        device.shell(f\"input swipe {x} {y} {x} {y} 100\")\n")
        out_lines.append("                        gui_log(serial, f\"Clicked {name_curr}\", step=f\"{name_curr} Click\")\n")
        out_lines.append("                        last_click_time = now\n")
        out_lines.append("            time.sleep(0.5)\n")
        out_lines.append("\n")
        out_lines.append("    while True:\n")
        out_lines.append("        nav_steps_2 = [\n")
        out_lines.append("            (\"fin6.bmp\", \"fin7.bmp\"),\n")
        out_lines.append("            (\"fin7.bmp\", \"fin8.bmp\"),\n")
        out_lines.append("            (\"fin8.bmp\", \"fin9.bmp\"),\n")
        out_lines.append("        ]\n")
        out_lines.append("        for name_curr, name_next in nav_steps_2:\n")
        out_lines.append("            gui_log(serial, f\"Waiting for {name_curr}...\", step=f\"{name_curr} Waiting\")\n")
        out_lines.append("            deadline = time.time() + 60\n")
        out_lines.append("            last_click_time = 0\n")
        out_lines.append("            while time.time() < deadline:\n")
        out_lines.append("                check_device_reset(serial, cycle_start)\n")
        out_lines.append("                img = get_screen_capture(device)\n")
        out_lines.append("                if img is not None:\n")
        out_lines.append("                    if img_search(img, os.path.join(IMG_DIR, name_next)):\n")
        out_lines.append("                        gui_log(serial, f\"{name_next} detected! Proceeding to next step.\", step=f\"{name_next} Seen\")\n")
        out_lines.append("                        break\n")
        out_lines.append("                    pts = img_search(img, os.path.join(IMG_DIR, name_curr))\n")
        out_lines.append("                    if pts:\n")
        out_lines.append("                        now = time.time()\n")
        out_lines.append("                        if now - last_click_time >= 5.0:\n")
        out_lines.append("                            x, y = pts[0]\n")
        out_lines.append("                            device.shell(f\"input swipe {x} {y} {x} {y} 100\")\n")
        out_lines.append("                            gui_log(serial, f\"Clicked {name_curr}\", step=f\"{name_curr} Click\")\n")
        out_lines.append("                            last_click_time = now\n")
        out_lines.append("                time.sleep(0.5)\n")
        out_lines.append("\n")
        
        # skip old nav_steps block (approx 30 lines, until "# 2. Wait, click, and verify fin9.bmp")
        while i < len(lines) and not lines[i].strip().startswith("# 2. Wait, click, and verify fin9.bmp"):
            i += 1
        continue
    
    # 2. Indent everything from "# 2. Wait, click, and verify fin9.bmp" until "# 6. Wait for checkpointfind (OCR Screen)"
    if line.strip() == "# 2. Wait, click, and verify fin9.bmp":
        # Process and indent until end of fin13
        while i < len(lines):
            l = lines[i]
            
            # Special case for Pos1 logic
            if "while True:" in l and i+2 < len(lines) and lines[i+1].strip() == "check_device_reset(serial, cycle_start)" and "Clicking Position 1" in lines[i+2]:
                out_lines.append("        need_restart = False\n")
                out_lines.append("        fixfind_first_seen = None\n")
                out_lines.append("        " + l)
                i += 1
                continue
                
            if "pts_v = img_search(img, os.path.join(IMG_DIR, \"verify.png\"), threshold=0.9)" in l and "if len(pts_v) >= 2:" in lines[i+1]:
                # inject fixfind check before verify check
                out_lines.append("                    pts_ff = img_search(img, os.path.join(IMG_DIR, \"fixfind.bmp\"), threshold=0.95)\n")
                out_lines.append("                    if pts_ff:\n")
                out_lines.append("                        if fixfind_first_seen is None:\n")
                out_lines.append("                            fixfind_first_seen = time.time()\n")
                out_lines.append("                            gui_log(serial, \"fixfind.bmp detected, watching for 15s...\", step=\"fixfind Watch\")\n")
                out_lines.append("                        elif time.time() - fixfind_first_seen >= 15.0:\n")
                out_lines.append("                            gui_log(serial, \"fixfind.bmp stuck for 15s! Restarting from fin6...\", step=\"fixfind Restart\")\n")
                out_lines.append("                            need_restart = True\n")
                out_lines.append("                            break\n")
                out_lines.append("                    else:\n")
                out_lines.append("                        fixfind_first_seen = None\n\n")
                out_lines.append("        " + l)
                i += 1
                continue
                
            if l.strip() == "if verified_pos1:":
                out_lines.append("            if need_restart or verified_pos1:\n")
                out_lines.append("                break\n")
                out_lines.append("            else:\n")
                out_lines.append("                gui_log(serial, \"Failed to find 2 verify icons in 5s! Retrying click on Position 1...\", step=\"Pos1 Retry\")\n")
                out_lines.append("\n")
                out_lines.append("        if need_restart:\n")
                out_lines.append("            continue\n")
                i += 4
                continue
                
            # Same for Pos2
            if "while True:" in l and i+2 < len(lines) and lines[i+1].strip() == "check_device_reset(serial, cycle_start)" and "Clicking Position 2" in lines[i+2]:
                out_lines.append("        fixfind_first_seen = None\n")
                out_lines.append("        " + l)
                i += 1
                continue

            if "pts_v = img_search(img, os.path.join(IMG_DIR, \"verify.png\"), threshold=0.9)" in l and "if len(pts_v) >= 3:" in lines[i+1]:
                # inject fixfind check before verify check
                out_lines.append("                    pts_ff = img_search(img, os.path.join(IMG_DIR, \"fixfind.bmp\"), threshold=0.95)\n")
                out_lines.append("                    if pts_ff:\n")
                out_lines.append("                        if fixfind_first_seen is None:\n")
                out_lines.append("                            fixfind_first_seen = time.time()\n")
                out_lines.append("                            gui_log(serial, \"fixfind.bmp detected, watching for 15s...\", step=\"fixfind Watch\")\n")
                out_lines.append("                        elif time.time() - fixfind_first_seen >= 15.0:\n")
                out_lines.append("                            gui_log(serial, \"fixfind.bmp stuck for 15s! Restarting from fin6...\", step=\"fixfind Restart\")\n")
                out_lines.append("                            need_restart = True\n")
                out_lines.append("                            break\n")
                out_lines.append("                    else:\n")
                out_lines.append("                        fixfind_first_seen = None\n\n")
                out_lines.append("        " + l)
                i += 1
                continue
                
            if l.strip() == "if verified_pos2:":
                out_lines.append("            if need_restart or verified_pos2:\n")
                out_lines.append("                break\n")
                out_lines.append("            else:\n")
                out_lines.append("                gui_log(serial, \"Failed to find 3 verify icons in 5s! Retrying click on Position 2...\", step=\"Pos2 Retry\")\n")
                out_lines.append("\n")
                out_lines.append("        if need_restart:\n")
                out_lines.append("            continue\n")
                i += 4
                continue

            if l.strip() == "# 6. Wait for checkpointfind (OCR Screen)":
                out_lines.append("        break # Successfully finished fin13, break the main retry loop\n\n")
                out_lines.append(l)
                i += 1
                break
                
            if l.strip() == "":
                out_lines.append(l)
            else:
                out_lines.append("    " + l)
            i += 1
        continue
        
    out_lines.append(line)
    i += 1

with open("d:/bot/pes/login_new.py", "w", encoding="utf-8") as f:
    f.writelines(out_lines)
print("done")

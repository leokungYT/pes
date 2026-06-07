with open('login.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the comment line
old_comment = "                                # 1. Delay 10 วินาทีก่อนเริ่มลาก จากนั้นกดค้างที่ 152 343 แล้วลากไป 310 304 (ใช้เวลาลาก 3 วินาที)"
new_comment = "                                # 1. Delay 10 วินาทีก่อนเริ่มลาก จากนั้นกดค้างที่ 96 124 แล้วลากไป 691 205 (ใช้เวลาลาก 5 วินาที)"
content = content.replace(old_comment, new_comment)

# Replace the drag command
old_drag = '                                drag_cmd = "input draganddrop 152 343 310 304 3000"'
new_drag = '                                drag_cmd = "input draganddrop 96 124 691 205 5000"'
content = content.replace(old_drag, new_drag)

# Replace the log statement
old_log = '                                gui_log(serial, "Dragging from 152 343 to 310 304...", step="Q5 Drag")'
new_log = '                                gui_log(serial, "Dragging from 96 124 to 691 205...", step="Q5 Drag")'
content = content.replace(old_log, new_log)

with open('login.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replacement successful!")

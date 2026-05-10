# ═══════════════════════════════════════════════════
#  config.py  —  ตั้งค่าบอท PES Login
# ═══════════════════════════════════════════════════

# ── Event Image Mode ───────────────────────────────
# 1  =  มี event (กด play22 → play31 ทีละภาพ)
# 0  =  ไม่มี event (เจอ play22 แล้วกด Back รัวๆ
#        จนเจอ cancel.bmp แล้วคลิก)
EVENT_IMG = 0

# ── Box Sequence (main-pes.py) ────────────────────
# 1 = เปิดกล่อง (ทำ play26-play31 และ box1-box4)
# 0 = ข้ามการเปิดกล่อง (จบที่ play25 แล้วส่งไฟล์เลย)
DO_BOX = 1

# ── Gacha Sequence (login.py) ──────────────────────
# 1 = สุ่มกาชา (ต่อจากจบ box4)
# 0 = ไม่สุ่มกาชา (จบงานปกติ)
DO_GACHA = 1

# รายชื่อนักเตะที่ต้องการเก็บ (Backup-id)
HERO_LIST = [
    "Gareth Bale",
    "Aubameyang",
    "Marcelo",
    "", # ว่างไว้ถ้าไม่ใช้
    "",
    ""
]

# ── Path ──────────────────────────────────────────
IMG_DIR           = "img"
INPUT_DIR         = "input-id"
LOGIN_SUCCESS_DIR = "login-success"

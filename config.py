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
DO_GACHA = 0

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

# ── Find Hero Sequence ─────────────────────────────
# 1 = ทำงาน fin1-fin8 และค้นหาฮีโร่ตามภาพ
# 0 = ข้าม
FIND_HERO = 0

# แมพไฟล์ภาพฮีโร่เข้ากับชื่อฮีโร่
HERO_IMG_MAP = {
    "heroo1.bmp": "sasuke",
    "heroo2.bmp": "minato",
    "heroo3.bmp": "naruto"
}

# ── Gacha Free Sequence ───────────────────────────
# 1 = ทำ gacha free หลังจบ box (gacha1 → gacha2 → เลื่อนหา gachafree1)
# 0 = ข้าม
GACHA_FREE = 1

# จำนวนลูปย่อยที่ต้องการสุ่มกาชาฟรี (เช่น 2, 3, 5)
GACHA_FREE_LOOPS = 6

# รายชื่อนักเตะที่ต้องการเก็บ (Gacha Free → backup-id)
HERO_LIST_FREE = [
    "Fabio Cannavaro",
    "Paolo Maldini",
    "Daniele De Rossi",
    "Didier Drogba",
    "Mohamed Salah",
    ""
]

# ── Debug OCR ─────────────────────────────────────
# 1 = บันทึกภาพที่สแกน OCR ทุกครั้งไว้ในโฟลเดอร์ debug-ocr/
#     (ดูได้ว่ามันสแกนอะไร ตรงไหน)
# 0 = ไม่บันทึก
DEBUG_OCR = 0

# ── Check Coin Sequence ───────────────────────────
# 1 = ทำงานสแกนเหรียญ (หา checkpointcoin.bmp → OCR สแกนหาเลขเหรียญที่ Region(52, 10, 106, 41) → บันทึกลง check-coin)
# 0 = ข้าม
CHECK_COIN = 0

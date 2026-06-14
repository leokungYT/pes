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

# ── Gacha + Check Mode ──────────────────────────────
# 1 = สุ่มกาชาเสร็จแล้วกด backhome ต่อด้วยค้นหาฮีโร่ทันที
# 0 = ข้าม
GACHA_CHECK = 0

# ── Gacha + Find Mode (DO_GACHA) ────────────────────
# 1 = สุ่มกาชาแบบเสียเงิน (DO_GACHA) เสร็จแล้ว "ไม่ต้อง clear app"
#     กด backhome ต่อด้วยค้นหาฮีโร่ทันที (ทำงานเหมือน gachafree+check)
# 0 = ข้าม (สุ่มกาชาเสร็จแล้วปิดแอปจบรอบตามปกติ)
GACHA_FIND = 1

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
GACHA_FREE = 0

# จำนวนลูปย่อยที่ต้องการสุ่มกาชาฟรี (เช่น 2, 3, 5)
GACHA_FREE_LOOPS = 10

# รายชื่อนักเตะที่ใช้สแกนหา (หากเจอชื่อซ้ำกัน ระบบจะตรวจจับและใส่ x2, x3 ต่อท้ายให้อัตโนมัติ)
list_find_hero = [
    "Fabio Cannavaro",
    "Paolo Maldini",
    "Daniele De Rossi",
    "Didier Drogba",
    "Mohamed Salah",
    "Nico Paz",
    "Federico Dimarco",
    "Luka",
    "rgson",
    "Arribas",
    "Ramedhan Saifullah",
    "Chrigor",
    "Lamine=x2",
    "Mbappe",
    "Joan Garcia",
    "Martin Odegaard",
    "Atep",
    "Gareth Bale",
    "Aubameyang",
    "Marcelo",
    "Peter Schmeichel",
    "Leonardo Bonucci",
    "Ronald Koeman",
    "Casemiro",
    "Erling Haaland",
    "Hugo Ekitike",
    "Declan Rice",
    "Hidetoshi Nakata",
    "Seigo Narazaki",
    "Shunsuke Nakamura",
    "Vitinha",
    "David Raya",
    "Kvaratskhelia",
    "Johan Cruyff",
    "Filippo Inzaghi",
    "Jordi Alba",
    "Oliver Kahn",
    "David Beckham",
    "Rivaldo",
    "Gianluigi Buffon",
    "Andrea Pirlo",
    "Gialuca Zambrotta",
    ""
]

# แชร์ list เดียวกัน — แก้ที่ list_find_hero อย่างเดียวพอ
HERO_LIST_FREE = list_find_hero


# ── Debug OCR ─────────────────────────────────────
# 1 = บันทึกภาพที่สแกน OCR ทุกครั้งไว้ในโฟลเดอร์ debug-ocr/
#     (ดูได้ว่ามันสแกนอะไร ตรงไหน)
# 0 = ไม่บันทึก
DEBUG_OCR = 0

# ── Check Coin Sequence ───────────────────────────
# 1 = ทำงานสแกนเหรียญ (หา checkpointcoin.bmp → OCR สแกนหาเลขเหรียญที่ Region(52, 10, 106, 41) → บันทึกลง check-coin)
# 0 = ข้าม
CHECK_COIN = 0

# ── No Scan Mode ──────────────────────────────────
# 1 = ข้ามขั้นตอน checkpointgacha (ไม่สแกน OCR)
#     ข้ามไปหา next.bmp ต่อเลย
#     ไฟล์จะเก็บในโฟลเดอร์ fast-random/ แทน backup-id/
# 0 = ทำงานปกติ (สแกน OCR ที่ checkpointgacha)
NOSCAN = 1

# ── Skip Animation (Gacha Free) ──────────────────
# 1 = หลังกด gachafree2 จะกดตำแหน่ง [611,129] ซ้ำๆเร็วๆ
#     จนกว่าจะเจอ skiphero.bmp แล้วคลิก → ไปหา next ต่อ
# 0 = ทำงานปกติ (ไม่กดข้ามแอนิเมชั่น)
SKIPANIMATION = 1

# ── Login Fast Mode ───────────────────────────────
# 1 = เจอ checkpointlogin ปุ๊บ clear app จบรอบทันที (เร็วสุด)
# 0 = ทำงานปกติ (กด checkpointlogin แล้วไปต่อ)
LOGIN_FAST = 0

# ── Timeout ───────────────────────────────────────
# 1 = Enable, 0 = Disable
TIMEOUT_ENABLE = 0

# Timeout duration in minutes
TIMEOUT_MINUTES = 10

# ── Autorun on Launch ──────────────────────────────
# 1 = เปิดโปรแกรมแล้วสแกนและรันบอทอัตโนมัติทันที
# 0 = ปิดการทำงานอัตโนมัติ (ต้องกดปุ่ม START เอง)
AUTORUN = 0

# ── Silent Update Mode ─────────────────────────────
# 'keep'  = สั่งอัปเดตแบบไม่ลบไฟล์เดิม (รักษาข้อมูลรหัสไอดีและฮีโร่ทั้งหมด)
# 'clean' = สั่งอัปเดตแบบล้างข้อมูลทั้งหมด (ลบไฟล์เก่าในระบบออกทั้งหมด)
SILENT_UPDATE_MODE = 'keep'

# ── Overwrite Config on Update ─────────────────────
# True  = อนุญาตให้อัปเดตไฟล์ config.py ตามเครื่องแม่ (GitHub Release)
# False = ห้ามเขียนทับไฟล์ config.py (เก็บการตั้งค่าเดิมของเครื่องลูกไว้)
OVERWRITE_CONFIG_ON_UPDATE = True

# ── Get Code Sequence ─────────────────────────────
# 1 = ทำขั้นตอน getcode (getcode1→getcode6 + พิมพ์โค้ด) ก่อน Box
# 0 = ข้าม
GETCODE = 0

# ข้อความที่จะพิมพ์ในช่อง code (สามารถเปลี่ยนได้ตามต้องการ)
GETCODE_TEXT = "eFCONNECT"

# ── Get Quest Sequence ─────────────────────────────
# 1 = ทำขั้นตอน getquest (เก็บรางวัลเควส) ก่อน Box
# 0 = ข้าม
GETQUEST = 0

# ── Send Code (playcode.py) ────────────────────────
# โค้ดที่จะกรอกในขั้นตอน sendcode (เปลี่ยนได้ตามต้องการ)
SEND_CODE = "M-CBFTKHBALEF"

# โฟลเดอร์รูป getquest (อยู่ใน img/getquest/)
GETQUEST_IMG_DIR = "img/getquest"

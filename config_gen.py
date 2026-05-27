# ═══════════════════════════════════════════════════
#  config_gen.py  —  ตั้งค่าบอทสำหรับ main-pes.py
# ═══════════════════════════════════════════════════

# ── Event Image Mode ───────────────────────────────
# 1  =  มี event (กด play22 → play31 ทีละภาพ)
# 0  =  ไม่มี event (เจอ play22 แล้วกด Back รัวๆ
#        จนเจอ cancel.bmp แล้วคลิก)
EVENT_IMG = 1

# ── Box Sequence (main-pes.py) ────────────────────
# 1 = เปิดกล่อง (ทำ play26-play31 และ box1-box4)
# 0 = ข้ามการเปิดกล่อง (จบที่ play25 แล้วส่งไฟล์เลย)
DO_BOX = 1

# ── Gacha Free Sequence ───────────────────────────
# 1 = ทำ gacha free หลังจบ box (gacha1 → gacha2 → เลื่อนหา gachafree1)
# 0 = ข้าม
GACHA_FREE = 1

# จำนวนลูปย่อยที่ต้องการสุ่มกาชาฟรี (เช่น 2, 3, 6)
GACHA_FREE_LOOPS = 3

# รายชื่อนักเตะที่ต้องการเก็บ (Gacha Free → found-hero)
HERO_LIST_FREE = ['Fabio Cannavaro', 'Paolo Maldini', 'Daniele De Rossi', 'Didier Drogba', 'Mohamed Salah', 'Nico Paz', 'Federico Dimarco', 'Luka', 'rgson', 'Arribas', 'Ramedhan Saifullah', 'Chrigor', 'Lamine Yamal', 'Kylian Mbappe', 'Joan Garcia', 'Martin Odegaard', 'Atep']

# ── Path ──────────────────────────────────────────
IMG_DIR = "img"

# ── Debug OCR ─────────────────────────────────────
# 1 = บันทึกภาพที่สแกน OCR ทุกครั้งไว้ในโฟลเดอร์ debug-ocr/
# 0 = ไม่บันทึก
DEBUG_OCR = 0

# ── No Scan Mode ──────────────────────────────────
# 1 = ข้ามขั้นตอน checkpointgacha (ไม่สแกน OCR)
#     ข้ามไปหา next.bmp ต่อเลย
#     ไฟล์จะเก็บในโฟลเดอร์ fast-random/ แทน backup-id/
# 0 = ทำงานปกติ (สแกน OCR ที่ checkpointgacha)
NOSCAN = 0

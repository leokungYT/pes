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

# ── New Gacha Sequence (login.py) ──────────────────
# 1 = เปิดการทำงาน new-gacha1 -> เลื่อนหา new-gacha1 -> ข้ามไป gacha4.bmp
# 0 = ปิด
NEW_GACHA = 0

# ── New Gacha Swipe (เลื่อนหน้าจอ) ──────────────────
# 1 = เปิดการเลื่อนหน้าจอ (swipe 144,243 -> 699,233) ตอนหา new-gacha1
# 0 = ปิดการเลื่อน (รอเฉยๆ ไม่ swipe)
NEW_GACHA_SWIPE = 0

# ── Custom Gacha Loop Mode ──────────────────────────
# 1 = เปิดโหมด Custom Gacha (loopgacha1 -> gacha4 -> gacha5 -> loop จนเจอ outloop)
# 0 = ปิดโหมด
CUSTOM_GACHA = 0

# ── Custom Gacha Loop Limit (ใช้คู่กับ "สุ่มจน coin หมด") ──
# 0  = สุ่มจนหมด (จนเจอ nocions/outloop) — พฤติกรรมเดิม
# >0 = Custom: สุ่มไม่เกินกี่รอบแล้ว break ออกเลย (เช่น 5 = สุ่มแค่ 5 รอบ)
GACHA_LOOP_LIMIT = 0

# ── GACHA500: step พิเศษ (หลังเจอ checkpoint-gacha4) ──
# *** ไม่ต้องเปิด CUSTOM_GACHA แล้ว — GACHA500 = 1 เข้า flow นี้ได้เอง ***
# 1 = เปิด step1 + step2:
#     • step1: ที่หน้า new-gacha1 → OCR อ่าน coin (region 52,10,106,41) 1 ครั้ง/รอบ
#         - coin >= COIN_GACHA_THRESHOLD → เก็บไฟล์เข้าโฟลเดอร์ coin<threshold>+ (ชื่อ [coin]+เดิม) แล้วจบบัญชี
#         - coin <  COIN_GACHA_THRESHOLD → สุ่ม loop ต่อ
#     • step2: gacha4v2 → gacha5v2 (สุ่ม 1 ครั้ง) → checkpointgacha → next
#              → gacha500 → gacha500v1 → nocions (Back 1 ครั้ง) / checkpointgacha (กด next จนหาย)
#              เจอ out900 เมื่อไหร่ = ข้าม step ที่เหลือทันที
# 0 = ปิด → สุ่ม loop แบบปกติ (ไม่เช็ค coin / ไม่หา gacha500)
GACHA500 = 0
# เกณฑ์ coin ที่จะ "เก็บ" (>= ค่านี้เก็บ, < ค่านี้สุ่มต่อ) — ชื่อโฟลเดอร์จะเป็น coin<ค่านี้>+
COIN_GACHA_THRESHOLD = 800

# ── One Gacha500: ทำ v2/gacha500 "รอบเดียวพอ" แล้วจบเลย ──
# 1 = ทำ step v2/gacha500 รอบเดียว → จบลูปสุ่มทันที (ไม่วนไปทำ gacha4 ต่อ)
# 0 = ทำ v2/gacha500 รอบเดียว แล้ววน gacha4 ต่อจนครบ GACHA_LOOP_LIMIT (ค่าเดิม)
ONE_GACHA500 = 0

# ── Gacha + Check Mode ──────────────────────────────
# 1 = สุ่มกาชาเสร็จแล้วกด backhome ต่อด้วยค้นหาฮีโร่ทันที
# 0 = ข้าม
GACHA_CHECK = 0

# ── Gacha + Find Mode (DO_GACHA) ────────────────────
# 1 = สุ่มกาชาแบบเสียเงิน (DO_GACHA) เสร็จแล้ว "ไม่ต้อง clear app"
#     กด backhome ต่อด้วยค้นหาฮีโร่ทันที (ทำงานเหมือน gachafree+check)
# 0 = ข้าม (สุ่มกาชาเสร็จแล้วปิดแอปจบรอบตามปกติ)
GACHA_FIND = 0

# รายชื่อนักเตะที่ต้องการเก็บ (Backup-id)
HERO_LIST = [
    "Gareth Bale",
    "Aubameyang",
    "Marcelo",
    "Lilian Thuram", # ว่างไว้ถ้าไม่ใช้
    "Patrick Vieira",
    "Marcel Desailly"
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
    "Aubameyang",
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
    "Lilian Thuram", 
    "Patrick Vieira",
    "Marcel Desailly",
    "Luis Suarez",
    "Schweinsteiger",
    "Bronckhorst",
    "Rodri",
    "Marc Cucurella",
    "Unai Simon",
    "Dani Olmo",
    "Ferran Torres",
    "Harry Kane",
    "Cristian Romero",
    "Lionel Messi",
    "Kevin De Bruyne",
    "James Rodriguez",
    "Nevmar",
    "Luka Modric",
    "Manuel Neuer",
    "Cristiano Ronaldo",
    "Jude Bellingham",
    "Ayyoub Bouaddi",
    "Michael Olise",
    "Enzo Fernandez",
    "Johan Manzambi"
]

# แชร์ list เดียวกัน — แก้ที่ list_find_hero อย่างเดียวพอ
HERO_LIST_FREE = list_find_hero


# ── Extra Find (ยืนยันซ้ำด้วยรูปภาพ) ────────────────
# ชื่อที่ใส่ไว้ใน dict นี้ ต้อง "OCR สแกนเจอชื่อ" + "เจอรูปในหน้าจอด้วย" ถึงจะนับว่าเจอ
#   - OCR เจอ + รูป match  → นับว่าเจอ
#   - OCR เจอ แต่ไม่เจอรูป → ไม่นับ (กัน OCR อ่านผิด/มั่ว)
#   - ชื่อที่ไม่ได้ใส่ในนี้ → ใช้ OCR อย่างเดียวเหมือนเดิม
# path รูป = img/extar/<ชื่อไฟล์>   (นามสกุล .png/.bmp สลับกันได้ ระบบหาให้เอง)
# ปิดฟีเจอร์นี้ = ปล่อยเป็น dict ว่าง  EXTAR_FIND = {}
EXTAR_FIND = {
    "Lionel Messi": "extarfind1.png",
    "Mbappe": "extarfind2.png"
}

# ความแม่นตอนเทียบรูปของ EXTAR_FIND (0.0 - 1.0) — ยิ่งสูงยิ่งเข้มงวด
EXTAR_FIND_THRESHOLD = 0.8


# ── Debug OCR ─────────────────────────────────────
# 1 = บันทึกภาพที่สแกน OCR ทุกครั้งไว้ในโฟลเดอร์ debug-ocr/
#     (ดูได้ว่ามันสแกนอะไร ตรงไหน)
# 0 = ไม่บันทึก
DEBUG_OCR = 0

# ── Debug Console ─────────────────────────────────
# 1 = โชว์ log ลงหน้าต่าง cmd (ไว้ดูตอน debug)
# 0 = ไม่ print ลง cmd เลย (รันจริง — กัน cmd ค้างจาก console + เบาเครื่อง)
#     *** log ยังถูกเซฟลงไฟล์ในโฟลเดอร์ logs/ ครบทุกกรณี ***
DEBUG_CONSOLE = 0

# ── Check Coin Sequence ───────────────────────────
# 1 = ทำงานสแกนเหรียญ (หา checkpointcoin.bmp → OCR สแกนหาเลขเหรียญที่ Region(52, 10, 106, 41) → บันทึกลง check-coin)
# 0 = ข้าม
CHECK_COIN = 0

# ── Min Coin to Gacha (ใช้ร่วมกับ Check Coin) ──────
# เลขเหรียญขั้นต่ำที่จะ "สุ่ม" — ถ้าสแกนเหรียญได้ "น้อยกว่า" ค่านี้:
#   • ถ้าเปิด Find  → ข้ามขั้นตอนสุ่ม (gacha/gacha free) ไปทำขั้นตอน fin เลย
#   • ถ้าไม่เปิด Find (สุ่มอย่างเดียว) → จบรอบทันที (ไม่สุ่ม)
# ใช้ทั้งใน Gacha mode และ Gacha Free mode (ทำงานเฉพาะเมื่อเปิด Check Coin)
GACHA_MIN_COIN = 100

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

# ── Move login-success → input-id (ตั้งเวลา) ────────
# 1 = ย้ายไฟล์ทั้งหมดจาก login-success → input-id อัตโนมัติทุกวันตามเวลา MOVE_LS_TIME
# 0 = ปิด (ย้ายเองด้วยปุ่มในหน้า config ได้ตลอด)
MOVE_LS_ENABLE = 0
# เวลาที่จะย้ายอัตโนมัติ (รูปแบบ HH:MM 24 ชั่วโมง เช่น "09:00")
MOVE_LS_TIME = "09:00"

# ── cap-id.py: รูปแบบการเก็บผลลัพธ์ ────────────────
# 1 = (ALL) เก็บไฟล์ .dat + รูป .png ลงในโฟลเดอร์ cap-id-result ตรงๆ (ไม่มีโฟลเดอร์ย่อย)
# 0 = แยกโฟลเดอร์ย่อยตามชื่อไฟล์ .dat เดิม → cap-id-result/<ชื่อ>/<uid>.png|.dat
CAP_ALL = 0

# ── เปิด/ปิด root ─────────────────────────────────────────────────────
# MuMu Player ตรวจ root จาก root_permission setting (ไม่ใช่ adb root)
# toggle root_permission ผ่าน MuMuManager มีผล "ทันที (live)" ไม่ต้อง restart
#   root_permission=false → เกมไม่เจอ root (เปิดเกมผ่าน)
#   su -c ยังใช้ได้เสมอจาก adb shell ไม่ว่า root_permission จะ true/false
#
# USE_MUMU_ROOT = True  → เปิด/ปิด root ผ่าน MuMuManager (สำหรับ MuMu)
# USE_MUMU_ROOT = False → ใช้ adb root/unroot (สำหรับ AVD ธรรมดา)
USE_MUMU_ROOT = True

# path ของ MuMuManager.exe (ดูจาก info: nx_main\MuMuManager.exe)
MUMU_MANAGER = r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe"
# index ของ instance — ดูได้จาก:  MuMuManager.exe info -v all  (instance ที่รันจริงคือ index 1)
MUMU_INDEX = "1"

# จัดการไฟล์ด้วย su -c หรือไม่
#   True  = MuMu (root ผ่าน su, adb shell ไม่ใช่ root)  ← ต้องเป็น True เมื่อ USE_MUMU_ROOT
#   False = adb root mode (adb shell เป็น root อยู่แล้ว)
USE_SU = True

# เวลารอหลัง adb root/unroot (เฉพาะโหมด adb root, USE_MUMU_ROOT=False) (วินาที)
ROOT_TOGGLE_WAIT = 3

# ── CPU Affinity Balancer (เครื่อง 2 socket / NUMA / >64 logical processors) ──
# True  = เกลี่ย process ของ MuMu ให้กระจายข้ามทุก processor group (ทั้ง 2 socket)
#         แก้อาการ MuMu ค้าง (Not Responding) บน Dual Xeon ที่โหลดกองอยู่ socket เดียว
#         (ทำงานเฉพาะเครื่องที่มี >1 processor group — เครื่อง socket เดียวจะข้ามให้เอง)
# False = ปิด (ปล่อยให้ Windows จัดการ affinity เอง)
CPU_AFFINITY_BALANCE = True

# ── Auto Restart เครื่องที่ ADB หลุด (offline ค้าง) ──────────────────────
# อาการ: log ขึ้น "⚠️ Device OFFLINE — reconnecting & waiting..." วนไม่จบ
#        = adb connect กลับไม่ได้แล้ว (MuMu instance ค้าง/ดับไปเอง)
#
# 1 = เครื่องไหน offline ติดกันนานเกิน OFFLINE_RESTART_AFTER วิ
#     → สั่ง MuMuManager ปิด-เปิด "เฉพาะ instance นั้นตัวเดียว" (เช่น 127.0.0.1:5579)
#       รอบูตกลับมา แล้วเริ่มกระบวนการใหม่ตั้งแต่ต้นของเครื่องนั้น
#     *** เครื่องอื่นไม่โดนแตะเลย ทำงานต่อตามปกติ ***
# 0 = ปิด (แค่ reconnect วนไปเรื่อยๆ แบบเดิม)
AUTO_RESTART_OFFLINE = 1

# offline ติดกันกี่วินาที ถึงจะยอมสั่ง restart (ต่ำไป = restart ทั้งที่มันกำลังจะกลับมาเอง)
OFFLINE_RESTART_AFTER = 90

# รอ instance บูตกลับมา online สูงสุดกี่วินาที (MuMu บูตช้าได้ถ้าเครื่องโหลดหนัก)
OFFLINE_BOOT_WAIT = 240

# หลังสั่ง restart เครื่องหนึ่งแล้ว ห้ามสั่ง restart เครื่องเดิมซ้ำภายในกี่วินาที
# (กันวนรีสตาร์ทรัวๆ ตอนเครื่องนั้นเสียจริงๆ)
OFFLINE_RESTART_COOLDOWN = 600

# ── โหลดที่ยิงใส่ ADB (กัน adb server ล้นจนจอหลุดเป็น offline) ──────────
# screencap 1 เฟรมคือ raw RGBA ไม่บีบอัด (540x960 ≈ 2 MB) และทุกจอวิ่งผ่าน
# adb server process เดียวกัน → เปิดหลายจอพร้อมกันแล้วยิงรัว = คอขวดจุดเดียว
#
# 1) เพดาน "จำนวนจอที่แคปจอพร้อมกันได้" ทั้งระบบ  ← ตัวสำคัญที่สุด
#    จอที่เกินโควตาจะรอคิวแป๊บเดียว (ปกติไม่ถึงวินาที) ไม่ได้ทำให้บอทช้าลงจริง
#    เปิด 72 จอ แนะนำ 12-16 / เปิดไม่กี่จอ ตั้งสูงได้หรือใส่ 0 = ไม่จำกัด
SCREENCAP_MAX_CONCURRENT = 12
#
# 2) เว้นระยะขั้นต่ำระหว่างการแคปจอ "ของจอเดียวกัน" (วินาที)
#    0.25 = แคปได้ไม่เกิน 4 ครั้ง/วิ/จอ — เพิ่มเป็น 0.4-0.5 ถ้ายังหลุดอยู่
#    (ยิ่งมาก = ยิง adb เบาลง แต่บอทตอบสนองช้าลงนิดหน่อย)
SCREENCAP_INTERVAL = 0.25

# ── ROI Cache: จำตำแหน่งปุ่ม ไม่ต้องกวาดหารูปทั้งจอทุกรอบ ──────────────
# ทุกเฟรมบอทต้องไล่หา popup 12-18 รูป (fixnet/download/sell/failed/fixout/...)
# กวาดเต็มจอ 1 รูป ≈ 12 ms → 25 จอ กินไปราว 15 CPU core เฉพาะงานนี้
#
# 1 = จำไว้ว่า "เจอรูปนั้นล่าสุดตรงไหน" รอบถัดไปเทียบเฉพาะกรอบเล็กๆ ตรงนั้นก่อน
#     (≈ 0.3 ms เร็วขึ้น ~40 เท่า) ไม่เจอที่เดิม → ถอยไปกวาดเต็มจอเองอัตโนมัติ
#     ผลลัพธ์ตรงกับแบบเดิมเป๊ะ ต่างแค่เร็วขึ้น
# 0 = ปิด กวาดเต็มจอทุกครั้งแบบเดิม
IMG_ROI_CACHE = 1

# ขนาดกรอบเผื่อรอบตำแหน่งเดิม (พิกเซล) — ปุ่มขยับได้ไม่เกินเท่านี้ถึงจะยังเจอในกรอบ
# ใหญ่ไป = ช้าลง / เล็กไป = หลุดกรอบบ่อย ต้องกวาดเต็มจอ (ไม่ผิด แค่ไม่ได้กำไร)
IMG_ROI_PAD = 40

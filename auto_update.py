import os
import urllib.request
import json
import zipfile
import shutil
import io
import sys
import subprocess
import tkinter as tk
from tkinter import font as tkfont

# ชื่อ Repository ของคุณบน GitHub
REPO = "leokungYT/pes"
VERSION_FILE = "version.txt"

# ── ช่องทางโหลดไฟล์อัปเดต (ลองไล่ทีละอันจนกว่าจะได้) ─────────────────
#    เจอบ่อย: raw.githubusercontent (เช็คเวอร์ชัน) ผ่าน แต่ github.com/codeload
#    ที่ใช้โหลด ZIP โดน timeout (WinError 10060) เพราะเน็ต/ISP บล็อกคนละโดเมนกัน
def _zip_candidates(zip_url):
    urls = []
    if zip_url:
        urls.append(zip_url)
    urls.append(f"https://github.com/{REPO}/archive/refs/heads/main.zip")
    urls.append(f"https://codeload.github.com/{REPO}/zip/refs/heads/main")
    # มิเรอร์สำรอง — เรียงตามผลทดสอบจริง (ghfast.top ตัดออก: SSL cert verify failed)
    for pre in ("https://ghproxy.net/", "https://gh-proxy.com/"):
        urls.append(pre + f"https://github.com/{REPO}/archive/refs/heads/main.zip")
    seen, out = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def download_update_zip(zip_url, tries_each=2, timeout=300):
    """โหลดไฟล์ ZIP อัปเดต — ลองทุกช่องทาง ช่องทางละ tries_each ครั้ง
    คืน bytes ของ zip (ตรวจ magic 'PK' ก่อน) หรือ raise ถ้าไม่ได้เลยสักช่องทาง

    *** timeout ต้องยาว: ZIP ของรีโปนี้ ~28 MB (มี Tesseract-OCR + รูปทั้งหมด)
        ของเดิมตั้งไว้ 30 วิ เน็ตเครื่องลูกโหลดไม่ทัน เลยเด้ง WinError 10060 ***"""
    import time as _time
    last_err = "ไม่ทราบสาเหตุ"
    for url in _zip_candidates(zip_url):
        for attempt in range(1, tries_each + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                if len(data) > 1000 and data[:2] == b"PK":
                    print(f"[Updater] Downloaded OK ({len(data):,} bytes) from {url}")
                    return data
                last_err = f"ไฟล์ที่ได้ไม่ใช่ zip ({len(data)} bytes)"
            except Exception as e:
                last_err = str(e)
            print(f"[Updater] โหลดไม่สำเร็จ (ครั้งที่ {attempt}/{tries_each}) {url} -> {last_err[:110]}")
            _time.sleep(3)
    raise RuntimeError(f"โหลดไฟล์อัปเดตไม่สำเร็จทุกช่องทาง: {last_err}")

def get_latest_release():
    # 🌟 ดึงข้อมูลเวอร์ชันผ่าน Raw Content ของกิ่งหลัก (main) และใช้ ZIP ล่าสุดของกิ่งนั้นโดยตรง
    # ข้อดี: พี่เพียงแค่แก้เลขเวอร์ชันใน version.txt แล้ว push ขึ้น GitHub บอตเครื่องลูกจะอัปเดตทันที (ไม่ต้องกดสร้าง Release/Tag บนเว็บ)
    url = f"https://raw.githubusercontent.com/{REPO}/main/version.txt"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            tag_name = response.read().decode().strip()
            # ใช้ไฟล์ ZIP ล่าสุดจากกิ่ง main
            zip_url = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
            return tag_name, zip_url
    except Exception as e:
        try:
            url_alt = f"https://raw.githubusercontent.com/{REPO}/master/version.txt"
            req = urllib.request.Request(url_alt, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                tag_name = response.read().decode().strip()
                # ใช้ไฟล์ ZIP ล่าสุดจากกิ่ง master
                zip_url = f"https://github.com/{REPO}/archive/refs/heads/master.zip"
                return tag_name, zip_url
        except Exception as e_alt:
            print(f"[Updater] Failed to check for updates (Raw Content): {e_alt}")
            return None, None

def get_local_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

def get_update_mode():
    """โหมดอัปเดตจาก config: 'keep' = เก็บข้อมูลเดิม (ดีฟอลต์) / 'clean' = ล้างทั้งหมด"""
    try:
        from config import SILENT_UPDATE_MODE
        return SILENT_UPDATE_MODE if SILENT_UPDATE_MODE in ["keep", "clean"] else "keep"
    except Exception:
        return "keep"


def is_unattended():
    """True = อัปเดตเองทั้งหมด ไม่มีป๊อปอัพให้กด ไม่มี pause (ดีฟอลต์ = True)

    เปิดเครื่องลูกทิ้งไว้หลายสิบเครื่องแล้วต้องเดินไปกดปุ่มทีละเครื่องไม่ไหว
    ปิดโหมดนี้ (กลับไปมีหน้าต่างถาม) ได้ด้วยการใส่ AUTO_UPDATE_NO_ASK = False ใน config.py
    """
    try:
        from config import AUTO_UPDATE_NO_ASK
        return bool(AUTO_UPDATE_NO_ASK)
    except Exception:
        return True


def ask_custom_update_ui(new_version):
    """สร้างหน้าต่าง UI ตักเตือนและถามอัปเดตขนาดใหญ่แบบพรีเมียม (ภาษาไทยสมบูรณ์)"""
    result = {"update": False}
    
    root = tk.Tk()
    root.title("⚠️ แจ้งเตือน: ตรวจพบเวอร์ชันใหม่ (New Update Found)")
    root.geometry("720x370")
    root.resizable(False, False)
    root.configure(bg="#FDFEFE")
    
    # นำหน้าต่างขึ้นมาบนสุดเสมอ
    root.attributes("-topmost", True)
    
    # ปรับตำแหน่งหน้าต่างให้อยู่กึ่งกลางหน้าจอ
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"+{x}+{y}")

    # ตั้งค่าฟอนต์อักษรให้มีขนาดใหญ่ชัดเจน
    title_font = tkfont.Font(family="Segoe UI", size=15, weight="bold")
    body_font = tkfont.Font(family="Segoe UI", size=11, weight="normal")
    warning_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    btn_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

    # ส่วนหัวแถบเตือนสีแดงอ่อนสุดพรีเมียม
    header_frame = tk.Frame(root, bg="#FADBD8", height=65)
    header_frame.pack(fill="x")
    
    lbl_title = tk.Label(
        header_frame, 
        text="⚠️ ตรวจพบเวอร์ชันใหม่ (New Version Detected: " + new_version + ")", 
        font=title_font, 
        fg="#C0392B", 
        bg="#FADBD8",
        pady=15
    )
    lbl_title.pack()

    # ส่วนเนื้อหาข่าวสารเตือน
    content_frame = tk.Frame(root, bg="#FDFEFE", padx=30, pady=20)
    content_frame.pack(fill="both", expand=True)

    msg1 = "การอัปเดตอัตโนมัติ (Auto Update) จะดาวน์โหลดโค้ดเวอร์ชันล่าสุดเขียนทับระบบบอททั้งหมด"
    msg2 = "🔴 คำเตือนเกี่ยวกับการล้างไฟล์:\nหากเลือกแบบ 'ล้างข้อมูลทั้งหมด' ระบบจะลบไฟล์ใน input-id, backup-id และพบฮีโร่ออกทั้งหมด!\nหากต้องการรักษารหัสและข้อมูลเดิมไว้ กรุณาเลือก 'ไม่ลบไฟล์เดิม'"
    msg3 = "กรุณาเลือกโหมดการอัปเดตที่ท่านต้องการ:"

    tk.Label(content_frame, text=msg1, font=body_font, bg="#FDFEFE", fg="#2C3E50", justify="left").pack(anchor="w", pady=2)
    
    lbl_warning = tk.Label(content_frame, text=msg2, font=warning_font, bg="#FDFEFE", fg="#C0392B", justify="left")
    lbl_warning.pack(anchor="w", pady=8)
    
    tk.Label(content_frame, text=msg3, font=body_font, bg="#FDFEFE", fg="#2C3E50", justify="left").pack(anchor="w", pady=5)

    # ส่วนปุ่มกดขนาดใหญ่
    btn_frame = tk.Frame(content_frame, bg="#FDFEFE", pady=20)
    btn_frame.pack(fill="x")

    def on_keep():
        result["update"] = "keep"
        root.destroy()

    def on_clean():
        result["update"] = "clean"
        root.destroy()

    def on_no():
        result["update"] = False
        root.destroy()

    # ปุ่มอัปเดตแบบไม่ลบไฟล์
    btn_keep = tk.Button(
        btn_frame, 
        text="อัปเดตแบบไม่ลบไฟล์เดิม (Keep Files)", 
        font=btn_font, 
        fg="white", 
        bg="#27AE60", 
        activebackground="#2ECC71",
        activeforeground="white",
        relief="flat",
        padx=10,
        pady=8,
        cursor="hand2",
        command=on_keep
    )
    btn_keep.pack(side="left", padx=5)

    # ปุ่มอัปเดตแบบล้างข้อมูลทั้งหมด
    btn_clean = tk.Button(
        btn_frame, 
        text="อัปเดตแบบล้างข้อมูลทั้งหมด (Clean)", 
        font=btn_font, 
        fg="white", 
        bg="#C0392B", 
        activebackground="#E74C3C",
        activeforeground="white",
        relief="flat",
        padx=10,
        pady=8,
        cursor="hand2",
        command=on_clean
    )
    btn_clean.pack(side="left", padx=5)

    # ปุ่มยกเลิก
    btn_no = tk.Button(
        btn_frame, 
        text="ยกเลิก (Cancel)", 
        font=btn_font, 
        fg="white", 
        bg="#7F8C8D", 
        activebackground="#95A5A6",
        activeforeground="white",
        relief="flat",
        padx=15,
        pady=8,
        cursor="hand2",
        command=on_no
    )
    btn_no.pack(side="right", padx=5)

    # ── นับถอยหลัง 10 วิ ไม่มีใครกด = เลือก "ไม่ลบไฟล์เดิม (Keep Files)" ให้เอง ──
    #    (เครื่องลูกหลายสิบเครื่อง เดินไปกดทีละเครื่องไม่ไหว — กดเองได้ตลอด ไม่ต้องรอครบ)
    countdown = {"left": 10}
    lbl_count = tk.Label(content_frame, text="", font=body_font, bg="#FDFEFE", fg="#7F8C8D")
    lbl_count.pack(anchor="w")

    def _tick():
        if result["update"] is not False and result["update"]:
            return                      # มีคนกดไปแล้ว
        n = countdown["left"]
        if n <= 0:
            lbl_count.config(text="⏱ หมดเวลา — อัปเดตแบบไม่ลบไฟล์เดิมอัตโนมัติ")
            on_keep()
            return
        lbl_count.config(text=f"⏱ ไม่กดอะไรภายใน {n} วินาที จะอัปเดตแบบ 'ไม่ลบไฟล์เดิม' ให้อัตโนมัติ")
        btn_keep.config(text=f"อัปเดตแบบไม่ลบไฟล์เดิม (Keep Files) — {n}s")
        countdown["left"] = n - 1
        root.after(1000, _tick)

    _tick()

    root.mainloop()
    return result["update"]

def show_custom_info_popup(title, message):
    """หน้าต่างป๊อปอัปแจ้งเตือนอัปเดตเสร็จสิ้นแบบพรีเมียม"""
    root = tk.Tk()
    root.title(title)
    root.geometry("500x200")
    root.resizable(False, False)
    root.configure(bg="#FDFEFE")
    root.attributes("-topmost", True)
    
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"+{x}+{y}")
    
    title_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
    body_font = tkfont.Font(family="Segoe UI", size=10, weight="normal")
    btn_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
    
    tk.Label(root, text=title, font=title_font, fg="#27AE60", bg="#FDFEFE", pady=15).pack()
    tk.Label(root, text=message, font=body_font, fg="#2C3E50", bg="#FDFEFE", justify="center").pack(pady=5)
    
    def on_ok():
        root.destroy()

    btn_confirm = tk.Button(
        root, 
        text="เข้าใจแล้ว (OK)", 
        font=btn_font, 
        fg="white", 
        bg="#2980B9", 
        activebackground="#3498DB",
        activeforeground="white",
        relief="flat",
        padx=30,
        pady=6,
        cursor="hand2",
        command=on_ok
    )
    btn_confirm.pack(pady=15)

    # ปิดเองใน 10 วิ ถ้าไม่มีใครกด (ไม่ให้หน้าต่างค้างขวางการเปิดบอทใหม่)
    root.after(10000, lambda: root.destroy() if root.winfo_exists() else None)

    root.mainloop()

def update(silent=False, force=False, no_relaunch=False):
    print("[Updater] Checking for latest release on GitHub...")
    latest_version, zip_url = get_latest_release()

    if not latest_version or not zip_url:
        sys.exit(0)

    local_version = get_local_version()

    if local_version == latest_version:
        if force:
            # --force: ดึงโค้ด+config ล่าสุดมาทับใหม่ แม้เลขเวอร์ชันจะตรงกัน
            #   (ใช้ตอนกดปุ่ม "อัปเดตบอท" ในหน้า remote แล้วอยากให้ sync โค้ดสดทุกครั้ง)
            print(f"[Updater] Already on {latest_version}, but --force set → re-downloading anyway.")
        else:
            print(f"[Updater] You are already on the latest version ({latest_version}).")
            sys.exit(0)
    else:
        print(f"[Updater] New version found: {latest_version}.")
    
    if silent or is_unattended():
        # โหมดอัตโนมัติ (เงียบ / ไม่ถาม): อ่านโหมดจาก config.py — ไม่มีหน้าต่างให้กด
        mode = get_update_mode()
        kind = "silent" if silent else "unattended"
        print(f"[Updater] Running {kind} update with mode: {mode}")
    else:
        # 🌟 เรียกใช้หน้าจอเตือนอัปเดตขนาดใหญ่
        mode = ask_custom_update_ui(latest_version)
        if not mode:
            print("[Updater] User skipped the update.")
            sys.exit(0)
        
    # 🌟 Kill adb.exe ก่อนเพื่อคลายการล็อกไฟล์ในโฟลเดอร์ adb/ (แก้ Permission Denied บน Windows)
    print("[Updater] Terminating active ADB server to unlock dll files...")
    try:
        subprocess.run(["taskkill", "/f", "/im", "adb.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    except Exception as e:
        print(f"[Updater] Failed to kill ADB: {e}")

    print(f"[Updater] Downloading update {latest_version}...")
    
    try:
        from config import OVERWRITE_CONFIG_ON_UPDATE
    except Exception:
        OVERWRITE_CONFIG_ON_UPDATE = True

    try:
        zip_bytes = download_update_zip(zip_url)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_ref:
            # ไฟล์ zip จาก GitHub จะมีโฟลเดอร์หลักครอบอยู่ 1 ชั้นเสมอ
            root_folder = zip_ref.namelist()[0]
            zip_files = {}        # path ในรีโป (ตัดโฟลเดอร์ครอบออก) -> ชื่อ member ใน zip

            for member in zip_ref.namelist():
                if member == root_folder or not member.startswith(root_folder):
                    continue
                rel = member[len(root_folder):].replace("\\", "/")
                if not rel:
                    continue
                if rel.endswith("/"):
                    continue
                zip_files[rel] = member

            # ── ล้างโฟลเดอร์ที่รีโปเป็นเจ้าของทั้งก้อน แล้วค่อยวางของใหม่จาก zip ──
            # img/ เป็นรูปของบอทล้วนๆ ไม่มีข้อมูลผู้ใช้ → ลบทิ้งทั้งโฟลเดอร์ง่ายกว่า
            # และชัวร์กว่าการไล่เทียบทีละไฟล์ (รูปที่ถอดออกจากรีโปแล้วไม่มีทางค้าง)
            # ลบหลังโหลด zip สำเร็จเท่านั้น (zip อยู่ในหน่วยความจำแล้ว) โหลดไม่ได้ = ไม่ลบอะไร
            WIPE_DIRS = ("img",)
            wiped = []
            for d in WIPE_DIRS:
                # กันพลาด: ถ้า zip ไม่มีไฟล์ในโฟลเดอร์นี้เลย (zip เพี้ยน) ห้ามลบ
                if not any(r == d or r.startswith(d + "/") for r in zip_files):
                    print(f"[Updater] ข้าม {d}/ - ไม่มีไฟล์ของโฟลเดอร์นี้ใน zip (กันลบแล้วไม่มีของมาแทน)")
                    continue
                if os.path.isdir(d):
                    before = sum(len(f) for _c, _dd, f in os.walk(d))
                    shutil.rmtree(d, ignore_errors=True)
                    left = sum(len(f) for _c, _dd, f in os.walk(d)) if os.path.isdir(d) else 0
                    wiped.append((d, before, left))
                    print(f"[Updater] ล้างโฟลเดอร์ {d}/ ทิ้ง ({before} ไฟล์"
                          + (f", ลบไม่ได้ {left} ไฟล์" if left else "") + ")")
                os.makedirs(d, exist_ok=True)

            written, same, failed = [], 0, []

            def _put(rel, member):
                """เขียนไฟล์เดียวจาก zip ลงที่เดิม — คืน 'new' / 'same' หรือ raise"""
                full = os.path.join(os.getcwd(), rel.replace("/", os.sep))
                with zip_ref.open(member) as src:
                    data = src.read()
                if os.path.isfile(full):
                    try:
                        with open(full, "rb") as f:
                            if f.read() == data:
                                return "same"   # เหมือนเดิม ไม่ต้องเขียนทับ (เร็วกว่า + ไม่ไปชนไฟล์ที่ถูกล็อก)
                    except Exception:
                        pass
                os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
                with open(full, "wb") as f:
                    f.write(data)
                return "new"

            for rel, member in zip_files.items():
                # version.txt จัดการตอนท้ายเอง — ถ้ามีไฟล์อัปเดตไม่สำเร็จจะต้องคงเลขเก่าไว้
                # ให้รอบหน้าลองใหม่ ถ้าปล่อยให้ zip เขียนทับตรงนี้ เลขจะกลายเป็นใหม่ทั้งที่ยังไม่ครบ
                if rel == "version.txt":
                    continue
                # ข้ามการเขียนทับไฟล์ config.py เพื่อป้องกันการตั้งค่าของคุณหาย
                if rel.endswith("config.py") and os.path.exists(rel.replace("/", os.sep)):
                    if not OVERWRITE_CONFIG_ON_UPDATE:
                        print(f"[Updater] Skipping {rel} to preserve your settings.")
                        continue
                    print(f"[Updater] Overwriting {rel} to synchronize with mother machine.")
                # *** ของเดิมไม่มี try ตรงนี้ — ไฟล์เดียวที่ถูกล็อก (dll ของ adb / รูปที่โปรแกรมอื่นเปิดค้าง)
                #     ทำให้ loop พังกลางทาง ไฟล์ที่เหลือ "ทั้งหมด" ไม่ได้อัปเดต แล้วเงียบ ไม่มี error โชว์
                #     = อาการ "กด force-update แล้วโค้ด/รูปไม่อัปเดต" ***
                try:
                    if _put(rel, member) == "same":
                        same += 1
                    else:
                        written.append(rel)
                except Exception as e:
                    failed.append((rel, str(e)))

            # ไฟล์ที่ติดล็อกตอนแรกมักหลุดล็อกหลังโปรเซสตายสนิท — ลองซ้ำอีก 2 รอบ
            for attempt in (1, 2):
                if not failed:
                    break
                import time as _t
                _t.sleep(3)
                retry, failed = failed, []
                print(f"[Updater] ลองเขียนไฟล์ที่ติดล็อกอีกครั้ง (รอบ {attempt}) - {len(retry)} ไฟล์")
                for rel, _err in retry:
                    try:
                        if _put(rel, zip_files[rel]) == "same":
                            same += 1
                        else:
                            written.append(rel)
                    except Exception as e:
                        failed.append((rel, str(e)))

        # ── สรุปผล: เขียนลงไฟล์ด้วย เพราะหน้าต่าง force-update ปิดเร็วเกินจะอ่านทัน ──
        summary = [
            f"[{latest_version}] mode={mode}",
            f"  update/add  : {len(written)} ไฟล์",
            f"  same        : {same} ไฟล์",
            f"  failed      : {len(failed)} ไฟล์",
        ]
        for d, before, left in wiped:
            summary.append(f"    wiped {d}/ : ลบเก่า {before} ไฟล์"
                           + (f" (ลบไม่ได้ {left})" if left else "") + " แล้ววางใหม่จาก zip")
        for rel, err in failed[:20]:
            summary.append(f"    ! {rel}: {err[:90]}")
        for line in summary:
            print("[Updater] " + line)
        try:
            with open("last-update.log", "w", encoding="utf-8") as f:
                f.write("\n".join(summary) + "\n")
        except Exception:
            pass

        if failed:
            # ยังมีไฟล์ที่เขียนไม่ได้ → ไม่บันทึกเลขเวอร์ชัน เพื่อให้รอบหน้าลองอัปเดตซ้ำอีก
            print(f"[Updater] ! ยังมี {len(failed)} ไฟล์ที่อัปเดตไม่ได้ - ไม่บันทึกเวอร์ชัน รอบหน้าจะลองใหม่")
            print(f"[Updater] Updated to {latest_version} PARTIALLY ({len(failed)} file(s) failed) - see last-update.log")
        else:
            with open(VERSION_FILE, "w") as f:
                f.write(latest_version)
            print(f"[Updater] Successfully updated to {latest_version}!")

        # จัดการโฟลเดอร์ข้อมูลตามโหมดที่ผู้ใช้เลือก
        if mode == "clean":
            print("[Updater] Resetting folders (Clean Update)...")
            folders_to_delete = [
                "backup-id", "backup", "file-error", "found-hero",
                "input-id", "login-success", "random-fail", "run-file", "no-hero", "fast-random"
            ]
            for folder in folders_to_delete:
                if os.path.exists(folder):
                    try:
                        shutil.rmtree(folder)
                        print(f"[Updater] Deleted folder: {folder}")
                    except Exception as e:
                        print(f"[Updater] Failed to delete {folder}: {e}")
            
            # สร้างใหม่เฉพาะโฟลเดอร์ที่จำเป็น
            os.makedirs("input-id", exist_ok=True)
            os.makedirs("backup", exist_ok=True)
            print("[Updater] Created: input-id, backup")
        else:
            print("[Updater] Keeping all old folders (Data Preserved)...")
            folders_to_ensure = [
                "input-id", "backup", "backup-id", "file-error",
                "found-hero", "login-success", "random-fail", "run-file", "no-hero", "fast-random"
            ]
            for folder in folders_to_ensure:
                os.makedirs(folder, exist_ok=True)

        if not silent:
            if is_unattended():
                # โหมดอัตโนมัติ: ไม่มีป๊อปอัพให้กด — คืน exit code 10 ให้ login.bat วนกลับไปเริ่มใหม่เอง
                print(f"[Updater] Updated to {latest_version} ({mode}) — login.bat will restart automatically.")
                sys.exit(10)
            # 🌟 แจ้งเตือนเมื่ออัปเดตเสร็จแบบ Custom UI
            detail_msg = "บอทได้รับการอัปเดตและเก็บรักษาข้อมูลเดิมเรียบร้อยแล้ว!" if mode == "keep" else "บอทได้รับการอัปเดตและล้างข้อมูลเก่าทั้งหมดเรียบร้อยแล้ว!"
            show_custom_info_popup(
                "อัปเดตเสร็จสมบูรณ์! ✅",
                f"บอทได้รับการอัปเดตเป็นเวอร์ชัน {latest_version} เรียบร้อยแล้ว!\n{detail_msg}\nกรุณากดเปิด login.bat ใหม่อีกครั้งเพื่อเริ่มทำงาน"
            )
            # ส่ง Exit Code 10 เพื่อบอกให้ batch ไฟล์หยุดการรันบอท (ให้ผู้ใช้เปิดใหม่เอง)
            sys.exit(10)
        else:
            # --no-relaunch: ถูกเรียกจาก force-update.bat ซึ่งมี step [3/3] เปิด login.bat ให้เองอยู่แล้ว
            #   ถ้า auto_update เปิดซ้ำตรงนี้ด้วย = ได้ login.bat 2 หน้าต่าง (บั๊ก cmd ซ้ำ 2 รอบ)
            if no_relaunch:
                print("[Updater] Silent update completed! (--no-relaunch → ปล่อยให้ force-update.bat เปิด login.bat เอง)")
                sys.exit(0)
            print("[Updater] Silent update completed! Re-launching login.bat...")
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            if os.name == 'nt':
                try:
                    subprocess.run(["taskkill", "/f", "/fi", "WINDOWTITLE eq PES Bot Runner*"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                except Exception:
                    pass
                os.system("start cmd /c login.bat")
            else:
                subprocess.Popen(["bash", "login.sh"])
            sys.exit(0)
        
    except Exception as e:
        print(f"[Updater] Update failed: {e}")
        if not silent:
            show_custom_info_popup("อัปเดตล้มเหลว ❌", f"เกิดข้อผิดพลาดในการอัปเดต: {e}")
        sys.exit(0)

if __name__ == "__main__":
    is_silent = "--silent" in sys.argv or "-s" in sys.argv
    is_force = "--force" in sys.argv or "-f" in sys.argv
    is_no_relaunch = "--no-relaunch" in sys.argv
    update(silent=is_silent, force=is_force, no_relaunch=is_no_relaunch)

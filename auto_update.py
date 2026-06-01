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

def get_latest_release():
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get('tag_name'), data.get('zipball_url')
    except Exception as e:
        print(f"[Updater] Failed to check for updates: {e}")
        return None, None

def get_local_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

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
    
    root.mainloop()

def update(silent=False):
    print("[Updater] Checking for latest release on GitHub...")
    latest_version, zip_url = get_latest_release()
    
    if not latest_version or not zip_url:
        sys.exit(0)

    local_version = get_local_version()
    
    if local_version == latest_version:
        print(f"[Updater] You are already on the latest version ({latest_version}).")
        sys.exit(0)
        
    print(f"[Updater] New version found: {latest_version}.")
    
    if silent:
        # ในโหมดเงียบ: เลือกเก็บข้อมูลเดิมไว้เพื่อความปลอดภัยเสมอ
        mode = "keep"
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
        req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            with zipfile.ZipFile(io.BytesIO(response.read())) as zip_ref:
                # ไฟล์ zip จาก GitHub จะมีโฟลเดอร์หลักครอบอยู่ 1 ชั้นเสมอ
                root_folder = zip_ref.namelist()[0]
                
                for member in zip_ref.namelist():
                    if member == root_folder:
                        continue
                    
                    # ตัดชื่อโฟลเดอร์หลักออก เพื่อให้แตกไฟล์ลงที่โฟลเดอร์ปัจจุบันได้พอดี
                    target_path = member[len(root_folder):]
                    if not target_path:
                        continue
                        
                    # ข้ามการเขียนทับไฟล์ config.py เพื่อป้องกันการตั้งค่าของคุณหาย
                    if target_path.endswith("config.py") and os.path.exists(target_path):
                        print(f"[Updater] Skipping {target_path} to preserve your settings.")
                        continue
                        
                    target_full_path = os.path.join(os.getcwd(), target_path)
                    
                    if member.endswith('/'):
                        os.makedirs(target_full_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target_full_path), exist_ok=True)
                        with zip_ref.open(member) as source, open(target_full_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                            
        with open(VERSION_FILE, "w") as f:
            f.write(latest_version)
            
        print(f"[Updater] Successfully updated to {latest_version}!")

        # จัดการโฟลเดอร์ข้อมูลตามโหมดที่ผู้ใช้เลือก
        if mode == "clean":
            print("[Updater] Resetting folders (Clean Update)...")
            folders_to_delete = [
                "backup-id", "backup", "file-error", "found-hero",
                "input-id", "login-success", "random-fail", "run-file", "no-hero"
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
                "found-hero", "login-success", "random-fail", "run-file", "no-hero"
            ]
            for folder in folders_to_ensure:
                os.makedirs(folder, exist_ok=True)

        if not silent:
            # 🌟 แจ้งเตือนเมื่ออัปเดตเสร็จแบบ Custom UI
            detail_msg = "บอทได้รับการอัปเดตและเก็บรักษาข้อมูลเดิมเรียบร้อยแล้ว!" if mode == "keep" else "บอทได้รับการอัปเดตและล้างข้อมูลเก่าทั้งหมดเรียบร้อยแล้ว!"
            show_custom_info_popup(
                "อัปเดตเสร็จสมบูรณ์! ✅",
                f"บอทได้รับการอัปเดตเป็นเวอร์ชัน {latest_version} เรียบร้อยแล้ว!\n{detail_msg}\nกรุณากดเปิด login.bat ใหม่อีกครั้งเพื่อเริ่มทำงาน"
            )
            # ส่ง Exit Code 10 เพื่อบอกให้ batch ไฟล์หยุดการรันบอท (ให้ผู้ใช้เปิดใหม่เอง)
            sys.exit(10)
        else:
            print("[Updater] Silent update completed! Re-launching login.bat...")
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            if os.name == 'nt':
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
    update(silent=is_silent)

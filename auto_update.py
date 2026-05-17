import os
import urllib.request
import json
import zipfile
import shutil
import io
import sys
import tkinter as tk
from tkinter import messagebox

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
        print(f"[Updater] ไม่สามารถเช็คอัปเดตได้: {e}")
        return None, None

def get_local_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

def ask_user_for_update(new_version):
    """สร้าง Popup ถามผู้ใช้ว่าต้องการอัปเดตหรือไม่"""
    root = tk.Tk()
    root.withdraw()  # ซ่อนหน้าต่างหลักของ tkinter
    root.attributes("-topmost", True)  # เอาหน้าต่าง Popup ขึ้นมาหน้าสุด
    
    ans = messagebox.askyesno(
        "พบเวอร์ชันใหม่ 🚀",
        f"มีบอทเวอร์ชันใหม่ ({new_version}) อยู่บน GitHub!\n\nคุณต้องการทำการอัปเดตตอนนี้เลยหรือไม่?"
    )
    root.destroy()
    return ans

def show_info_popup(title, message):
    """สร้าง Popup แจ้งเตือนข้อความทั่วไป"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showinfo(title, message)
    root.destroy()

def update():
    print("[Updater] Checking for latest release on GitHub...")
    latest_version, zip_url = get_latest_release()
    
    if not latest_version or not zip_url:
        sys.exit(0)

    local_version = get_local_version()
    
    if local_version == latest_version:
        print(f"[Updater] You are already on the latest version ({latest_version}).")
        sys.exit(0)
        
    print(f"[Updater] New version found: {latest_version}.")
    
    # 🌟 ถามผู้ใช้ด้วย Popup ก่อนอัปเดต
    if not ask_user_for_update(latest_version):
        print("[Updater] User skipped the update.")
        sys.exit(0)
        
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
        
        # 🌟 แจ้งเตือนเมื่ออัปเดตเสร็จ
        show_info_popup(
            "อัปเดตเสร็จสมบูรณ์! ✅",
            f"บอทได้รับการอัปเดตเป็นเวอร์ชัน {latest_version} เรียบร้อยแล้ว!\n\nโปรแกรมจะปิดตัวลง กรุณากดรัน login.bat อีกครั้งเพื่อใช้งาน"
        )
        
        # ส่ง Exit Code 10 เพื่อบอกให้ batch ไฟล์หยุดการรันบอท (ให้ผู้ใช้เปิดใหม่เอง)
        sys.exit(10)
        
    except Exception as e:
        print(f"[Updater] Update failed: {e}")
        show_info_popup("อัปเดตล้มเหลว ❌", f"เกิดข้อผิดพลาดในการอัปเดต: {e}")
        sys.exit(0)

if __name__ == "__main__":
    update()

import os
import urllib.request
import json
import zipfile
import shutil
import io

# ชื่อ Repository ของคุณบน GitHub (แก้ให้ตรงกับของคุณถ้าไม่ใช่ชื่อนี้)
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

def update():
    print("[Updater] Checking for latest release on GitHub...")
    latest_version, zip_url = get_latest_release()
    
    if not latest_version or not zip_url:
        return

    local_version = get_local_version()
    
    if local_version == latest_version:
        print(f"[Updater] You are already on the latest version ({latest_version}).")
        return
        
    print(f"[Updater] New version found: {latest_version}. Downloading...")
    
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
    except Exception as e:
        print(f"[Updater] Update failed: {e}")

if __name__ == "__main__":
    update()

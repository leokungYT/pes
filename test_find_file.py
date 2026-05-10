import os
import subprocess
import time
from ppadb.client import Client as AdbClient
from colorama import Fore, Style, init

init(autoreset=True)

def main():
    print(f"{Fore.CYAN}=== UID File Visibility Tester ==={Style.RESET_ALL}")
    
    # Connect to ADB
    client = AdbClient(host="127.0.0.1", port=5037)
    devices = client.devices()
    
    if not devices:
        print(f"{Fore.RED}[ERROR] No devices found. Please connect via ADB.{Style.RESET_ALL}")
        return
    
    device = devices[0]
    print(f"{Fore.GREEN}[SUCCESS] Connected to {device.serial}{Style.RESET_ALL}")
    
    remote_folder = "/data/data/jp.konami.pesam/files/SaveData/AUTH"
    target_file = "online_user_id_data.dat"
    full_path = f"{remote_folder}/{target_file}"
    
    print(f"{Fore.YELLOW}[INFO] Target Folder: {remote_folder}")
    print(f"{Fore.YELLOW}[INFO] Target File  : {target_file}")
    print("-" * 40)
    
    try:
        while True:
            print(f"\n{Fore.WHITE}[CHECKING] {time.strftime('%H:%M:%S')}...")
            
            # 1. Check folder existence
            folder_check = device.shell(f"su -c 'ls -d {remote_folder}'").strip()
            if "No such" in folder_check:
                print(f"{Fore.RED}[FOLDER] NOT FOUND: {remote_folder}")
            else:
                print(f"{Fore.GREEN}[FOLDER] EXISTS: {remote_folder}")
                
                # 2. List all contents
                contents = device.shell(f"su -c 'ls -la {remote_folder}/'").strip()
                print(f"{Fore.CYAN}[CONTENTS]:\n{contents}")
                
                # 3. Specific file search
                search = device.shell(f"su -c 'ls {full_path}'").strip()
                if full_path in search and "No such" not in search:
                    print(f"{Fore.GREEN}[FOUND] FILE DETECTED! Path: {full_path}")
                    # Try to get size
                    size = device.shell(f"su -c 'stat -c %s {full_path}'").strip()
                    print(f"{Fore.GREEN}[SIZE] {size} bytes")
                else:
                    print(f"{Fore.RED}[MISSING] File not found in folder.")
                    
                # 4. Global search (New)
                print(f"{Fore.CYAN}[SEARCHING] Scanning for any .dat files in app data...")
                global_search = device.shell("su -c 'find /data/data/jp.konami.pesam/ -name \"*.dat\"'").strip()
                if global_search:
                    print(f"{Fore.GREEN}[FOUND GLOBALLY]:\n{global_search}")
                else:
                    print(f"{Fore.YELLOW}[NOT FOUND GLOBALLY] No .dat files found anywhere.")
            
            print(f"{Fore.YELLOW}Waiting 3s for next check... (Ctrl+C to stop)")
            time.sleep(3)
            
    except KeyboardInterrupt:
        print(f"\n{Fore.CYAN}Tester stopped by user.{Style.RESET_ALL}")

if __name__ == "__main__":
    main()

import subprocess
import time
from ppadb.client import Client as AdbClient

def main():
    print("Connecting to ADB...")
    client = AdbClient(host="127.0.0.1", port=5037)
    devices = client.devices()
    if not devices:
        print("No devices found via ppadb. Please check if your emulator is connected to ADB (run 'adb devices').")
        return
    
    print("Available devices:")
    for i, dev in enumerate(devices):
        print(f"[{i}] {dev.serial}")
        
    device = devices[0]
    print(f"\nTesting on device: {device.serial}")
    
    # วิธีที่ 1: ใช้ draganddrop (กดค้างแล้วลาก)
    # draganddrop จะกดค้างที่จุดแรกสักครู่ แล้วค่อยลากไปยังจุดที่สอง
    # โดยตัวเลข 5000 คือระยะเวลาในการลาก (5 วินาที)
    cmd_drag = "input draganddrop 96 124 691 205 5000"
    print(f"Running: adb shell {cmd_drag}")
    device.shell(cmd_drag)
    
    print("\nDrag and drop command sent. Did it press and hold then drag?")

if __name__ == "__main__":
    main()

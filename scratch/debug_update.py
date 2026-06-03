import sys
import threading
import time
import socket
socket.setdefaulttimeout(15.0)

try:
    import auto_update
    print("auto_update imported successfully")
    latest_version, zip_url = auto_update.get_latest_release()
    local_version = auto_update.get_local_version() or ""
    print(f"Latest: {latest_version}, Local: {local_version}")
    if latest_version and latest_version != local_version:
        print("Update detected!")
except Exception as e:
    print(f"Error: {e}")

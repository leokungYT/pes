# patch_thread_isolation.py

with open('main-pes.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace GQ_ACTIVE definition
content = content.replace("GQ_ACTIVE = False", "GQ_ACTIVE = {}")

# 2. Replace GQ_ACTIVE check in backquest3 floating check
content = content.replace("if GQ_ACTIVE and img is not None:", "if GQ_ACTIVE.get(device.serial, False) and img is not None:")

# 3. Replace process_device definition
target_proc = """def process_device(device):
    serial = device.serial
    gui_log(serial, "Starting automation...", step="Initializing", status="working")"""

replacement_proc = """def process_device(serial_or_device):
    if hasattr(serial_or_device, 'serial'):
        serial = serial_or_device.serial
    else:
        serial = str(serial_or_device)
    
    # Create thread-local AdbClient to prevent socket/data sharing between threads
    client = AdbClient(host="127.0.0.1", port=5037)
    device = client.device(serial)
    if device is None:
        gui_log(serial, "ERROR: Thread failed to initialize private AdbClient device", status="stuck")
        return
        
    gui_log(serial, "Starting automation...", step="Initializing", status="working")"""

if target_proc in content:
    content = content.replace(target_proc, replacement_proc)
    print("process_device patched successfully!")
else:
    print("process_device target NOT found!")

# 4. Replace GQ_ACTIVE inside GETQUEST
target_gq_true = """                    global GQ_ACTIVE
                    GQ_ACTIVE = True"""

replacement_gq_true = """                    GQ_ACTIVE[serial] = True"""

if target_gq_true in content:
    content = content.replace(target_gq_true, replacement_gq_true)
    print("GQ_ACTIVE = True patched successfully!")
else:
    print("GQ_ACTIVE = True target NOT found!")

# 5. Replace GQ_ACTIVE = False inside GETQUEST finally
target_gq_false = """                    finally:
                        GQ_ACTIVE = False"""

replacement_gq_false = """                    finally:
                        GQ_ACTIVE[serial] = False"""

if target_gq_false in content:
    content = content.replace(target_gq_false, replacement_gq_false)
    print("GQ_ACTIVE = False patched successfully!")
else:
    print("GQ_ACTIVE = False target NOT found!")

with open('main-pes.py', 'w', encoding='utf-8') as f:
    f.write(content)

import os
import sys
import time
import subprocess
import importlib.util

spec = importlib.util.spec_from_file_location("gndroid", os.path.join(os.getcwd(), "gndroid.pyw"))
gndroid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gndroid)

def test_production_launch():
    print("Testing production launcher...")
    proc, port, log_path = gndroid.AVDManager.launch_emulator_instance(
        name="gndroid",
        gpu_mode="auto",
        is_root=False
    )
    
    assert proc is not None, "Failed to launch"
    print(f"Emulator started with PID {proc.pid} on port {port}. Log: {log_path}")
    
    adb = gndroid.SystemPaths.get_adb()
    online = False
    for s in range(30):
        time.sleep(1)
        if proc.poll() is not None:
            print(f"Process died at second {s} with exit code {proc.poll()}!")
            break
        try:
            st = subprocess.check_output([adb, "-s", f"emulator-{port}", "get-state"], text=True, timeout=2, creationflags=0x08000000).strip()
            if st == "device":
                print(f"SUCCESS! Device ONLINE (device) on port {port} at second {s}!")
                online = True
                break
        except Exception:
            pass
        if s % 5 == 0:
            print(f"Second {s}: emulator booting normally in background...")
            
    time.sleep(3)
    # Check log
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        log_content = f.read()
        
    has_fatal = "FATAL" in log_content
    has_crash = "closeEvent" in log_content
    print(f"Log checks: has_fatal={has_fatal}, has_crash={has_crash}")
    
    # Cleanup
    subprocess.run([adb, "-s", f"emulator-{port}", "emu", "kill"], timeout=5, creationflags=0x08000000)
    time.sleep(2)
    proc.kill()
    
    assert online, "Emulator did not reach online state"
    print("PRODUCTION LAUNCH TEST PASSED 100%!")

if __name__ == "__main__":
    test_production_launch()

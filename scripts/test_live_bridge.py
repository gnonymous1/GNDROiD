import socket
import urllib.request
import json
import time

target_ip = "192.168.100.245"
print(f"=== LIVE BRIDGE DIAGNOSTIC TEST ({target_ip}) ===")

# Test ping / socket ports
ports = [51880, 51888, 5555, 8080]
for p in ports:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        res = s.connect_ex((target_ip, p))
        s.close()
        status = "OPEN" if res == 0 else f"CLOSED (code {res})"
        print(f"[*] Port {p:5d}: {status}")
    except Exception as e:
        print(f"[!] Port {p:5d}: {e}")

# Query HTTP APIs
for p in [51888, 51880]:
    url = f"http://{target_ip}:{p}/status"
    try:
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "GNDROiD-BridgeTest"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            lat = int((time.time() - t0) * 1000)
            data = json.loads(r.read().decode("utf-8"))
            print(f"\n[+] HTTP Port {p} /status is ACTIVE ({lat}ms latency):")
            print(f"    - Device:          {data.get('device_name')}")
            print(f"    - Model:           {data.get('model')}")
            print(f"    - Android Version: {data.get('android_version')} (SDK {data.get('sdk_int')})")
            print(f"    - App Version:     {data.get('version')}")
            print(f"    - Battery:         {data.get('battery')}% (Charging: {data.get('charging')})")
            print(f"    - Screen Cast:     {data.get('screen_cast_active')}")
            print(f"    - Accessibility:   {data.get('accessibility_active')}")
            print(f"    - Battery Exempt:  {data.get('is_ignoring_battery_optimizations')}")
            print(f"    - Resolution:      {data.get('screen_width')}x{data.get('screen_height')}")
    except Exception as e:
        print(f"[-] HTTP Port {p} /status error: {e}")

# Test frame retrieval
for p in [51888, 51880]:
    frame_url = f"http://{target_ip}:{p}/screen.jpg"
    try:
        t0 = time.time()
        req = urllib.request.Request(frame_url, headers={"User-Agent": "GNDROiD-BridgeTest"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            lat = int((time.time() - t0) * 1000)
            img_bytes = r.read()
            print(f"[+] Screen endpoint /screen.jpg on port {p}: {len(img_bytes)} bytes received in {lat}ms")
    except Exception as e:
        print(f"[-] Screen endpoint /screen.jpg on port {p} error: {e}")

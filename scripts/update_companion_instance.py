import re

with open("gndroid.pyw", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update start_mirror_with_fallback
target_fb = """    selected_serial = target_serial
    if not selected_serial or selected_serial == "gndroid":"""

replace_fb = """    # Check if target is a Companion device (Port 51880/51888 or direct LAN companion)
    host_ip = (target_serial.split(":")[0] if ":" in target_serial else target_serial) if target_serial else ""
    target_port = int(target_serial.split(":")[-1]) if ":" in (target_serial or "") and target_serial.split(":")[-1].isdigit() else None
    comp_port = None
    if target_port in (51880, 51888):
        comp_port = target_port
    elif host_ip and not host_ip.startswith("emulator-") and host_ip != "gndroid":
        for p in (51880, 51888):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.18)
                    if s.connect_ex((host_ip, p)) == 0:
                        comp_port = p
                        break
            except Exception:
                pass
    if comp_port:
        win = GNDroidWirelessMirrorWindow(host_ip=host_ip, port=comp_port, model_name="Infinix X690B", parent=parent)
        win.show()
        return win

    selected_serial = target_serial
    if not selected_serial or selected_serial == "gndroid":"""

if target_fb in content:
    content = content.replace(target_fb, replace_fb, 1)
    print("Hook 1 (start_mirror_with_fallback) replaced.")
else:
    print("Hook 1 not found.")

# 2. Add Companion device directly to dev_combo in on_devices_updated
target_combo = """        # 2. Add physical devices and any unmapped emulators
        has_physical = False"""

replace_combo = """        # 2. Add physical devices, companion handsets, and any unmapped emulators
        has_physical = False

        # Add active Companion mobile handsets as first-class instances
        for comp_ip in ["192.168.100.245"]:
            for cp in (51880, 51888):
                try:
                    import socket
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_comp:
                        s_comp.settimeout(0.15)
                        if s_comp.connect_ex((comp_ip, cp)) == 0:
                            self.dev_combo.addItem(f"📱 [Mobile Instance] Infinix X690B ({comp_ip}:{cp} • Wireless Companion)", {
                                "type": "companion", "host_ip": comp_ip, "port": cp, "name": "Infinix X690B"
                            })
                            has_physical = True
                            break
                except Exception:
                    pass"""

if target_combo in content:
    content = content.replace(target_combo, replace_combo, 1)
    print("Hook 2 (on_devices_updated companion combo) replaced.")
else:
    print("Hook 2 not found.")

# 3. Add selection handling for companion in on_device_selection_changed
target_sel = """        elif dtype == "phone":
            serial = data.get("serial", "")
            self.btn_launch_vm.setText(f"🔗 Mirror Phone ({serial})")"""

replace_sel = """        elif dtype == "companion":
            name = data.get("name", "Infinix X690B")
            host_ip = data.get("host_ip", "192.168.100.245")
            port = data.get("port", 51888)
            self.btn_launch_vm.setText(f"🚀 Launch {name} (Mobile Instance)")
            self.btn_launch_vm.setToolTip(f"Open dedicated 60 FPS wireless mirror and controls for {name}")
            self.status_bar.setText(f"🟢 Mobile Handset Ready: {name} at {host_ip}:{port}. Click Launch to start.")
        elif dtype == "phone":
            serial = data.get("serial", "")
            self.btn_launch_vm.setText(f"🔗 Mirror Phone ({serial})")"""

if target_sel in content:
    content = content.replace(target_sel, replace_sel, 1)
    print("Hook 3 (on_device_selection_changed companion) replaced.")
else:
    print("Hook 3 not found.")

# 4. Handle companion in launch_virtual_machine
target_launch = """        if isinstance(data, dict):
            if data.get("type") in ["phone", "mode_usb"]:
                self.mirror_physical_device()
                return"""

replace_launch = """        if isinstance(data, dict):
            if data.get("type") == "companion":
                win = GNDroidWirelessMirrorWindow(
                    host_ip=data.get("host_ip", "192.168.100.245"),
                    port=data.get("port", 51888),
                    model_name=data.get("name", "Infinix X690B"),
                    parent=self
                )
                win.show()
                return
            elif data.get("type") in ["phone", "mode_usb"]:
                self.mirror_physical_device()
                return"""

if target_launch in content:
    content = content.replace(target_launch, replace_launch, 1)
    print("Hook 4 (launch_virtual_machine companion) replaced.")
else:
    print("Hook 4 not found.")

# 5. Add CLI flag for --mobile / --companion in main()
target_cli = """    # 3. Direct Wireless LAN Mode: gndroid.exe --lan or --wireless
    if "--lan" in args or "--wireless" in args or "lan" in args:"""

replace_cli = """    # Direct Mobile Instance Launcher: gndroid.exe --mobile [ip] or --companion [ip]
    if "--mobile" in args or "--companion" in args or "mobile" in args:
        m_ip = "192.168.100.245"
        for idx, a in enumerate(args):
            if a in ("--mobile", "--companion", "mobile") and idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                m_ip = args[idx + 1]
        m_port = 51880
        for p in (51880, 51888):
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.25)
                    if s.connect_ex((m_ip, p)) == 0:
                        m_port = p
                        break
            except Exception:
                pass
        win = GNDroidWirelessMirrorWindow(host_ip=m_ip, port=m_port, model_name="Infinix X690B")
        win.show()
        sys.exit(app.exec())

    # 3. Direct Wireless LAN Mode: gndroid.exe --lan or --wireless
    if "--lan" in args or "--wireless" in args or "lan" in args:"""

if target_cli in content:
    content = content.replace(target_cli, replace_cli, 1)
    print("Hook 5 (main CLI mobile flag) replaced.")
else:
    print("Hook 5 not found.")

with open("gndroid.pyw", "w", encoding="utf-8") as f:
    f.write(content)

print("All hooks processed.")

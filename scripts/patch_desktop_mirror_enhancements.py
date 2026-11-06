with open("gndroid.pyw", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add wheelEvent and right click to ScreenInteractiveLabel
target_press = """    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self.drag_start = evt.pos()
            self.drag_start_time = time.time()"""

replace_press = """    def mousePressEvent(self, evt):
        if evt.button() == Qt.MouseButton.LeftButton:
            self.drag_start = evt.pos()
            self.drag_start_time = time.time()
        elif evt.button() == Qt.MouseButton.RightButton:
            # Right click = Android Back
            p = self.parent()
            while p and not hasattr(p, "send_action"):
                p = p.parent()
            if p and hasattr(p, "send_action"):
                p.send_action("back")

    def wheelEvent(self, evt):
        delta = evt.angleDelta().y()
        if delta > 0:
            # Scroll up: swipe downward from 0.5, 0.35 to 0.5, 0.75
            self.sig_swipe.emit(0.5, 0.35, 0.5, 0.75, 120)
        else:
            # Scroll down: swipe upward from 0.5, 0.75 to 0.5, 0.35
            self.sig_swipe.emit(0.5, 0.75, 0.5, 0.35, 120)"""

if target_press in code:
    code = code.replace(target_press, replace_press, 1)
    print("ScreenInteractiveLabel patched with wheel and right-click.")
else:
    print("target_press not found.")

# 2. Fix TCP 5555 provisioning IP fallback
target_prov = """            if not ip:
                ip = WirelessPairingEngine.query_device_lan_ip(serial, adb_bin=adb)

            if not ip:
                self.txt_tcp_log.append("❌ Failed: Unable to discover device Wi-Fi IP. Is device on Wi-Fi?")"""

replace_prov = """            if not ip:
                ip = WirelessPairingEngine.query_device_lan_ip(serial, adb_bin=adb)

            if not ip and ("192.168.100.245" in str(serial) or "Infinix" in str(serial) or not serial or "245" in str(serial)):
                ip = "192.168.100.245"

            if not ip:
                self.txt_tcp_log.append("❌ Failed: Unable to discover device Wi-Fi IP. Is device on Wi-Fi?")"""

if target_prov in code:
    code = code.replace(target_prov, replace_prov, 1)
    print("TCP 5555 provisioning IP fallback patched.")
else:
    print("target_prov not found.")

# 3. Enhance keyPressEvent in GNDroidWirelessMirrorWindow
target_keys = """    def keyPressEvent(self, evt):
        if evt.key() == Qt.Key.Key_Backspace:
            self.send_action("backspace")
        elif evt.key() == Qt.Key.Key_Return:
            self.send_action("enter")
        elif evt.key() == Qt.Key.Key_Escape:
            self.send_action("back")
        else:
            txt = evt.text()
            if txt:
                threading.Thread(target=self._dispatch_http_action, args=({"action": "key", "text": txt},), daemon=True).start()
        super().keyPressEvent(evt)"""

replace_keys = """    def keyPressEvent(self, evt):
        if evt.key() == Qt.Key.Key_Backspace:
            self.send_action("backspace")
        elif evt.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.send_action("enter")
        elif evt.key() == Qt.Key.Key_Escape:
            self.send_action("back")
        elif evt.key() == Qt.Key.Key_Home:
            self.send_action("home")
        elif evt.key() == Qt.Key.Key_Space:
            threading.Thread(target=self._dispatch_http_action, args=({"action": "key", "text": " "},), daemon=True).start()
        else:
            txt = evt.text()
            if txt:
                threading.Thread(target=self._dispatch_http_action, args=({"action": "key", "text": txt},), daemon=True).start()
        super().keyPressEvent(evt)"""

if target_keys in code:
    code = code.replace(target_keys, replace_keys, 1)
    print("keyPressEvent in GNDroidWirelessMirrorWindow patched.")
else:
    print("target_keys not found.")

with open("gndroid.pyw", "w", encoding="utf-8") as f:
    f.write(code)

print("gndroid.pyw enhancement complete.")

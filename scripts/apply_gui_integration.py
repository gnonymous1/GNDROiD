import os
import re
import sys

def main():
    with open("gndroid.pyw", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Macro Dialog definition
    macro_dialog_code = '''
# ----------------------------------------------------------------------
# GNDROiD Macro Recorder & Automation Engine Dialog
# ----------------------------------------------------------------------
class GNDroidMacroDialog(QDialog):
    def __init__(self, parent=None, default_serial: str = "emulator-5554"):
        super().__init__(parent)
        self.setWindowTitle("🎬 GNDROiD Macro Recorder & Automation Engine")
        self.setFixedSize(540, 480)
        self.serial = default_serial
        import nexus.macro_engine
        self.engine = nexus.macro_engine.MacroEngine(serial=self.serial)
        self.current_script = None
        self._is_recording = False
        self._is_playing = False
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f8f9fa; color: #0f172a; font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif; }
            QFrame.cardBox { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }
            QPushButton { border-radius: 6px; padding: 6px 14px; font-weight: 500; font-size: 11px; }
            QPushButton.btnHero { background: #0067c0; border: 1px solid #005a9e; color: #ffffff; font-weight: 600; }
            QPushButton.btnHero:hover { background: #1879c9; }
            QPushButton.btnAction { background: #ffffff; border: 1px solid #cbd5e1; color: #0f172a; }
            QPushButton.btnAction:hover { background: #f8fafc; border-color: #94a3b8; }
            QComboBox, QSpinBox { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 10px; font-size: 12px; }
        """)
        l = QVBoxLayout(self)
        l.setContentsMargins(18, 18, 18, 18)
        l.setSpacing(12)

        # Header
        h_row = QHBoxLayout()
        t = QLabel("🎬 Macro Recorder & Auto-Clicker")
        t.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        h_row.addWidget(t)
        h_row.addStretch()
        l.addLayout(h_row)

        desc = QLabel("Record live touch gestures and keyboard sequences, then loop-play them with sub-millisecond precision.")
        desc.setStyleSheet("color: #64748b; font-size: 11px;")
        desc.setWordWrap(True)
        l.addWidget(desc)

        # Target Serial
        ser_row = QHBoxLayout()
        ser_row.addWidget(QLabel("Target Instance:"))
        self.combo_target = QComboBox()
        devs = SystemPaths.list_devices()
        for d in devs:
            if d.get("state") == "device":
                self.combo_target.addItem(f"{d['serial']} ({d.get('name', 'Android')})", d['serial'])
        if self.combo_target.count() == 0:
            self.combo_target.addItem(self.serial, self.serial)
        ser_row.addWidget(self.combo_target, 1)
        l.addLayout(ser_row)

        # Action Buttons
        btn_card = QFrame()
        btn_card.setProperty("class", "cardBox")
        bc_l = QHBoxLayout(btn_card)
        bc_l.setContentsMargins(12, 10, 12, 10)
        bc_l.setSpacing(8)

        self.btn_rec = QPushButton("⏺ Start Recording")
        self.btn_rec.setStyleSheet("background: #dc2626; color: #ffffff; font-weight: 600; border: 1px solid #b91c1c;")
        self.btn_rec.clicked.connect(self.toggle_record)
        bc_l.addWidget(self.btn_rec)

        self.btn_play = QPushButton("▶ Play Script")
        self.btn_play.setStyleSheet("background: #0284c7; color: #ffffff; font-weight: 600; border: 1px solid #0369a1;")
        self.btn_play.clicked.connect(self.play_script)
        bc_l.addWidget(self.btn_play)

        self.btn_save = QPushButton("💾 Save JSON")
        self.btn_save.setProperty("class", "btnAction")
        self.btn_save.clicked.connect(self.save_script)
        bc_l.addWidget(self.btn_save)

        self.btn_load = QPushButton("📂 Load JSON")
        self.btn_load.setProperty("class", "btnAction")
        self.btn_load.clicked.connect(self.load_script)
        bc_l.addWidget(self.btn_load)

        l.addWidget(btn_card)

        # Options Card
        opt_card = QFrame()
        opt_card.setProperty("class", "cardBox")
        oc_l = QGridLayout(opt_card)
        oc_l.setContentsMargins(12, 10, 12, 10)
        oc_l.setHorizontalSpacing(12)
        oc_l.setVerticalSpacing(8)

        oc_l.addWidget(QLabel("Loop Iterations:"), 0, 0)
        self.spin_loops = QSpinBox()
        self.spin_loops.setRange(1, 1000)
        self.spin_loops.setValue(1)
        oc_l.addWidget(self.spin_loops, 0, 1)

        oc_l.addWidget(QLabel("Speed Multiplier:"), 0, 2)
        self.combo_speed = QComboBox()
        self.combo_speed.addItem("0.5x (Slow)", 0.5)
        self.combo_speed.addItem("1.0x (Normal)", 1.0)
        self.combo_speed.addItem("1.5x (Fast)", 1.5)
        self.combo_speed.addItem("2.0x (Turbo)", 2.0)
        self.combo_speed.setCurrentIndex(1)
        oc_l.addWidget(self.combo_speed, 0, 3)

        l.addWidget(opt_card)

        # Event Log
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; font-family: Consolas, monospace; font-size: 11px;")
        self.log_text.setPlaceholderText("Recorded macro events and execution telemetry will appear here...")
        l.addWidget(self.log_text, 1)

        # Footer
        f_row = QHBoxLayout()
        f_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setProperty("class", "btnAction")
        btn_close.clicked.connect(self.accept)
        f_row.addWidget(btn_close)
        l.addLayout(f_row)

    def toggle_record(self):
        target_ser = self.combo_target.currentData() or self.serial
        self.engine.serial = target_ser
        if not self._is_recording:
            self.engine.start_recording()
            self._is_recording = True
            self.btn_rec.setText("⏹ Stop Recording")
            self.btn_rec.setStyleSheet("background: #475569; color: #ffffff; font-weight: 600; border: 1px solid #334155;")
            self.log_text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] ⏺ Recording started on {target_ser}...")
        else:
            self.current_script = self.engine.stop_recording()
            self._is_recording = False
            self.btn_rec.setText("⏺ Start Recording")
            self.btn_rec.setStyleSheet("background: #dc2626; color: #ffffff; font-weight: 600; border: 1px solid #b91c1c;")
            count = len(self.current_script.steps) if self.current_script else 0
            dur = self.current_script.duration_ms / 1000.0 if self.current_script else 0.0
            self.log_text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] ⏹ Stopped. Captured {count} steps ({dur:.2f}s duration).")

    def play_script(self):
        if not self.current_script or not self.current_script.steps:
            QMessageBox.information(self, "No Macro", "Please record or load a macro script first.")
            return
        loops = self.spin_loops.value()
        speed = self.combo_speed.currentData() or 1.0
        target_ser = self.combo_target.currentData() or self.serial
        self.engine.serial = target_ser

        self.log_text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] ▶ Playing {len(self.current_script.steps)} steps (Loops: {loops}, Speed: {speed}x)...")
        def _worker():
            self.engine.play(self.current_script.steps, repeat_count=loops, speed=speed)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def save_script(self):
        if not self.current_script or not self.current_script.steps:
            QMessageBox.information(self, "Nothing to Save", "Record a macro script first before saving.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Macro Script", "macro.json", "JSON Files (*.json);;All Files (*.*)")
        if path:
            self.engine.save_to_file(path)
            self.log_text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] 💾 Script saved to: {os.path.basename(path)}")

    def load_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Macro Script", "", "JSON Files (*.json);;All Files (*.*)")
        if path:
            self.current_script = self.engine.load_from_file(path)
            count = len(self.current_script.steps) if self.current_script else 0
            self.log_text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] 📂 Loaded {count} steps from: {os.path.basename(path)}")


'''

    # Insert macro dialog code before GNDroidMultiInstanceManager
    target_cls = "class GNDroidMultiInstanceManager(QDialog):"
    if macro_dialog_code.strip() not in content:
        assert target_cls in content
        content = content.replace(target_cls, macro_dialog_code + target_cls)
        print("Inserted GNDroidMacroDialog")

    # 2. Add next-gen toolbar in GNDroidMultiInstanceManager
    target_head_add = "layout.addLayout(head_box)\n\n        # 2. Telemetry Bar"
    nextgen_bar_code = '''layout.addLayout(head_box)

        # 1b. Next-Gen Multi-Instance Action Bar
        nextgen_bar = QHBoxLayout()
        nextgen_bar.setSpacing(8)

        self.btn_sync = QPushButton("⚡ Sync Operations: OFF")
        self.btn_sync.setProperty("class", "btnAction")
        self.btn_sync.setToolTip("Sub-millisecond input multiplexing across all running instances")
        self.btn_sync.clicked.connect(self.toggle_sync_operations)
        nextgen_bar.addWidget(self.btn_sync)

        self.btn_eco = QPushButton("🌱 Eco Mode: OFF")
        self.btn_eco.setProperty("class", "btnAction")
        self.btn_eco.setToolTip("Throttles background instances to 5 FPS to reduce host CPU and GPU consumption")
        self.btn_eco.clicked.connect(self.toggle_eco_mode)
        nextgen_bar.addWidget(self.btn_eco)

        self.btn_trim_ram = QPushButton("🧹 Trim RAM (Free Memory)")
        self.btn_trim_ram.setProperty("class", "btnAction")
        self.btn_trim_ram.setToolTip("Purge guest ART caches, Linux kernel caches, and host working set across all instances")
        self.btn_trim_ram.clicked.connect(self.action_trim_ram)
        nextgen_bar.addWidget(self.btn_trim_ram)

        self.btn_macro = QPushButton("🎬 Macro Recorder")
        self.btn_macro.setProperty("class", "btnAction")
        self.btn_macro.setToolTip("Record and replay touch gestures and key events")
        self.btn_macro.clicked.connect(self.action_macro_recorder)
        nextgen_bar.addWidget(self.btn_macro)

        nextgen_bar.addStretch()
        layout.addLayout(nextgen_bar)

        # 2. Telemetry Bar'''
    if "self.btn_sync = QPushButton" not in content:
        assert target_head_add in content
        content = content.replace(target_head_add, nextgen_bar_code)
        print("Inserted next-gen toolbar into GNDroidMultiInstanceManager")

    # 3. Add methods to GNDroidMultiInstanceManager
    multi_inst_methods = '''    def toggle_sync_operations(self):
        if not hasattr(self, "_sync_active"):
            self._sync_active = False
            self._sync_mux = None

        if not self._sync_active:
            devs = SystemPaths.list_devices()
            running = [d["serial"] for d in devs if d.get("state") == "device"]
            if len(running) < 2:
                QMessageBox.information(
                    self, "Sync Operations",
                    f"Found {len(running)} running instance(s).\\n\\n"
                    "At least 2 running instances are required for multi-instance input synchronization.\\n"
                    "Start another instance and try again."
                )
                return
            master = running[0]
            slaves = running[1:]
            try:
                from nexus.sync_multiplexer import InputSyncMultiplexer
                self._sync_mux = InputSyncMultiplexer(master_serial=master)
                for s in slaves:
                    self._sync_mux.add_slave(s)
                self._sync_mux.set_syncing(True)
                self._sync_active = True
                self.btn_sync.setText("⚡ Sync Operations: ON")
                self.btn_sync.setStyleSheet("background: #0284c7; color: #ffffff; font-weight: 600; border: 1px solid #0369a1;")
                QMessageBox.information(
                    self, "Sync Operations Active",
                    f"Input synchronization is now ACTIVE!\\n\\n"
                    f"• Master Instance: {master}\\n"
                    f"• Synchronized Slaves: {', '.join(slaves)}\\n\\n"
                    "All mouse clicks, drags, and keystrokes on the master window are automatically mirrored."
                )
            except Exception as e:
                QMessageBox.warning(self, "Sync Error", f"Failed to activate Input Sync Multiplexer:\\n{e}")
        else:
            if getattr(self, "_sync_mux", None):
                try:
                    self._sync_mux.set_syncing(False)
                    self._sync_mux.close()
                except Exception:
                    pass
                self._sync_mux = None
            self._sync_active = False
            self.btn_sync.setText("⚡ Sync Operations: OFF")
            self.btn_sync.setStyleSheet("")

    def toggle_eco_mode(self):
        if not hasattr(self, "_eco_active"):
            self._eco_active = False
            self._eco_throttler = None

        if not self._eco_active:
            try:
                from nexus.eco_throttler import EcoThrottler
                self._eco_throttler = EcoThrottler(target_fps=5)
                devs = SystemPaths.list_devices()
                count = 0
                for d in devs:
                    if d.get("state") == "device":
                        ser = d["serial"]
                        self._eco_throttler.register_instance(ser)
                        count += 1
                self._eco_throttler.enable_eco_mode()
                self._eco_active = True
                self.btn_eco.setText("🌱 Eco Mode: ON (5 FPS)")
                self.btn_eco.setStyleSheet("background: #10b981; color: #ffffff; font-weight: 600; border: 1px solid #059669;")
                QMessageBox.information(
                    self, "Eco Mode Enabled",
                    f"🌱 Eco Mode is now ACTIVE across {count} instance(s)!\\n\\n"
                    "Background instances will automatically throttle to 5 FPS when out of focus, "
                    "reducing host CPU and GPU consumption by up to 75%."
                )
            except Exception as e:
                QMessageBox.warning(self, "Eco Mode Error", f"Failed to enable Eco Mode:\\n{e}")
        else:
            if getattr(self, "_eco_throttler", None):
                try:
                    self._eco_throttler.disable_eco_mode()
                except Exception:
                    pass
                self._eco_throttler = None
            self._eco_active = False
            self.btn_eco.setText("🌱 Eco Mode: OFF")
            self.btn_eco.setStyleSheet("")

    def action_trim_ram(self):
        try:
            from nexus.memory_trimmer import MemoryTrimmer
            trimmer = MemoryTrimmer(adb_path=SystemPaths.get_adb())
            devs = SystemPaths.list_devices()
            running = [d["serial"] for d in devs if d.get("state") == "device"]

            reclaimed_total = 0.0
            guest_results = []
            for ser in running:
                res = trimmer.trim_instance(ser)
                reclaimed_total += res.get("reclaimed_mb", 0.0)
                guest_results.append(f"• {ser}: {res.get('reclaimed_mb', 0):.1f} MB freed")

            host_freed = trimmer.execute_tier4_host_empty_working_set()

            detail = "\\n".join(guest_results) if guest_results else "No active guest instances running."
            QMessageBox.information(
                self, "RAM Trim Complete",
                f"🧹 4-Tier Memory Purge Finished!\\n\\n"
                f"• Guest Instances Cleaned: {len(running)}\\n"
                f"• Guest RAM Reclaimed: {reclaimed_total:.1f} MB\\n"
                f"• Host Working Set Empty: {'Success' if host_freed else 'N/A'}\\n\\n"
                f"{detail}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Trim RAM Error", f"Failed to execute memory purge:\\n{e}")

    def action_macro_recorder(self):
        devs = SystemPaths.list_devices()
        running = [d["serial"] for d in devs if d.get("state") == "device"]
        default_ser = running[0] if running else "emulator-5554"
        dlg = GNDroidMacroDialog(parent=self, default_serial=default_ser)
        dlg.exec()

    def closeEvent(self, event):
        if getattr(self, "_sync_mux", None):
            try:
                self._sync_mux.set_syncing(False)
                self._sync_mux.close()
            except Exception:
                pass
        if getattr(self, "_eco_throttler", None):
            try:
                self._eco_throttler.disable_eco_mode()
            except Exception:
                pass
        super().closeEvent(event)

'''
    if "def toggle_sync_operations(self):" not in content:
        target_confirm = "    def show_confirm_dialog(self, title: str, heading: str, body: str, confirm_text: str = \"Delete\", is_danger: bool = True) -> bool:"
        assert target_confirm in content
        content = content.replace(target_confirm, multi_inst_methods + target_confirm)
        print("Inserted next-gen methods into GNDroidMultiInstanceManager")

    # 4. Update file filters in GNDroidCompanionSidebar and Dropzone
    old_filter_sidebar = 'path, _ = QFileDialog.getOpenFileName(self, "Select APK to Install", "", "Android Package (*.apk);;All Files (*.*)")'
    new_filter_sidebar = 'path, _ = QFileDialog.getOpenFileName(self, "Select APK or Bundle to Install", "", "Android Packages & Split Bundles (*.apk *.xapk *.apkm *.apks *.aab);;APK Package (*.apk);;Split Bundle (*.xapk *.apkm *.apks);;App Bundle (*.aab);;All Files (*.*)")'
    if old_filter_sidebar in content:
        content = content.replace(old_filter_sidebar, new_filter_sidebar)
        print("Updated sidebar APK file picker filter")

    old_filter_push = 'file_path, _ = QFileDialog.getOpenFileName(self, "Select File or APK to Push to Device", "", "All Files (*.*);;Android APKs (*.apk)")'
    new_filter_push = 'file_path, _ = QFileDialog.getOpenFileName(self, "Select File or Android Package", "", "Android Packages & Bundles (*.apk *.xapk *.apkm *.apks *.aab);;All Files (*.*);;Android APKs (*.apk)")'
    if old_filter_push in content:
        content = content.replace(old_filter_push, new_filter_push)
        print("Updated push file picker filter")

    # 5. Add Tab 5: Universal Region & Proxy into GNDroidSettingsDialog
    tab4_anchor = 'self.tabs.addTab(tab_net_container, "🌐 Network & Adapters")'
    tab5_code = '''self.tabs.addTab(tab_net_container, "🌐 Network & Adapters")

        # -------------------------------------------------------------
        # Tab 5: Universal Region & Enterprise Proxy
        # -------------------------------------------------------------
        tab_region_proxy_container = QWidget()
        scroll_rp = QScrollArea()
        scroll_rp.setWidgetResizable(True)
        scroll_rp.setFrameShape(QFrame.Shape.NoFrame)
        tab_rp = QWidget()
        trp_l = QVBoxLayout(tab_rp)
        trp_l.setContentsMargins(16, 16, 16, 16)
        trp_l.setSpacing(14)

        # Card 1: 4-Tier Universal Region Synchronization
        grp_region = QGroupBox("🌍 4-Tier Universal Region Persona Synchronization")
        grp_region.setProperty("class", "cardBox")
        g_reg_l = QVBoxLayout(grp_region)
        g_reg_l.setSpacing(10)

        reg_info = QLabel(
            "Synchronizes all 4 fingerprinting tiers simultaneously: Telephony SIM/SPN, "
            "OS Locale/Timezone, Hardware GPS, and Network DNS. Bypasses geo-blocking in Play Store, TikTok, and Banking apps."
        )
        reg_info.setWordWrap(True)
        reg_info.setStyleSheet("color: #64748b; font-size: 11px;")
        g_reg_l.addWidget(reg_info)

        reg_row = QHBoxLayout()
        reg_row.addWidget(QLabel("Target Region / Carrier:"))
        self.combo_region = QComboBox()
        self.combo_region.setMinimumHeight(32)
        GNDroidSettingsDialog.style_combo(self.combo_region)

        from nexus.region_controller import REGIONS
        for code, profile in REGIONS.items():
            self.combo_region.addItem(f"{code} — {profile.country_name} ({profile.carrier_spn})", code)

        saved_reg = self.cfg.get("gndroid.region", "US").upper()
        idx_reg = self.combo_region.findData(saved_reg)
        if idx_reg >= 0:
            self.combo_region.setCurrentIndex(idx_reg)
        self.combo_region.currentIndexChanged.connect(self.on_region_preset_changed)
        reg_row.addWidget(self.combo_region, 1)
        g_reg_l.addLayout(reg_row)

        self.lbl_region_details = QLabel()
        self.lbl_region_details.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; font-size: 11px; color: #334155;")
        self.lbl_region_details.setWordWrap(True)
        g_reg_l.addWidget(self.lbl_region_details)
        self.update_region_details_display()

        reg_act_row = QHBoxLayout()
        self.btn_apply_region = QPushButton("⚡ Apply 4-Tier Region Sync Now")
        self.btn_apply_region.setProperty("class", "btnHero")
        self.btn_apply_region.clicked.connect(self.action_apply_region_sync)
        reg_act_row.addWidget(self.btn_apply_region)

        self.btn_test_egress = QPushButton("🔍 Check Egress IP & Flag")
        self.btn_test_egress.setProperty("class", "btnAction")
        self.btn_test_egress.clicked.connect(self.action_check_egress_ip)
        reg_act_row.addWidget(self.btn_test_egress)
        g_reg_l.addLayout(reg_act_row)

        self.lbl_region_status = QLabel("Region Status: Ready to synchronize")
        self.lbl_region_status.setStyleSheet("color: #64748b; font-size: 11px;")
        g_reg_l.addWidget(self.lbl_region_status)

        trp_l.addWidget(grp_region)

        # Card 2: Enterprise Proxy & Transparent Routing
        grp_proxy = QGroupBox("🛡️ Enterprise Authenticated Proxy & Transparent Routing")
        grp_proxy.setProperty("class", "cardBox")
        g_prx_l = QVBoxLayout(grp_proxy)
        g_prx_l.setSpacing(10)

        prx_info = QLabel(
            "Local Auth Loopback (127.0.0.1:8990) strips upstream HTTP/SOCKS5 credentials so Android system proxy "
            "connects without username/password prompts. Tun2Socks transparently redirects all TCP/UDP traffic."
        )
        prx_info.setWordWrap(True)
        prx_info.setStyleSheet("color: #64748b; font-size: 11px;")
        g_prx_l.addWidget(prx_info)

        prx_mode_row = QHBoxLayout()
        prx_mode_row.addWidget(QLabel("Proxy Mode:"))
        self.combo_proxy_mode = QComboBox()
        self.combo_proxy_mode.setMinimumHeight(32)
        GNDroidSettingsDialog.style_combo(self.combo_proxy_mode)
        self.combo_proxy_mode.addItem("🚫 Disabled (Direct Connection)", "disabled")
        self.combo_proxy_mode.addItem("⚡ Local Auth Loopback (127.0.0.1:8990)", "local_auth")
        self.combo_proxy_mode.addItem("🌐 Transparent Tun2Socks (All Apps/UDP/TCP)", "tun2socks")
        saved_pm = self.cfg.get("gndroid.proxy_mode", "disabled").lower()
        idx_pm = self.combo_proxy_mode.findData(saved_pm)
        if idx_pm >= 0:
            self.combo_proxy_mode.setCurrentIndex(idx_pm)
        prx_mode_row.addWidget(self.combo_proxy_mode, 1)

        prx_mode_row.addWidget(QLabel("Protocol:"))
        self.combo_proxy_proto = QComboBox()
        self.combo_proxy_proto.setMinimumHeight(32)
        GNDroidSettingsDialog.style_combo(self.combo_proxy_proto)
        self.combo_proxy_proto.addItem("HTTP", "HTTP")
        self.combo_proxy_proto.addItem("HTTPS", "HTTPS")
        self.combo_proxy_proto.addItem("SOCKS5", "SOCKS5")
        self.combo_proxy_proto.addItem("SOCKS5H", "SOCKS5H")
        saved_proto = self.cfg.get("gndroid.proxy_protocol", "HTTP").upper()
        idx_proto = self.combo_proxy_proto.findData(saved_proto)
        if idx_proto >= 0:
            self.combo_proxy_proto.setCurrentIndex(idx_proto)
        prx_mode_row.addWidget(self.combo_proxy_proto)
        g_prx_l.addLayout(prx_mode_row)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Upstream Host:"))
        self.txt_proxy_host = QLineEdit(self.cfg.get("gndroid.proxy_host", ""))
        self.txt_proxy_host.setPlaceholderText("e.g. proxy.corporate.com or 10.0.0.1")
        host_row.addWidget(self.txt_proxy_host, 2)

        host_row.addWidget(QLabel("Port:"))
        self.spin_proxy_port = QSpinBox()
        self.spin_proxy_port.setRange(1, 65535)
        self.spin_proxy_port.setValue(int(self.cfg.get("gndroid.proxy_port", "8080")))
        host_row.addWidget(self.spin_proxy_port, 1)
        g_prx_l.addLayout(host_row)

        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("Username:"))
        self.txt_proxy_user = QLineEdit(self.cfg.get("gndroid.proxy_user", ""))
        self.txt_proxy_user.setPlaceholderText("Optional auth username")
        auth_row.addWidget(self.txt_proxy_user, 1)

        auth_row.addWidget(QLabel("Password:"))
        self.txt_proxy_pass = QLineEdit(self.cfg.get("gndroid.proxy_pass", ""))
        self.txt_proxy_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_proxy_pass.setPlaceholderText("Optional auth password")
        auth_row.addWidget(self.txt_proxy_pass, 1)
        g_prx_l.addLayout(auth_row)

        self.chk_dns_over_proxy = QCheckBox("🛡️ Route DNS queries through Proxy (Prevents ISP DNS Leak)")
        self.chk_dns_over_proxy.setChecked(self.cfg.get("gndroid.proxy_dns", "yes").lower() in ["yes", "true", "1"])
        g_prx_l.addWidget(self.chk_dns_over_proxy)

        self.chk_kill_switch = QCheckBox("🚫 Egress Kill-Switch (Block traffic if proxy connection drops)")
        self.chk_kill_switch.setChecked(self.cfg.get("gndroid.proxy_killswitch", "no").lower() in ["yes", "true", "1"])
        g_prx_l.addWidget(self.chk_kill_switch)

        prx_act_row = QHBoxLayout()
        self.btn_test_proxy = QPushButton("⚡ Test Proxy Health")
        self.btn_test_proxy.setProperty("class", "btnAction")
        self.btn_test_proxy.clicked.connect(self.action_test_proxy_health)
        prx_act_row.addWidget(self.btn_test_proxy)

        self.btn_toggle_proxy_daemon = QPushButton("▶ Start Local Proxy Daemon")
        self.btn_toggle_proxy_daemon.setProperty("class", "btnHero")
        self.btn_toggle_proxy_daemon.clicked.connect(self.action_toggle_proxy_daemon)
        prx_act_row.addWidget(self.btn_toggle_proxy_daemon)
        g_prx_l.addLayout(prx_act_row)

        self.lbl_proxy_status = QLabel("Proxy Status: Standby")
        self.lbl_proxy_status.setStyleSheet("color: #64748b; font-size: 11px;")
        g_prx_l.addWidget(self.lbl_proxy_status)

        trp_l.addWidget(grp_proxy)

        # Card 3: LDPlayer-Grade Gaming Launch Profile
        grp_gaming = QGroupBox("🎮 High-Performance Gaming Launch Profile")
        grp_gaming.setProperty("class", "cardBox")
        g_game_l = QVBoxLayout(grp_gaming)
        g_game_l.setSpacing(8)

        self.chk_gaming_mode = QCheckBox("⚡ LDPlayer-Grade Gaming Profile (120Hz Display, Host P-Core Affinity, Low Latency Scrcpy)")
        self.chk_gaming_mode.setChecked(self.cfg.get("gndroid.gaming_mode", "no").lower() in ["yes", "true", "1"])
        self.chk_gaming_mode.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        g_game_l.addWidget(self.chk_gaming_mode)

        game_desc = QLabel(
            "• Allocates emulator thread execution exclusively to Intel/AMD Performance (P) cores.\\n"
            "• Configures guest SurfaceFlinger and vendor display for smooth 120 FPS rendering.\\n"
            "• Enables sub-millisecond UHID mouse/keyboard polling and touch coordinate streaming."
        )
        game_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        g_game_l.addWidget(game_desc)

        trp_l.addWidget(grp_gaming)
        trp_l.addStretch()

        scroll_rp.setWidget(tab_rp)
        tab_rp_l = QVBoxLayout(tab_region_proxy_container)
        tab_rp_l.setContentsMargins(0, 0, 0, 0)
        tab_rp_l.addWidget(scroll_rp)

        self.tabs.addTab(tab_region_proxy_container, "🌍 Region & Proxy")'''

    if 'self.tabs.addTab(tab_region_proxy_container, "🌍 Region & Proxy")' not in content:
        assert tab4_anchor in content
        content = content.replace(tab4_anchor, tab5_code)
        print("Inserted Tab 5: Universal Region & Proxy into GNDroidSettingsDialog")

    # 6. Add helper methods to GNDroidSettingsDialog
    settings_methods = '''    def on_region_preset_changed(self, idx: int):
        self.update_region_details_display()

    def update_region_details_display(self):
        code = self.combo_region.currentData()
        try:
            from nexus.region_controller import REGIONS
            prof = REGIONS.get(code)
            if prof:
                info = (
                    f"<b>Country:</b> {prof.country_name} ({prof.code}) | "
                    f"<b>Carrier SPN:</b> {prof.carrier_spn} | <b>MCC/MNC:</b> {prof.mcc_mnc}<br>"
                    f"<b>Locale:</b> {prof.locale} | <b>Timezone:</b> {prof.timezone}<br>"
                    f"<b>Hardware Coordinates:</b> {prof.coordinates[1]}° N, {prof.coordinates[0]}° E | "
                    f"<b>Regional DNS:</b> {prof.regional_dns}"
                )
                self.lbl_region_details.setText(info)
            else:
                self.lbl_region_details.setText("No region selected")
        except Exception as e:
            self.lbl_region_details.setText(str(e))

    def action_apply_region_sync(self):
        code = self.combo_region.currentData()
        if not code:
            return
        target_ser = self.target_serial or "emulator-5554"
        self.lbl_region_status.setText(f"Applying 4-Tier Region Sync for {code} on {target_ser}...")
        try:
            from nexus.region_controller import UniversalRegionController
            rc = UniversalRegionController(serial=target_ser, adb_path=SystemPaths.get_adb())
            res = rc.switch_region(code)
            if res.is_success:
                self.lbl_region_status.setText(f"✅ Region successfully synced to {code} ({res.country})!")
                self.lbl_region_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px;")
                QMessageBox.information(
                    self, "Region Persona Synchronized",
                    f"4-Tier Region Persona Applied Successfully!\\n\\n"
                    f"• Target: {res.country} ({res.code})\\n"
                    f"• Carrier: {res.carrier_spn} (MCC/MNC: {res.mcc_mnc})\\n"
                    f"• Timezone: {res.timezone}\\n"
                    f"• GPS: {res.coordinates[1]}°, {res.coordinates[0]}°\\n\\n"
                    "Telephony SIM properties, OS locales, and Hardware GPS are synchronized."
                )
            else:
                err_msg = ", ".join(res.errors) if res.errors else "Unknown sync error"
                self.lbl_region_status.setText(f"⚠️ Partial sync: {err_msg}")
                self.lbl_region_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
                QMessageBox.warning(self, "Region Sync Incomplete", f"Partial region switch results:\\n{err_msg}")
        except Exception as e:
            self.lbl_region_status.setText(f"❌ Error: {e}")
            self.lbl_region_status.setStyleSheet("color: #dc2626; font-size: 11px;")
            QMessageBox.critical(self, "Region Sync Failed", str(e))

    def action_check_egress_ip(self):
        self.lbl_region_status.setText("Checking live egress IP and geo-location...")
        try:
            from nexus.region_controller import UniversalRegionController
            target_ser = self.target_serial or "emulator-5554"
            rc = UniversalRegionController(serial=target_ser, adb_path=SystemPaths.get_adb())
            egress = rc.verify_egress()
            ip = egress.get("ip", "Unknown")
            cc = egress.get("country", "Unknown")
            isp = egress.get("org", "Unknown")
            self.lbl_region_status.setText(f"🌐 Egress: {ip} | Country: {cc} | ISP: {isp}")
            self.lbl_region_status.setStyleSheet("color: #0284c7; font-weight: 600; font-size: 11px;")
            QMessageBox.information(
                self, "Live Egress Verified",
                f"Active Public Internet Egress:\\n\\n"
                f"• IP Address: {ip}\\n"
                f"• Country Code: {cc}\\n"
                f"• Provider / ISP: {isp}"
            )
        except Exception as e:
            self.lbl_region_status.setText(f"❌ Egress check failed: {e}")
            self.lbl_region_status.setStyleSheet("color: #dc2626; font-size: 11px;")
            QMessageBox.warning(self, "Egress Check Failed", str(e))

    def action_test_proxy_health(self):
        host = self.txt_proxy_host.text().strip()
        port = self.spin_proxy_port.value()
        proto_str = self.combo_proxy_proto.currentData() or "HTTP"
        user = self.txt_proxy_user.text().strip()
        pwd = self.txt_proxy_pass.text().strip()
        if not host:
            QMessageBox.warning(self, "Proxy Test", "Please specify an upstream proxy host.")
            return

        self.lbl_proxy_status.setText(f"Testing connectivity to {host}:{port} via {proto_str}...")
        try:
            from nexus.proxy_manager import EnterpriseProxyManager, UpstreamConfig, ProxyProtocol
            proto_map = {
                "HTTP": ProxyProtocol.HTTP,
                "HTTPS": ProxyProtocol.HTTPS,
                "SOCKS5": ProxyProtocol.SOCKS5,
                "SOCKS5H": ProxyProtocol.SOCKS5H,
            }
            cfg = UpstreamConfig(
                host=host,
                port=port,
                protocol=proto_map.get(proto_str, ProxyProtocol.HTTP),
                username=user,
                password=pwd
            )
            pm = EnterpriseProxyManager()
            ok, msg = pm.check_upstream_health(cfg)
            if ok:
                self.lbl_proxy_status.setText(f"✅ {msg}")
                self.lbl_proxy_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px;")
                QMessageBox.information(self, "Proxy Online", f"Upstream Proxy Online!\\n\\n{msg}")
            else:
                self.lbl_proxy_status.setText(f"❌ Connection failed: {msg}")
                self.lbl_proxy_status.setStyleSheet("color: #dc2626; font-size: 11px;")
                QMessageBox.warning(self, "Proxy Unreachable", f"Failed to connect to proxy:\\n\\n{msg}")
        except Exception as e:
            self.lbl_proxy_status.setText(f"❌ Test error: {e}")
            self.lbl_proxy_status.setStyleSheet("color: #dc2626; font-size: 11px;")
            QMessageBox.critical(self, "Proxy Test Error", str(e))

    def action_toggle_proxy_daemon(self):
        if not hasattr(self, "_proxy_daemon_running"):
            self._proxy_daemon_running = False
            self._proxy_mgr = None

        if not self._proxy_daemon_running:
            host = self.txt_proxy_host.text().strip()
            port = self.spin_proxy_port.value()
            proto_str = self.combo_proxy_proto.currentData() or "HTTP"
            user = self.txt_proxy_user.text().strip()
            pwd = self.txt_proxy_pass.text().strip()
            if not host:
                QMessageBox.warning(self, "Proxy Host Missing", "Please enter upstream proxy host first.")
                return
            try:
                from nexus.proxy_manager import EnterpriseProxyManager, UpstreamConfig, ProxyProtocol, ProxyMode
                proto_map = {
                    "HTTP": ProxyProtocol.HTTP,
                    "HTTPS": ProxyProtocol.HTTPS,
                    "SOCKS5": ProxyProtocol.SOCKS5,
                    "SOCKS5H": ProxyProtocol.SOCKS5H,
                }
                cfg = UpstreamConfig(
                    host=host,
                    port=port,
                    protocol=proto_map.get(proto_str, ProxyProtocol.HTTP),
                    username=user,
                    password=pwd
                )
                self._proxy_mgr = EnterpriseProxyManager(upstream=cfg)
                local_port = self._proxy_mgr.start_auth_proxy()
                target_ser = self.target_serial or "emulator-5554"
                mode_str = self.combo_proxy_mode.currentData() or "local_auth"
                mode = ProxyMode.TUN2SOCKS if mode_str == "tun2socks" else ProxyMode.LOCAL_AUTH
                self._proxy_mgr.attach_instance_proxy(serial=target_ser, mode=mode)
                self._proxy_daemon_running = True
                self.btn_toggle_proxy_daemon.setText("⏹ Stop Local Proxy Daemon")
                self.btn_toggle_proxy_daemon.setStyleSheet("background: #dc2626; color: #ffffff; font-weight: 600;")
                self.lbl_proxy_status.setText(f"🟢 Proxy Daemon running on 127.0.0.1:{local_port} (Attached to {target_ser})")
                self.lbl_proxy_status.setStyleSheet("color: #10b981; font-weight: 600; font-size: 11px;")
                QMessageBox.information(
                    self, "Proxy Daemon Active",
                    f"Enterprise Proxy Daemon is running!\\n\\n"
                    f"• Local Endpoint: 127.0.0.1:{local_port}\\n"
                    f"• Upstream Target: {proto_str}://{host}:{port}\\n"
                    f"• Auth Stripping: Active (No Android credential popups)\\n"
                    f"• Attached Serial: {target_ser}"
                )
            except Exception as e:
                self.lbl_proxy_status.setText(f"❌ Failed to start daemon: {e}")
                self.lbl_proxy_status.setStyleSheet("color: #dc2626; font-size: 11px;")
                QMessageBox.critical(self, "Proxy Daemon Error", str(e))
        else:
            if getattr(self, "_proxy_mgr", None):
                try:
                    target_ser = self.target_serial or "emulator-5554"
                    self._proxy_mgr.detach_instance_proxy(serial=target_ser)
                    self._proxy_mgr.stop_auth_proxy()
                except Exception:
                    pass
                self._proxy_mgr = None
            self._proxy_daemon_running = False
            self.btn_toggle_proxy_daemon.setText("▶ Start Local Proxy Daemon")
            self.btn_toggle_proxy_daemon.setStyleSheet("")
            self.lbl_proxy_status.setText("Proxy Status: Standby")
            self.lbl_proxy_status.setStyleSheet("color: #64748b; font-size: 11px;")

'''
    if "def action_apply_region_sync(self):" not in content:
        target_ip_mode = "    def on_ip_mode_toggled(self):"
        assert target_ip_mode in content
        content = content.replace(target_ip_mode, settings_methods + target_ip_mode)
        print("Inserted helper methods into GNDroidSettingsDialog")

    # 7. Update action_save_settings in GNDroidSettingsDialog
    save_anchor = '"runtime.network.speed": str(self.combo_net_speed.currentData())\n        }'
    save_expansion = '''"runtime.network.speed": str(self.combo_net_speed.currentData()),
            "gndroid.region": str(self.combo_region.currentData() or "US"),
            "gndroid.proxy_mode": str(self.combo_proxy_mode.currentData() or "disabled"),
            "gndroid.proxy_protocol": str(self.combo_proxy_proto.currentData() or "HTTP"),
            "gndroid.proxy_host": self.txt_proxy_host.text().strip(),
            "gndroid.proxy_port": str(self.spin_proxy_port.value()),
            "gndroid.proxy_user": self.txt_proxy_user.text().strip(),
            "gndroid.proxy_pass": self.txt_proxy_pass.text().strip(),
            "gndroid.proxy_dns": "yes" if self.chk_dns_over_proxy.isChecked() else "no",
            "gndroid.proxy_killswitch": "yes" if self.chk_kill_switch.isChecked() else "no",
            "gndroid.gaming_mode": "yes" if self.chk_gaming_mode.isChecked() else "no"
        }'''
    if '"gndroid.region":' not in content:
        assert save_anchor in content
        content = content.replace(save_anchor, save_expansion)
        print("Updated action_save_settings to persist region, proxy, and gaming mode")

    # 8. Add Gaming Mode Quick-Toggle in Main Window (GNDroidApp)
    btn_row_anchor = 'df_layout.addLayout(btn_row)'
    game_toggle_code = '''df_layout.addLayout(btn_row)

        # Gaming Mode Quick-Toggle
        game_toggle_row = QHBoxLayout()
        game_toggle_row.setContentsMargins(2, 2, 2, 4)
        self.chk_gaming_mode = QCheckBox("⚡ Gaming Mode (120Hz Display / Host P-Core Priority / <1ms Latency)")
        self.chk_gaming_mode.setStyleSheet("color: #0284c7; font-weight: 600; font-size: 11px;")
        self.chk_gaming_mode.setToolTip("Allocates VM execution exclusively to Intel/AMD Performance cores and enables 120 FPS high-refresh rate")
        self.chk_gaming_mode.toggled.connect(self.on_gaming_mode_toggled)
        game_toggle_row.addWidget(self.chk_gaming_mode)
        game_toggle_row.addStretch()
        df_layout.addLayout(game_toggle_row)'''
    if 'self.chk_gaming_mode = QCheckBox' not in content:
        assert btn_row_anchor in content
        content = content.replace(btn_row_anchor, game_toggle_code, 1)
        print("Inserted Gaming Mode Quick-Toggle into GNDroidApp")

    # 9. Add on_gaming_mode_toggled and hook into on_device_selection_changed
    gaming_toggle_handler = '''    def on_gaming_mode_toggled(self, checked: bool):
        data = self.dev_combo.currentData()
        if isinstance(data, dict) and data.get("type") == "vm":
            raw_name = data.get("name", "gndroid")
            try:
                AVDManager.save_full_instance_config(raw_name, {"gndroid.gaming_mode": "yes" if checked else "no"})
            except Exception:
                pass

'''
    if "def on_gaming_mode_toggled(self" not in content:
        target_dev_sel = "    def on_device_selection_changed(self, index: int):"
        assert target_dev_sel in content
        content = content.replace(target_dev_sel, gaming_toggle_handler + target_dev_sel)
        print("Inserted on_gaming_mode_toggled handler into GNDroidApp")

    # Hook config reading into on_device_selection_changed
    sel_hook_anchor = 'is_booting = raw_name in getattr(self, "_booting_instances", set())'
    sel_hook_code = '''if hasattr(self, "chk_gaming_mode"):
                try:
                    _c = AVDManager.get_instance_full_config(raw_name)
                    self.chk_gaming_mode.blockSignals(True)
                    self.chk_gaming_mode.setChecked(_c.get("gndroid.gaming_mode", "no").lower() in ("yes", "true", "1"))
                    self.chk_gaming_mode.blockSignals(False)
                except Exception:
                    pass
            is_booting = raw_name in getattr(self, "_booting_instances", set())'''
    if "self.chk_gaming_mode.blockSignals(True)" not in content:
        assert sel_hook_anchor in content
        content = content.replace(sel_hook_anchor, sel_hook_code)
        print("Hooked gaming mode config state into on_device_selection_changed")

    # Pass gaming_mode into launch_virtual_machine
    launch_anchor = '''            proc, port, log_path = AVDManager.launch_emulator_instance(
                name=name,
                gpu_mode=gpu_mode,
                is_root=inst.get("root", False) if inst else False
            )'''
    launch_expansion = '''            is_gaming = getattr(self, "chk_gaming_mode", None) and self.chk_gaming_mode.isChecked()
            proc, port, log_path = AVDManager.launch_emulator_instance(
                name=name,
                gpu_mode=gpu_mode,
                is_root=inst.get("root", False) if inst else False,
                gaming_mode=is_gaming
            )'''
    if "gaming_mode=is_gaming" not in content:
        assert launch_anchor in content
        content = content.replace(launch_anchor, launch_expansion)
        print("Updated launch_virtual_machine to pass gaming_mode")

    with open("gndroid.pyw", "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully wrote updated gndroid.pyw")

if __name__ == "__main__":
    main()

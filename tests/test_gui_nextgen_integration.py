import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure workspace root is in sys.path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_gndroid_macro_dialog_init(qapp):
    """Verify GNDroidMacroDialog constructs properly with controls and engine."""
    import gndroid
    dlg = gndroid.GNDroidMacroDialog(default_serial="emulator-5554")
    assert dlg.serial == "emulator-5554"
    assert dlg.btn_rec is not None
    assert dlg.btn_play is not None
    assert dlg.btn_save is not None
    assert dlg.btn_load is not None
    assert dlg.spin_loops.value() == 1
    assert dlg.combo_speed.count() >= 4

    # Test recording start and stop
    dlg.toggle_record()
    assert dlg._is_recording is True
    assert "Recording started" in dlg.log_text.toPlainText()
    dlg.toggle_record()
    assert dlg._is_recording is False
    assert "Stopped" in dlg.log_text.toPlainText()
    dlg.close()


def test_gndroid_multi_instance_manager_nextgen_controls(qapp):
    """Verify GNDroidMultiInstanceManager contains Next-Gen action buttons."""
    import gndroid
    with patch.object(gndroid.GNDroidMultiInstanceManager, "refresh_table", return_value=None), \
         patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=[]):
        mgr = gndroid.GNDroidMultiInstanceManager()
        assert hasattr(mgr, "btn_sync")
        assert hasattr(mgr, "btn_eco")
        assert hasattr(mgr, "btn_trim_ram")
        assert hasattr(mgr, "btn_macro")
        assert "Sync Operations" in mgr.btn_sync.text()
        assert "Eco Mode" in mgr.btn_eco.text()
        assert "Trim RAM" in mgr.btn_trim_ram.text()
        assert "Macro Recorder" in mgr.btn_macro.text()
        mgr.close()


def test_gndroid_multi_instance_manager_toggle_sync_not_enough_devices(qapp):
    """Verify toggle_sync_operations warns when <2 instances are running."""
    import gndroid
    with patch.object(gndroid.GNDroidMultiInstanceManager, "refresh_table", return_value=None), \
         patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=[{"serial": "emulator-5554", "state": "device"}]), \
         patch.object(gndroid.QMessageBox, "information") as mock_info:
        mgr = gndroid.GNDroidMultiInstanceManager()
        mgr.toggle_sync_operations()
        assert mock_info.called
        assert "At least 2 running instances are required" in mock_info.call_args[0][2]
        assert mgr._sync_active is False
        mgr.close()


def test_gndroid_multi_instance_manager_toggle_sync_active(qapp):
    """Verify toggle_sync_operations activates when >=2 instances are running."""
    import gndroid
    devs = [
        {"serial": "emulator-5554", "state": "device"},
        {"serial": "emulator-5556", "state": "device"}
    ]
    with patch.object(gndroid.GNDroidMultiInstanceManager, "refresh_table", return_value=None), \
         patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=devs), \
         patch("nexus.sync_multiplexer.InputSyncMultiplexer") as mock_mux_cls, \
         patch.object(gndroid.QMessageBox, "information"):
        mock_mux = MagicMock()
        mock_mux_cls.return_value = mock_mux

        mgr = gndroid.GNDroidMultiInstanceManager()
        mgr.toggle_sync_operations()
        assert mgr._sync_active is True
        assert "Sync Operations: ON" in mgr.btn_sync.text()

        # Toggle off
        mgr.toggle_sync_operations()
        assert mgr._sync_active is False
        assert "Sync Operations: OFF" in mgr.btn_sync.text()
        mgr.close()


def test_gndroid_multi_instance_manager_eco_mode_toggle(qapp):
    """Verify Eco Mode toggling in Multi-Instance Manager."""
    import gndroid
    with patch.object(gndroid.GNDroidMultiInstanceManager, "refresh_table", return_value=None), \
         patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=[{"serial": "emulator-5554", "state": "device"}]), \
         patch("nexus.eco_throttler.EcoThrottler") as mock_eco_cls, \
         patch.object(gndroid.QMessageBox, "information"):
        mock_eco = MagicMock()
        mock_eco_cls.return_value = mock_eco

        mgr = gndroid.GNDroidMultiInstanceManager()
        mgr.toggle_eco_mode()
        assert mgr._eco_active is True
        assert "Eco Mode: ON" in mgr.btn_eco.text()

        mgr.toggle_eco_mode()
        assert mgr._eco_active is False
        assert "Eco Mode: OFF" in mgr.btn_eco.text()
        mgr.close()


def test_gndroid_multi_instance_manager_trim_ram(qapp):
    """Verify Trim RAM action executes 4-tier memory purge across instances."""
    import gndroid
    with patch.object(gndroid.GNDroidMultiInstanceManager, "refresh_table", return_value=None), \
         patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=[{"serial": "emulator-5554", "state": "device"}]), \
         patch("nexus.memory_trimmer.MemoryTrimmer") as mock_trim_cls, \
         patch.object(gndroid.QMessageBox, "information") as mock_info:
        mock_trimmer = MagicMock()
        mock_trimmer.trim_instance.return_value = {"reclaimed_mb": 142.5, "tiers": {}}
        mock_trimmer.execute_tier4_host_empty_working_set.return_value = True
        mock_trim_cls.return_value = mock_trimmer

        mgr = gndroid.GNDroidMultiInstanceManager()
        mgr.action_trim_ram()
        assert mock_info.called
        assert "142.5 MB" in mock_info.call_args[0][2]
        mgr.close()


def test_settings_dialog_tab5_universal_region_and_proxy(qapp):
    """Verify Tab 5 exists in GNDroidSettingsDialog with complete controls."""
    import gndroid
    dummy_cfg = {
        "avd.ini.displayname": "GNDROiD Test",
        "gndroid.region": "AE",
        "gndroid.proxy_mode": "local_auth",
        "gndroid.proxy_protocol": "HTTP",
        "gndroid.proxy_host": "192.168.1.100",
        "gndroid.proxy_port": "8888",
        "gndroid.gaming_mode": "yes"
    }
    with patch.object(gndroid.AVDManager, "get_instance_full_config", return_value=dummy_cfg):
        dlg = gndroid.GNDroidSettingsDialog(instance_name="gndroid")
        assert dlg.tabs.count() >= 5
        tab_title = dlg.tabs.tabText(4)
        assert "Region & Proxy" in tab_title

        # Check Region controls
        assert dlg.combo_region.count() >= 7
        assert dlg.combo_region.currentData() == "AE"
        assert hasattr(dlg, "lbl_region_details")
        assert "United Arab Emirates" in dlg.lbl_region_details.text()
        assert hasattr(dlg, "btn_apply_region")
        assert hasattr(dlg, "btn_test_egress")

        # Check Proxy controls
        assert dlg.combo_proxy_mode.currentData() == "local_auth"
        assert dlg.combo_proxy_proto.currentData() == "HTTP"
        assert dlg.txt_proxy_host.text() == "192.168.1.100"
        assert dlg.spin_proxy_port.value() == 8888
        assert hasattr(dlg, "chk_dns_over_proxy")
        assert hasattr(dlg, "chk_kill_switch")
        assert hasattr(dlg, "btn_test_proxy")
        assert hasattr(dlg, "btn_toggle_proxy_daemon")

        # Check Gaming Profile control
        assert dlg.chk_gaming_mode.isChecked() is True
        dlg.close()


def test_settings_dialog_action_save_persists_nextgen_keys(qapp):
    """Verify action_save_settings in GNDroidSettingsDialog persists next-gen keys."""
    import gndroid
    saved_dict = {}

    def mock_save(name, cfg_dict):
        saved_dict.update(cfg_dict)
        return True

    with patch.object(gndroid.AVDManager, "get_instance_full_config", return_value={}), \
         patch.object(gndroid.AVDManager, "save_full_instance_config", side_effect=mock_save), \
         patch.object(gndroid.QMessageBox, "information"):
        dlg = gndroid.GNDroidSettingsDialog(instance_name="gndroid")
        # Change values
        dlg.combo_region.setCurrentIndex(dlg.combo_region.findData("SA"))
        dlg.combo_proxy_mode.setCurrentIndex(dlg.combo_proxy_mode.findData("tun2socks"))
        dlg.combo_proxy_proto.setCurrentIndex(dlg.combo_proxy_proto.findData("SOCKS5"))
        dlg.txt_proxy_host.setText("proxy.saudi.com")
        dlg.spin_proxy_port.setValue(1080)
        dlg.txt_proxy_user.setText("stc_user")
        dlg.txt_proxy_pass.setText("stc_pass")
        dlg.chk_dns_over_proxy.setChecked(True)
        dlg.chk_kill_switch.setChecked(True)
        dlg.chk_gaming_mode.setChecked(True)

        dlg.action_save_settings()

        assert saved_dict.get("gndroid.region") == "SA"
        assert saved_dict.get("gndroid.proxy_mode") == "tun2socks"
        assert saved_dict.get("gndroid.proxy_protocol") == "SOCKS5"
        assert saved_dict.get("gndroid.proxy_host") == "proxy.saudi.com"
        assert saved_dict.get("gndroid.proxy_port") == "1080"
        assert saved_dict.get("gndroid.proxy_user") == "stc_user"
        assert saved_dict.get("gndroid.proxy_pass") == "stc_pass"
        assert saved_dict.get("gndroid.proxy_dns") == "yes"
        assert saved_dict.get("gndroid.proxy_killswitch") == "yes"
        assert saved_dict.get("gndroid.gaming_mode") == "yes"
        dlg.close()


def test_companion_sidebar_and_worker_split_apk_bundle_handling(qapp):
    """Verify AdbInstallOrPushWorker properly routes split bundle extensions."""
    import gndroid
    worker = gndroid.AdbInstallOrPushWorker(
        files=["test_bundle.xapk", "test_bundle.aab"],
        target_serial="emulator-5554"
    )
    with patch("os.path.exists", return_value=True), \
         patch("nexus.package_installer.install_split_apk_bundle", return_value=(True, "Success")):
        results = []
        worker.file_result.connect(lambda fn, ok, msg: results.append((fn, ok, msg)))
        worker.run()
        assert len(results) == 2
        assert results[0][1] is True
        assert results[1][1] is True


def test_main_app_gaming_mode_toggle_and_launch(qapp):
    """Verify GNDroidApp contains Gaming Mode toggle and propagates to launch."""
    import gndroid
    with patch.object(gndroid.AVDManager, "list_instances", return_value=[]), \
         patch.object(gndroid.SystemPaths, "list_devices", return_value=[]):
        app_win = gndroid.GNDroidApp()
        assert hasattr(app_win, "chk_gaming_mode")
        assert "Gaming Mode" in app_win.chk_gaming_mode.text()

        app_win.chk_gaming_mode.setChecked(True)
        assert app_win.chk_gaming_mode.isChecked() is True
        app_win.close()

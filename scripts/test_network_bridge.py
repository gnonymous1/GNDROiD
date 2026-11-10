"""
scripts/test_network_bridge.py
==============================
Unit and integration test suite for GNDROiD Network Adapter & Hardware Bridging.
"""

import os
import sys
import time
import socket
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nexus.network_bridge import (
    get_system_network_adapters,
    get_primary_physical_adapter,
    get_system_bluetooth_adapters,
    get_physical_bluetooth_controller,
    get_paired_bluetooth_devices,
    get_default_gateway,
    get_instance_network_config,
    save_instance_network_config,
    get_emulator_network_args,
    SocketRelayHub
)

class TestNetworkBridgeSuite(unittest.TestCase):

    def test_01_get_system_network_adapters(self):
        adapters = get_system_network_adapters()
        self.assertIsInstance(adapters, list)
        self.assertGreater(len(adapters), 0)
        
        # Verify structure
        for a in adapters:
            self.assertIn("name", a)
            self.assertIn("description", a)
            self.assertIn("display_label", a)
            self.assertIn("is_physical", a)
            self.assertIn("ips", a)

    def test_02_get_primary_physical_adapter(self):
        primary = get_primary_physical_adapter()
        self.assertIsNotNone(primary)
        self.assertTrue(primary.get("is_physical"))
        self.assertTrue(len(primary.get("ips", [])) > 0)
        self.assertTrue(primary["primary_ip"].startswith("192.168."))

    def test_03_get_default_gateway(self):
        gw = get_default_gateway()
        self.assertTrue(len(gw) > 6)
        self.assertTrue(gw.startswith("192.168."))

    def test_04_get_bluetooth_adapters(self):
        bt_ctrl = get_physical_bluetooth_controller()
        self.assertIsNotNone(bt_ctrl)
        self.assertTrue(bt_ctrl.get("is_physical"))
        self.assertIn("Realtek", bt_ctrl.get("name", ""))

        paired = get_paired_bluetooth_devices()
        self.assertIsInstance(paired, list)
        self.assertGreater(len(paired), 0)

    def test_05_instance_network_config_io(self):
        # Read default config and preserve it
        orig_cfg = get_instance_network_config("gndroid")
        self.assertIn("mode", orig_cfg)
        self.assertIn("adapter_name", orig_cfg)
        self.assertIn("replicate_state", orig_cfg)

        try:
            # Write test config
            test_cfg = {
                "mode": "lan_bridge",
                "adapter_name": "Realtek RTL8852BE WiFi 6 802.11ax PCIe Adapter",
                "replicate_state": True,
                "bluetooth_enabled": True,
                "bluetooth_mode": "netsimd",
                "exposed_ports": "51888, 51880, 5555, 8080, 8088"
            }
            ok = save_instance_network_config("gndroid", test_cfg)
            self.assertTrue(ok)

            # Re-read and verify
            re_cfg = get_instance_network_config("gndroid")
            self.assertEqual(re_cfg["mode"], "lan_bridge")
            self.assertEqual(re_cfg["adapter_name"], "Realtek RTL8852BE WiFi 6 802.11ax PCIe Adapter")
            self.assertTrue(re_cfg["replicate_state"])
        finally:
            save_instance_network_config("gndroid", orig_cfg)

    def test_06_emulator_network_args(self):
        args = get_emulator_network_args("gndroid")
        self.assertIsInstance(args, list)
        self.assertIn("-dns-server", args)
        self.assertIn("-wifi-mac-address", args)
        # Ensure -grpc override is not injected (which would stall ADB registration)
        self.assertNotIn("-grpc", args)
        # Ensure -qemu (if present) only appears after all emulator flags
        if "-qemu" in args:
            q_idx = args.index("-qemu")
            self.assertGreater(q_idx, args.index("-dns-server"))

    def test_07_socket_relay_hub(self):
        # Test custom high-speed socket relay on high ephemeral port
        test_ext_port = 59123
        test_target_port = 59124

        # Start a local echo server on target port
        target_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_server.bind(("127.0.0.1", test_target_port))
        target_server.listen(1)

        hub = SocketRelayHub(host_bind="127.0.0.1", port_map={test_ext_port: test_target_port})
        hub.start()
        time.sleep(0.1)

        # Connect client to relay port
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", test_ext_port))

        target_conn, _ = target_server.accept()
        client.sendall(b"GNDROiD_TEST_PACKET")
        received = target_conn.recv(1024)
        self.assertEqual(received, b"GNDROiD_TEST_PACKET")

        target_conn.sendall(b"GNDROiD_RESPONSE_PACKET")
        resp = client.recv(1024)
        self.assertEqual(resp, b"GNDROiD_RESPONSE_PACKET")

        client.close()
        target_conn.close()
        target_server.close()
        hub.stop()

if __name__ == '__main__':
    unittest.main()

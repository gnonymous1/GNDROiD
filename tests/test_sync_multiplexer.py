"""
tests/test_sync_multiplexer.py
==============================
E2E Test Suite for Feature 13: Multi-Instance Input Synchronizer.

Covers:
- Tier 1: Feature Coverage (Happy Path, 5 tests)
  * [F13-T1-01] Master-to-Slave Touch Event Broadcast Serialization (32-byte wire format)
  * [F13-T1-02] Master-to-Slave Key Event Broadcast Serialization (14-byte wire format)
  * [F13-T1-03] Multi-Slave Concurrent Fan-Out (Simultaneous Dispatch)
  * [F13-T1-04] Heterogeneous Coordinate Normalization and Scaling
  * [F13-T1-05] Dynamic Slave Addition and Removal During Active Stream
- Tier 2: Boundary & Corner Cases (Fault Injection, 5 tests)
  * [F13-T2-01] Slave Socket Broken Pipe Auto-Eviction
  * [F13-T2-02] Malformed Packet Injection Handling
  * [F13-T2-03] Out-of-Bounds Coordinate Clamping
  * [F13-T2-04] Burst Event Flooding Stress Test (1,000 Events)
  * [F13-T2-05] Zero-Dimension and Degenerate Viewport Safety

Total: 10 Test Cases (5 Tier 1, 5 Tier 2)
"""

import time
import socket
import struct
import unittest
from typing import List, Tuple

from tests.fixtures.mock_scrcpy import MockScrcpyControlServer
from nexus.sync_multiplexer import (
    AMOTION_EVENT_ACTION_DOWN,
    AMOTION_EVENT_ACTION_MOVE,
    AMOTION_EVENT_ACTION_UP,
    AMOTION_EVENT_BUTTON_PRIMARY,
    AKEY_EVENT_ACTION_DOWN,
    AKEY_EVENT_ACTION_UP,
    CONTROL_MSG_TYPE_INJECT_KEYCODE,
    CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT,
    KEY_PACKET_FORMAT,
    KEY_PACKET_SIZE,
    TOUCH_PACKET_FORMAT,
    TOUCH_PACKET_SIZE,
    InputSyncMultiplexer,
    decode_key_packet,
    decode_touch_packet,
    encode_key_packet,
    encode_touch_packet,
    scale_coordinate,
)


class TestFeature13InputSynchronizer(unittest.TestCase):
    """Feature 13: Multi-Instance Input Synchronizer (10 Tests)"""

    def setUp(self):
        self.multiplexer = InputSyncMultiplexer()

    def tearDown(self):
        # Cleanly close all slave and master sockets
        slaves = self.multiplexer.get_slaves()
        for serial in list(slaves.keys()):
            self.multiplexer.remove_slave(serial)
        master = self.multiplexer.get_master()
        if master:
            master.close()

    # =========================================================================
    # Tier 1: Feature Coverage (Happy Path)
    # =========================================================================

    def test_01_master_to_slave_touch_broadcast_serialization(self):
        """[F13-T1-01] Verify master-to-slave touch event serialization in Scrcpy 32-byte wire format."""
        s_send, s_recv = socket.socketpair()
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)
            self.multiplexer.add_slave("slave-5556", 1440, 3120, control_socket=s_send)

            # Master dispatches touch DOWN at (720, 1560)
            sent_count = self.multiplexer.send_touch(
                action=AMOTION_EVENT_ACTION_DOWN,
                pointer_id=1,
                x=720,
                y=1560,
                pressure=0xFFFF,
                action_button=AMOTION_EVENT_BUTTON_PRIMARY,
                buttons=AMOTION_EVENT_BUTTON_PRIMARY,
            )
            self.assertEqual(sent_count, 1)

            # Receive raw packet on slave socket
            raw_pkt = s_recv.recv(32)
            self.assertEqual(len(raw_pkt), 32)

            # Struct unpack verification
            fields = struct.unpack_from(">BBQIIHHHII", raw_pkt, 0)
            msg_type, action, pointer_id, x, y, width, height, pressure, action_btn, buttons = fields

            self.assertEqual(msg_type, CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT)
            self.assertEqual(action, AMOTION_EVENT_ACTION_DOWN)
            self.assertEqual(pointer_id, 1)
            self.assertEqual(x, 720)
            self.assertEqual(y, 1560)
            self.assertEqual(width, 1440)
            self.assertEqual(height, 3120)
            self.assertEqual(pressure, 0xFFFF)
            self.assertEqual(action_btn, AMOTION_EVENT_BUTTON_PRIMARY)
            self.assertEqual(buttons, AMOTION_EVENT_BUTTON_PRIMARY)
        finally:
            s_send.close()
            s_recv.close()

    def test_02_master_to_slave_key_broadcast_serialization(self):
        """[F13-T1-02] Verify master-to-slave key event serialization in Scrcpy 14-byte wire format."""
        s_send, s_recv = socket.socketpair()
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)
            self.multiplexer.add_slave("slave-5556", 1440, 3120, control_socket=s_send)

            # Dispatch BACK key DOWN (AKEYCODE_BACK = 4)
            sent_count = self.multiplexer.send_key(
                action=AKEY_EVENT_ACTION_DOWN,
                keycode=4,
                repeat=0,
                metastate=0,
            )
            self.assertEqual(sent_count, 1)

            # Receive raw key packet
            raw_pkt = s_recv.recv(14)
            self.assertEqual(len(raw_pkt), 14)

            # Struct unpack: >BBIII
            msg_type, action, keycode, repeat, metastate = struct.unpack_from(">BBIII", raw_pkt, 0)
            self.assertEqual(msg_type, CONTROL_MSG_TYPE_INJECT_KEYCODE)
            self.assertEqual(action, AKEY_EVENT_ACTION_DOWN)
            self.assertEqual(keycode, 4)
            self.assertEqual(repeat, 0)
            self.assertEqual(metastate, 0)
        finally:
            s_send.close()
            s_recv.close()

    def test_03_multi_slave_concurrent_fan_out(self):
        """[F13-T1-03] Verify concurrent fan-out to 3 connected slaves simultaneously."""
        s1_send, s1_recv = socket.socketpair()
        s2_send, s2_recv = socket.socketpair()
        s3_send, s3_recv = socket.socketpair()
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)
            self.multiplexer.add_slave("slave-1", 1440, 3120, control_socket=s1_send)
            self.multiplexer.add_slave("slave-2", 1440, 3120, control_socket=s2_send)
            self.multiplexer.add_slave("slave-3", 1440, 3120, control_socket=s3_send)

            pkt = encode_touch_packet(
                action=AMOTION_EVENT_ACTION_MOVE,
                pointer_id=0,
                x=500,
                y=1000,
                width=1440,
                height=3120,
            )
            sent_count = self.multiplexer.broadcast_event(pkt, event_type="touch")
            self.assertEqual(sent_count, 3)

            # Verify all 3 sockets received the identical 32 bytes
            for s_recv in (s1_recv, s2_recv, s3_recv):
                recv_bytes = s_recv.recv(32)
                self.assertEqual(len(recv_bytes), 32)
                decoded = decode_touch_packet(recv_bytes)
                self.assertEqual((decoded["x"], decoded["y"]), (500, 1000))
        finally:
            for s in (s1_send, s1_recv, s2_send, s2_recv, s3_send, s3_recv):
                s.close()

    def test_04_heterogeneous_coordinate_normalization_scaling(self):
        """[F13-T1-04] Verify coordinate scaling from Master 1440x3120 to Slave 1 1080x2400 and Slave 2 720x1600."""
        # Top-left corner (0, 0)
        s1_x, s1_y = scale_coordinate(0, 0, 1440, 3120, 1080, 2400)
        s2_x, s2_y = scale_coordinate(0, 0, 1440, 3120, 720, 1600)
        self.assertEqual((s1_x, s1_y), (0, 0))
        self.assertEqual((s2_x, s2_y), (0, 0))

        # Center point (720, 1560)
        s1_cx, s1_cy = scale_coordinate(720, 1560, 1440, 3120, 1080, 2400)
        s2_cx, s2_cy = scale_coordinate(720, 1560, 1440, 3120, 720, 1600)
        self.assertEqual((s1_cx, s1_cy), (540, 1200))
        self.assertEqual((s2_cx, s2_cy), (360, 800))

        # Max bounds (1440, 3120)
        s1_mx, s1_my = scale_coordinate(1440, 3120, 1440, 3120, 1080, 2400)
        s2_mx, s2_my = scale_coordinate(1440, 3120, 1440, 3120, 720, 1600)
        self.assertEqual((s1_mx, s1_my), (1080, 2400))
        self.assertEqual((s2_mx, s2_my), (720, 1600))

    def test_05_dynamic_slave_addition_removal_active_stream(self):
        """[F13-T1-05] Verify dynamic addition and removal of slaves during an active touch broadcast stream."""
        s1_send, s1_recv = socket.socketpair()
        s2_send, s2_recv = socket.socketpair()
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)

            # Step 1: Add Slave 1 -> broadcast returns 1
            self.multiplexer.add_slave("slave-1", 1440, 3120, control_socket=s1_send)
            count1 = self.multiplexer.send_touch(action=0, pointer_id=0, x=100, y=100)
            self.assertEqual(count1, 1)

            # Step 2: Add Slave 2 -> broadcast returns 2
            self.multiplexer.add_slave("slave-2", 1440, 3120, control_socket=s2_send)
            count2 = self.multiplexer.send_touch(action=2, pointer_id=0, x=150, y=150)
            self.assertEqual(count2, 2)

            # Step 3: Remove Slave 1 -> broadcast returns 1
            self.multiplexer.remove_slave("slave-1")
            count3 = self.multiplexer.send_touch(action=1, pointer_id=0, x=150, y=150)
            self.assertEqual(count3, 1)

            # Verify Slave 2 received the final touch UP
            data2 = s2_recv.recv(64)
            self.assertTrue(len(data2) >= 32)
        finally:
            s1_send.close()
            s1_recv.close()
            s2_send.close()
            s2_recv.close()

    # =========================================================================
    # Tier 2: Boundary & Corner Cases (Fault Injection)
    # =========================================================================

    def test_06_slave_socket_broken_pipe_auto_eviction(self):
        """[F13-T2-01] Verify abrupt slave socket termination results in automatic eviction without raising unhandled errors."""
        s1_send, s1_recv = socket.socketpair()
        s2_send, s2_recv = socket.socketpair()
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)
            self.multiplexer.add_slave("slave-healthy", 1080, 2400, control_socket=s1_send)
            self.multiplexer.add_slave("slave-crashing", 1080, 2400, control_socket=s2_send)

            # Simulate abrupt crash of slave 2
            s2_recv.close()
            s2_send.close()

            # Dispatch touch event - should succeed for healthy slave and cleanly evict crashing slave
            count = self.multiplexer.send_touch(action=AMOTION_EVENT_ACTION_DOWN, pointer_id=0, x=500, y=500)
            self.assertEqual(count, 1)

            # Verify dead slave was pruned from active list
            self.assertEqual(self.multiplexer.get_slave_count(), 1)
            self.assertIn("slave-healthy", self.multiplexer.get_slaves())
            self.assertNotIn("slave-crashing", self.multiplexer.get_slaves())
        finally:
            s1_send.close()
            s1_recv.close()

    def test_07_malformed_packet_injection_handling(self):
        """[F13-T2-02] Verify graceful rejection of truncated or corrupted binary packets."""
        # Truncated packet (fewer than 32 bytes)
        truncated_pkt = b"\x02\x00\x12\x34"
        with self.assertRaises(ValueError):
            decode_touch_packet(truncated_pkt)

        # Truncated key packet
        truncated_key = b"\x00\x01\x02"
        with self.assertRaises(ValueError):
            decode_key_packet(truncated_key)

    def test_08_out_of_bounds_coordinate_clamping(self):
        """[F13-T2-03] Verify that out-of-bounds coordinates (negative or exceeding resolution) are safely clamped."""
        # Negative coordinates clamped to 0
        neg_x, neg_y = scale_coordinate(-100, -200, 1440, 3120, 1080, 2400)
        self.assertEqual(neg_x, 0)
        self.assertEqual(neg_y, 0)

        # Extreme overshoot clamped to destination viewport max
        over_x, over_y = scale_coordinate(5000, 10000, 1440, 3120, 1080, 2400)
        self.assertEqual(over_x, 1080)
        self.assertEqual(over_y, 2400)

    def test_09_burst_event_flooding_stress_test(self):
        """[F13-T2-04] Verify burst event dispatch of 1,000 touch move events across 4 connected slaves executes in <1.0s."""
        pairs = [socket.socketpair() for _ in range(4)]
        try:
            self.multiplexer.register_master("master-5554", 1440, 3120)
            for idx, (s_send, _) in enumerate(pairs):
                self.multiplexer.add_slave(f"slave-{idx}", 1080, 2400, control_socket=s_send)

            start_t = time.perf_counter()
            for i in range(1000):
                x = (i * 7) % 1440
                y = (i * 13) % 3120
                pkt = encode_touch_packet(AMOTION_EVENT_ACTION_MOVE, 0, x, y, 1440, 3120)
                sent = self.multiplexer.broadcast_event(pkt, event_type="touch")
                self.assertEqual(sent, 4)
            elapsed = time.perf_counter() - start_t

            # Verify performance: 1,000 events * 4 slaves in less than 1.0 second
            self.assertLess(elapsed, 1.0, f"Burst took too long: {elapsed:.3f}s")
        finally:
            for s_send, s_recv in pairs:
                s_send.close()
                s_recv.close()

    def test_10_zero_dimension_and_degenerate_viewport_safety(self):
        """[F13-T2-05] Verify that zero-dimension or negative viewport dimensions do not cause division by zero."""
        # Zero source dimensions
        x0, y0 = scale_coordinate(100, 200, 0, 0, 1080, 2400)
        self.assertEqual((x0, y0), (100, 200))

        # Zero destination dimensions
        x1, y1 = scale_coordinate(100, 200, 1440, 3120, 0, 0)
        self.assertEqual((x1, y1), (100, 200))

        # Negative dimensions
        x2, y2 = scale_coordinate(100, 200, -1440, -3120, 1080, 2400)
        self.assertEqual((x2, y2), (100, 200))


if __name__ == "__main__":
    unittest.main()

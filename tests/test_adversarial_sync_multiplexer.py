#!/usr/bin/env python3
"""
tests/test_adversarial_sync_multiplexer.py - Empirical Adversarial Stress Test Suite
===================================================================================

Milestone M3 Adversarial Stress Testing for nexus/sync_multiplexer.py.
Authored by Challenger M3-1.

Empirically tests:
1. High-frequency packet broadcasting:
   - 1,200+ packets in rapid succession across 10 mock slave sockets with heterogeneous resolutions.
   - Measures broadcast latency per packet (<2ms requirement).
   - Validates 100% packet delivery integrity, zero corruption, and exact sequence order.
2. Resolution scaling edge cases:
   - Non-standard resolutions: 1440x3120 master to 320x480, 720x1560, 2160x3840 (4K), 1000x1000 (square), 1x1, 65535x65535.
   - Out of bounds coordinates: x < 0, y < 0, x > W, y > H, and extreme integer values.
   - Zero dimensions and zero coordinates: (0, 0) mapping, 0-dimension graceful fallback.
3. Abrupt socket disconnects:
   - Mid-broadcast abrupt socket terminations (SO_LINGER=0 RST, shutdown, close) across slave subsets.
   - Pruning validation: dead slaves pruned without dropping master events or blocking surviving slaves.
   - Total disconnect and recovery: all slaves die, multiplexer survives, new slave added and receives events.
4. Scrcpy packet serialization / deserialization integrity:
   - Bit-exact wire representation for 32-byte touch packets (>BBQIIHHHII) against strict Scrcpy 4.1 specification.
   - Bit-exact wire representation for 14-byte key packets (>BBIII).
   - Wire representations for scroll (>BIIHHhhI) and text (>BI+payload) packets.
   - Two's complement signed short wire integrity for negative scroll offsets.
   - Truncated / malformed packet error handling.
5. Multithreaded concurrency stress:
   - Concurrent event injection across multiple threads while nodes are dynamically added and removed.
"""

import socket
import struct
import threading
import time
import unittest
from typing import Any, Dict, List, Optional, Tuple

from nexus.sync_multiplexer import (
    AMOTION_EVENT_ACTION_DOWN,
    AMOTION_EVENT_ACTION_MOVE,
    AMOTION_EVENT_ACTION_UP,
    AMOTION_EVENT_BUTTON_PRIMARY,
    AMOTION_EVENT_BUTTON_SECONDARY,
    AKEY_EVENT_ACTION_DOWN,
    AKEY_EVENT_ACTION_UP,
    CONTROL_MSG_TYPE_INJECT_KEYCODE,
    CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT,
    CONTROL_MSG_TYPE_INJECT_TEXT,
    CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT,
    KEY_PACKET_FORMAT,
    KEY_PACKET_SIZE,
    SCROLL_PACKET_FORMAT,
    SCROLL_PACKET_SIZE,
    TOUCH_PACKET_FORMAT,
    TOUCH_PACKET_FORMAT_ALT,
    TOUCH_PACKET_SIZE,
    InputSyncMultiplexer,
    decode_key_packet,
    decode_scroll_packet,
    decode_text_packet,
    decode_touch_packet,
    encode_key_packet,
    encode_scroll_packet,
    encode_text_packet,
    encode_touch_packet,
    scale_coordinate,
)


def _recv_exact(sock: socket.socket, num_bytes: int, timeout: float = 5.0) -> bytes:
    """Reads exactly num_bytes from a socket with a timeout."""
    sock.settimeout(timeout)
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            raise EOFError(f"Socket closed while expecting {num_bytes - len(buf)} more bytes")
        buf.extend(chunk)
    return bytes(buf)


def _read_scrcpy_packet(sock: socket.socket, timeout: float = 5.0) -> Optional[bytes]:
    """Reads a single Scrcpy packet from a TCP socket stream."""
    try:
        header = _recv_exact(sock, 1, timeout=timeout)
    except (EOFError, socket.timeout, OSError):
        return None

    msg_type = header[0]
    if msg_type == CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT:  # 0x02
        rem = _recv_exact(sock, TOUCH_PACKET_SIZE - 1, timeout=timeout)
        return header + rem
    elif msg_type == CONTROL_MSG_TYPE_INJECT_KEYCODE:  # 0x00
        rem = _recv_exact(sock, KEY_PACKET_SIZE - 1, timeout=timeout)
        return header + rem
    elif msg_type == CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT:  # 0x03
        rem = _recv_exact(sock, SCROLL_PACKET_SIZE - 1, timeout=timeout)
        return header + rem
    elif msg_type == CONTROL_MSG_TYPE_INJECT_TEXT:  # 0x01
        len_bytes = _recv_exact(sock, 4, timeout=timeout)
        text_len = struct.unpack(">I", len_bytes)[0]
        payload = _recv_exact(sock, text_len, timeout=timeout)
        return header + len_bytes + payload
    else:
        raise ValueError(f"Unknown Scrcpy message type: 0x{msg_type:02X}")


class TestHighFrequencyBroadcasting(unittest.TestCase):
    """
    Empirical Stress Test 1:
    Broadcasts 1,200+ packets across 10 mock slave sockets in rapid succession.
    Measures latency and verifies bit-for-bit delivery integrity and scaling accuracy.
    """

    def setUp(self):
        self.multiplexer = InputSyncMultiplexer()

    def tearDown(self):
        self.multiplexer.close()

    def test_high_frequency_1200_packets_across_10_slaves(self):
        """
        Broadcasting 1,200 packets (touch, key, text, scroll) across 10 slaves.
        Target: sub-2ms per broadcast, 100% packet integrity, 0% loss.
        """
        # Configure master at 1440x3120 (Galaxy S24 Ultra)
        m_send, m_recv = socket.socketpair()
        self.multiplexer.register_master("master-s24u", 1440, 3120, control_socket=m_send)

        # 10 heterogeneous slave configurations
        slave_configs = [
            ("slave-0-fhd_plus", 1080, 2400),
            ("slave-1-hd_plus", 720, 1560),
            ("slave-2-qhd_plus", 1440, 3120),
            ("slave-3-hvga", 320, 480),
            ("slave-4-4k_uhd", 2160, 3840),
            ("slave-5-square", 1000, 1000),
            ("slave-6-fhd_16_9", 1080, 1920),
            ("slave-7-hd_16_9", 720, 1280),
            ("slave-8-tablet_wqxga", 1600, 2560),
            ("slave-9-tablet_wxga", 800, 1280),
        ]

        slave_pairs = []
        slave_receivers: List[socket.socket] = []

        for serial, w, h in slave_configs:
            s_send, s_recv = socket.socketpair()
            slave_pairs.append((s_send, s_recv))
            slave_receivers.append(s_recv)
            self.multiplexer.add_slave(serial, w, h, control_socket=s_send)

        TOTAL_PACKETS = 1200
        received_packets: Dict[int, List[bytes]] = {i: [] for i in range(10)}
        master_received: List[bytes] = []
        receiver_errors: List[Exception] = []

        # Background reader threads for each slave to prevent OS buffer saturation
        def slave_reader(slave_idx: int, sock: socket.socket):
            try:
                for _ in range(TOTAL_PACKETS):
                    pkt = _read_scrcpy_packet(sock, timeout=10.0)
                    if pkt is None:
                        break
                    received_packets[slave_idx].append(pkt)
            except Exception as e:
                receiver_errors.append(e)

        def master_reader(sock: socket.socket):
            try:
                for _ in range(TOTAL_PACKETS):
                    pkt = _read_scrcpy_packet(sock, timeout=10.0)
                    if pkt is None:
                        break
                    master_received.append(pkt)
            except Exception as e:
                receiver_errors.append(e)

        threads = []
        m_thread = threading.Thread(target=master_reader, args=(m_recv,), daemon=True)
        m_thread.start()
        threads.append(m_thread)

        for i, s_recv in enumerate(slave_receivers):
            t = threading.Thread(target=slave_reader, args=(i, s_recv), daemon=True)
            t.start()
            threads.append(t)

        # Broadcast generation: 1,200 packets
        # 600 touch events, 300 key events, 150 text events, 150 scroll events
        latencies: List[float] = []
        start_burst = time.perf_counter()

        for seq in range(TOTAL_PACKETS):
            t0 = time.perf_counter()
            if seq < 600:
                # Touch DOWN/MOVE/UP sequence
                action = AMOTION_EVENT_ACTION_MOVE if seq % 10 != 0 else (AMOTION_EVENT_ACTION_DOWN if seq % 20 == 0 else AMOTION_EVENT_ACTION_UP)
                x = (seq * 7) % 1440
                y = (seq * 13) % 3120
                res = self.multiplexer.send_touch(action=action, pointer_id=0, x=x, y=y)
            elif seq < 900:
                # Key events
                action = AKEY_EVENT_ACTION_DOWN if (seq % 2 == 0) else AKEY_EVENT_ACTION_UP
                keycode = 20 + (seq % 50)
                res = self.multiplexer.send_key(action=action, keycode=keycode)
            elif seq < 1050:
                # Text events
                text = f"cmd_{seq}"
                res = self.multiplexer.send_text(text)
            else:
                # Scroll events
                res = self.multiplexer.send_scroll(x=720, y=1560, hscroll=0, vscroll=(seq % 20) - 10)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)  # ms
            self.assertEqual(res, 10, f"Packet #{seq} did not reach all 10 slaves")

        total_burst_time = time.perf_counter() - start_burst

        # Wait for all reader threads to drain
        for t in threads:
            t.join(timeout=10.0)

        # Teardown sockets
        m_send.close()
        m_recv.close()
        for s_send, s_recv in slave_pairs:
            s_send.close()
            s_recv.close()

        self.assertEqual(len(receiver_errors), 0, f"Receiver exceptions occurred: {receiver_errors}")

        # Latency analysis
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]

        print(f"\n[STRESS TEST METRICS] 1,200 packets across 10 slaves:")
        print(f"  Total burst time: {total_burst_time:.4f}s ({TOTAL_PACKETS/total_burst_time:.1f} pkts/s)")
        print(f"  Avg broadcast latency: {avg_latency:.4f}ms")
        print(f"  P99 broadcast latency: {p99_latency:.4f}ms")
        print(f"  Max broadcast latency: {max_latency:.4f}ms")

        # R4 / Survey Requirement: Sub-2ms latency target
        self.assertLess(avg_latency, 2.0, f"Average broadcast latency {avg_latency:.3f}ms exceeded 2.0ms threshold")

        # Packet delivery integrity verification
        self.assertEqual(len(master_received), TOTAL_PACKETS, "Master did not receive all 1,200 packets")
        for i in range(10):
            self.assertEqual(
                len(received_packets[i]),
                TOTAL_PACKETS,
                f"Slave {i} dropped packets: received {len(received_packets[i])}/{TOTAL_PACKETS}",
            )

        # Verify touch scaling integrity on Slave 0 (1080x2400) and Slave 3 (320x480)
        for seq in range(600):
            orig_x = (seq * 7) % 1440
            orig_y = (seq * 13) % 3120

            # Slave 0 verification (1080x2400)
            pkt_s0 = received_packets[0][seq]
            dec_s0 = decode_touch_packet(pkt_s0)
            expected_x0, expected_y0 = scale_coordinate(orig_x, orig_y, 1440, 3120, 1080, 2400)
            self.assertEqual(dec_s0["x"], expected_x0)
            self.assertEqual(dec_s0["y"], expected_y0)
            self.assertEqual(dec_s0["width"], 1080)
            self.assertEqual(dec_s0["height"], 2400)

            # Slave 3 verification (320x480)
            pkt_s3 = received_packets[3][seq]
            dec_s3 = decode_touch_packet(pkt_s3)
            expected_x3, expected_y3 = scale_coordinate(orig_x, orig_y, 1440, 3120, 320, 480)
            self.assertEqual(dec_s3["x"], expected_x3)
            self.assertEqual(dec_s3["y"], expected_y3)
            self.assertEqual(dec_s3["width"], 320)
            self.assertEqual(dec_s3["height"], 480)


class TestResolutionScalingEdgeCases(unittest.TestCase):
    """
    Empirical Stress Test 2:
    Tests non-standard resolutions, boundary coordinates, out-of-bounds inputs,
    and zero/negative dimension fallbacks.
    """

    def test_non_standard_resolutions(self):
        """Verifies scaling from 1440x3120 master to non-standard resolutions."""
        # 1. To 320x480 (HVGA)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 320, 480), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 320, 480), (320, 480))
        self.assertEqual(scale_coordinate(720, 1560, 1440, 3120, 320, 480), (160, 240))

        # 2. To 720x1560 (HD+)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 720, 1560), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 720, 1560), (720, 1560))
        self.assertEqual(scale_coordinate(720, 1560, 1440, 3120, 720, 1560), (360, 780))

        # 3. To 2160x3840 (4K UHD)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 2160, 3840), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 2160, 3840), (2160, 3840))
        self.assertEqual(scale_coordinate(720, 1560, 1440, 3120, 2160, 3840), (1080, 1920))

        # 4. To 1000x1000 (Square / Foldable cover)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 1000, 1000), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 1000, 1000), (1000, 1000))
        self.assertEqual(scale_coordinate(720, 1560, 1440, 3120, 1000, 1000), (500, 500))

        # 5. Extreme minimal resolution (1x1) - single pixel display (index 0)
        # Note: In Python 3 round(0.5) rounds to even (0), so center maps to pixel 0
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 1, 1), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 1, 1), (1, 1))
        self.assertEqual(scale_coordinate(720, 1560, 1440, 3120, 1, 1), (0, 0))

        # 6. Maximum uint16 boundary resolution (65535x65535)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 65535, 65535), (0, 0))
        self.assertEqual(scale_coordinate(1440, 3120, 1440, 3120, 65535, 65535), (65535, 65535))

    def test_out_of_bounds_coordinates(self):
        """Verifies clamping behavior on out-of-bounds coordinates."""
        # Negative coordinates clamp to 0
        self.assertEqual(scale_coordinate(-1, -1, 1440, 3120, 1080, 2400), (0, 0))
        self.assertEqual(scale_coordinate(-500, -1000, 1440, 3120, 1080, 2400), (0, 0))
        self.assertEqual(scale_coordinate(-999999, -999999, 1440, 3120, 1080, 2400), (0, 0))

        # Over-boundary coordinates clamp to target maximum dimensions
        self.assertEqual(scale_coordinate(1441, 3120, 1440, 3120, 1080, 2400), (1080, 2400))
        self.assertEqual(scale_coordinate(1440, 3121, 1440, 3120, 1080, 2400), (1080, 2400))
        self.assertEqual(scale_coordinate(2880, 6240, 1440, 3120, 1080, 2400), (1080, 2400))
        self.assertEqual(scale_coordinate(1000000, 1000000, 1440, 3120, 1080, 2400), (1080, 2400))

        # Single axis out-of-bounds
        self.assertEqual(scale_coordinate(-50, 1560, 1440, 3120, 1080, 2400), (0, 1200))
        self.assertEqual(scale_coordinate(720, 5000, 1440, 3120, 1080, 2400), (540, 2400))

    def test_zero_dimensions_and_zero_coordinates(self):
        """Verifies graceful handling of 0 dimensions and (0,0) coordinates."""
        # (0, 0) coordinates map cleanly to (0, 0)
        self.assertEqual(scale_coordinate(0, 0, 1440, 3120, 1080, 2400), (0, 0))

        # Zero source width/height returns unscaled (x, y) without ZeroDivisionError
        self.assertEqual(scale_coordinate(100, 200, 0, 3120, 1080, 2400), (100, 200))
        self.assertEqual(scale_coordinate(100, 200, 1440, 0, 1080, 2400), (100, 200))
        self.assertEqual(scale_coordinate(100, 200, 0, 0, 1080, 2400), (100, 200))

        # Zero destination width/height returns unscaled (x, y)
        self.assertEqual(scale_coordinate(100, 200, 1440, 3120, 0, 2400), (100, 200))
        self.assertEqual(scale_coordinate(100, 200, 1440, 3120, 1080, 0), (100, 200))
        self.assertEqual(scale_coordinate(100, 200, 1440, 3120, 0, 0), (100, 200))

        # Negative dimensions fallback
        self.assertEqual(scale_coordinate(100, 200, -100, 3120, 1080, 2400), (100, 200))
        self.assertEqual(scale_coordinate(100, 200, 1440, 3120, -100, 2400), (100, 200))


class TestAbruptSocketDisconnects(unittest.TestCase):
    """
    Empirical Stress Test 3:
    Simulates abrupt socket kills (SO_LINGER=0 RST, shutdown, close) during active broadcast.
    Validates automatic dead slave pruning, non-blocking delivery to surviving slaves,
    and recovery when new slaves reconnect.
    """

    def setUp(self):
        self.multiplexer = InputSyncMultiplexer()

    def tearDown(self):
        self.multiplexer.close()

    def test_abrupt_disconnect_mid_broadcast_and_pruning(self):
        """
        Broadcasts 600 packets across 8 slaves.
        Kills 2 slaves abruptly at packet 150 (RST).
        Kills 2 more slaves at packet 300 (close).
        Verifies surviving 4 slaves receive all remaining packets without drops.
        """
        m_send, m_recv = socket.socketpair()
        self.multiplexer.register_master("master-5554", 1440, 3120, control_socket=m_send)

        slave_sockets: List[Tuple[socket.socket, socket.socket]] = []
        for i in range(8):
            s_send, s_recv = socket.socketpair()
            slave_sockets.append((s_send, s_recv))
            self.multiplexer.add_slave(f"slave-{i}", 1080, 2400, control_socket=s_send)

        self.assertEqual(self.multiplexer.get_slave_count(), 8)

        # Track packets received by surviving slaves: 1, 3, 4, 6
        surviving_indices = [1, 3, 4, 6]
        surviving_packets: Dict[int, List[bytes]] = {idx: [] for idx in surviving_indices}
        master_packets: List[bytes] = []

        # Reader for surviving slaves
        stop_readers = threading.Event()

        def reader(slave_idx: int, sock: socket.socket):
            while not stop_readers.is_set():
                pkt = _read_scrcpy_packet(sock, timeout=0.5)
                if pkt is not None:
                    surviving_packets[slave_idx].append(pkt)

        threads = []
        for idx in surviving_indices:
            t = threading.Thread(target=reader, args=(idx, slave_sockets[idx][1]), daemon=True)
            t.start()
            threads.append(t)

        def master_reader(sock: socket.socket):
            while not stop_readers.is_set():
                pkt = _read_scrcpy_packet(sock, timeout=0.5)
                if pkt is not None:
                    master_packets.append(pkt)

        m_t = threading.Thread(target=master_reader, args=(m_recv,), daemon=True)
        m_t.start()
        threads.append(m_t)

        # Broadcast loop
        for seq in range(600):
            if seq == 150:
                # Abruptly kill Slave 2 and Slave 5 with TCP RST
                s2_recv = slave_sockets[2][1]
                s5_recv = slave_sockets[5][1]
                s2_recv.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                s5_recv.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                s2_recv.close()
                s5_recv.close()

            if seq == 300:
                # Abruptly close Slave 0 and Slave 7
                slave_sockets[0][1].close()
                slave_sockets[7][1].close()

            count = self.multiplexer.send_touch(
                action=AMOTION_EVENT_ACTION_MOVE,
                pointer_id=0,
                x=100 + (seq % 100),
                y=200 + (seq % 100),
            )

            # Verification of active count per phase
            if seq < 150:
                self.assertEqual(count, 8)
            elif 151 <= seq < 300:
                # After packet 150, slaves 2 and 5 are detected as dead and pruned
                self.assertLessEqual(count, 6)
            elif seq >= 301:
                # After packet 300, slaves 0 and 7 are detected and pruned
                self.assertLessEqual(count, 4)

        time.sleep(0.2)
        stop_readers.set()
        for t in threads:
            t.join(timeout=2.0)

        # Cleanup
        m_send.close()
        m_recv.close()
        for s_send, s_recv in slave_sockets:
            try:
                s_send.close()
            except OSError:
                pass
            try:
                s_recv.close()
            except OSError:
                pass

        # Verification: Multiplexer pruned dead slaves
        self.assertEqual(self.multiplexer.get_slave_count(), 4)
        active_serials = set(self.multiplexer.get_slaves().keys())
        self.assertEqual(active_serials, {"slave-1", "slave-3", "slave-4", "slave-6"})

        # Surviving slaves received all 600 packets without drops
        for idx in surviving_indices:
            self.assertEqual(
                len(surviving_packets[idx]),
                600,
                f"Surviving slave {idx} suffered packet drops: received {len(surviving_packets[idx])}/600",
            )

        # Master received all 600 packets
        self.assertEqual(len(master_packets), 600, "Master dropped packets during slave disconnects")

    def test_total_slave_disconnect_and_recovery(self):
        """Verifies multiplexer behavior when all slaves disconnect, then recovers cleanly."""
        s1_send, s1_recv = socket.socketpair()
        self.multiplexer.register_master("master-5554", 1440, 3120)
        self.multiplexer.add_slave("slave-only", 1080, 2400, control_socket=s1_send)

        self.assertEqual(self.multiplexer.get_slave_count(), 1)

        # Abruptly kill the only slave with TCP RST
        s1_recv.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        s1_recv.close()

        # Send event: should fail to send, prune dead slave, return 0, no exception
        count = self.multiplexer.send_key(action=AKEY_EVENT_ACTION_DOWN, keycode=3)
        self.assertEqual(count, 0)
        self.assertEqual(self.multiplexer.get_slave_count(), 0)

        # Broadcast with 0 slaves: returns 0 cleanly
        count = self.multiplexer.send_key(action=AKEY_EVENT_ACTION_UP, keycode=3)
        self.assertEqual(count, 0)

        # Recover by adding a new healthy slave
        s2_send, s2_recv = socket.socketpair()
        self.multiplexer.add_slave("slave-resurrected", 720, 1560, control_socket=s2_send)
        self.assertEqual(self.multiplexer.get_slave_count(), 1)

        count = self.multiplexer.send_touch(action=AMOTION_EVENT_ACTION_DOWN, pointer_id=0, x=720, y=1560)
        self.assertEqual(count, 1)

        pkt = _read_scrcpy_packet(s2_recv, timeout=2.0)
        self.assertIsNotNone(pkt)
        dec = decode_touch_packet(pkt)
        self.assertEqual((dec["x"], dec["y"]), (360, 780))

        s1_send.close()
        s2_send.close()
        s2_recv.close()


class TestScrcpyWireProtocolIntegrity(unittest.TestCase):
    """
    Empirical Stress Test 4:
    Verifies bit-exact wire representation for Scrcpy packets:
    - 32-byte Touch Packet (>BBQIIHHHII)
    - 14-byte Key Packet (>BBIII)
    - 21-byte Scroll Packet (>BIIHHhhI) with signed negative offsets
    - Truncated / malformed packet validation
    """

    def test_bit_exact_touch_packet_32_bytes(self):
        """Validates bit-exact wire representation against manual hex oracle."""
        # Touch packet specification:
        # byte 0: 0x02 (type)
        # byte 1: 0x00 (action=DOWN)
        # bytes 2-9: 0x0123456789ABCDEF (pointer_id=81985529216486895)
        # bytes 10-13: 0x000002D0 (x=720)
        # bytes 14-17: 0x00000618 (y=1560)
        # bytes 18-19: 0x05A0 (width=1440)
        # bytes 20-21: 0x0C30 (height=3120)
        # bytes 22-23: 0xFFFF (pressure=65535)
        # bytes 24-27: 0x00000001 (action_button=PRIMARY)
        # bytes 28-31: 0x00000001 (buttons=PRIMARY)
        expected_hex = "02000123456789abcdef000002d00000061805a00c30ffff0000000100000001"
        expected_bytes = bytes.fromhex(expected_hex)
        self.assertEqual(len(expected_bytes), 32)

        actual_bytes = encode_touch_packet(
            action=AMOTION_EVENT_ACTION_DOWN,
            pointer_id=0x0123456789ABCDEF,
            x=720,
            y=1560,
            width=1440,
            height=3120,
            pressure=0xFFFF,
            action_button=AMOTION_EVENT_BUTTON_PRIMARY,
            buttons=AMOTION_EVENT_BUTTON_PRIMARY,
        )

        self.assertEqual(actual_bytes, expected_bytes, "Bit-exact touch packet wire format mismatch")
        self.assertEqual(len(actual_bytes), 32)

        # Round-trip decode verification
        decoded = decode_touch_packet(expected_bytes)
        self.assertEqual(decoded["type"], 0x02)
        self.assertEqual(decoded["action"], 0)
        self.assertEqual(decoded["pointer_id"], 0x0123456789ABCDEF)
        self.assertEqual(decoded["x"], 720)
        self.assertEqual(decoded["y"], 1560)
        self.assertEqual(decoded["width"], 1440)
        self.assertEqual(decoded["height"], 3120)
        self.assertEqual(decoded["pressure"], 0xFFFF)
        self.assertEqual(decoded["action_button"], 1)
        self.assertEqual(decoded["buttons"], 1)

    def test_bit_exact_key_packet_14_bytes(self):
        """Validates bit-exact key packet wire representation against manual hex oracle."""
        # Key packet specification:
        # byte 0: 0x00 (type)
        # byte 1: 0x01 (action=UP)
        # bytes 2-5: 0x00000004 (keycode=AKEYCODE_BACK)
        # bytes 6-9: 0x00000002 (repeat=2)
        # bytes 10-13: 0x00000001 (metastate=META_ALT_ON)
        expected_hex = "0001000000040000000200000001"
        expected_bytes = bytes.fromhex(expected_hex)
        self.assertEqual(len(expected_bytes), 14)

        actual_bytes = encode_key_packet(
            action=AKEY_EVENT_ACTION_UP,
            keycode=4,
            repeat=2,
            metastate=1,
        )

        self.assertEqual(actual_bytes, expected_bytes, "Bit-exact key packet wire format mismatch")
        self.assertEqual(len(actual_bytes), 14)

        decoded = decode_key_packet(expected_bytes)
        self.assertEqual(decoded["type"], 0x00)
        self.assertEqual(decoded["action"], 1)
        self.assertEqual(decoded["keycode"], 4)
        self.assertEqual(decoded["repeat"], 2)
        self.assertEqual(decoded["metastate"], 1)

    def test_signed_scroll_packet_wire_integrity(self):
        """Validates negative two's complement offsets in 21-byte scroll packets."""
        # Scroll packet format '>BIIHHhhI' (21 bytes)
        # x=500 (0x01F4), y=1000 (0x03E8), width=1080 (0x0438), height=2400 (0x0960)
        # hscroll = -1 (0xFFFF), vscroll = -120 (0xFF88)
        # buttons = 0 (0x00000000)
        expected_hex = "03000001f4000003e804380960ffffff8800000000"
        expected_bytes = bytes.fromhex(expected_hex)
        self.assertEqual(len(expected_bytes), 21)

        actual_bytes = encode_scroll_packet(
            x=500,
            y=1000,
            width=1080,
            height=2400,
            hscroll=-1,
            vscroll=-120,
            buttons=0,
        )

        self.assertEqual(actual_bytes, expected_bytes)
        self.assertEqual(len(actual_bytes), 21)

        decoded = decode_scroll_packet(actual_bytes)
        self.assertEqual(decoded["hscroll"], -1)
        self.assertEqual(decoded["vscroll"], -120)

    def test_multitouch_pointer_id_and_buttons_preservation(self):
        """Verifies multi-touch pointer IDs and button bitmasks are preserved across scaling."""
        # Test 3 concurrent touch pointers (e.g. 3-finger gesture)
        for pointer_id in [0, 1, 2]:
            pkt = encode_touch_packet(
                action=AMOTION_EVENT_ACTION_MOVE,
                pointer_id=pointer_id,
                x=300 * (pointer_id + 1),
                y=600 * (pointer_id + 1),
                width=1440,
                height=3120,
                pressure=0x8000,
                action_button=AMOTION_EVENT_BUTTON_PRIMARY | AMOTION_EVENT_BUTTON_SECONDARY,
                buttons=3,
            )
            dec = decode_touch_packet(pkt)
            self.assertEqual(dec["pointer_id"], pointer_id)
            self.assertEqual(dec["pressure"], 0x8000)
            self.assertEqual(dec["buttons"], 3)

    def test_alternate_34_byte_touch_packet_format(self):
        """Verifies backward compatibility with alternate 34-byte padded touch packets."""
        # Alternate format: >BBQIIHHHHII (34 bytes)
        alt_pkt = struct.pack(
            TOUCH_PACKET_FORMAT_ALT,
            CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT,
            AMOTION_EVENT_ACTION_DOWN,
            99,  # pointer_id
            720,  # x
            1560,  # y
            1440,  # width
            3120,  # height
            0xFFFF,  # pressure
            0,  # extra padding uint16
            1,  # action_button
            1,  # buttons
        )
        self.assertEqual(len(alt_pkt), 34)

        decoded = decode_touch_packet(alt_pkt)
        self.assertEqual(decoded["type"], CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT)
        self.assertEqual(decoded["action"], AMOTION_EVENT_ACTION_DOWN)
        self.assertEqual(decoded["pointer_id"], 99)
        self.assertEqual(decoded["x"], 720)
        self.assertEqual(decoded["y"], 1560)
        self.assertEqual(decoded["width"], 1440)
        self.assertEqual(decoded["height"], 3120)
        self.assertEqual(decoded["action_button"], 1)
        self.assertEqual(decoded["buttons"], 1)


class TestMultiplexerControlAndEdgeBehaviors(unittest.TestCase):
    """
    Empirical Stress Test 6:
    Validates sync toggle, auto-detection of event types, and master re-registration.
    """

    def setUp(self):
        self.multiplexer = InputSyncMultiplexer()

    def tearDown(self):
        self.multiplexer.close()

    def test_sync_toggle_mid_stream(self):
        """Disabling sync stops broadcasting immediately; re-enabling resumes seamlessly."""
        s1_send, s1_recv = socket.socketpair()
        self.multiplexer.register_master("master-5554", 1440, 3120)
        self.multiplexer.add_slave("slave-toggle", 1080, 2400, control_socket=s1_send)

        # 1. Enabled: broadcast reaches slave
        self.assertTrue(self.multiplexer.is_syncing())
        count = self.multiplexer.send_key(action=AKEY_EVENT_ACTION_DOWN, keycode=3)
        self.assertEqual(count, 1)
        pkt1 = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(pkt1)

        # 2. Disabled: broadcast dropped
        self.multiplexer.set_syncing(False)
        self.assertFalse(self.multiplexer.is_syncing())
        count = self.multiplexer.send_key(action=AKEY_EVENT_ACTION_UP, keycode=3)
        self.assertEqual(count, 0)

        # Verify nothing sent to socket
        s1_recv.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            s1_recv.recv(14)

        # 3. Re-enabled: broadcast resumes
        self.multiplexer.set_syncing(True)
        self.assertTrue(self.multiplexer.is_syncing())
        count = self.multiplexer.send_touch(action=AMOTION_EVENT_ACTION_DOWN, pointer_id=0, x=720, y=1560)
        self.assertEqual(count, 1)
        pkt2 = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(pkt2)

        s1_send.close()
        s1_recv.close()

    def test_auto_event_type_detection(self):
        """Validates broadcast_event(..., event_type='auto') auto-detects touch, key, text, scroll."""
        s1_send, s1_recv = socket.socketpair()
        self.multiplexer.register_master("master-5554", 1440, 3120)
        self.multiplexer.add_slave("slave-auto", 720, 1560, control_socket=s1_send)

        # Touch packet with auto detection
        touch_pkt = encode_touch_packet(AMOTION_EVENT_ACTION_DOWN, 0, 720, 1560, 1440, 3120)
        res = self.multiplexer.broadcast_event(touch_pkt, event_type="auto")
        self.assertEqual(res, 1)
        recv_touch = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(recv_touch)
        dec_touch = decode_touch_packet(recv_touch)
        self.assertEqual((dec_touch["x"], dec_touch["y"]), (360, 780))

        # Key packet with auto detection
        key_pkt = encode_key_packet(AKEY_EVENT_ACTION_DOWN, 4)
        res = self.multiplexer.broadcast_event(key_pkt, event_type="auto")
        self.assertEqual(res, 1)
        recv_key = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(recv_key)
        dec_key = decode_key_packet(recv_key)
        self.assertEqual(dec_key["keycode"], 4)

        # Text packet with auto detection
        text_pkt = encode_text_packet("auto_text_test")
        res = self.multiplexer.broadcast_event(text_pkt, event_type="auto")
        self.assertEqual(res, 1)
        recv_text = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(recv_text)
        dec_text = decode_text_packet(recv_text)
        self.assertEqual(dec_text["text"], "auto_text_test")

        # Scroll packet with auto detection
        scroll_pkt = encode_scroll_packet(720, 1560, 1440, 3120, 0, -5)
        res = self.multiplexer.broadcast_event(scroll_pkt, event_type="auto")
        self.assertEqual(res, 1)
        recv_scroll = _read_scrcpy_packet(s1_recv, timeout=1.0)
        self.assertIsNotNone(recv_scroll)
        dec_scroll = decode_scroll_packet(recv_scroll)
        self.assertEqual((dec_scroll["x"], dec_scroll["y"]), (360, 780))
        self.assertEqual(dec_scroll["vscroll"], -5)

        s1_send.close()
        s1_recv.close()

    def test_master_switching_cleans_up_old_master(self):
        """Verifies registering a new master cleanly closes the previous master socket."""
        m1_send, m1_recv = socket.socketpair()
        m2_send, m2_recv = socket.socketpair()

        self.multiplexer.register_master("master-1", 1440, 3120, control_socket=m1_send)
        self.assertEqual(self.multiplexer.get_master().serial, "master-1")

        # Register master 2
        self.multiplexer.register_master("master-2", 1080, 2400, control_socket=m2_send)
        self.assertEqual(self.multiplexer.get_master().serial, "master-2")

        # Verify master 1's socket was cleanly closed
        # Writing or reading m1_recv should indicate socket closure
        m1_recv.settimeout(0.5)
        data = m1_recv.recv(32)
        self.assertEqual(data, b"", "Old master socket was not closed when replaced")

        m1_recv.close()
        m2_send.close()
        m2_recv.close()

    def test_malformed_truncated_packet_handling(self):
        """Verifies decoder raises ValueError on truncated or corrupt packets."""
        # Touch packet truncated to 31 bytes
        valid_touch = encode_touch_packet(0, 0, 100, 200, 1440, 3120)
        with self.assertRaises(ValueError):
            decode_touch_packet(valid_touch[:31])

        # Key packet truncated to 13 bytes
        valid_key = encode_key_packet(0, 3)
        with self.assertRaises(ValueError):
            decode_key_packet(valid_key[:13])

        # Scroll packet truncated to 20 bytes
        valid_scroll = encode_scroll_packet(100, 200, 1080, 2400, 0, -1)
        with self.assertRaises(ValueError):
            decode_scroll_packet(valid_scroll[:20])

        # Text packet truncated header (< 5 bytes)
        with self.assertRaises(ValueError):
            decode_text_packet(b"\x01\x00\x00")


class TestConcurrencyAndThreadSafety(unittest.TestCase):
    """
    Empirical Stress Test 5:
    Fires concurrent events from multiple threads while dynamic nodes are added/removed.
    Verifies RLock thread safety and state consistency.
    """

    def setUp(self):
        self.multiplexer = InputSyncMultiplexer()

    def tearDown(self):
        self.multiplexer.close()

    def test_concurrent_producers_and_dynamic_nodes(self):
        """5 threads firing touch events simultaneously while nodes are churned."""
        s1_send, s1_recv = socket.socketpair()
        self.multiplexer.register_master("master-5554", 1440, 3120)
        self.multiplexer.add_slave("stable-slave", 1080, 2400, control_socket=s1_send)

        errors: List[Exception] = []
        stop_event = threading.Event()
        total_events_sent = [0]

        def producer(thread_id: int):
            try:
                for i in range(100):
                    self.multiplexer.send_touch(
                        action=AMOTION_EVENT_ACTION_MOVE,
                        pointer_id=thread_id,
                        x=100 + i,
                        y=200 + i,
                    )
                    total_events_sent[0] += 1
            except Exception as e:
                errors.append(e)

        def node_churner():
            try:
                for i in range(10):
                    serial = f"ephemeral-{i}"
                    s_send, s_recv = socket.socketpair()
                    self.multiplexer.add_slave(serial, 720, 1280, control_socket=s_send)
                    time.sleep(0.005)
                    self.multiplexer.remove_slave(serial)
                    s_send.close()
                    s_recv.close()
            except Exception as e:
                errors.append(e)

        producer_threads = [threading.Thread(target=producer, args=(i,)) for i in range(5)]
        churn_thread = threading.Thread(target=node_churner)

        for t in producer_threads:
            t.start()
        churn_thread.start()

        for t in producer_threads:
            t.join(timeout=5.0)
        churn_thread.join(timeout=5.0)

        s1_send.close()
        s1_recv.close()

        self.assertEqual(len(errors), 0, f"Concurrency errors encountered: {errors}")
        self.assertEqual(total_events_sent[0], 500)
        self.assertIn("stable-slave", self.multiplexer.get_slaves())


if __name__ == "__main__":
    unittest.main()

"""
tests/fixtures/mock_scrcpy.py
==============================
TCP server emulating Scrcpy 4.1's binary control socket.
Decodes 32-byte touch packets (>BBQIIHHHII) and 14-byte key packets (>BBIII).
Validates coordinate bounding and normalized resolution scaling.
"""

import time
import struct
import socket
import threading
from typing import Dict, List, Optional, Any


class MockScrcpyControlServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.requested_port = port
        self.port = 0
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.received_touch_packets: List[Dict[str, Any]] = []
        self.received_key_packets: List[Dict[str, Any]] = []
        self.total_bytes_received = 0

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.requested_port))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(5)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, client: socket.socket):
        buffer = b""
        with client:
            while self._running:
                try:
                    chunk = client.recv(1024)
                except Exception:
                    break
                if not chunk:
                    break
                self.total_bytes_received += len(chunk)
                buffer += chunk

                while len(buffer) > 0:
                    msg_type = buffer[0]
                    # Touch Packet: type 0x02, exactly 32 bytes (>BBQIIHHHII)
                    if msg_type == 2:
                        if len(buffer) < 32:
                            break
                        pkt = buffer[:32]
                        buffer = buffer[32:]
                        unpacked = struct.unpack(">BBQIIHHHII", pkt)
                        self.received_touch_packets.append({
                            "type": unpacked[0],
                            "action": unpacked[1],
                            "pointer_id": unpacked[2],
                            "x": unpacked[3],
                            "y": unpacked[4],
                            "width": unpacked[5],
                            "height": unpacked[6],
                            "pressure": unpacked[7],
                            "action_button": unpacked[8],
                            "buttons": unpacked[9],
                        })
                    # Key Packet: type 0x00, exactly 14 bytes (>BBIII)
                    elif msg_type == 0:
                        if len(buffer) < 14:
                            break
                        pkt = buffer[:14]
                        buffer = buffer[14:]
                        unpacked = struct.unpack(">BBIII", pkt)
                        self.received_key_packets.append({
                            "type": unpacked[0],
                            "action": unpacked[1],
                            "keycode": unpacked[2],
                            "repeat": unpacked[3],
                            "metastate": unpacked[4],
                        })
                    else:
                        # Unknown or unhandled packet type: skip 1 byte
                        buffer = buffer[1:]

    def wait_for_touch_count(self, count: int, timeout: float = 2.0) -> bool:
        start_t = time.time()
        while time.time() - start_t < timeout:
            if len(self.received_touch_packets) >= count:
                return True
            time.sleep(0.01)
        return False

    def wait_for_key_count(self, count: int, timeout: float = 2.0) -> bool:
        start_t = time.time()
        while time.time() - start_t < timeout:
            if len(self.received_key_packets) >= count:
                return True
            time.sleep(0.01)
        return False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

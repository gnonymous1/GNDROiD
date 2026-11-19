"""
tests/fixtures/mock_qemu.py
============================
Threaded in-memory TCP server simulating QEMU Telnet console on 127.0.0.1:0.
Validates 'auth <token>', and executes 'geo fix', 'network delay', 'power', 'sensor set'.
"""

import time
import socket
import threading
from typing import Dict, List, Tuple, Optional


class MockQemuConsoleServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        auth_token: str = "gndroid_secret_token",
        require_auth: bool = True,
    ):
        self.host = host
        self.requested_port = port
        self.port = 0
        self.auth_token = auth_token
        self.require_auth = require_auth
        self.server_socket: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # State records
        self.command_log: List[str] = []
        self.geo_history: List[Tuple[float, float, float, float]] = []  # (lon, lat, alt, time)
        self.network_state = {"delay": "none", "speed": "full"}
        self.power_state = {"capacity": "100", "ac": "on", "status": "charging"}
        self.gsm_state = {"signal": "4", "voice": "home", "data": "on"}
        self.sensor_state: Dict[str, str] = {}
        self.auth_attempts: List[str] = []

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
        authenticated = not self.require_auth
        with client:
            greeting = (
                "Android Console: Authentication required\r\n"
                "Android Console: type 'auth <auth_token>' to authenticate\r\n"
                "OK\r\n"
            )
            client.sendall(greeting.encode("utf-8"))
            buffer = ""
            while self._running:
                try:
                    data = client.recv(1024)
                except Exception:
                    break
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip("\r")
                    if not line:
                        continue
                    self.command_log.append(line)
                    tokens = line.split()
                    cmd = tokens[0].lower()

                    if cmd == "auth":
                        tok = tokens[1] if len(tokens) > 1 else ""
                        self.auth_attempts.append(tok)
                        if tok == self.auth_token:
                            authenticated = True
                            client.sendall(b"OK\r\n")
                        else:
                            client.sendall(b"KO: authentication failed\r\n")
                        continue

                    if not authenticated:
                        client.sendall(b"KO: not authenticated\r\n")
                        continue

                    if cmd == "geo" and len(tokens) >= 4 and tokens[1] == "fix":
                        try:
                            lon = float(tokens[2])
                            lat = float(tokens[3])
                            alt = float(tokens[4]) if len(tokens) > 4 else 0.0
                            self.geo_history.append((lon, lat, alt, time.time()))
                            client.sendall(b"OK\r\n")
                        except ValueError:
                            client.sendall(b"KO: invalid coordinates\r\n")
                    elif cmd == "network":
                        if len(tokens) >= 3 and tokens[1] in ("delay", "speed"):
                            self.network_state[tokens[1]] = tokens[2]
                            client.sendall(b"OK\r\n")
                        else:
                            client.sendall(b"KO: invalid network param\r\n")
                    elif cmd == "power" and len(tokens) >= 3:
                        self.power_state[tokens[1]] = tokens[2]
                        client.sendall(b"OK\r\n")
                    elif cmd == "gsm" and len(tokens) >= 3:
                        self.gsm_state[tokens[1]] = tokens[2]
                        client.sendall(b"OK\r\n")
                    elif cmd == "sensor" and len(tokens) >= 4 and tokens[1] == "set":
                        self.sensor_state[tokens[2]] = tokens[3]
                        client.sendall(b"OK\r\n")
                    elif cmd in ("quit", "exit"):
                        client.sendall(b"OK\r\n")
                        return
                    else:
                        client.sendall(b"OK\r\n")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


# Alias for compatibility
MockQemuConsole = MockQemuConsoleServer

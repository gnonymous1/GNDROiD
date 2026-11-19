#!/usr/bin/env python3
"""
nexus/sync_multiplexer.py - GNDROiD Next-Gen Input Synchronizer & Socket Multiplexer
===================================================================================

Implements millisecond-responsive multi-instance input synchronization using the
Scrcpy binary control socket protocol (v4.1 compatible).

Wire Protocol Specification:
- Touch Packet: 32 bytes (or 34 bytes alternate)
  Format: '>BBQIIHHHII' (32 bytes)
  Fields:
    0x00 uint8     type = 0x02 (CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT)
    0x01 uint8     action (0=DOWN, 1=UP, 2=MOVE, 3=CANCEL)
    0x02 uint64_be pointer_id (0 or 0xFFFFFFFFFFFFFFFF)
    0x0A uint32_be position_x
    0x0E uint32_be position_y
    0x12 uint16_be screen_width
    0x14 uint16_be screen_height
    0x16 uint16_be pressure (0xFFFF = 1.0f)
    0x18 uint32_be action_button (1 = AMOTION_EVENT_BUTTON_PRIMARY)
    0x1C uint32_be buttons (1 = AMOTION_EVENT_BUTTON_PRIMARY)

- Key Packet: 14 bytes
  Format: '>BBIII' (14 bytes)
  Fields:
    0x00 uint8     type = 0x00 (CONTROL_MSG_TYPE_INJECT_KEYCODE)
    0x01 uint8     action (0=DOWN, 1=UP)
    0x02 uint32_be keycode (Android AKEYCODE_*)
    0x06 uint32_be repeat (0)
    0x0A uint32_be metastate (0 or modifier flags)

- Text Packet: 5 + len(utf8_bytes)
  Format: '>BI' + text_bytes
  Fields:
    0x00 uint8     type = 0x01 (CONTROL_MSG_TYPE_INJECT_TEXT)
    0x01 uint32_be text_length
    0x05 bytes     text (utf-8)

- Scroll Packet: 21 bytes
  Format: '>BIIHHiiI'
  Fields:
    0x00 uint8     type = 0x03 (CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT)
    0x01 uint32_be position_x
    0x05 uint32_be position_y
    0x09 uint16_be screen_width
    0x0B uint16_be screen_height
    0x0D int32_be  hscroll
    0x11 int32_be  vscroll
    0x15 uint32_be buttons

Features:
- Master and slave instance registration with dynamic resolution management
- Strict coordinate normalization:
    x_norm = x_master / W_master,  y_norm = y_master / H_master
    x_slave = round(x_norm * W_slave), y_slave = round(y_norm * H_slave)
- Low-latency socket broadcast (<2ms) with TCP_NODELAY enabled
- Dead slave pruning and fault-tolerant socket transmission
- Thread-safe multiplexing operations
"""

import logging
import socket
import struct
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nexus.sync_multiplexer")

# ---------------------------------------------------------------------------
# Scrcpy Control Message Types
# ---------------------------------------------------------------------------
CONTROL_MSG_TYPE_INJECT_KEYCODE = 0
CONTROL_MSG_TYPE_INJECT_TEXT = 1
CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT = 2
CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT = 3
CONTROL_MSG_TYPE_BACK_OR_SCREEN_ON = 4
CONTROL_MSG_TYPE_EXPAND_NOTIFICATION_PANEL = 5
CONTROL_MSG_TYPE_EXPAND_SETTINGS_PANEL = 6
CONTROL_MSG_TYPE_COLLAPSE_PANELS = 7
CONTROL_MSG_TYPE_GET_CLIPBOARD = 8
CONTROL_MSG_TYPE_SET_CLIPBOARD = 9
CONTROL_MSG_TYPE_SET_SCREEN_POWER_MODE = 10
CONTROL_MSG_TYPE_ROTATE_DEVICE = 11

# ---------------------------------------------------------------------------
# Android Motion & Key Event Actions
# ---------------------------------------------------------------------------
AMOTION_EVENT_ACTION_DOWN = 0
AMOTION_EVENT_ACTION_UP = 1
AMOTION_EVENT_ACTION_MOVE = 2
AMOTION_EVENT_ACTION_CANCEL = 3

AKEY_EVENT_ACTION_DOWN = 0
AKEY_EVENT_ACTION_UP = 1

AMOTION_EVENT_BUTTON_PRIMARY = 1
AMOTION_EVENT_BUTTON_SECONDARY = 2
AMOTION_EVENT_BUTTON_TERTIARY = 4

# Wire struct formats
TOUCH_PACKET_FORMAT = ">BBQIIHHHII"  # 32 bytes (Standard Scrcpy 4.1 touch packet)
TOUCH_PACKET_FORMAT_ALT = ">BBQIIHHHHII"  # 34 bytes (Alternate padded variant)
KEY_PACKET_FORMAT = ">BBIII"  # 14 bytes
SCROLL_PACKET_FORMAT = ">BIIHHhhI"  # 21 bytes (Standard Scrcpy scroll packet with int16 hscroll/vscroll)
SCROLL_PACKET_FORMAT_ALT = ">BIIHHiiI"  # 25 bytes (Alternate variant with int32 hscroll/vscroll)

TOUCH_PACKET_SIZE = struct.calcsize(TOUCH_PACKET_FORMAT)  # 32
KEY_PACKET_SIZE = struct.calcsize(KEY_PACKET_FORMAT)  # 14
SCROLL_PACKET_SIZE = struct.calcsize(SCROLL_PACKET_FORMAT)  # 21


# ---------------------------------------------------------------------------
# Coordinate Scaling
# ---------------------------------------------------------------------------
def scale_coordinate(
    x: int,
    y: int,
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int
) -> Tuple[int, int]:
    """
    Normalizes coordinates from a source viewport and scales them to a target
    viewport using standard rounding.

    Formula:
        x_norm = x / src_w, y_norm = y / src_h
        x_dst = round(x_norm * dst_w), y_dst = round(y_norm * dst_h)
    """
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return (x, y)

    x_norm = max(0.0, min(1.0, float(x) / float(src_w)))
    y_norm = max(0.0, min(1.0, float(y) / float(src_h)))

    x_dst = int(round(x_norm * float(dst_w)))
    y_dst = int(round(y_norm * float(dst_h)))

    return (x_dst, y_dst)


# ---------------------------------------------------------------------------
# Packet Encoders and Decoders
# ---------------------------------------------------------------------------
def encode_touch_packet(
    action: int,
    pointer_id: int,
    x: int,
    y: int,
    width: int,
    height: int,
    pressure: int = 0xFFFF,
    action_button: int = AMOTION_EVENT_BUTTON_PRIMARY,
    buttons: int = AMOTION_EVENT_BUTTON_PRIMARY,
) -> bytes:
    """Encodes a 32-byte Scrcpy touch event packet."""
    return struct.pack(
        TOUCH_PACKET_FORMAT,
        CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT,
        action & 0xFF,
        pointer_id & 0xFFFFFFFFFFFFFFFF,
        x & 0xFFFFFFFF,
        y & 0xFFFFFFFF,
        width & 0xFFFF,
        height & 0xFFFF,
        pressure & 0xFFFF,
        action_button & 0xFFFFFFFF,
        buttons & 0xFFFFFFFF,
    )


def decode_touch_packet(data: bytes) -> Dict[str, Any]:
    """Decodes a binary Scrcpy touch event packet (supports 32-byte and 34-byte formats)."""
    if len(data) < TOUCH_PACKET_SIZE:
        raise ValueError(
            f"Touch packet too short: expected at least {TOUCH_PACKET_SIZE} bytes, got {len(data)}"
        )

    if len(data) >= 34:
        # Check if 34-byte format
        try:
            fields = struct.unpack_from(TOUCH_PACKET_FORMAT_ALT, data, 0)
            return {
                "type": fields[0],
                "action": fields[1],
                "pointer_id": fields[2],
                "x": fields[3],
                "y": fields[4],
                "width": fields[5],
                "height": fields[6],
                "pressure": fields[7],
                "action_button": fields[9],
                "buttons": fields[10],
            }
        except struct.error:
            pass

    fields = struct.unpack_from(TOUCH_PACKET_FORMAT, data, 0)
    return {
        "type": fields[0],
        "action": fields[1],
        "pointer_id": fields[2],
        "x": fields[3],
        "y": fields[4],
        "width": fields[5],
        "height": fields[6],
        "pressure": fields[7],
        "action_button": fields[8],
        "buttons": fields[9],
    }


def encode_key_packet(
    action: int,
    keycode: int,
    repeat: int = 0,
    metastate: int = 0
) -> bytes:
    """Encodes a 14-byte Scrcpy key event packet."""
    return struct.pack(
        KEY_PACKET_FORMAT,
        CONTROL_MSG_TYPE_INJECT_KEYCODE,
        action & 0xFF,
        keycode & 0xFFFFFFFF,
        repeat & 0xFFFFFFFF,
        metastate & 0xFFFFFFFF,
    )


def decode_key_packet(data: bytes) -> Dict[str, Any]:
    """Decodes a 14-byte Scrcpy key event packet."""
    if len(data) < KEY_PACKET_SIZE:
        raise ValueError(
            f"Key packet too short: expected at least {KEY_PACKET_SIZE} bytes, got {len(data)}"
        )
    fields = struct.unpack_from(KEY_PACKET_FORMAT, data, 0)
    return {
        "type": fields[0],
        "action": fields[1],
        "keycode": fields[2],
        "repeat": fields[3],
        "metastate": fields[4],
    }


def encode_text_packet(text: str) -> bytes:
    """Encodes a variable-length Scrcpy text injection packet."""
    text_bytes = text.encode("utf-8")
    header = struct.pack(">BI", CONTROL_MSG_TYPE_INJECT_TEXT, len(text_bytes))
    return header + text_bytes


def decode_text_packet(data: bytes) -> Dict[str, Any]:
    """Decodes a Scrcpy text injection packet."""
    if len(data) < 5:
        raise ValueError(f"Text packet too short: got {len(data)} bytes")
    msg_type, length = struct.unpack_from(">BI", data, 0)
    text = data[5 : 5 + length].decode("utf-8", errors="replace")
    return {"type": msg_type, "length": length, "text": text}


def encode_scroll_packet(
    x: int,
    y: int,
    width: int,
    height: int,
    hscroll: int,
    vscroll: int,
    buttons: int = 0
) -> bytes:
    """Encodes a 21-byte Scrcpy scroll event packet."""
    return struct.pack(
        SCROLL_PACKET_FORMAT,
        CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT,
        x & 0xFFFFFFFF,
        y & 0xFFFFFFFF,
        width & 0xFFFF,
        height & 0xFFFF,
        int(hscroll),
        int(vscroll),
        buttons & 0xFFFFFFFF,
    )


def decode_scroll_packet(data: bytes) -> Dict[str, Any]:
    """Decodes a Scrcpy scroll event packet (supports 21-byte and 25-byte variants)."""
    if len(data) < SCROLL_PACKET_SIZE:
        raise ValueError(
            f"Scroll packet too short: expected at least {SCROLL_PACKET_SIZE} bytes, got {len(data)}"
        )
    if len(data) >= 25:
        try:
            fields = struct.unpack_from(SCROLL_PACKET_FORMAT_ALT, data, 0)
            return {
                "type": fields[0],
                "x": fields[1],
                "y": fields[2],
                "width": fields[3],
                "height": fields[4],
                "hscroll": fields[5],
                "vscroll": fields[6],
                "buttons": fields[7],
            }
        except struct.error:
            pass

    fields = struct.unpack_from(SCROLL_PACKET_FORMAT, data, 0)
    return {
        "type": fields[0],
        "x": fields[1],
        "y": fields[2],
        "width": fields[3],
        "height": fields[4],
        "hscroll": fields[5],
        "vscroll": fields[6],
        "buttons": fields[7],
    }


# ---------------------------------------------------------------------------
# Node Representation (Master and Slave)
# ---------------------------------------------------------------------------
class InstanceNode:
    """Represents a master or slave viewport node connected to the multiplexer."""

    def __init__(
        self,
        serial: str,
        width: int,
        height: int,
        control_socket: Optional[socket.socket] = None
    ) -> None:
        self.serial = serial
        self.width = max(1, width)
        self.height = max(1, height)
        self.socket = control_socket
        self.active = True

        if self.socket is not None:
            self._configure_socket(self.socket)

    def _configure_socket(self, sock: socket.socket) -> None:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (AttributeError, OSError) as exc:
            logger.debug(f"Could not set TCP_NODELAY on socket for {self.serial}: {exc}")

    def send_raw(self, packet: bytes) -> bool:
        """Sends raw bytes over the control socket with error handling."""
        if not self.active or self.socket is None:
            return False
        try:
            self.socket.sendall(packet)
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            logger.warning(f"Connection lost to node {self.serial}: {exc}")
            self.active = False
            return False

    def close(self) -> None:
        """Closes the socket cleanly."""
        self.active = False
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None


# ---------------------------------------------------------------------------
# InputSyncMultiplexer
# ---------------------------------------------------------------------------
class InputSyncMultiplexer:
    """
    Multiplexes touch, keyboard, text, and scroll events from a master
    Android instance to one or more slave instances in real time.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._master: Optional[InstanceNode] = None
        self._slaves: Dict[str, InstanceNode] = {}
        self._is_syncing = True

    @staticmethod
    def scale_coordinate(
        x: int,
        y: int,
        src_w: int,
        src_h: int,
        dst_w: int,
        dst_h: int
    ) -> Tuple[int, int]:
        """Class-level wrapper for coordinate normalization and scaling."""
        return scale_coordinate(x, y, src_w, src_h, dst_w, dst_h)

    def register_master(
        self,
        serial: str,
        width: int,
        height: int,
        control_socket: Optional[socket.socket] = None
    ) -> None:
        """Registers or updates the master viewport instance."""
        with self._lock:
            if self._master is not None and self._master.serial != serial:
                self._master.close()
            self._master = InstanceNode(serial, width, height, control_socket)
            logger.info(
                f"Master registered: serial={serial}, resolution={width}x{height}, socket={control_socket is not None}"
            )

    def add_slave(
        self,
        serial: str,
        width: int,
        height: int,
        control_socket: Optional[socket.socket] = None
    ) -> None:
        """Adds a slave viewport instance to receive multiplexed events."""
        with self._lock:
            if serial in self._slaves:
                self._slaves[serial].close()
            self._slaves[serial] = InstanceNode(serial, width, height, control_socket)
            logger.info(
                f"Slave added: serial={serial}, resolution={width}x{height}, socket={control_socket is not None}"
            )

    def remove_slave(self, serial: str) -> None:
        """Removes a slave viewport instance and releases its socket."""
        with self._lock:
            if serial in self._slaves:
                self._slaves[serial].close()
                del self._slaves[serial]
                logger.info(f"Slave removed: serial={serial}")

    def get_master(self) -> Optional[InstanceNode]:
        """Returns the current master node if registered."""
        with self._lock:
            return self._master

    def get_slaves(self) -> Dict[str, InstanceNode]:
        """Returns a shallow copy of registered slaves."""
        with self._lock:
            return dict(self._slaves)

    def get_slave_count(self) -> int:
        """Returns the number of registered slaves."""
        with self._lock:
            return len(self._slaves)

    def set_syncing(self, enabled: bool) -> None:
        """Enables or disables event broadcasting to slaves."""
        with self._lock:
            self._is_syncing = enabled

    def is_syncing(self) -> bool:
        """Returns whether event broadcasting to slaves is active."""
        with self._lock:
            return self._is_syncing

    def broadcast_event(self, packet_bytes: bytes, event_type: str = "touch") -> int:
        """
        Broadcasts an event packet across all active slaves.
        If the event is positional (touch/scroll), coordinates are scaled from
        master dimensions to each slave's native dimensions.

        Returns the number of slaves successfully written to.
        """
        with self._lock:
            if not self._is_syncing or not self._slaves:
                return 0

            successful_sends = 0
            dead_serials: List[str] = []

            # Determine event type from header byte if not explicitly indicated
            if len(packet_bytes) > 0 and event_type == "auto":
                msg_type = packet_bytes[0]
                if msg_type == CONTROL_MSG_TYPE_INJECT_TOUCH_EVENT:
                    event_type = "touch"
                elif msg_type == CONTROL_MSG_TYPE_INJECT_KEYCODE:
                    event_type = "key"
                elif msg_type == CONTROL_MSG_TYPE_INJECT_SCROLL_EVENT:
                    event_type = "scroll"
                elif msg_type == CONTROL_MSG_TYPE_INJECT_TEXT:
                    event_type = "text"

            if event_type == "touch":
                parsed = decode_touch_packet(packet_bytes)
                src_w = self._master.width if self._master else parsed["width"]
                src_h = self._master.height if self._master else parsed["height"]

                for serial, slave in self._slaves.items():
                    if not slave.active:
                        dead_serials.append(serial)
                        continue

                    # Scale coordinates specifically for this slave
                    sx, sy = scale_coordinate(
                        parsed["x"], parsed["y"], src_w, src_h, slave.width, slave.height
                    )

                    slave_pkt = encode_touch_packet(
                        action=parsed["action"],
                        pointer_id=parsed["pointer_id"],
                        x=sx,
                        y=sy,
                        width=slave.width,
                        height=slave.height,
                        pressure=parsed["pressure"],
                        action_button=parsed["action_button"],
                        buttons=parsed["buttons"],
                    )

                    if slave.send_raw(slave_pkt):
                        successful_sends += 1
                    else:
                        dead_serials.append(serial)

            elif event_type == "scroll":
                parsed = decode_scroll_packet(packet_bytes)
                src_w = self._master.width if self._master else parsed["width"]
                src_h = self._master.height if self._master else parsed["height"]

                for serial, slave in self._slaves.items():
                    if not slave.active:
                        dead_serials.append(serial)
                        continue

                    sx, sy = scale_coordinate(
                        parsed["x"], parsed["y"], src_w, src_h, slave.width, slave.height
                    )

                    slave_pkt = encode_scroll_packet(
                        x=sx,
                        y=sy,
                        width=slave.width,
                        height=slave.height,
                        hscroll=parsed["hscroll"],
                        vscroll=parsed["vscroll"],
                        buttons=parsed["buttons"],
                    )

                    if slave.send_raw(slave_pkt):
                        successful_sends += 1
                    else:
                        dead_serials.append(serial)

            else:
                # Key / Text / non-positional events can be forwarded directly
                for serial, slave in self._slaves.items():
                    if not slave.active:
                        dead_serials.append(serial)
                        continue
                    if slave.send_raw(packet_bytes):
                        successful_sends += 1
                    else:
                        dead_serials.append(serial)

            # Prune disconnected slaves
            for dead_serial in dead_serials:
                self.remove_slave(dead_serial)

            return successful_sends

    def send_touch(
        self,
        action: int,
        pointer_id: int,
        x: int,
        y: int,
        pressure: int = 0xFFFF,
        action_button: int = AMOTION_EVENT_BUTTON_PRIMARY,
        buttons: int = AMOTION_EVENT_BUTTON_PRIMARY,
    ) -> int:
        """
        Creates a touch event using master coordinates, sends to master if socket
        is present, and broadcasts scaled touch events to all slave viewports.
        """
        with self._lock:
            src_w = self._master.width if self._master else 1440
            src_h = self._master.height if self._master else 3120

            master_pkt = encode_touch_packet(
                action=action,
                pointer_id=pointer_id,
                x=x,
                y=y,
                width=src_w,
                height=src_h,
                pressure=pressure,
                action_button=action_button,
                buttons=buttons,
            )

            if self._master and self._master.socket:
                self._master.send_raw(master_pkt)

            return self.broadcast_event(master_pkt, event_type="touch")

    def send_key(
        self,
        action: int,
        keycode: int,
        repeat: int = 0,
        metastate: int = 0
    ) -> int:
        """
        Creates a key event, sends to master if socket is present, and
        broadcasts to all slave viewports.
        """
        with self._lock:
            key_pkt = encode_key_packet(action, keycode, repeat, metastate)
            if self._master and self._master.socket:
                self._master.send_raw(key_pkt)
            return self.broadcast_event(key_pkt, event_type="key")

    def send_text(self, text: str) -> int:
        """
        Creates a text packet, sends to master if socket is present, and
        broadcasts to all slave viewports.
        """
        with self._lock:
            text_pkt = encode_text_packet(text)
            if self._master and self._master.socket:
                self._master.send_raw(text_pkt)
            return self.broadcast_event(text_pkt, event_type="text")

    def send_scroll(
        self,
        x: int,
        y: int,
        hscroll: int,
        vscroll: int,
        buttons: int = 0
    ) -> int:
        """
        Creates a scroll packet using master coordinates, sends to master if socket
        is present, and broadcasts scaled scroll events to all slave viewports.
        """
        with self._lock:
            src_w = self._master.width if self._master else 1440
            src_h = self._master.height if self._master else 3120

            scroll_pkt = encode_scroll_packet(
                x=x,
                y=y,
                width=src_w,
                height=src_h,
                hscroll=hscroll,
                vscroll=vscroll,
                buttons=buttons,
            )

            if self._master and self._master.socket:
                self._master.send_raw(scroll_pkt)

            return self.broadcast_event(scroll_pkt, event_type="scroll")

    def close(self) -> None:
        """Closes all master and slave sockets and halts synchronization."""
        with self._lock:
            self._is_syncing = False
            if self._master is not None:
                self._master.close()
                self._master = None
            for slave in self._slaves.values():
                slave.close()
            self._slaves.clear()
            logger.info("InputSyncMultiplexer closed all nodes.")

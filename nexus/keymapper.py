"""
nexus/keymapper.py
==================
LDPlayer-Grade Precision Input Keymapper & Gamepad Mapping Engine.

Features:
- PC keyboard & mouse to Android touch/motion translation
- WASD 8-directional movement vectorizer with diagonal magnitude normalization
- Crosshair aim / mouse-look relative delta to swipe sweeps with sensitivity & invert-y
- MOBA smart casting (target aiming on hold, cast on release, cancellation)
- Single-key normal tap & continuous rapid-fire auto-clicker (10-30 Hz pulse tap train)
- Gamepad mapping (left stick to D-pad, right stick to aim, buttons to coordinates)
- Scrcpy binary control socket packet encoding (>BBQIIHHHHII touch, >BBIII key)
- JSON schema persistence for keymaps (keymaps/<package_name>.json) and built-in presets
"""

import os
import json
import math
import time
import struct
import threading
from typing import Dict, List, Tuple, Optional, Union, Any, Set
from dataclasses import dataclass, field, asdict

# Scrcpy binary packet format strings
SCRCPY_TOUCH_PACKET_FORMAT = ">BBQIIHHHHII"  # 34 bytes (type=0x02, action, pointer_id, x, y, w, h, pressure, action_btn, buttons, display_id)
SCRCPY_KEY_PACKET_FORMAT = ">BBIII"          # 14 bytes (type=0x00, action, keycode, repeat, metastate)

# Common Android Keycodes (AKEYCODE_*)
KEY_NAME_TO_ANDROID_KEYCODE = {
    "0": 7, "1": 8, "2": 9, "3": 10, "4": 11, "5": 12, "6": 13, "7": 14, "8": 15, "9": 16,
    "A": 29, "B": 30, "C": 31, "D": 32, "E": 33, "F": 34, "G": 35, "H": 36, "I": 37, "J": 38,
    "K": 39, "L": 40, "M": 41, "N": 42, "O": 43, "P": 44, "Q": 45, "R": 46, "S": 47, "T": 48,
    "U": 49, "V": 50, "W": 51, "X": 52, "Y": 53, "Z": 54,
    "SPACE": 62, "ENTER": 66, "RETURN": 66, "ESC": 111, "ESCAPE": 111, "BACKSPACE": 67,
    "TAB": 61, "SHIFT": 59, "LSHIFT": 59, "RSHIFT": 60, "CTRL": 113, "LCTRL": 113, "RCTRL": 114,
    "ALT": 57, "LALT": 57, "RALT": 58, "HOME": 3, "BACK": 4, "MENU": 82, "GRAVE": 68, "~": 68,
    "UP": 19, "DOWN": 20, "LEFT": 21, "RIGHT": 22,
    "F1": 131, "F2": 132, "F3": 133, "F4": 134, "F5": 135, "F6": 136,
    "F7": 137, "F8": 138, "F9": 139, "F10": 140, "F11": 141, "F12": 142
}


@dataclass
class AndroidInputEvent:
    """Represents an Android input event (touch, motion, or key)."""
    event_type: str            # "touch", "key", "mouse_move"
    action: int                # touch: 0=DOWN, 1=UP, 2=MOVE; key: 0=DOWN, 1=UP
    x: int = 0
    y: int = 0
    pointer_id: int = 0
    keycode: int = 0
    pressure: float = 1.0
    action_button: int = 0
    buttons: int = 0

    def to_scrcpy_touch_packet(self, width: int = 1440, height: int = 3120) -> bytes:
        """Serializes event to Scrcpy 34-byte binary touch packet (>BBQIIHHHHII) with uint32 clamping."""
        pressure_int = int(max(0.0, min(1.0, self.pressure)) * 0xFFFF)
        clamped_x = max(0, min(0xFFFFFFFF, int(self.x)))
        clamped_y = max(0, min(0xFFFFFFFF, int(self.y)))
        clamped_w = max(1, min(0xFFFF, int(width)))
        clamped_h = max(1, min(0xFFFF, int(height)))
        clamped_pressure = max(0, min(0xFFFF, pressure_int))
        clamped_btn = max(0, min(0xFFFF, int(self.action_button)))
        clamped_buttons = max(0, min(0xFFFFFFFF, int(self.buttons)))
        clamped_action = max(0, min(0xFF, int(self.action)))
        clamped_pid = max(0, min(0xFFFFFFFFFFFFFFFF, int(self.pointer_id)))

        return struct.pack(
            SCRCPY_TOUCH_PACKET_FORMAT,
            0x02,                       # type = TOUCH
            clamped_action,             # action: 0=DOWN, 1=UP, 2=MOVE, 3=CANCEL
            clamped_pid,                # pointer_id (uint64)
            clamped_x,                  # position_x (uint32)
            clamped_y,                  # position_y (uint32)
            clamped_w,                  # screen_width (uint16)
            clamped_h,                  # screen_height (uint16)
            clamped_pressure,           # pressure (uint16)
            clamped_btn,                # action_button (uint16)
            clamped_buttons,            # buttons (uint32)
            0                           # display_id (uint32)
        )

    def to_scrcpy_key_packet(self, repeat: int = 0, metastate: int = 0) -> bytes:
        """Serializes event to Scrcpy 14-byte binary key packet (>BBIII)."""
        return struct.pack(
            SCRCPY_KEY_PACKET_FORMAT,
            0x00,                       # type = KEY
            self.action,                # action: 0=DOWN, 1=UP
            self.keycode,               # keycode (uint32)
            repeat,                     # repeat (uint32)
            metastate                   # metastate (uint32)
        )

    def to_scrcpy_packet(self, width: int = 1440, height: int = 3120) -> bytes:
        """Encodes event into the appropriate Scrcpy binary packet format."""
        if self.event_type == "key":
            return self.to_scrcpy_key_packet()
        return self.to_scrcpy_touch_packet(width, height)

    @classmethod
    def from_scrcpy_touch_packet(cls, data: bytes) -> "AndroidInputEvent":
        """Deserializes a Scrcpy touch packet."""
        (msg_type, action, pointer_id, x, y, width, height,
         pressure_int, action_btn, buttons, display_id) = struct.unpack(SCRCPY_TOUCH_PACKET_FORMAT, data)
        return cls(
            event_type="touch",
            action=action,
            x=x,
            y=y,
            pointer_id=pointer_id,
            pressure=pressure_int / 0xFFFF,
            action_button=action_btn,
            buttons=buttons
        )

    @classmethod
    def from_scrcpy_key_packet(cls, data: bytes) -> "AndroidInputEvent":
        """Deserializes a Scrcpy key packet."""
        msg_type, action, keycode, repeat, metastate = struct.unpack(SCRCPY_KEY_PACKET_FORMAT, data)
        return cls(
            event_type="key",
            action=action,
            keycode=keycode
        )


@dataclass
class KeymapNode:
    """Represents a single control node on the screen layout."""
    node_id: str
    control_type: str  # "dpad", "aim_look", "single_key", "smart_cast", "rapid_fire", "gamepad_stick", "gamepad_button"
    name: str
    coords: Dict[str, float] = field(default_factory=dict)     # e.g. {"x": 0.22, "y": 0.74, "radius": 0.12}
    bindings: Dict[str, Any] = field(default_factory=dict)     # e.g. {"up": "W", "down": "S", ...} or {"key": "Space"}
    extra: Dict[str, Any] = field(default_factory=dict)        # e.g. {"sensitivity": [1.4, 1.4], "frequency_hz": 15}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "KeymapNode":
        coords_in = data.get("coords")
        if not isinstance(coords_in, dict):
            coords_in = {}

        center_val = None
        for k in ("center", "coord", "origin"):
            if k in data and data[k] is not None:
                center_val = data[k]
                break

        if not isinstance(center_val, (list, tuple)):
            center_val = [0.5, 0.5]

        try:
            def_x = float(center_val[0]) if len(center_val) > 0 and center_val[0] is not None else 0.5
        except (ValueError, TypeError):
            def_x = 0.5

        try:
            def_y = float(center_val[1]) if len(center_val) > 1 and center_val[1] is not None else 0.5
        except (ValueError, TypeError):
            def_y = 0.5

        try:
            def_r = float(data.get("radius", data.get("range", 0.10)))
        except (ValueError, TypeError):
            def_r = 0.10

        x = coords_in.get("x", def_x)
        y = coords_in.get("y", def_y)
        r = coords_in.get("radius", def_r)

        bindings = data.get("bindings")
        if not isinstance(bindings, dict):
            bindings = data.get("keys")
            if not isinstance(bindings, dict):
                bindings = {"key": data.get("key", data.get("toggle_key", ""))}

        extra = data.get("extra")
        if not isinstance(extra, dict):
            extra = {
                "sensitivity": data.get("sensitivity", [1.0, 1.0]),
                "invert_y": data.get("invert_y", False),
                "frequency_hz": data.get("frequency_hz", 20),
                "range": data.get("range", 0.15)
            }

        return cls(
            node_id=str(data.get("id", data.get("node_id", ""))),
            control_type=str(data.get("type", data.get("control_type", "single_key"))),
            name=str(data.get("name", "")),
            coords={"x": float(x), "y": float(y), "radius": float(r)},
            bindings=bindings,
            extra=extra
        )


@dataclass
class KeymapConfig:
    """Configuration profile holding a set of keymap nodes and viewport dimensions."""
    profile_name: str
    package_name: str
    viewport_dimensions: Tuple[int, int] = (1440, 3120)
    controls: List[KeymapNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "package_name": self.package_name,
            "viewport_dimensions": list(self.viewport_dimensions),
            "controls": [c.to_dict() for c in self.controls]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeymapConfig":
        raw_controls = data.get("controls", [])
        controls = []
        if isinstance(raw_controls, (list, tuple)):
            for c in raw_controls:
                if isinstance(c, KeymapNode):
                    controls.append(c)
                elif isinstance(c, dict):
                    controls.append(KeymapNode.from_dict(c))

        dims = data.get("viewport_dimensions")
        w, h = 1440, 3120
        if isinstance(dims, (list, tuple)):
            if len(dims) >= 1:
                try:
                    w = int(dims[0]) if int(dims[0]) > 0 else 1440
                except (ValueError, TypeError):
                    pass
            if len(dims) >= 2:
                try:
                    h = int(dims[1]) if int(dims[1]) > 0 else 3120
                except (ValueError, TypeError):
                    pass
            elif len(dims) == 1:
                h = 3120

        return cls(
            profile_name=str(data.get("profile_name", "Default Profile")),
            package_name=str(data.get("package_name", "default")),
            viewport_dimensions=(w, h),
            controls=controls
        )

    def save_to_file(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "KeymapConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# Built-in Default Presets
BUILTIN_PRESETS: Dict[str, KeymapConfig] = {
    "fps": KeymapConfig(
        profile_name="FPS Tactical Shooter",
        package_name="com.tencent.ig",
        viewport_dimensions=(1440, 3120),
        controls=[
            KeymapNode(
                node_id="wasd_movement",
                control_type="dpad",
                name="WASD Joystick",
                coords={"x": 0.22, "y": 0.74, "radius": 0.12},
                bindings={"up": "W", "down": "S", "left": "A", "right": "D"}
            ),
            KeymapNode(
                node_id="crosshair_aim",
                control_type="aim_look",
                name="FPS Mouse Look",
                coords={"x": 0.65, "y": 0.50},
                bindings={"toggle_key": "~"},
                extra={"sensitivity": [1.4, 1.4], "invert_y": False}
            ),
            KeymapNode(
                node_id="fire_button",
                control_type="single_key",
                name="Fire Primary",
                coords={"x": 0.86, "y": 0.72},
                bindings={"key": "LButton"}
            ),
            KeymapNode(
                node_id="jump_button",
                control_type="single_key",
                name="Jump",
                coords={"x": 0.92, "y": 0.82},
                bindings={"key": "Space"}
            ),
            KeymapNode(
                node_id="reload_button",
                control_type="single_key",
                name="Reload",
                coords={"x": 0.78, "y": 0.88},
                bindings={"key": "R"}
            ),
            KeymapNode(
                node_id="rapid_burst",
                control_type="rapid_fire",
                name="Auto Burst",
                coords={"x": 0.86, "y": 0.72},
                bindings={"key": "E"},
                extra={"frequency_hz": 20}
            )
        ]
    ),
    "moba": KeymapConfig(
        profile_name="MOBA Standard",
        package_name="com.mobile.legends",
        viewport_dimensions=(1440, 3120),
        controls=[
            KeymapNode(
                node_id="moba_dpad",
                control_type="dpad",
                name="Movement D-Pad",
                coords={"x": 0.18, "y": 0.78, "radius": 0.10},
                bindings={"up": "W", "down": "S", "left": "A", "right": "D"}
            ),
            KeymapNode(
                node_id="skill_1",
                control_type="smart_cast",
                name="Skill 1 Smart Cast",
                coords={"x": 0.80, "y": 0.65, "range": 0.15},
                bindings={"key": "Q", "cancel_key": "Escape"},
                extra={"range": 0.15}
            ),
            KeymapNode(
                node_id="skill_2",
                control_type="smart_cast",
                name="Skill 2 Smart Cast",
                coords={"x": 0.85, "y": 0.55, "range": 0.15},
                bindings={"key": "E", "cancel_key": "Escape"},
                extra={"range": 0.15}
            ),
            KeymapNode(
                node_id="basic_attack",
                control_type="single_key",
                name="Basic Attack",
                coords={"x": 0.88, "y": 0.82},
                bindings={"key": "Space"}
            )
        ]
    ),
    "action": KeymapConfig(
        profile_name="Action RPG",
        package_name="com.miHoYo.GenshinImpact",
        viewport_dimensions=(1440, 3120),
        controls=[
            KeymapNode(
                node_id="action_dpad",
                control_type="dpad",
                name="Character Movement",
                coords={"x": 0.20, "y": 0.75, "radius": 0.12},
                bindings={"up": "W", "down": "S", "left": "A", "right": "D"}
            ),
            KeymapNode(
                node_id="normal_attack",
                control_type="single_key",
                name="Normal Attack",
                coords={"x": 0.88, "y": 0.82},
                bindings={"key": "J"}
            ),
            KeymapNode(
                node_id="elemental_skill",
                control_type="single_key",
                name="Elemental Skill",
                coords={"x": 0.80, "y": 0.75},
                bindings={"key": "E"}
            ),
            KeymapNode(
                node_id="burst_skill",
                control_type="single_key",
                name="Elemental Burst",
                coords={"x": 0.85, "y": 0.60},
                bindings={"key": "Q"}
            ),
            KeymapNode(
                node_id="dash_dodge",
                control_type="single_key",
                name="Dash",
                coords={"x": 0.92, "y": 0.90},
                bindings={"key": "RButton"}
            )
        ]
    )
}


class PrecisionKeymapper:
    """
    Translates host PC keyboard, mouse, and gamepad inputs into sub-millisecond
    Android touch and motion packets via Scrcpy Control Socket.
    """
    def __init__(
        self,
        serial: str = "emulator-5554",
        control_sender: Any = None,
        display_dims: Tuple[int, int] = (1440, 3120)
    ):
        self.serial = serial
        self.sender = control_sender
        self.disp_w, self.disp_h = display_dims
        self.config: Optional[KeymapConfig] = None
        self.nodes: Dict[str, KeymapNode] = {}
        
        # State tracking
        self.active_dpad_keys: Set[str] = set()
        self.aim_active: bool = False
        self.active_pointers: Dict[str, int] = {}
        self._pointer_counter: int = 10
        self._lock = threading.Lock()

        # MOBA Smart Cast state
        self.smart_cast_active_node: Optional[KeymapNode] = None
        self.smart_cast_aim_point: Tuple[int, int] = (0, 0)
        self.smart_cast_canceled: bool = False

        # Rapid Fire state
        self.rapid_fire_threads: Dict[str, threading.Thread] = {}
        self.rapid_fire_stops: Dict[str, threading.Event] = {}

        # Default load FPS preset
        self.load_preset("fps")

    # =========================================================================
    # Configuration and Presets
    # =========================================================================

    def load_preset(self, game_id: str) -> KeymapConfig:
        """Loads a built-in or cached preset by name or package_name."""
        key = game_id.lower().strip()
        matched = None
        for preset_id, preset in BUILTIN_PRESETS.items():
            if preset_id == key or preset.package_name.lower() == key or preset.profile_name.lower() == key:
                matched = preset
                break
        
        if not matched:
            # Check if keymaps/<game_id>.json exists
            preset_file = os.path.join("keymaps", f"{game_id}.json")
            if os.path.isfile(preset_file):
                matched = KeymapConfig.load_from_file(preset_file)
            else:
                matched = BUILTIN_PRESETS["fps"]
        
        self.load_profile(matched.to_dict())
        return matched

    def load_profile(self, profile_dict: dict):
        """Loads a profile dictionary, parsing viewport dimensions and control nodes."""
        with self._lock:
            self.stop_all_rapid_fire()
            self.nodes.clear()
            self.active_dpad_keys.clear()
            self.active_pointers.clear()
            
            cfg = KeymapConfig.from_dict(profile_dict)
            self.config = cfg
            self.disp_w, self.disp_h = cfg.viewport_dimensions
            for node in cfg.controls:
                self.nodes[node.node_id] = node

    def save_profile_to_file(self, file_path: str):
        """Persists current profile configuration to a JSON file."""
        if not self.config:
            self.config = KeymapConfig(
                profile_name="Custom Profile",
                package_name="custom",
                viewport_dimensions=(self.disp_w, self.disp_h),
                controls=list(self.nodes.values())
            )
        self.config.viewport_dimensions = (self.disp_w, self.disp_h)
        self.config.controls = list(self.nodes.values())
        self.config.save_to_file(file_path)

    # =========================================================================
    # Pointer Allocation
    # =========================================================================

    def _alloc_pointer(self, node_id: str) -> int:
        if node_id not in self.active_pointers:
            self._pointer_counter += 1
            self.active_pointers[node_id] = self._pointer_counter
        return self.active_pointers[node_id]

    def _free_pointer(self, node_id: str) -> int:
        return self.active_pointers.pop(node_id, self._pointer_counter)

    # =========================================================================
    # WASD 8-Directional Movement Vectorizer
    # =========================================================================

    def compute_dpad_vector(self, active_keys: Set[str], cx: int, cy: int, radius: int) -> Tuple[int, int]:
        """
        Calculates 8-directional movement vector from active keys:
        Applies diagonal normalization so magnitude is exactly radius.
        """
        if not active_keys:
            return (cx, cy)

        dx, dy = 0.0, 0.0
        if "up" in active_keys:
            dy -= 1.0
        if "down" in active_keys:
            dy += 1.0
        if "left" in active_keys:
            dx -= 1.0
        if "right" in active_keys:
            dx += 1.0

        mag = math.hypot(dx, dy)
        if mag > 0:
            dx /= mag
            dy /= mag

        target_x = int(cx + dx * radius)
        target_y = int(cy + dy * radius)
        return (target_x, target_y)

    def _dispatch_dpad_motion(self, node: KeymapNode) -> List[AndroidInputEvent]:
        events = []
        cx = int(node.coords.get("x", 0.5) * self.disp_w)
        cy = int(node.coords.get("y", 0.5) * self.disp_h)
        radius = int(node.coords.get("radius", 0.12) * min(self.disp_w, self.disp_h))
        pid = self._alloc_pointer(node.node_id)

        if not self.active_dpad_keys:
            # Release touch
            evt = AndroidInputEvent(event_type="touch", action=1, x=cx, y=cy, pointer_id=pid)
            events.append(evt)
            self._free_pointer(node.node_id)
        else:
            tx, ty = self.compute_dpad_vector(self.active_dpad_keys, cx, cy, radius)
            # Send move event (or down if newly allocated)
            evt = AndroidInputEvent(event_type="touch", action=2, x=tx, y=ty, pointer_id=pid)
            events.append(evt)

        self._broadcast_events(events)
        return events

    # =========================================================================
    # Mouse Look / Crosshair Aim
    # =========================================================================

    def handle_mouse_delta(self, dx: int, dy: int) -> List[AndroidInputEvent]:
        """
        Translates relative mouse delta into smooth drag sweep motion events
        or relative aim events when mouse-look is active.
        """
        if not self.aim_active:
            return []

        events = []
        for node in self.nodes.values():
            if node.control_type == "aim_look":
                cx = int(node.coords.get("x", 0.5) * self.disp_w)
                cy = int(node.coords.get("y", 0.5) * self.disp_h)
                sens = node.extra.get("sensitivity", [1.0, 1.0])
                invert_y = node.extra.get("invert_y", False)

                sx = sens[0] if isinstance(sens, (list, tuple)) else float(sens)
                sy = sens[1] if isinstance(sens, (list, tuple)) and len(sens) > 1 else sx

                eff_dy = -dy if invert_y else dy
                target_x = max(0, min(self.disp_w, cx + int(dx * sx)))
                target_y = max(0, min(self.disp_h, cy + int(eff_dy * sy)))

                pid = self._alloc_pointer(node.node_id)
                evt = AndroidInputEvent(event_type="touch", action=2, x=target_x, y=target_y, pointer_id=pid)
                events.append(evt)

        self._broadcast_events(events)
        return events

    # =========================================================================
    # MOBA Smart Casting
    # =========================================================================

    def start_smart_cast(self, node: KeymapNode) -> List[AndroidInputEvent]:
        """Pressing a skill key initiates targeting at skill origin."""
        self.smart_cast_active_node = node
        self.smart_cast_canceled = False
        ox = int(node.coords.get("x", 0.5) * self.disp_w)
        oy = int(node.coords.get("y", 0.5) * self.disp_h)
        self.smart_cast_aim_point = (ox, oy)

        pid = self._alloc_pointer(node.node_id)
        evt = AndroidInputEvent(event_type="touch", action=0, x=ox, y=oy, pointer_id=pid)
        events = [evt]
        self._broadcast_events(events)
        return events

    def update_smart_cast_aim(self, mouse_x: int, mouse_y: int) -> List[AndroidInputEvent]:
        """Mouse movement while aiming drags the trajectory indicator."""
        if not self.smart_cast_active_node or self.smart_cast_canceled:
            return []

        node = self.smart_cast_active_node
        ox = int(node.coords.get("x", 0.5) * self.disp_w)
        oy = int(node.coords.get("y", 0.5) * self.disp_h)
        r = int(node.extra.get("range", 0.15) * min(self.disp_w, self.disp_h))

        dx = mouse_x - ox
        dy = mouse_y - oy
        dist = math.hypot(dx, dy)
        if dist > 0:
            norm_dx = dx / dist
            norm_dy = dy / dist
            clamped_dist = min(dist, r)
            target_x = int(ox + norm_dx * clamped_dist)
            target_y = int(oy + norm_dy * clamped_dist)
        else:
            target_x, target_y = ox, oy

        self.smart_cast_aim_point = (target_x, target_y)
        pid = self._alloc_pointer(node.node_id)
        evt = AndroidInputEvent(event_type="touch", action=2, x=target_x, y=target_y, pointer_id=pid)
        events = [evt]
        self._broadcast_events(events)
        return events

    def release_smart_cast(self) -> List[AndroidInputEvent]:
        """Releasing skill key casts the ability at current aim point."""
        if not self.smart_cast_active_node:
            return []

        node = self.smart_cast_active_node
        pid = self._free_pointer(node.node_id)
        events = []

        if not self.smart_cast_canceled:
            tx, ty = self.smart_cast_aim_point
            evt = AndroidInputEvent(event_type="touch", action=1, x=tx, y=ty, pointer_id=pid)
            events.append(evt)
        else:
            # Cancel: Touch UP without triggering skill
            ox = int(node.coords.get("x", 0.5) * self.disp_w)
            oy = int(node.coords.get("y", 0.5) * self.disp_h)
            evt = AndroidInputEvent(event_type="touch", action=1, x=ox, y=oy, pointer_id=pid)
            events.append(evt)

        self.smart_cast_active_node = None
        self.smart_cast_canceled = False
        self._broadcast_events(events)
        return events

    def cancel_smart_cast(self) -> List[AndroidInputEvent]:
        """Cancels active smart cast without firing."""
        if not self.smart_cast_active_node:
            return []
        self.smart_cast_canceled = True
        return self.release_smart_cast()

    # =========================================================================
    # Rapid Fire Auto-Clicker
    # =========================================================================

    def start_rapid_fire(self, node: KeymapNode):
        """Starts 10-30 Hz pulse tap train while key is held down."""
        if node.node_id in self.rapid_fire_threads:
            return

        stop_event = threading.Event()
        self.rapid_fire_stops[node.node_id] = stop_event
        freq = node.extra.get("frequency_hz", 20)
        freq = max(5, min(50, freq))
        period = 1.0 / freq
        half_period = period / 2.0

        def _worker():
            px = int(node.coords.get("x", 0.5) * self.disp_w)
            py = int(node.coords.get("y", 0.5) * self.disp_h)
            pid = self._alloc_pointer(node.node_id)
            while not stop_event.is_set():
                # Down
                e_down = AndroidInputEvent(event_type="touch", action=0, x=px, y=py, pointer_id=pid)
                self._broadcast_events([e_down])
                time.sleep(half_period)
                if stop_event.is_set():
                    break
                # Up
                e_up = AndroidInputEvent(event_type="touch", action=1, x=px, y=py, pointer_id=pid)
                self._broadcast_events([e_up])
                time.sleep(half_period)
            # Ensure final UP
            e_final = AndroidInputEvent(event_type="touch", action=1, x=px, y=py, pointer_id=pid)
            self._broadcast_events([e_final])
            self._free_pointer(node.node_id)

        t = threading.Thread(target=_worker, daemon=True)
        self.rapid_fire_threads[node.node_id] = t
        t.start()

    def stop_rapid_fire(self, node_id: str):
        """Stops rapid fire tap train."""
        stop_event = self.rapid_fire_stops.pop(node_id, None)
        if stop_event:
            stop_event.set()
        t = self.rapid_fire_threads.pop(node_id, None)
        if t and t.is_alive():
            t.join(timeout=0.2)

    def stop_all_rapid_fire(self):
        """Stops all active rapid fire tap trains."""
        for nid in list(self.rapid_fire_stops.keys()):
            self.stop_rapid_fire(nid)

    def trigger_rapid_fire_pulses(self, node: KeymapNode, count: int = 5) -> List[AndroidInputEvent]:
        """Deterministic rapid-fire pulse sequence generator for unit tests and synchronous invocation."""
        px = int(node.coords.get("x", 0.5) * self.disp_w)
        py = int(node.coords.get("y", 0.5) * self.disp_h)
        pid = self._alloc_pointer(node.node_id)
        events = []
        for _ in range(count):
            events.append(AndroidInputEvent(event_type="touch", action=0, x=px, y=py, pointer_id=pid))
            events.append(AndroidInputEvent(event_type="touch", action=1, x=px, y=py, pointer_id=pid))
        self._free_pointer(node.node_id)
        return events

    # =========================================================================
    # Event Handlers (Keyboard, Mouse, Gamepad)
    # =========================================================================

    def handle_key_down(self, key_name: str) -> bool:
        """Processes a key-down event, returns True if mapped."""
        events = self.handle_host_key_event(key_name, is_down=True)
        return len(events) > 0

    def handle_key_up(self, key_name: str) -> bool:
        """Processes a key-up event, returns True if mapped."""
        events = self.handle_host_key_event(key_name, is_down=False)
        return len(events) > 0

    def handle_host_key_event(self, key: Union[int, str], is_down: bool) -> List[AndroidInputEvent]:
        """
        Translates a host keyboard event into Android input events.
        Accepts integer keycodes or string key names.
        """
        key_str = self._normalize_key_name(key)
        events: List[AndroidInputEvent] = []

        # Check Smart Cast cancel key
        if is_down and (key_str in ("ESC", "ESCAPE") or
                        (self.smart_cast_active_node and
                         self.smart_cast_active_node.bindings.get("cancel_key", "").upper() == key_str)):
            if self.smart_cast_active_node:
                return self.cancel_smart_cast()

        # Check all nodes
        for node in self.nodes.values():
            if node.control_type == "dpad":
                for direction, bound_k in node.bindings.items():
                    if bound_k.upper() == key_str:
                        if is_down:
                            self.active_dpad_keys.add(direction)
                        else:
                            self.active_dpad_keys.discard(direction)
                        return self._dispatch_dpad_motion(node)

            elif node.control_type == "single_key":
                bound = node.bindings.get("key", "").upper()
                if bound == key_str:
                    px = int(node.coords.get("x", 0.5) * self.disp_w)
                    py = int(node.coords.get("y", 0.5) * self.disp_h)
                    pid = self._alloc_pointer(node.node_id) if is_down else self._free_pointer(node.node_id)
                    action = 0 if is_down else 1
                    evt = AndroidInputEvent(event_type="touch", action=action, x=px, y=py, pointer_id=pid)
                    events.append(evt)

            elif node.control_type == "smart_cast":
                bound = node.bindings.get("key", "").upper()
                if bound == key_str:
                    if is_down:
                        events.extend(self.start_smart_cast(node))
                    else:
                        events.extend(self.release_smart_cast())

            elif node.control_type == "rapid_fire":
                bound = node.bindings.get("key", "").upper()
                if bound == key_str:
                    if is_down:
                        self.start_rapid_fire(node)
                    else:
                        self.stop_rapid_fire(node.node_id)
                    px = int(node.coords.get("x", 0.5) * self.disp_w)
                    py = int(node.coords.get("y", 0.5) * self.disp_h)
                    action = 0 if is_down else 1
                    events.append(AndroidInputEvent(event_type="touch", action=action, x=px, y=py, pointer_id=0))

            elif node.control_type == "aim_look":
                toggle = node.bindings.get("toggle_key", "~").upper()
                if toggle == key_str and is_down:
                    self.aim_active = not self.aim_active

        # If not mapped to touch, provide Android key event fallback
        if not events and key_str in KEY_NAME_TO_ANDROID_KEYCODE:
            ak = KEY_NAME_TO_ANDROID_KEYCODE[key_str]
            evt = AndroidInputEvent(event_type="key", action=0 if is_down else 1, keycode=ak)
            events.append(evt)

        self._broadcast_events(events)
        return events

    def handle_host_mouse_event(self, x: int, y: int, buttons: int) -> List[AndroidInputEvent]:
        """
        Translates host mouse events into Android touch events.
        buttons: bitmask (1=LButton, 2=RButton, 4=MButton)
        """
        events: List[AndroidInputEvent] = []

        # Check if smart cast is actively aiming
        if self.smart_cast_active_node and not self.smart_cast_canceled:
            return self.update_smart_cast_aim(x, y)

        # Check mouse buttons mapped as single keys
        if buttons & 1:  # Left button
            events.extend(self.handle_host_key_event("LBUTTON", is_down=True))
        if buttons & 2:  # Right button
            events.extend(self.handle_host_key_event("RBUTTON", is_down=True))

        return events

    def handle_gamepad_axis(self, axis_name: str, value: float) -> List[AndroidInputEvent]:
        """
        Maps gamepad sticks to D-pad movement or mouse aim.
        axis_name: 'lx', 'ly', 'rx', 'ry'
        value: -1.0 to 1.0 (with 0.15 deadzone applied)
        """
        deadzone = 0.15
        val = 0.0 if abs(value) < deadzone else value
        events: List[AndroidInputEvent] = []

        if axis_name in ("lx", "ly"):
            # Update virtual WASD based on left stick
            if axis_name == "lx":
                if val < -0.3:
                    self.active_dpad_keys.add("left")
                    self.active_dpad_keys.discard("right")
                elif val > 0.3:
                    self.active_dpad_keys.add("right")
                    self.active_dpad_keys.discard("left")
                else:
                    self.active_dpad_keys.discard("left")
                    self.active_dpad_keys.discard("right")
            elif axis_name == "ly":
                if val < -0.3:
                    self.active_dpad_keys.add("up")
                    self.active_dpad_keys.discard("down")
                elif val > 0.3:
                    self.active_dpad_keys.add("down")
                    self.active_dpad_keys.discard("up")
                else:
                    self.active_dpad_keys.discard("up")
                    self.active_dpad_keys.discard("down")

            for node in self.nodes.values():
                if node.control_type == "dpad":
                    return self._dispatch_dpad_motion(node)

        elif axis_name in ("rx", "ry"):
            # Right stick directly drives aim delta
            dx = int(val * 20.0) if axis_name == "rx" else 0
            dy = int(val * 20.0) if axis_name == "ry" else 0
            if self.aim_active and (dx != 0 or dy != 0):
                return self.handle_mouse_delta(dx, dy)

        return events

    def handle_gamepad_button(self, button_name: str, is_down: bool) -> List[AndroidInputEvent]:
        """Maps gamepad buttons (A, B, X, Y, LB, RB, LT, RT) to keymapper nodes."""
        return self.handle_host_key_event(button_name.upper(), is_down=is_down)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _broadcast_events(self, events: List[AndroidInputEvent]):
        """Dispatches generated events to control sender if registered."""
        if not self.sender:
            return
        for evt in events:
            if evt.event_type == "touch":
                if hasattr(self.sender, "broadcast_touch"):
                    self.sender.broadcast_touch(
                        action=evt.action,
                        master_x=evt.x,
                        master_y=evt.y,
                        pointer_id=evt.pointer_id
                    )
            elif evt.event_type == "key":
                if hasattr(self.sender, "broadcast_key"):
                    self.sender.broadcast_key(
                        action=evt.action,
                        keycode=evt.keycode
                    )

    def _normalize_key_name(self, key: Union[int, str]) -> str:
        if isinstance(key, str):
            return key.upper().strip()
        # If integer ASCII, convert to char
        if 32 <= key <= 126:
            return chr(key).upper()
        # Search inverted keycode table
        for name, code in KEY_NAME_TO_ANDROID_KEYCODE.items():
            if code == key:
                return name
        return str(key)


# Alias for compatibility per requirements
Keymapper = PrecisionKeymapper

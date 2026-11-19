"""
tests/test_keymapper_and_macro.py
=================================
Comprehensive unit tests for Feature 17 (Precision Keymapper)
and Feature 18 (Macro Engine).
"""

import os
import time
import math
import struct
import tempfile
import unittest

from nexus.keymapper import (
    PrecisionKeymapper,
    Keymapper,
    KeymapConfig,
    KeymapNode,
    AndroidInputEvent,
    SCRCPY_TOUCH_PACKET_FORMAT,
    SCRCPY_KEY_PACKET_FORMAT,
    BUILTIN_PRESETS
)
from nexus.macro_engine import MacroEngine, MacroStep, MacroScript


class TestKeymapperPresetsAndConfig(unittest.TestCase):
    """Tests preset loading, dataclass creation, and schema serialization."""

    def test_builtin_presets_exist(self):
        self.assertIn("fps", BUILTIN_PRESETS)
        self.assertIn("moba", BUILTIN_PRESETS)
        self.assertIn("action", BUILTIN_PRESETS)

        fps = BUILTIN_PRESETS["fps"]
        self.assertEqual(fps.profile_name, "FPS Tactical Shooter")
        self.assertEqual(fps.viewport_dimensions, (1440, 3120))
        self.assertTrue(len(fps.controls) >= 5)

    def test_keymapper_alias_and_init(self):
        km = Keymapper()
        self.assertIsInstance(km, PrecisionKeymapper)
        self.assertEqual(km.disp_w, 1440)
        self.assertEqual(km.disp_h, 3120)

    def test_load_preset_by_package_or_alias(self):
        km = PrecisionKeymapper()
        cfg_fps = km.load_preset("fps")
        self.assertEqual(cfg_fps.profile_name, "FPS Tactical Shooter")

        cfg_moba = km.load_preset("com.mobile.legends")
        self.assertEqual(cfg_moba.profile_name, "MOBA Standard")

        cfg_action = km.load_preset("action")
        self.assertEqual(cfg_action.profile_name, "Action RPG")

    def test_config_json_roundtrip(self):
        cfg = BUILTIN_PRESETS["fps"]
        d = cfg.to_dict()
        reconstructed = KeymapConfig.from_dict(d)
        self.assertEqual(reconstructed.profile_name, cfg.profile_name)
        self.assertEqual(reconstructed.package_name, cfg.package_name)
        self.assertEqual(len(reconstructed.controls), len(cfg.controls))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name
        try:
            cfg.save_to_file(temp_path)
            loaded = KeymapConfig.load_from_file(temp_path)
            self.assertEqual(loaded.profile_name, cfg.profile_name)
            self.assertEqual(len(loaded.controls), len(cfg.controls))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestWASDMovementVectorizer(unittest.TestCase):
    """Tests WASD 8-directional movement vectorizer and diagonal normalization."""

    def setUp(self):
        self.km = PrecisionKeymapper(display_dims=(1000, 1000))
        # Ensure FPS preset with WASD at center (200, 700), radius 100
        node = KeymapNode(
            node_id="test_wasd",
            control_type="dpad",
            name="Test DPad",
            coords={"x": 0.20, "y": 0.70, "radius": 0.10},
            bindings={"up": "W", "down": "S", "left": "A", "right": "D"}
        )
        self.km.load_profile({
            "profile_name": "Test",
            "viewport_dimensions": [1000, 1000],
            "controls": [node.to_dict()]
        })

    def test_cardinal_directions(self):
        cx, cy, radius = 200, 700, 100

        # UP (W)
        tx, ty = self.km.compute_dpad_vector({"up"}, cx, cy, radius)
        self.assertEqual(tx, cx)
        self.assertEqual(ty, cy - radius)

        # DOWN (S)
        tx, ty = self.km.compute_dpad_vector({"down"}, cx, cy, radius)
        self.assertEqual(tx, cx)
        self.assertEqual(ty, cy + radius)

        # LEFT (A)
        tx, ty = self.km.compute_dpad_vector({"left"}, cx, cy, radius)
        self.assertEqual(tx, cx - radius)
        self.assertEqual(ty, cy)

        # RIGHT (D)
        tx, ty = self.km.compute_dpad_vector({"right"}, cx, cy, radius)
        self.assertEqual(tx, cx + radius)
        self.assertEqual(ty, cy)

    def test_diagonal_normalization(self):
        cx, cy, radius = 200, 700, 100
        expected_offset = int(radius / math.sqrt(2))  # ~70 px

        # UP + RIGHT (W + D)
        tx, ty = self.km.compute_dpad_vector({"up", "right"}, cx, cy, radius)
        self.assertAlmostEqual(tx - cx, expected_offset, delta=2)
        self.assertAlmostEqual(ty - cy, -expected_offset, delta=2)
        mag = math.hypot(tx - cx, ty - cy)
        self.assertAlmostEqual(mag, radius, delta=2)

        # UP + LEFT (W + A)
        tx, ty = self.km.compute_dpad_vector({"up", "left"}, cx, cy, radius)
        self.assertAlmostEqual(tx - cx, -expected_offset, delta=2)
        self.assertAlmostEqual(ty - cy, -expected_offset, delta=2)
        mag = math.hypot(tx - cx, ty - cy)
        self.assertAlmostEqual(mag, radius, delta=2)

        # DOWN + RIGHT (S + D)
        tx, ty = self.km.compute_dpad_vector({"down", "right"}, cx, cy, radius)
        self.assertAlmostEqual(tx - cx, expected_offset, delta=2)
        self.assertAlmostEqual(ty - cy, expected_offset, delta=2)
        mag = math.hypot(tx - cx, ty - cy)
        self.assertAlmostEqual(mag, radius, delta=2)

        # DOWN + LEFT (S + A)
        tx, ty = self.km.compute_dpad_vector({"down", "left"}, cx, cy, radius)
        self.assertAlmostEqual(tx - cx, -expected_offset, delta=2)
        self.assertAlmostEqual(ty - cy, expected_offset, delta=2)
        mag = math.hypot(tx - cx, ty - cy)
        self.assertAlmostEqual(mag, radius, delta=2)

    def test_host_key_events_dispatch_dpad(self):
        # Press W
        evts = self.km.handle_host_key_event("W", is_down=True)
        self.assertTrue(len(evts) > 0)
        self.assertEqual(evts[0].action, 2)  # MOVE to target
        self.assertIn("up", self.km.active_dpad_keys)

        # Press D (now W+D diagonal)
        evts = self.km.handle_host_key_event("D", is_down=True)
        self.assertTrue(len(evts) > 0)
        self.assertEqual(evts[0].action, 2)
        self.assertIn("right", self.km.active_dpad_keys)

        # Release W (now only D active)
        evts = self.km.handle_host_key_event("W", is_down=False)
        self.assertTrue(len(evts) > 0)
        self.assertNotIn("up", self.km.active_dpad_keys)
        self.assertIn("right", self.km.active_dpad_keys)

        # Release D (all released -> Touch UP)
        evts = self.km.handle_host_key_event("D", is_down=False)
        self.assertTrue(len(evts) > 0)
        self.assertEqual(evts[0].action, 1)  # UP


class TestMouseDeltaAimLook(unittest.TestCase):
    """Tests mouse look, sensitivity scaling, and invert-Y."""

    def setUp(self):
        self.km = PrecisionKeymapper(display_dims=(1000, 1000))
        self.km.load_preset("fps")

    def test_aim_toggle(self):
        self.assertFalse(self.km.aim_active)
        # Mouse delta does nothing when inactive
        evts = self.km.handle_mouse_delta(15, -10)
        self.assertEqual(len(evts), 0)

        # Toggle aim with ~
        self.km.handle_host_key_event("~", is_down=True)
        self.assertTrue(self.km.aim_active)

        # Now delta dispatches touch events
        evts = self.km.handle_mouse_delta(20, 30)
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].action, 2)  # MOVE

        # Toggle off
        self.km.handle_host_key_event("~", is_down=True)
        self.assertFalse(self.km.aim_active)

    def test_aim_sensitivity_and_invert_y(self):
        # Configure custom aim node with invert_y=True and sensitivity=2.0
        aim_node = KeymapNode(
            node_id="custom_aim",
            control_type="aim_look",
            name="Inverted Aim",
            coords={"x": 0.5, "y": 0.5},
            bindings={"toggle_key": "F1"},
            extra={"sensitivity": [2.0, 2.0], "invert_y": True}
        )
        self.km.load_profile({
            "profile_name": "InvertTest",
            "viewport_dimensions": [1000, 1000],
            "controls": [aim_node.to_dict()]
        })

        self.km.handle_host_key_event("F1", is_down=True)
        self.assertTrue(self.km.aim_active)

        # Delta dx=10, dy=10 -> target_x = 500 + 10*2 = 520, target_y = 500 - 10*2 = 480 (inverted)
        evts = self.km.handle_mouse_delta(10, 10)
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].x, 520)
        self.assertEqual(evts[0].y, 480)


class TestMOBASmartCast(unittest.TestCase):
    """Tests MOBA smart cast targeting, drag vector, release cast, and cancellation."""

    def setUp(self):
        self.km = PrecisionKeymapper()
        self.km.load_preset("moba")
        self.km.disp_w = 1000
        self.km.disp_h = 1000

    def test_smart_cast_aim_and_release(self):
        # Key down initiates targeting at skill origin (x=800, y=650)
        evts = self.km.handle_host_key_event("Q", is_down=True)
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].action, 0)  # DOWN
        self.assertEqual(evts[0].x, 800)
        self.assertEqual(evts[0].y, 650)

        # Mouse targeting sweep to (600, 450)
        evts = self.km.handle_host_mouse_event(600, 450, buttons=0)
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].action, 2)  # MOVE
        # Aim point moved towards mouse direction
        self.assertTrue(evts[0].x < 800)
        self.assertTrue(evts[0].y < 650)

        # Key up casts the skill at aim point
        evts = self.km.handle_host_key_event("Q", is_down=False)
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].action, 1)  # UP
        self.assertIsNone(self.km.smart_cast_active_node)

    def test_smart_cast_cancel(self):
        # Key down initiates targeting
        self.km.handle_host_key_event("Q", is_down=True)
        self.assertIsNotNone(self.km.smart_cast_active_node)

        # Mouse aim
        self.km.handle_host_mouse_event(500, 500, buttons=0)

        # Press Escape to cancel
        evts = self.km.handle_host_key_event("ESCAPE", is_down=True)
        self.assertTrue(len(evts) > 0)
        self.assertEqual(evts[0].action, 1)  # UP (canceled at origin)
        self.assertEqual(evts[0].x, 800)
        self.assertEqual(evts[0].y, 650)
        self.assertIsNone(self.km.smart_cast_active_node)


class TestRapidFireAutoClicker(unittest.TestCase):
    """Tests rapid fire pulse generation and thread lifecycle."""

    def setUp(self):
        self.km = PrecisionKeymapper(display_dims=(1000, 1000))
        self.node = KeymapNode(
            node_id="rapid_node",
            control_type="rapid_fire",
            name="Rapid Test",
            coords={"x": 0.5, "y": 0.5},
            bindings={"key": "E"},
            extra={"frequency_hz": 20}
        )
        self.km.load_profile({
            "profile_name": "RapidTest",
            "viewport_dimensions": [1000, 1000],
            "controls": [self.node.to_dict()]
        })

    def test_deterministic_pulse_generation(self):
        pulses = self.km.trigger_rapid_fire_pulses(self.node, count=5)
        self.assertEqual(len(pulses), 10)  # 5 DOWN, 5 UP
        for i in range(5):
            self.assertEqual(pulses[2 * i].action, 0)      # DOWN
            self.assertEqual(pulses[2 * i + 1].action, 1)  # UP
            self.assertEqual(pulses[2 * i].x, 500)
            self.assertEqual(pulses[2 * i].y, 500)

    def test_rapid_fire_start_stop(self):
        self.km.handle_host_key_event("E", is_down=True)
        self.assertIn("rapid_node", self.km.rapid_fire_threads)
        self.assertTrue(self.km.rapid_fire_threads["rapid_node"].is_alive())

        time.sleep(0.1)  # Let a few pulses fire

        self.km.handle_host_key_event("E", is_down=False)
        self.assertNotIn("rapid_node", self.km.rapid_fire_threads)


class TestScrcpyBinaryPacketEncoding(unittest.TestCase):
    """Tests Scrcpy binary packet encoding (>BBQIIHHHHII for touch, >BBIII for key)."""

    def test_touch_packet_structure_and_size(self):
        evt = AndroidInputEvent(
            event_type="touch",
            action=0,  # DOWN
            x=720,
            y=1560,
            pointer_id=12,
            pressure=1.0,
            action_button=1,
            buttons=1
        )
        pkt = evt.to_scrcpy_touch_packet(width=1440, height=3120)
        self.assertEqual(len(pkt), 34)
        self.assertEqual(len(pkt), struct.calcsize(SCRCPY_TOUCH_PACKET_FORMAT))

        # Unpack and verify fields
        unpacked = struct.unpack(SCRCPY_TOUCH_PACKET_FORMAT, pkt)
        self.assertEqual(unpacked[0], 0x02)       # type TOUCH
        self.assertEqual(unpacked[1], 0)          # action DOWN
        self.assertEqual(unpacked[2], 12)         # pointer_id
        self.assertEqual(unpacked[3], 720)        # x
        self.assertEqual(unpacked[4], 1560)       # y
        self.assertEqual(unpacked[5], 1440)       # width
        self.assertEqual(unpacked[6], 3120)       # height
        self.assertEqual(unpacked[7], 0xFFFF)     # pressure 1.0f
        self.assertEqual(unpacked[8], 1)          # action_button
        self.assertEqual(unpacked[9], 1)          # buttons
        self.assertEqual(unpacked[10], 0)         # display_id

        # Roundtrip deserialization
        restored = AndroidInputEvent.from_scrcpy_touch_packet(pkt)
        self.assertEqual(restored.action, evt.action)
        self.assertEqual(restored.x, evt.x)
        self.assertEqual(restored.y, evt.y)
        self.assertEqual(restored.pointer_id, evt.pointer_id)
        self.assertAlmostEqual(restored.pressure, 1.0, places=3)

    def test_key_packet_structure_and_size(self):
        evt = AndroidInputEvent(
            event_type="key",
            action=0,  # DOWN
            keycode=51  # AKEYCODE_W
        )
        pkt = evt.to_scrcpy_key_packet(repeat=0, metastate=0)
        self.assertEqual(len(pkt), 14)
        self.assertEqual(len(pkt), struct.calcsize(SCRCPY_KEY_PACKET_FORMAT))

        unpacked = struct.unpack(SCRCPY_KEY_PACKET_FORMAT, pkt)
        self.assertEqual(unpacked[0], 0x00)  # type KEY
        self.assertEqual(unpacked[1], 0)     # action DOWN
        self.assertEqual(unpacked[2], 51)    # keycode
        self.assertEqual(unpacked[3], 0)     # repeat
        self.assertEqual(unpacked[4], 0)     # metastate

        restored = AndroidInputEvent.from_scrcpy_key_packet(pkt)
        self.assertEqual(restored.action, 0)
        self.assertEqual(restored.keycode, 51)


class TestMacroEngine(unittest.TestCase):
    """Tests action sequence recorder, JSON serialization, and variable-speed playback."""

    def setUp(self):
        self.engine = MacroEngine()

    def test_record_actions(self):
        self.engine.start_recording()
        self.assertTrue(self.engine.is_recording)

        self.engine.record_touch(action=0, x_norm=0.25, y_norm=0.75, pointer_id=1)
        time.sleep(0.02)
        self.engine.record_touch(action=2, x_norm=0.30, y_norm=0.70, pointer_id=1)
        time.sleep(0.02)
        self.engine.record_touch(action=1, x_norm=0.30, y_norm=0.70, pointer_id=1)
        self.engine.record_key(is_down=True, keycode=51)

        script = self.engine.stop_recording()
        self.assertFalse(self.engine.is_recording)
        self.assertEqual(len(script.steps), 4)
        self.assertEqual(script.steps[0].action, 0)
        self.assertEqual(script.steps[0].x_norm, 0.25)
        self.assertEqual(script.steps[1].action, 2)
        self.assertEqual(script.steps[2].action, 1)
        self.assertEqual(script.steps[3].action, 10)
        self.assertEqual(script.steps[3].keycode, 51)
        self.assertTrue(script.duration_ms >= 30)

    def test_json_roundtrip(self):
        steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.1, y_norm=0.2, pointer_id=1),
            MacroStep(timestamp_ms=50, action=2, x_norm=0.2, y_norm=0.3, pointer_id=1),
            MacroStep(timestamp_ms=100, action=1, x_norm=0.2, y_norm=0.3, pointer_id=1),
            MacroStep(timestamp_ms=150, action=10, keycode=62)
        ]
        script = MacroScript(name="TestRoundtrip", steps=steps, duration_ms=150)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name
        try:
            script.save_to_file(temp_path)
            loaded = MacroScript.load_from_file(temp_path)
            self.assertEqual(loaded.name, script.name)
            self.assertEqual(len(loaded.steps), 4)
            self.assertEqual(loaded.steps[1].timestamp_ms, 50)
            self.assertEqual(loaded.steps[3].keycode, 62)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_playback_repeat_and_speed(self):
        steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.5, y_norm=0.5),
            MacroStep(timestamp_ms=40, action=1, x_norm=0.5, y_norm=0.5)
        ]

        # Test at 2.0x speed with repeat_count=2
        t0 = time.perf_counter()
        self.engine.play(steps, repeat_count=2, speed=2.0, loop_delay_sec=0.02)

        # Wait until playback finishes
        timeout = time.perf_counter() + 2.0
        while self.engine.is_playing and time.perf_counter() < timeout:
            time.sleep(0.01)

        elapsed = time.perf_counter() - t0
        self.assertFalse(self.engine.is_playing)
        self.assertEqual(len(self.engine.dispatched_events), 4)  # 2 steps * 2 loops
        # Expected duration: 40ms / 2.0 = 20ms per iteration + 20ms delay ~ 60ms total
        self.assertTrue(elapsed < 0.5)

    def test_playback_stop_cancellation(self):
        # Long sequence or infinite loop
        steps = [
            MacroStep(timestamp_ms=0, action=0, x_norm=0.5, y_norm=0.5),
            MacroStep(timestamp_ms=1000, action=1, x_norm=0.5, y_norm=0.5)
        ]
        self.engine.play(steps, repeat_count=0, speed=1.0, loop_delay_sec=0.1)
        self.assertTrue(self.engine.is_playing)

        time.sleep(0.05)
        t_stop_start = time.perf_counter()
        self.engine.stop()
        stop_duration = time.perf_counter() - t_stop_start

        self.assertFalse(self.engine.is_playing)
        self.assertTrue(stop_duration < 0.2)  # Stopped promptly


if __name__ == "__main__":
    unittest.main()

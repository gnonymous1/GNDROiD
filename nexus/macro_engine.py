"""
nexus/macro_engine.py
=====================
Sub-millisecond Action Recorder & Auto-Click Macro Engine.

Features:
- Action sequence recorder for touch (down, up, move) and key events
- Millisecond timestamps from recording start (MacroStep)
- Variable-speed playback (0.5x to 5.0x) with precise timing adjustment
- Automated repeat loops (infinite or N iterations) with configurable loop delay
- Threaded playback worker with responsive stop/cancellation
- JSON script serialization/loading (roundtrip compatibility)
- Interface contracts compliant with PROJECT.md and Milestone M4 specifications
"""

import os
import json
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Union, Dict, Any, Callable


@dataclass
class MacroStep:
    """Represents an individual recorded touch, key, or delay action."""
    timestamp_ms: int       # Milliseconds elapsed from recording start
    action: int             # 0=DOWN, 1=UP, 2=MOVE; 10=KEY_DOWN, 11=KEY_UP
    pointer_id: int = 0
    x_norm: float = 0.0     # Normalized coordinate 0.0 .. 1.0
    y_norm: float = 0.0     # Normalized coordinate 0.0 .. 1.0
    keycode: int = 0        # Android keycode if key event
    pressure: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MacroStep":
        return cls(
            timestamp_ms=int(data.get("timestamp_ms", 0)),
            action=int(data.get("action", 0)),
            pointer_id=int(data.get("pointer_id", 0)),
            x_norm=float(data.get("x_norm", 0.0)),
            y_norm=float(data.get("y_norm", 0.0)),
            keycode=int(data.get("keycode", 0)),
            pressure=float(data.get("pressure", 1.0))
        )


@dataclass
class MacroScript:
    """Container for recorded macro steps with metadata and serialization."""
    name: str = "Macro Script"
    steps: List[MacroStep] = field(default_factory=list)
    duration_ms: int = 0
    created_at: float = field(default_factory=time.time)

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __getitem__(self, index):
        return self.steps[index]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MacroScript":
        raw_steps = data.get("steps", [])
        steps = [MacroStep.from_dict(s) if isinstance(s, dict) else s for s in raw_steps]
        return cls(
            name=data.get("name", "Macro Script"),
            duration_ms=int(data.get("duration_ms", 0)),
            created_at=float(data.get("created_at", time.time())),
            steps=steps
        )

    def save_to_file(self, path: str):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "MacroScript":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            # Backward compatibility for direct list format
            steps = [MacroStep.from_dict(d) for d in data]
            dur = steps[-1].timestamp_ms if steps else 0
            return cls(name=os.path.basename(path), steps=steps, duration_ms=dur)
        return cls.from_dict(data)


class MacroEngine:
    """
    Action Sequence Recorder and Variable-Speed Playback Engine.
    Records touch and key sequences; replays with configurable speed, loops, and intervals.
    """
    def __init__(
        self,
        serial: str = "emulator-5554",
        packet_sender: Any = None,
        master_dims: tuple = (1440, 3120)
    ):
        self.serial = serial
        self.sender = packet_sender
        self.master_w, self.master_h = master_dims

        self.is_recording: bool = False
        self.is_playing: bool = False
        self.recorded_steps: List[MacroStep] = []
        self._record_start_t: float = 0.0

        self._play_thread: Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()
        self.event_dispatch_callback: Optional[Callable[[MacroStep], None]] = None
        self.dispatched_events: List[MacroStep] = []  # History of played events for audit/testing

    # =========================================================================
    # Recording
    # =========================================================================

    def start_recording(self):
        """Starts a new recording session, clearing previously recorded steps."""
        self.recorded_steps.clear()
        self._record_start_t = time.perf_counter()
        self.is_recording = True

    def stop_recording(self) -> MacroScript:
        """Stops recording and returns the compiled MacroScript."""
        self.is_recording = False
        elapsed_ms = int((time.perf_counter() - self._record_start_t) * 1000)
        script = MacroScript(
            name=f"Macro_{int(time.time())}",
            steps=list(self.recorded_steps),
            duration_ms=elapsed_ms
        )
        return script

    def record_touch(self, action: int, x_norm: float, y_norm: float, pointer_id: int = 0):
        """
        Records a touch event (action: 0=DOWN, 1=UP, 2=MOVE) with normalized coords (0.0..1.0).
        """
        if not self.is_recording:
            return
        elapsed = int((time.perf_counter() - self._record_start_t) * 1000)
        step = MacroStep(
            timestamp_ms=elapsed,
            action=action,
            pointer_id=pointer_id,
            x_norm=max(0.0, min(1.0, float(x_norm))),
            y_norm=max(0.0, min(1.0, float(y_norm)))
        )
        self.recorded_steps.append(step)

    def record_key(self, is_down: bool, keycode: int):
        """Records a key event (is_down: True for DOWN, False for UP) with Android keycode."""
        if not self.is_recording:
            return
        elapsed = int((time.perf_counter() - self._record_start_t) * 1000)
        action = 10 if is_down else 11
        step = MacroStep(
            timestamp_ms=elapsed,
            action=action,
            pointer_id=0,
            x_norm=0.0,
            y_norm=0.0,
            keycode=int(keycode)
        )
        self.recorded_steps.append(step)

    # =========================================================================
    # Playback & Timing
    # =========================================================================

    def play_macro(
        self,
        serial: str,
        script: Union[MacroScript, List[MacroStep]],
        speed: float = 1.0,
        loop_count: int = 1
    ):
        """
        Plays a MacroScript or list of MacroSteps on the specified serial target.
        Interface contract specified in PROJECT.md.
        """
        self.serial = serial
        steps = script.steps if isinstance(script, MacroScript) else list(script)
        self.play(steps, repeat_count=loop_count, speed=speed, loop_delay_sec=0.1)

    def play(
        self,
        steps: List[MacroStep],
        repeat_count: int = 1,
        speed: float = 1.0,
        loop_delay_sec: float = 0.5
    ):
        """
        Starts threaded background playback.
        repeat_count: 0 for infinite loop until stop(), or positive integer.
        speed: 0.5x to 5.0x speed multiplier.
        """
        if self.is_playing:
            self.stop()

        self._stop_event.clear()
        self.dispatched_events.clear()
        clamped_speed = max(0.1, min(10.0, speed))

        self._play_thread = threading.Thread(
            target=self._playback_worker,
            args=(list(steps), repeat_count, clamped_speed, loop_delay_sec),
            daemon=True
        )
        self._play_thread.start()

    def stop(self):
        """Requests immediate cancellation and waits for playback thread termination."""
        self._stop_event.set()
        self.is_playing = False
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=1.0)
            self._play_thread = None

    def _playback_worker(
        self,
        steps: List[MacroStep],
        repeat_count: int,
        speed: float,
        loop_delay: float
    ):
        """Background thread executing scheduled steps with variable speed scaling."""
        self.is_playing = True
        iterations = 0

        try:
            while not self._stop_event.is_set() and (repeat_count == 0 or iterations < repeat_count):
                if not steps:
                    break

                t_base = time.perf_counter()
                for step in steps:
                    if self._stop_event.is_set():
                        break

                    # Scheduled target time in seconds
                    target_time = (step.timestamp_ms / 1000.0) / speed
                    now_elapsed = time.perf_counter() - t_base
                    sleep_dur = target_time - now_elapsed

                    if sleep_dur > 0.001:
                        # Chunked sleep allowing responsive stop()
                        end_sleep = time.perf_counter() + sleep_dur
                        while time.perf_counter() < end_sleep:
                            if self._stop_event.is_set():
                                break
                            time.sleep(min(0.005, max(0.0, end_sleep - time.perf_counter())))

                    if self._stop_event.is_set():
                        break

                    # Dispatch event
                    self._dispatch_step(step)

                iterations += 1
                if not self._stop_event.is_set() and (repeat_count == 0 or iterations < repeat_count):
                    # Inter-loop delay
                    end_loop_sleep = time.perf_counter() + loop_delay
                    while time.perf_counter() < end_loop_sleep:
                        if self._stop_event.is_set():
                            break
                        time.sleep(min(0.01, max(0.0, end_loop_sleep - time.perf_counter())))
        finally:
            self.is_playing = False

    def _dispatch_step(self, step: MacroStep):
        """Translates and broadcasts a single macro step to receiver."""
        self.dispatched_events.append(step)

        if self.event_dispatch_callback:
            try:
                self.event_dispatch_callback(step)
            except Exception:
                pass

        if not self.sender:
            return

        w = getattr(self.sender, "master_w", self.master_w)
        h = getattr(self.sender, "master_h", self.master_h)

        if step.action in (0, 1, 2):  # Touch event
            px = int(step.x_norm * w)
            py = int(step.y_norm * h)
            if hasattr(self.sender, "broadcast_touch"):
                self.sender.broadcast_touch(
                    action=step.action,
                    master_x=px,
                    master_y=py,
                    pointer_id=step.pointer_id
                )
        elif step.action in (10, 11):  # Key event
            key_action = 0 if step.action == 10 else 1
            if hasattr(self.sender, "broadcast_key"):
                self.sender.broadcast_key(
                    action=key_action,
                    keycode=step.keycode
                )

    # =========================================================================
    # Serialization
    # =========================================================================

    def save_to_file(self, file_path: str):
        """Serializes recorded steps to JSON file."""
        script = MacroScript(
            name=os.path.basename(file_path),
            steps=list(self.recorded_steps),
            duration_ms=self.recorded_steps[-1].timestamp_ms if self.recorded_steps else 0
        )
        script.save_to_file(file_path)

    def load_from_file(self, file_path: str) -> MacroScript:
        """Loads macro steps from JSON file."""
        script = MacroScript.load_from_file(file_path)
        self.recorded_steps = list(script.steps)
        return script

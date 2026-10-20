"""Time-based animation state. Geometry is calculated by the renderer."""
from dataclasses import replace
from math import isfinite
from src.engine.state import Action, GameState
from src.gui.contracts import MotionFrame


class RollAnimation:
    def __init__(self, duration_sec: float = 0.2):
        if not isfinite(duration_sec) or duration_sec <= 0:
            raise ValueError("Animation duration must be positive and finite.")
        self.duration_sec = duration_sec
        self.reset()

    def start(self, before: GameState, after: GameState, action: Action,
              falling: bool = False, sinking: bool = False) -> None:
        """falling=True: `after` is the illegal pose; the renderer drops the block.
        sinking=True: the block stands on the goal and sinks into the hole."""
        if self.busy:
            raise RuntimeError("An animation is already running.")
        self.frame = MotionFrame(before, after, action, 0.0, falling, sinking)
        self.busy = True

    def update(self, dt: float) -> None:
        if not isfinite(dt) or dt < 0:
            raise ValueError("dt must be nonnegative and finite.")
        if self.frame is None:
            return
        progress = self.frame.progress + dt / self.duration_sec
        if progress >= 1.0 - 1e-9:
            self.reset()
        else:
            self.frame = replace(self.frame, progress=progress)

    def reset(self) -> None:
        self.busy = False
        self.frame: MotionFrame | None = None

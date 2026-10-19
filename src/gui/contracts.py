"""Stable contracts between the GUI and the search/benchmark layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol, Sequence

from src.engine.loader import StageData
from src.engine.state import Action, GameState

if TYPE_CHECKING:
    from pygame import Surface


class SolverStatus(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    SOLVED = "SOLVED"
    NO_SOLUTION = "NO_SOLUTION"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class ReplayStatus(Enum):
    EMPTY = "EMPTY"
    READY = "READY"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


@dataclass(frozen=True)
class SolverMetrics:
    time_sec: float = 0.0
    peak_memory_mb: float = 0.0
    expanded_nodes: int = 0
    solution_length: int = 0
    total_cost: float = 0.0


@dataclass(frozen=True)
class SolverResultView:
    """Presentation shape independent of the P3/P4 solver implementation."""

    algorithm: str
    found: bool
    path: tuple[Action, ...] = ()
    metrics: SolverMetrics = field(default_factory=SolverMetrics)
    error: str | None = None


@dataclass(frozen=True)
class SolverRequest:
    request_id: int
    algorithm: str
    stage: StageData
    initial_state: GameState
    timeout_sec: float = 30.0


@dataclass(frozen=True)
class SolverResponse:
    request_id: int
    status: SolverStatus
    result: SolverResultView


@dataclass(frozen=True)
class MotionFrame:
    before: GameState
    after: GameState
    action: Action
    progress: float  # Normalized animation progress in [0, 1].


class SolverGateway(Protocol):
    """Nonblocking worker adapter. App polls results on the main thread."""

    def submit(self, request: SolverRequest) -> None:
        """Start one job; reject a new job while the worker is busy."""
        ...

    def poll(self) -> SolverResponse | None:
        """Consume one completed response, or return None without waiting."""
        ...

    def cancel(self, request_id: int) -> None:
        """Request cancellation without blocking; unknown IDs are a no-op."""
        ...

    def close(self) -> None:
        """Release worker resources when the app exits."""
        ...


class ReplayController(Protocol):
    status: ReplayStatus
    initial_state: GameState | None
    index: int  # Number of actions already issued.
    length: int

    def load(self, initial_state: GameState, path: Sequence[Action]) -> None:
        """Copy path; reset index to zero. Empty paths are FINISHED."""
        ...

    def play(self) -> None:
        ...

    def pause(self) -> None:
        ...

    def step(self) -> Action | None:
        """Issue one action and advance index; never modify the game session.

        Allowed in READY, PLAYING or PAUSED; preserve playback mode until
        the final action is issued, then mark FINISHED. Otherwise return None.
        App calls only when animation is idle and owns playback timing.
        """
        ...

    def reset(self) -> None:
        """Clear path and initial state, reset index, and become EMPTY."""
        ...


class BoardRenderer(Protocol):
    def set_stage(self, stage: StageData) -> None:
        ...

    def resize(self, size: tuple[int, int]) -> None:
        """Fit camera to the board surface size in pixels."""
        ...

    def draw(
        self, surface: Surface, state: GameState,
        motion: MotionFrame | None = None,
    ) -> None:
        """Draw only on the dedicated board surface; never mutate state."""
        ...


class AnimationController(Protocol):
    busy: bool
    frame: MotionFrame | None

    def start(self, before: GameState, after: GameState, action: Action) -> None:
        """Start an engine-accepted transition while idle."""
        ...

    def update(self, dt: float) -> None:
        """Advance by seconds; on completion set busy=False and frame=None."""
        ...

    def reset(self) -> None:
        """Immediately clear frame and busy state."""
        ...

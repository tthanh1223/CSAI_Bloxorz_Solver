"""Các hợp đồng ổn định giữa GUI và lớp search/benchmark."""

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
    """Dạng dữ liệu để hiển thị, độc lập với cài đặt solver của P3/P4."""

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
    progress: float  # Tiến độ animation đã chuẩn hoá trong [0, 1].
    # True: `after` là tư thế không hợp lệ mà khối lăn vào trước khi rơi
    # khỏi bàn (engine không bao giờ chấp nhận). Giá trị mặc định giữ cho code gọi cũ vẫn đúng.
    falling: bool = False
    # True: khối (đứng trên ô đích, before == after) chìm vào lỗ.
    sinking: bool = False


class SolverGateway(Protocol):
    """Adapter worker không chặn. App lấy kết quả (poll) trên luồng chính."""

    def submit(self, request: SolverRequest) -> None:
        """Bắt đầu một việc; từ chối việc mới khi worker đang bận."""
        ...

    def poll(self) -> SolverResponse | None:
        """Lấy một kết quả đã xong, hoặc trả về None mà không chờ."""
        ...

    def cancel(self, request_id: int) -> None:
        """Yêu cầu huỷ mà không chặn; ID không biết thì bỏ qua."""
        ...

    def close(self) -> None:
        """Giải phóng tài nguyên worker khi app thoát."""
        ...


class ReplayController(Protocol):
    status: ReplayStatus
    initial_state: GameState | None
    index: int  # Số action đã phát ra.
    length: int

    def load(self, initial_state: GameState, path: Sequence[Action]) -> None:
        """Sao chép đường đi; đặt index về 0. Đường đi rỗng thì là FINISHED."""
        ...

    def play(self) -> None:
        ...

    def pause(self) -> None:
        ...

    def step(self) -> Action | None:
        """Phát một action và tăng index; không bao giờ sửa session của game.

        Được phép ở READY, PLAYING hoặc PAUSED; giữ nguyên chế độ phát cho tới
        khi phát action cuối, rồi đánh dấu FINISHED. Các trường hợp khác trả về None.
        App chỉ gọi khi animation rảnh và tự quản lý nhịp phát.
        """
        ...

    def reset(self) -> None:
        """Xoá đường đi và state ban đầu, đặt lại index, và chuyển sang EMPTY."""
        ...


class BoardRenderer(Protocol):
    def set_stage(self, stage: StageData) -> None:
        ...

    def resize(self, size: tuple[int, int]) -> None:
        """Căn camera theo kích thước surface của bàn chơi (pixel)."""
        ...

    def draw(
        self, surface: Surface, state: GameState,
        motion: MotionFrame | None = None,
        intro_t: float | None = None,
        outro_t: float | None = None,
        shockwave: tuple[float, float, float] | None = None,
        bridges: tuple[tuple[bool, ...], tuple[bool, ...], float] | None = None,
        clear: bool = True,
    ) -> None:
        """Chỉ vẽ lên surface riêng của bàn chơi; không bao giờ sửa state."""
        ...


class AnimationController(Protocol):
    busy: bool
    frame: MotionFrame | None

    def start(self, before: GameState, after: GameState, action: Action,
              falling: bool = False, sinking: bool = False) -> None:
        """Bắt đầu một chuyển trạng thái đã được engine chấp nhận, khi đang rảnh."""
        ...

    def update(self, dt: float) -> None:
        """Tiến thêm dt giây; khi xong đặt busy=False và frame=None."""
        ...

    def reset(self) -> None:
        """Xoá ngay frame và trạng thái bận."""
        ...

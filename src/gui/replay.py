"""Con trỏ phát lại; luật chơi và nhịp thời gian thuộc về app."""
from collections.abc import Sequence
from src.engine.state import Action, GameState
from src.gui.contracts import ReplayStatus


class PathReplay:
    def __init__(self):
        self.reset()

    @property
    def length(self) -> int:
        return len(self.path)

    def load(self, initial_state: GameState, path: Sequence[Action]) -> None:
        copied = tuple(path)
        if any(not isinstance(action, Action) for action in copied):
            raise ValueError("Replay path must contain Action values.")
        self.initial_state = initial_state
        self.path = copied
        self.index = 0
        self.status = ReplayStatus.READY if copied else ReplayStatus.FINISHED

    def play(self) -> None:
        if self.status in (ReplayStatus.READY, ReplayStatus.PAUSED):
            self.status = ReplayStatus.PLAYING

    def pause(self) -> None:
        if self.status == ReplayStatus.PLAYING:
            self.status = ReplayStatus.PAUSED

    def step(self) -> Action | None:
        if self.status not in (ReplayStatus.READY, ReplayStatus.PLAYING, ReplayStatus.PAUSED):
            return None
        action = self.path[self.index]
        self.index += 1
        if self.index == self.length:
            self.status = ReplayStatus.FINISHED
        return action

    def reset(self) -> None:
        self.initial_state: GameState | None = None
        self.path: tuple[Action, ...] = ()
        self.index = 0
        self.status = ReplayStatus.EMPTY

from typing import List, Tuple

from src.contract import Coord, SearchProblem, State
from src.engine.loader import StageData
from src.engine.switches import apply_tile_effects


class BloxorzProblem(SearchProblem):
    def __init__(self, stage_data: StageData):
        self.stage_data = stage_data

    def initial_state(self) -> State:
        return State(
            blocks=(self.stage_data.start_coord,),
            is_split=False,
            bridge_mask=self.stage_data.initial_bridge_mask,
        )

    def is_goal(self, state: State) -> bool:
        return not state.is_split and state.blocks == (self.stage_data.goal_coord,)

    def get_goal_coord(self) -> Coord:
        return self.stage_data.goal_coord

    def get_successors(self, state: State) -> List[Tuple[str, State, float]]:
        # TODO: calculate legal block rolls, validate tiles, apply effects, and emit successors.
        return []


class GameSession:
    """Manage the state of a manually played game for the UI."""

    def __init__(self, problem: BloxorzProblem):
        self.problem = problem
        self.current_state = problem.initial_state()
        self.history: List[State] = []
        self.status = "PLAYING"
        self.active_cube_idx = 0

    def move(self, direction: str) -> bool:
        """Try a move, saving history and updating the current state if legal."""
        raise NotImplementedError

    def switch_cube(self) -> None:
        self.active_cube_idx = 1 - self.active_cube_idx

    def undo(self) -> None:
        raise NotImplementedError

    def restart(self) -> None:
        raise NotImplementedError

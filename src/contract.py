from dataclasses import dataclass
from typing import List, Protocol, Tuple

from src.engine.state import Coord, GameState, State


@dataclass
class SolverResult:
    found: bool
    path: List[str]
    solution_length: int
    total_cost: float
    expanded_nodes: int
    time_sec: float
    peak_memory_mb: float


class SearchProblem(Protocol):
    def initial_state(self) -> State: ...

    def is_goal(self, state: State) -> bool: ...

    def get_goal_coord(self) -> Coord: ...

    def get_successors(self, state: State) -> List[Tuple[str, State, float]]: ...


class SearchSolver(Protocol):
    def solve(self, problem: SearchProblem) -> SolverResult: ...

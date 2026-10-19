from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple, Any

State = Any  
@dataclass
class SolverResult:
    found: bool
    path: List[str]
    solution_length: int
    total_cost: float
    expanded_nodes: int
    time_sec: float
    peak_memory_mb: float

class SearchProblem(ABC):
    @property
    @abstractmethod
    def initial_state(self) -> State:
        ...

    @abstractmethod
    def is_goal(self, state: State) -> bool:
        ...

    @abstractmethod
    def get_successors(self, state: State) -> List[Tuple[Any, State, int]]:
        ...


class SearchSolver(ABC):
    @abstractmethod
    def solve(self, problem: SearchProblem) -> SolverResult:
        ...
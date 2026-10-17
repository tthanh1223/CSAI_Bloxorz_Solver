from src.contract import SearchProblem, SearchSolver, SolverResult, State
from src.solvers.profiler import run_with_profiler


def heuristic_manhattan(state: State, problem: SearchProblem) -> float:
    # TODO: implement a heuristic for the current block configuration.
    return 0.0


class AStar(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _astar():
            # TODO: implement A* using f = g + h.
            return False, [], 0, 0.0

        return run_with_profiler(_astar)

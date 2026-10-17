from src.contract import SearchProblem, SearchSolver, SolverResult
from src.solvers.profiler import run_with_profiler


class BFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _bfs():
            # TODO: implement breadth-first search.
            return False, [], 0, 0.0

        return run_with_profiler(_bfs)


class DFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _dfs():
            # TODO: implement depth-first search.
            return False, [], 0, 0.0

        return run_with_profiler(_dfs)


class UCS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _ucs():
            # TODO: implement uniform-cost search.
            return False, [], 0, 0.0

        return run_with_profiler(_ucs)

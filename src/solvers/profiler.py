import time
import tracemalloc
from typing import Callable, List, Tuple

from src.contract import SolverResult


def run_with_profiler(
    solve_func: Callable[[], Tuple[bool, List[str], int, float]],
) -> SolverResult:
    """Run a solver callback and collect elapsed time and peak memory."""
    tracemalloc.start()
    start_time = time.perf_counter()
    found, path, expanded_nodes, total_cost = solve_func()
    end_time = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return SolverResult(
        found=found,
        path=path,
        solution_length=len(path),
        total_cost=total_cost,
        expanded_nodes=expanded_nodes,
        time_sec=end_time - start_time,
        peak_memory_mb=peak / (1024 * 1024),
    )

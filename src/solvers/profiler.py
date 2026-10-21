import time
import tracemalloc
from typing import Callable, List, Tuple

from src.contract import SolverResult


def run_with_profiler(
    solve_func: Callable[[], Tuple[bool, List[str], int, float]],
) -> SolverResult:
    """Run a solver callback and collect elapsed time and peak memory.

    The search runs twice:
      1) timed run, WITHOUT tracemalloc: tracemalloc records every allocation and
         makes Python search code about 4-5x slower, which would inflate the time;
      2) memory run, WITH tracemalloc, to measure the peak memory.
    The search is deterministic, so both runs expand exactly the same nodes.
    Path, expanded nodes and cost come from the timed run.
    """
    start_time = time.perf_counter()
    found, path, expanded_nodes, total_cost = solve_func()
    elapsed = time.perf_counter() - start_time

    tracemalloc.start()
    try:
        solve_func()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    return SolverResult(
        found=found,
        path=path,
        solution_length=len(path),
        total_cost=total_cost,
        expanded_nodes=expanded_nodes,
        time_sec=elapsed,
        peak_memory_mb=peak / (1024 * 1024),
    )

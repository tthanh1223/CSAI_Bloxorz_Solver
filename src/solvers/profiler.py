import time
import tracemalloc
from typing import Callable, List, Tuple

from src.contract import SolverResult


def run_with_profiler(
    solve_func: Callable[[], Tuple[bool, List[str], int, float]],
) -> SolverResult:
    """Chạy hàm solver và đo thời gian chạy cùng bộ nhớ đỉnh.

    Việc tìm kiếm chạy hai lần:
      1) lần đo thời gian, KHÔNG bật tracemalloc: tracemalloc ghi lại mọi lần cấp phát
         và làm code tìm kiếm Python chậm khoảng 4-5 lần, sẽ làm thời gian bị phóng đại;
      2) lần đo bộ nhớ, CÓ bật tracemalloc, để lấy bộ nhớ đỉnh.
    Việc tìm kiếm là tất định, nên hai lần mở rộng đúng cùng các nút.
    Đường đi, số nút mở rộng và chi phí lấy từ lần đo thời gian.
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

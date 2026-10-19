"""Chạy thực nghiệm (benchmark) cho 4 solver và xuất CSV + biểu đồ.

Cách chạy (từ thư mục gốc của project):
    python -m src.solvers.benchmark                    # chạy toàn bộ bộ test
    python -m src.solvers.benchmark --time-limit 30    # giới hạn 30 giây mỗi lần chạy
    python -m src.solvers.benchmark --plot-only        # chỉ vẽ lại biểu đồ từ CSV có sẵn

Kết quả nằm trong thư mục data/:
    data/benchmark_results.csv
    data/chart_time.png, chart_memory.png, chart_expanded.png, chart_length.png
"""
from __future__ import annotations

import argparse
import csv
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
LEVELS_DIR = ROOT / "levels"
DATA_DIR = ROOT / "data"

# ----------------------------------------------------------------------------
# BỘ TEST CỐ ĐỊNH, chia nhóm theo độ khó tăng dần (giống nhau cho mọi thuật toán)
# ----------------------------------------------------------------------------
TEST_SUITE: Dict[str, List[str]] = {
    "G1 - Basic": ["stage_01", "stage_03", "stage_06"],
    "G2 - Fragile": ["stage_04", "stage_13"],
    "G3 - Switches & Bridges": ["stage_02", "stage_07", "stage_05", "stage_11"],
    "G4 - Split block": ["stage_08", "stage_09", "stage_16"],
    "G5 - Combined": ["stage_27", "stage_30", "stage_28"],
}

SOLVER_NAMES = ["BFS", "DFS (IDS)", "UCS", "A*"]

CSV_COLUMNS = [
    "group", "stage", "algorithm", "status",
    "time_sec", "peak_memory_mb", "expanded_nodes",
    "solution_length", "total_cost",
]


def _make_solver(name: str):
    """Tạo object solver theo tên (Strategy pattern: cùng hàm solve())."""
    from src.solvers.astar import AStar
    from src.solvers.uninformed import BFS, DFS, UCS

    return {"BFS": BFS, "DFS (IDS)": DFS, "UCS": UCS, "A*": AStar}[name]()


def _make_problem(stage_name: str):
    from src.engine.loader import load_stage
    from src.engine.problem import BloxorzProblem
    from src.engine.state import GameState, Orientation

    stage = load_stage(str(LEVELS_DIR / f"{stage_name}.json"))
    start = GameState(
        pos1=stage.start,
        pos2=stage.start,
        orientation=Orientation.STANDING,
        active_cube=0,
        bridges_status=stage.initial_bridge_mask,
    )
    return BloxorzProblem(stage, start)


def _worker(stage_name: str, solver_name: str, queue) -> None:
    """Chạy 1 solver trên 1 màn trong một process riêng.

    Chạy trong process riêng để: (1) dừng được khi quá thời gian,
    (2) đo bộ nhớ của mỗi lần chạy độc lập, không bị lần chạy trước ảnh hưởng.
    """
    result = _make_solver(solver_name).solve(_make_problem(stage_name))
    queue.put({
        "status": "solved" if result.found else "no_solution",
        "time_sec": result.time_sec,
        "peak_memory_mb": result.peak_memory_mb,
        "expanded_nodes": result.expanded_nodes,
        "solution_length": result.solution_length,
        "total_cost": result.total_cost,
    })


def run_one(stage_name: str, solver_name: str, time_limit: float) -> dict:
    """Chạy 1 lần, trả về 1 dòng kết quả. Quá time_limit giây thì ghi 'timeout'."""
    ctx = mp.get_context("spawn")  # giống nhau trên macOS, Windows và Linux
    queue = ctx.Queue()
    process = ctx.Process(target=_worker, args=(stage_name, solver_name, queue))
    process.start()
    process.join(time_limit)

    if process.is_alive():
        process.terminate()
        process.join()
        return {"status": "timeout"}
    if queue.empty():
        return {"status": "error"}
    return queue.get()


def run_benchmarks(time_limit: float = 60.0, output_csv: Path | None = None) -> Path:
    """Chạy mọi (màn, thuật toán) trong TEST_SUITE và ghi ra CSV."""
    output_csv = output_csv or DATA_DIR / "benchmark_results.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for group, stages in TEST_SUITE.items():
        for stage_name in stages:
            for solver_name in SOLVER_NAMES:
                row = {"group": group, "stage": stage_name, "algorithm": solver_name}
                row.update(run_one(stage_name, solver_name, time_limit))
                rows.append(row)
                print(_format_row(row), flush=True)

    with open(output_csv, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nĐã ghi kết quả vào {output_csv}")
    return output_csv


def _format_row(row: dict) -> str:
    head = f"{row['stage']:9} {row['algorithm']:10}"
    if row["status"] != "solved":
        return f"{head} {row['status'].upper()}"
    return (
        f"{head} time={row['time_sec']:8.3f}s  mem={row['peak_memory_mb']:7.2f}MB  "
        f"expanded={row['expanded_nodes']:8}  length={row['solution_length']:4}  "
        f"cost={row['total_cost']:6.1f}"
    )


# ----------------------------------------------------------------------------
# VẼ BIỂU ĐỒ
# ----------------------------------------------------------------------------
# Bảng màu 4 thuật toán: thứ tự cố định, đã kiểm tra an toàn cho người mù màu.
COLORS = {"BFS": "#2a78d6", "DFS (IDS)": "#eb6834", "UCS": "#1baf7a", "A*": "#eda100"}

METRICS = [
    # (cột trong CSV, tiêu đề, nhãn trục y, tên file, dùng thang log?)
    ("time_sec", "Search time", "Seconds (log scale)", "chart_time.png", True),
    ("peak_memory_mb", "Peak memory", "MB (log scale)", "chart_memory.png", True),
    ("expanded_nodes", "Expanded nodes", "Nodes (log scale)", "chart_expanded.png", True),
    ("solution_length", "Solution length", "Moves", "chart_length.png", False),
]


def plot_results(csv_path: Path | None = None) -> List[Path]:
    """Vẽ 4 biểu đồ cột nhóm: mỗi màn là một nhóm, mỗi thuật toán là một cột."""
    import matplotlib

    matplotlib.use("Agg")  # vẽ ra file, không cần mở cửa sổ
    import matplotlib.pyplot as plt

    csv_path = csv_path or DATA_DIR / "benchmark_results.csv"
    with open(csv_path, encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    stages = list(dict.fromkeys(row["stage"] for row in rows))
    lookup = {(row["stage"], row["algorithm"]): row for row in rows}
    width = 0.8 / len(SOLVER_NAMES)
    saved = []

    for column, title, ylabel, filename, log_scale in METRICS:
        fig, ax = plt.subplots(figsize=(13, 4.8))
        for i, algo in enumerate(SOLVER_NAMES):
            xs, ys, missing = [], [], []
            for x, stage in enumerate(stages):
                row = lookup.get((stage, algo))
                x_pos = x - 0.4 + width * (i + 0.5)
                if row and row["status"] == "solved":
                    xs.append(x_pos)
                    ys.append(max(float(row[column]), 1e-4) if log_scale else float(row[column]))
                else:
                    missing.append(x_pos)
            ax.bar(xs, ys, width=width * 0.9, color=COLORS[algo], label=algo,
                   edgecolor="white", linewidth=1)
            for x_pos in missing:  # thuật toán bị timeout: ghi chữ thay vì cột
                ax.text(x_pos, 0.02, "timeout", transform=ax.get_xaxis_transform(),
                        rotation=90, ha="center", va="bottom", fontsize=7, color="#555555")

        ax.set_title(title, loc="left", fontsize=13, color="#1f1f1e")
        ax.set_ylabel(ylabel, color="#555555")
        ax.set_xticks(range(len(stages)))
        ax.set_xticklabels([s.replace("stage_", "Stage ") for s in stages], rotation=30, ha="right")
        if log_scale:
            ax.set_yscale("log")
        ax.grid(axis="y", color="#e6e6e3", linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#bbbbb5")
        ax.legend(ncol=4, frameon=False, loc="upper left", bbox_to_anchor=(0, -0.22))
        fig.tight_layout()

        path = csv_path.parent / filename
        fig.savefig(path, dpi=150)
        plt.close(fig)
        saved.append(path)
        print(f"Đã lưu biểu đồ {path}")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark các solver Bloxorz")
    parser.add_argument("--time-limit", type=float, default=60.0,
                        help="số giây tối đa cho mỗi lần chạy (mặc định 60)")
    parser.add_argument("--plot-only", action="store_true",
                        help="chỉ vẽ lại biểu đồ từ data/benchmark_results.csv")
    args = parser.parse_args()

    if not args.plot_only:
        run_benchmarks(time_limit=args.time_limit)
    plot_results()


if __name__ == "__main__":
    main()
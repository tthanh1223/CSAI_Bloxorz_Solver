from pathlib import Path

import pytest

from src.engine.loader import StageData, TileType, initial_state, load_stage
from src.engine.problem import BloxorzProblem
from src.engine.state import GameState, Orientation
from src.solvers.astar import AStar
from src.solvers.uninformed import BFS, DFS, UCS

LEVELS = Path(__file__).resolve().parents[1] / 'levels'


def problem_for(name):
    stage = load_stage(str(LEVELS / f'{name}.json'))
    return BloxorzProblem(stage, initial_state(stage))


@pytest.mark.parametrize('name', ['stage_01', 'stage_02', 'stage_04', 'stage_08'])
def test_bfs_and_astar_find_the_same_shortest_length(name):
    problem = problem_for(name)
    bfs, astar = BFS().solve(problem), AStar().solve(problem)
    assert bfs.found and astar.found
    assert bfs.solution_length == astar.solution_length
    assert astar.expanded_nodes <= bfs.expanded_nodes
    assert bfs.time_sec >= 0 and bfs.peak_memory_mb > 0


def test_ids_and_ucs_solutions_reach_the_goal():
    problem = problem_for('stage_01')
    for solver in (DFS(), UCS()):
        result = solver.solve(problem)
        state = problem.initial_state
        for name in result.path:
            state = {a.value: s for a, s, _ in problem.get_successors(state)}[name]
        assert problem.is_goal(state)


def test_unsolvable_stage_returns_not_found():
    # Xuất phát và đích nằm trên hai đảo không có đường nối.
    stage = StageData()
    stage.grid = [[TileType.FLOOR] * 3 + [TileType.VOID] * 3 + [TileType.FLOOR] * 3 for _ in range(3)]
    stage.start, stage.goal = (1, 1), (1, 7)
    problem = BloxorzProblem(stage, GameState((1, 1), (1, 1), Orientation.STANDING, 0, ()))
    for solver in (BFS(), DFS(), UCS(), AStar()):
        result = solver.solve(problem)  # Trước đây IDS lặp vô hạn ở đây
        assert not result.found and result.path == [] and result.expanded_nodes > 0

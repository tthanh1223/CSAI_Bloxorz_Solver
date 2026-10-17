from src.engine.loader import StageData
from src.engine.problem import BloxorzProblem
from src.engine.state import GameState, Orientation


def _make_problem():
    stage = StageData()
    stage.goal = (5, 5)
    initial_state = GameState((0, 0), (0, 0), Orientation.STANDING, 0, ())
    return BloxorzProblem(stage, initial_state)

def test_is_goal_win_condition():
    problem = _make_problem()
    win_state = GameState((5, 5), (5, 5), Orientation.STANDING, 0, ())

    assert problem.is_goal(win_state) is True

def test_is_goal_lose_conditions():
    problem = _make_problem()
    lying_state = GameState((5, 5), (5, 6), Orientation.LYING_H, 0, ())
    split_state = GameState((5, 5), (2, 2), Orientation.SPLIT, 0, ())

    assert problem.is_goal(lying_state) is False
    assert problem.is_goal(split_state) is False

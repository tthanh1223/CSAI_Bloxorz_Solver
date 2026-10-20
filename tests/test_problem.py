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


def _stage_01():
    from pathlib import Path
    from src.engine.loader import load_stage
    stage = load_stage(str(Path(__file__).resolve().parents[1] / 'levels' / 'stage_01.json'))
    return stage, GameState(stage.start, stage.start, Orientation.STANDING, 0, stage.initial_bridge_mask)


def test_fall_result_only_for_rejected_rolls():
    from src.engine.state import Action
    stage, start = _stage_01()
    problem = BloxorzProblem(stage, start)
    legal = {action for action, _, _ in problem.get_successors(start)}
    for action in (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT):
        fallen = problem.fall_result(start, action)
        if action in legal:
            assert fallen is None
        else:
            assert fallen == problem.roll_block(start, action)
    assert problem.fall_result(start, Action.SPACE) is None


def test_session_fall_sets_lost_and_keeps_state():
    from src.engine.problem import GameSession
    from src.engine.state import Action
    stage, start = _stage_01()
    session = GameSession(BloxorzProblem(stage, start))
    assert session.fall(Action.UP) is not None      # stage 01 start is on the top edge
    assert session.status == 'LOST'
    assert session.current_state == start
    assert session.apply_action(Action.RIGHT) is False
    session.restart()
    assert session.status == 'PLAYING'

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
    from src.engine.loader import initial_state, load_stage
    stage = load_stage(str(Path(__file__).resolve().parents[1] / 'levels' / 'stage_01.json'))
    return stage, initial_state(stage)


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
    assert session.fall(Action.UP) is not None      # vị trí xuất phát của stage 01 nằm ở mép trên
    assert session.status == 'LOST'
    assert session.current_state == start
    assert session.apply_action(Action.RIGHT) is False
    session.restart()
    assert session.status == 'PLAYING'


def test_parked_split_cube_does_not_retrigger_soft_switch():
    """Stage 02 có một công tắc mềm kiểu bật/tắt ở (2, 2). Một khối nhỏ đang đứng
    trên đó không được bật/tắt cầu lại mỗi lần khối kia di chuyển."""
    from pathlib import Path
    from src.engine.loader import load_stage
    from src.engine.state import Action
    stage = load_stage(str(Path(__file__).resolve().parents[1] / 'levels' / 'stage_02.json'))
    problem = BloxorzProblem(stage, None)
    parked = GameState((2, 2), (0, 6), Orientation.SPLIT, 1, stage.initial_bridge_mask)
    for action, after, _ in problem.get_successors(parked):
        if action != Action.SPACE and after.orientation == Orientation.SPLIT:
            assert after.bridges_status == parked.bridges_status
    # Đưa một khối nhỏ LÊN công tắc thì vẫn bật/tắt nó.
    arriving = GameState((2, 3), (0, 6), Orientation.SPLIT, 0, stage.initial_bridge_mask)
    moved = {a: s for a, s, _ in problem.get_successors(arriving)}[Action.LEFT]
    assert moved.pos1 == (2, 2) and moved.bridges_status != arriving.bridges_status

import pytest
from src.engine.state import GameState, Orientation, Action
from src.engine.problem import BloxorzProblem

def test_roll_standing_to_lying():
    # Khối đang đứng ở (2, 2) lăn LÊN
    state = GameState((2, 2), (2, 2), Orientation.STANDING, 0, ())
    new_state = BloxorzProblem.roll_block(state, Action.UP)
    
    # Kì vọng: Thành khối nằm dọc, chiếm 2 ô (0, 2) và (1, 2)
    assert new_state.orientation == Orientation.LYING_V
    assert new_state.pos1 == (0, 2)
    assert new_state.pos2 == (1, 2)

def test_roll_lying_to_standing():
    # Khối đang nằm dọc ở (0, 2) và (1, 2), lăn XUỐNG
    state = GameState((0, 2), (1, 2), Orientation.LYING_V, 0, ())
    new_state = BloxorzProblem.roll_block(state, Action.DOWN)
    
    # Kì vọng: Dựng đứng lên ở ô (2, 2)
    assert new_state.orientation == Orientation.STANDING
    assert new_state.pos1 == (2, 2)
    assert new_state.pos2 == (2, 2)

def test_split_movement_and_merge():
    # Hai khối nhỏ đang nằm ở (0, 0) và (0, 2). Đang điều khiển khối 0.
    state = GameState((0, 0), (0, 2), Orientation.SPLIT, 0, ())
    
    # Bước 1: Lăn khối 0 sang PHẢI (về ô 0, 1)
    moved_state = BloxorzProblem.roll_block(state, Action.RIGHT)
    
    # Kì vọng: Hai khối nằm cạnh nhau ở (0,1) và (0,2) -> Tự Hợp Thể thành LYING_H
    assert moved_state.orientation == Orientation.LYING_H
    assert moved_state.pos1 == (0, 1)
    assert moved_state.pos2 == (0, 2)
    assert moved_state.active_cube == -1  # Đã hợp thể thì mất quyền active
    
def test_split_switch_cube():
    # Bấm SPACE để đổi quyền điều khiển
    state = GameState((0, 0), (0, 2), Orientation.SPLIT, 0, ())
    new_state = BloxorzProblem.roll_block(state, Action.SPACE)
    
    assert new_state.active_cube == 1
    assert new_state.pos1 == state.pos1
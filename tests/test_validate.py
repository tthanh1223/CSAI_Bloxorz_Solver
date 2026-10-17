from src.engine.loader import StageData
from src.engine.problem import BloxorzProblem, TileType
from src.engine.state import GameState, Orientation


def _make_problem():
    stage = StageData()
    stage.grid = [
        [TileType.FLOOR, TileType.VOID, TileType.FLOOR],
        [TileType.FLOOR, TileType.FLOOR, TileType.FLOOR],
        [TileType.FRAGILE, TileType.FLOOR, TileType.FRAGILE],
    ]
    stage.bridges = {}
    stage.goal = (1, 1)
    initial_state = GameState((1, 0), (1, 0), Orientation.STANDING, 0, ())
    return BloxorzProblem(stage, initial_state)

def test_validity_out_of_bounds():
    problem = _make_problem()
    
    # Khối văng ra khỏi mảng (row = -1)
    state = GameState((-1, 0), (-1, 0), Orientation.STANDING, 0, ())
    assert problem.check_validity(state) == False

def test_validity_void_falling():
    problem = _make_problem()
    
    # Khối rơi trúng VOID ở (0, 1)
    state = GameState((0, 1), (0, 1), Orientation.STANDING, 0, ())
    assert problem.check_validity(state) == False

def test_validity_fragile_tile():
    problem = _make_problem()
    
    # Khối ĐỨNG đè lên gạch cam ở (2, 0) -> Gạch vỡ -> False
    state_standing = GameState((2, 0), (2, 0), Orientation.STANDING, 0, ())
    assert problem.check_validity(state_standing) == False
    
    # Khối NẰM đè lên gạch cam ở (2, 0) và (2, 1) -> Hợp lệ -> True
    state_lying = GameState((2, 0), (2, 1), Orientation.LYING_H, 0, ())
    assert problem.check_validity(state_lying) == True

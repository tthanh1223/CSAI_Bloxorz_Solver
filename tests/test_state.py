import pytest
from dataclasses import FrozenInstanceError
from src.engine.state import GameState, Orientation, Action, SearchNode

def test_gamestate_equality_and_hashing():
    # 1. Hai state giống hệt nhau phải bằng nhau và có cùng Hash
    state1 = GameState(
        pos1=(2, 3), pos2=(3, 3), 
        orientation=Orientation.LYING_H, 
        active_cube=0, 
        bridges_status=(True, False, True)
    )
    state2 = GameState(
        pos1=(2, 3), pos2=(3, 3), 
        orientation=Orientation.LYING_H, 
        active_cube=0, 
        bridges_status=(True, False, True)
    )
    assert state1 == state2
    assert hash(state1) == hash(state2)

    # 2. Hai state khác trạng thái Cầu (bridges_status) phải KHÁC NHAU hoàn toàn
    state3 = GameState(
        pos1=(2, 3), pos2=(3, 3), 
        orientation=Orientation.LYING_H, 
        active_cube=0, 
        bridges_status=(True, True, True) # Cầu số 2 đang MỞ thay vì ĐÓNG
    )
    assert state1 != state3

def test_gamestate_is_immutable():
    state = GameState((0, 0), (0, 0), Orientation.STANDING, 0, (True,))
    
    # Cố tình sửa dữ liệu State sẽ bị Python chặn lại (FrozenInstanceError)
    with pytest.raises(FrozenInstanceError):
        state.pos1 = (1, 1)

def test_searchnode_f_cost_calculation():
    state = GameState((0, 0), (0, 0), Orientation.STANDING, 0, ())
    node = SearchNode(state=state, parent=None, action=Action.UP, g=5, h=2.5)
    
    # f = g + h
    assert node.f == 7.5

def test_searchnode_priority_queue_sorting():
    state = GameState((0, 0), (0, 0), Orientation.STANDING, 0, ())
    
    # Giả lập 3 nút trên cây tìm kiếm A*
    node_f10 = SearchNode(state, None, Action.UP, g=5, h=5)   # f = 10
    node_f8 = SearchNode(state, None, Action.DOWN, g=6, h=2)  # f = 8
    node_f12 = SearchNode(state, None, Action.LEFT, g=4, h=8) # f = 12

    # Node có f nhỏ hơn phải được đánh giá là "nhỏ hơn" để heapq đẩy lên đầu
    assert node_f8 < node_f10
    assert node_f10 < node_f12
    
    # Test sort thực tế trong list
    queue = [node_f10, node_f12, node_f8]
    queue.sort()
    assert queue == [node_f8, node_f10, node_f12]

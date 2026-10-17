from types import SimpleNamespace

from src.engine.loader import StageData
from src.engine.switches import apply_tile_effects
from src.engine.switches import SwitchType


def _switch(switch_type, **kwargs):
    attributes = {"type": switch_type, "linked_bridges": [], "is_toggle": True}
    attributes.update(kwargs)
    return SimpleNamespace(**attributes)

def test_heavy_switch_requires_standing():
    stage = StageData()
    stage.switches = {
        (0, 0): _switch(SwitchType.HEAVY, linked_bridges=[0], is_toggle=False),
        (0, 1): _switch(SwitchType.SOFT, linked_bridges=[1]),
    }
    # Mảng cầu ban đầu: Cầu 0 và Cầu 1 đều đang ĐÓNG (False)
    initial_bridges = (False, False)
    
    # 1. Khối NẰM đè lên cả nút X (0,0) và nút Tròn (0,1)
    blocks_lying = ((0, 0), (0, 1))
    _, _, new_bridges = apply_tile_effects(blocks_lying, False, initial_bridges, stage)
    
    # Nút X bị trượt vì khối đang Nằm, nhưng nút Tròn vẫn kích hoạt
    assert new_bridges[0] == False  # Cầu 0 của nút X không mở
    assert new_bridges[1] == True   # Cầu 1 của nút Tròn mở
    
    # 2. Khối ĐỨNG đè lên nút X ở (0,0)
    # Standing blocks use the existing two-position representation (same cell twice).
    blocks_standing = ((0, 0), (0, 0))
    _, _, new_bridges_standing = apply_tile_effects(blocks_standing, False, initial_bridges, stage)
    
    # Nút X được kích hoạt vì khối đang Đứng
    assert new_bridges_standing[0] == True  # Cầu 0 mở

def test_split_switch_activation():
    # Setup map có nút tách ở (2, 2)
    stage = StageData()
    stage.switches = {}
    stage.switches[(2, 2)] = _switch(
        SwitchType.SPLIT,
        target_pos1=(4, 4), target_pos2=(5, 5),
    )
    
    # Khối ĐỨNG đè lên nút SPLIT
    blocks = ((2, 2), (2, 2))
    new_blocks, is_split, _ = apply_tile_effects(blocks, False, (), stage)
    
    # Trạng thái phải bị biến thành is_split = True và dịch chuyển đến target
    assert is_split == True
    assert list(new_blocks) == [(4, 4), (5, 5)]

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Tuple

from src.engine.state import Coord

if TYPE_CHECKING:
    from src.engine.loader import StageData


class SwitchType(Enum):
    SOFT = 'SOFT'  # Nút tròn: Cứ đè lên là kích hoạt (đứng, nằm, hay tách 1 khối đều được)
    HEAVY = 'HEAVY'  # Nút X: CHỈ kích hoạt khi nguyên khối 1x1x2 ĐỨNG THẲNG đè lên
    SPLIT = 'SPLIT'  # Nút TÁCH (ngoặc đơn): CHỈ kích hoạt khi nguyên khối ĐỨNG THẲNG đè lên


@dataclass(frozen=True)
class SwitchData:
    type: SwitchType
    linked_bridges: Tuple[int, ...] = ()
    is_toggle: bool = True
    bridge_actions: Tuple[Tuple[int, str], ...] = ()
    target_pos1: Coord | None = None
    target_pos2: Coord | None = None


def apply_tile_effects(
    blocks: List[Coord], 
    is_split: bool, 
    current_bridges_status: Tuple[bool, ...], 
    stage_data: StageData
) -> Tuple[List[Coord], bool, Tuple[bool, ...]]:
    """Mục tiêu cảu hàm này như kiểu một bộ lọc á, kiểm tra các ô mà khối gỗ đang đè lên có công tắc hay không, nếu có thì thực hiện hiệu ứng của công tắc đó."""
    new_bridges_status = list(current_bridges_status)
    new_blocks = list(blocks)
    new_is_split = is_split
    
    # A standing block is represented by one occupied cell in the engine.
    # Also accept the duplicated two-cell form for callers that use it.
    is_standing = not is_split and (
        len(blocks) == 1 or (len(blocks) == 2 and blocks[0] == blocks[1])
    )

    for row, col in dict.fromkeys(blocks):
        if (row, col) not in stage_data.switches:
            continue
            
        # Lấy dữ liệu công tắc
        switch = stage_data.switches[(row, col)]
        
        is_activated = False
        
        if switch.type == SwitchType.SOFT:
            # Nút TRÒN: Cứ đè lên là kích hoạt (đứng, nằm, hay tách 1 khối đều được)
            is_activated = True
            
        elif switch.type == SwitchType.HEAVY:
            # Nút X: CHỈ kích hoạt khi nguyên khối 1x1x2 ĐỨNG THẲNG đè lên
            if is_standing:
                is_activated = True
                
        elif switch.type == SwitchType.SPLIT:
            # Nút TÁCH: CHỈ kích hoạt khi nguyên khối ĐỨNG THẲNG đè lên
            if is_standing:
                is_activated = True

        # 4. Thực thi hiệu ứng nếu công tắc được kích hoạt
        if is_activated:
            
            # Xử lý nút tách khối
            if switch.type == SwitchType.SPLIT:
                new_is_split = True
                # Lấy tọa độ 2 khối nhỏ do map quy định sẵn cho nút này
                new_blocks = [switch.target_pos1, switch.target_pos2]
                
            # Xử lý bật/tắt cầu
            else:
                bridge_actions = getattr(switch, "bridge_actions", None)
                if bridge_actions is None:
                    bridge_actions = tuple(
                        (
                            bridge_id,
                            "swap" if switch.is_toggle else "on",
                        )
                        for bridge_id in switch.linked_bridges
                    )
                for bridge_id, action in bridge_actions:
                    if action == "swap":
                        new_bridges_status[bridge_id] = not new_bridges_status[bridge_id]
                    elif action == "on":
                        new_bridges_status[bridge_id] = True
                    elif action == "off":
                        new_bridges_status[bridge_id] = False
                    else:
                        raise ValueError(f"Unsupported bridge action: {action!r}")

    return tuple(new_blocks), new_is_split, tuple(new_bridges_status)

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Sequence, Tuple

from src.engine.state import Coord

if TYPE_CHECKING:
    from src.engine.loader import StageData

BRIDGE_ON = "on"
BRIDGE_OFF = "off"
BRIDGE_SWAP = "swap"
BRIDGE_ACTIONS = (BRIDGE_ON, BRIDGE_OFF, BRIDGE_SWAP)


class SwitchType(Enum):
    SOFT = 'SOFT'  # nút tròn: cứ đè lên là kích hoạt (đứng, nằm, hay một khối nhỏ khi tách đều được)
    HEAVY = 'HEAVY'  # nút X: chỉ kích hoạt khi nguyên khối 1x1x2 đứng thẳng đè lên
    SPLIT = 'SPLIT'  # nút tách (ngoặc đơn): chỉ kích hoạt khi nguyên khối đứng thẳng đè lên


@dataclass(frozen=True)
class SwitchData:
    type: SwitchType
    linked_bridges: Tuple[int, ...] = ()
    is_toggle: bool = True
    bridge_actions: Tuple[Tuple[int, str], ...] = ()
    target_pos1: Coord | None = None
    target_pos2: Coord | None = None


def apply_tile_effects(
    blocks: Sequence[Coord],
    is_split: bool,
    current_bridges_status: Tuple[bool, ...],
    stage_data: StageData,
    pressed: Sequence[Coord] | None = None,
) -> Tuple[Tuple[Coord, ...], bool, Tuple[bool, ...]]:
    """Bộ lọc hiệu ứng ô: kiểm tra các ô khối đang đè lên có công tắc không, nếu có thì thực hiện hiệu ứng của công tắc đó.

    pressed: các ô khối VỪA đè lên ở nước đi này (mặc định: mọi ô của `blocks`).
    Switch chỉ kích hoạt khi bị đè xuống, nên khi khối bị tách, khối nhỏ đang
    đứng yên trên switch không được kích hoạt lại mỗi lần khối kia di chuyển.
    """
    new_bridges_status = list(current_bridges_status)
    new_blocks = list(blocks)
    new_is_split = is_split

    # Khối đứng được engine biểu diễn bằng một ô.
    # Vẫn chấp nhận dạng hai ô trùng nhau cho những nơi gọi dùng dạng đó.
    is_standing = not is_split and (
        len(blocks) == 1 or (len(blocks) == 2 and blocks[0] == blocks[1])
    )

    for row, col in dict.fromkeys(blocks if pressed is None else pressed):
        if (row, col) not in stage_data.switches:
            continue

        # lấy dữ liệu công tắc
        switch = stage_data.switches[(row, col)]

        is_activated = False

        if switch.type == SwitchType.SOFT:
            # nút tròn: cứ đè lên là kích hoạt
            is_activated = True

        elif switch.type == SwitchType.HEAVY:
            # nút X: chỉ kích hoạt khi nguyên khối đứng thẳng đè lên
            if is_standing:
                is_activated = True

        elif switch.type == SwitchType.SPLIT:
            # nút tách: chỉ kích hoạt khi nguyên khối đứng thẳng đè lên
            if is_standing:
                is_activated = True

        # thực thi hiệu ứng nếu công tắc được kích hoạt
        if is_activated:

            # nút tách khối
            if switch.type == SwitchType.SPLIT:
                new_is_split = True
                # toạ độ 2 khối nhỏ do màn chơi quy định sẵn cho nút này
                new_blocks = [switch.target_pos1, switch.target_pos2]

            # bật/tắt cầu
            else:
                bridge_actions = getattr(switch, "bridge_actions", None)
                if bridge_actions is None:
                    bridge_actions = tuple(
                        (
                            bridge_id,
                            BRIDGE_SWAP if switch.is_toggle else BRIDGE_ON,
                        )
                        for bridge_id in switch.linked_bridges
                    )
                for bridge_id, action in bridge_actions:
                    if action == BRIDGE_SWAP:
                        new_bridges_status[bridge_id] = not new_bridges_status[bridge_id]
                    elif action == BRIDGE_ON:
                        new_bridges_status[bridge_id] = True
                    elif action == BRIDGE_OFF:
                        new_bridges_status[bridge_id] = False
                    else:
                        raise ValueError(f"Unsupported bridge action: {action!r}")

    return tuple(new_blocks), new_is_split, tuple(new_bridges_status)

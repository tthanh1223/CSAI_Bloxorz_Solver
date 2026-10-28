from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

Coord = Tuple[int, int]

class Orientation(Enum):
    STANDING = 'STANDING'
    LYING_H = 'LYING_H'
    LYING_V = 'LYING_V'
    SPLIT = 'SPLIT'

class Action(Enum):
    UP = 'UP'
    DOWN = 'DOWN'
    LEFT = 'LEFT'
    RIGHT = 'RIGHT'
    SPACE = 'SPACE'

@dataclass(frozen=True)
class GameState:
    """Trạng thái bất biến, hash được, dùng cho tập visited và hàng đợi của solver."""
    pos1: Coord  # toạ độ ô 1
    pos2: Coord  # toạ độ ô 2; khi khối đứng thì pos1 == pos2
    orientation: Orientation  # tư thế của khối
    active_cube: int  # khi tách làm hai: 0 là khối ở pos1, 1 là khối ở pos2; chỉ có ý nghĩa khi orientation == SPLIT
    bridges_status: Tuple[bool, ...]  # trạng thái đóng/mở của từng cầu
    # frozen=True nên dataclass tự sinh __hash__ và __eq__ để so sánh hai trạng thái.

@dataclass(frozen=True)
class SearchNode:
    """Nút trên cây tìm kiếm, dùng cho các thuật toán search."""
    state: GameState  # trạng thái của nút
    parent: Optional['SearchNode']  # nút cha, dùng để lần ngược ra đường đi khi tới đích
    action: Optional[Action]  # hành động tạo ra nút này
    g: float  # chi phí tích luỹ từ điểm xuất phát
    h: float = 0.0  # giá trị heuristic
    @property
    def f(self) -> float:
        return self.g + self.h

    # so sánh theo f để nút có thể đưa vào heap
    def __lt__(self, other: 'SearchNode') -> bool:
        return self.f < other.f

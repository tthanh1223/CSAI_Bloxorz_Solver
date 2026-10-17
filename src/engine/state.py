from dataclasses import dataclass
from typing import Tuple
from enum import Enum

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
    """Hashable state representation used by visited sets and solver queues."""
    pos1: Coord #tọa dộ ô 2
    pos2: Coord #tọa độ ô 2
    ## nếu khối đứng thì pos1 = pos2
    orientation: Orientation # trạng thái của block 
    active_cube: int # tách làm hai khối thì 0 (pos1) và 1 (pos2) = có ý nghĩa khi orientation == SPLIT
    bridges_status: Tuple[bool, ...] # Trạng thái đóng mơ cửa cầu (trạng thái)
    #Phương thức: Ghi đè __hash__ và __eq__ để Python biết cách so sánh 2 trạng thái.

State = GameState

@dataclass(frozen=True)
class SearchNode:
    """nút trên cây tìm kiếm phục vụ cho các thuật toán search"""
    state: GameState #trạng thái của node 
    parent: 'SearchNode' #Trỏ về chính nó (cần vì lấy chuỗi khi thắng)
    action: Action # hành động tạo ra nút này
    g: int # Chi phí thích lũy từ điểm xuất phát
    h: float = 0.0 # hàm heuristic (cài đặt)
    @property
    def f(self) -> float:
        return self.g + self.h

    # override phép so sánh á anh em
    def __lt__(self, other: 'SearchNode') -> bool:
        return self.f < other.f 
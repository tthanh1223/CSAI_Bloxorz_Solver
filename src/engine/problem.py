from typing import List, Tuple

from src.engine.state import Action, GameState, Orientation
from src.engine.loader import StageData
from src.engine.switches import apply_tile_effects
from enum import Enum
from src.engine.loader import TileType
ACTION_DELTAS = {
    Action.UP: (-1, 0),
    Action.DOWN: (1, 0),
    Action.LEFT: (0, -1),
    Action.RIGHT: (0, 1),
}


#đọc không hiểu thi di học về cái FSM là hiểu
class BloxorzProblem:
    def __init__(self, stage_data: StageData, initial_state: GameState):
        self.stage_data = stage_data #màn chơi hiện tại
        self.initial_state = initial_state #trạng thái hiện tại 

    def is_goal(self, state: GameState) -> bool:
        if state.pos1 == self.stage_data.goal and state.orientation == Orientation.STANDING:
            return True
        return False

    def get_successors(self, state: GameState) -> List[Tuple[Action, GameState, int]]:
        """
        Nhận vào state hiện tại.
        Trả về danh sách các (Hành động, State Mới, Cost) hợp lệ.
        Cost mặc định bằng 1 (cho UCS/A*).
        """

        successors: List[Tuple[Action, GameState, int]] = []
        for action in [Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.SPACE]:
            moved_state = self.roll_block(state, action)
            if moved_state is None or not self.check_validity(moved_state):
                continue
            if action == Action.SPACE:
                successors.append((action, moved_state, 1))
                continue

            blocks = self._blocks_for_state(moved_state)
            next_blocks, is_split, bridge_mask = apply_tile_effects(
                blocks,
                moved_state.orientation == Orientation.SPLIT, #ở đây là một bool nha, coi đọc hong hiểu
                moved_state.bridges_status,
                self.stage_data,
            )
            next_state = self._state_from_blocks(
                next_blocks,
                is_split,
                moved_state.active_cube,
                bridge_mask,
            )
            if next_state is not None and self.check_validity(next_state):
                successors.append((action, next_state, 1))
        return successors


    @staticmethod
    def roll_block(state: GameState, action: Action) -> GameState | None:
        """Đây là Transition method của một FSM : trả về GameState mới tùy một State hiện tại"""
        ori = state.orientation
        # xử lý đổi lượt khối nhỏ bằng dấu space
        if action ==  Action.SPACE:
            if ori != Orientation.SPLIT:
                return None
            return GameState(state.pos1, state.pos2, ori, 1 - state.active_cube, state.bridges_status)

        if action not in ACTION_DELTAS:
            return None
        dr, dc = ACTION_DELTAS[action]
        r1, c1 = state.pos1
        r2, c2 = state.pos2

        new_pos1, new_pos2 = state.pos1, state.pos2
        new_ori = ori
        new_active = state.active_cube

        # xử lí di chuyển khối
        if ori == Orientation.STANDING: # đang đứng
            if dr != 0: #lăn dọc
                new_pos1 = (r1 + dr, c1)
                new_pos2 = (r1 + 2 * dr, c1)
                new_ori = Orientation.LYING_V # thành nằm dọc
            else: # lăn ngang
                new_pos1 = (r1, c1 + dc)
                new_pos2 = (r1, c1 + 2 * dc)
                new_ori = Orientation.LYING_H # thành nằm ngang
            new_pos1, new_pos2 = sorted([new_pos1, new_pos2])

        elif ori == Orientation.LYING_H: #đang nằm ngang
            if dr != 0: #lăn dọc
                new_pos1 = (r1 + dr, c1)
                new_pos2 = (r2 + dr, c2)
            else: # lăn ngang
                new_c = c1 - 1 if dc == -1 else c2 + 1
                new_pos1 = new_pos2 = (r1, new_c)
                new_ori = Orientation.STANDING # thành đứng
        
        elif ori == Orientation.LYING_V: #đang nằm dọc
            if dc != 0: #lăn ngang
                new_pos1 = (r1, c1 + dc)
                new_pos2 = (r2, c2 + dc)
            else: # lăn dọc
                new_r = r1 - 1 if dr == -1 else r2 + 1
                new_pos1 = new_pos2 = (new_r, c1)
                new_ori = Orientation.STANDING # thành đứng

        elif ori == Orientation.SPLIT: #đang tách
            if new_active == 0:
                new_pos1 = (r1 + dr, c1 + dc)
            else:
                new_pos2 = (r2 + dr, c2 + dc)

            #Kiểm tra để hợp lại thành 1
            dr_diff = abs(new_pos1[0] - new_pos2[0])
            dc_diff = abs(new_pos1[1] - new_pos2[1])

            if dr_diff + dc_diff == 1: # nếu hai khối sát nhau
                new_pos1, new_pos2 = sorted([new_pos1, new_pos2])
                if dr_diff == 1:
                    new_ori = Orientation.LYING_V
                else:
                    new_ori = Orientation.LYING_H
                new_active = -1
        else:
            return None
        
        return GameState(new_pos1, new_pos2, new_ori, new_active, state.bridges_status)

    def check_validity(self, state: GameState) -> bool:
        """Check that every occupied cell is supported by the current stage."""
        occupied = set(self._blocks_for_state(state))
        grid = self.stage_data.grid
        for row, col in occupied:
            if row < 0 or row >= len(grid) or col < 0 or col >= len(grid[row]):
                return False

            bridge_indices = [
                index
                for index, cells in enumerate(self.stage_data.bridges.values())
                if (row, col) in cells
            ]
            if any(
                index >= len(state.bridges_status) or not state.bridges_status[index]
                for index in bridge_indices
            ):
                return False
            if grid[row][col] == TileType.VOID and not bridge_indices:
                return False
            if  grid[row][col] == TileType.FRAGILE and state.orientation == Orientation.STANDING:
                return False

        return True

    @staticmethod
    def _blocks_for_state(state: GameState) -> Tuple[Tuple[int, int], ...]:
        """Lấy vị trí của block từ GameState hiện tại"""
        if state.orientation == Orientation.STANDING:
            return (state.pos1,)
        return (state.pos1, state.pos2)

    @staticmethod
    def _state_from_blocks(
        blocks: Tuple[Tuple[int, int], ...],
        is_split: bool,
        active_cube: int,
        bridge_mask: Tuple[bool, ...],
                ) -> GameState | None:
        """Biến kết quả từ apply_tile_effects() thành một GameState hoàn chỉnh"""
        if is_split:
            if len(blocks) != 2:
                return None
            return GameState(blocks[0], blocks[1], Orientation.SPLIT, active_cube, bridge_mask)
        if len(blocks) == 1:
            return GameState(blocks[0], blocks[0], Orientation.STANDING, 0, bridge_mask)
        if len(blocks) != 2:
            return None

        pos1, pos2 = blocks
        if pos1[0] == pos2[0] and abs(pos1[1] - pos2[1]) == 1:
            orientation = Orientation.LYING_H
        elif pos1[1] == pos2[1] and abs(pos1[0] - pos2[0]) == 1:
            orientation = Orientation.LYING_V
        else:
            return None
        return GameState(pos1, pos2, orientation, 0, bridge_mask)

from typing import List
from src.engine.state import Action, GameState
from src.engine.problem import BloxorzProblem

class GameSession:
    def __init__(self, problem: BloxorzProblem):
        self.problem = problem
        self.current_state = problem.initial_state
        self.history: List[GameState] = []  # Lưu lịch sử để Undo
        self.moves = 0
        self.status = "PLAYING"  # Có thể là "PLAYING", "WON", "LOST"

    def apply_action(self, action: Action) -> bool:
        """Nhận phím bấm, hỏi FSM xem đi được không. Nếu được thì cập nhật."""
        if self.status != "PLAYING":
            return False

        # Hỏi FSM: "Từ state hiện tại, nếu đi các hướng thì ra state nào?"
        successors = self.problem.get_successors(self.current_state)
        
        for valid_action, next_state, _ in successors:
            if valid_action == action:
                # Nếu phím bấm hợp lệ -> Lưu lịch sử và đi tiếp
                self.history.append(self.current_state)
                self.current_state = next_state
                if action != Action.SPACE:  # Đổi khối không tính là 1 move
                    self.moves += 1
                
                # Check thắng
                if self.problem.is_goal(self.current_state):
                    self.status = "WON"
                return True
                
        # Nước đi làm rớt vực hoặc không hợp lệ -> FSM không trả về -> Giữ nguyên (hoặc cho thua tùy luật)
        return False

    def undo(self):
        """Quay lại nước đi trước đó"""
        if self.history:
            self.current_state = self.history.pop()
            self.moves -= 1
            self.status = "PLAYING"

    def restart(self):
        """Chơi lại từ đầu"""
        self.current_state = self.problem.initial_state
        self.history.clear()
        self.moves = 0
        self.status = "PLAYING"

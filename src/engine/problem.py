from typing import List, Tuple

from src.engine.loader import StageData, TileType
from src.engine.state import Action, Coord, GameState, Orientation
from src.engine.switches import apply_tile_effects

PLAYING = "PLAYING"
WON = "WON"
LOST = "LOST"

ACTION_DELTAS = {
    Action.UP: (-1, 0),
    Action.DOWN: (1, 0),
    Action.LEFT: (0, -1),
    Action.RIGHT: (0, 1),
}


def occupied_cells(state: GameState) -> Tuple[Coord, ...]:
    """Các ô mà khối (hoặc 2 khối nhỏ khi bị tách) đang chiếm."""
    if state.orientation == Orientation.STANDING:
        return (state.pos1,)
    return (state.pos1, state.pos2)


# Bài toán được mô hình như một FSM: roll_block() là hàm chuyển trạng thái.
class BloxorzProblem:
    def __init__(self, stage_data: StageData, initial_state: GameState):
        self.stage_data = stage_data  # màn chơi hiện tại
        self.initial_state = initial_state  # trạng thái xuất phát

    def is_goal(self, state: GameState) -> bool:
        if state.pos1 == self.stage_data.goal and state.orientation == Orientation.STANDING:
            return True
        return False

    def get_successors(self, state: GameState) -> List[Tuple[Action, GameState, int]]:
        """
        Nhận vào state hiện tại.
        Trả về danh sách các (hành động, state mới, cost) hợp lệ.
        Cost mặc định bằng 1 (cho UCS/A*).
        """

        successors: List[Tuple[Action, GameState, int]] = []
        for action in Action:
            moved_state = self.roll_block(state, action)
            if moved_state is None or not self.check_validity(moved_state):
                continue
            if action == Action.SPACE:
                successors.append((action, moved_state, 1))
                continue

            blocks = occupied_cells(moved_state)
            # Chỉ những ô khối vừa đè lên mới kích hoạt switch. Khi bị tách, khối
            # nhỏ đứng yên vẫn nằm trong `blocks` nhưng không "bấm" switch lần nữa.
            previous = set(occupied_cells(state))
            pressed = [cell for cell in blocks if cell not in previous]
            next_blocks, is_split, bridge_mask = apply_tile_effects(
                blocks,
                moved_state.orientation == Orientation.SPLIT,  # is_split (bool)
                moved_state.bridges_status,
                self.stage_data,
                pressed,
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
        """Hàm chuyển trạng thái của FSM: trả về GameState mới từ state hiện tại và action."""
        ori = state.orientation
        # đổi lượt khối nhỏ bằng phím space
        if action == Action.SPACE:
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

        # xử lý di chuyển khối
        if ori == Orientation.STANDING:  # đang đứng
            if dr != 0:  # lăn dọc
                new_pos1 = (r1 + dr, c1)
                new_pos2 = (r1 + 2 * dr, c1)
                new_ori = Orientation.LYING_V  # thành nằm dọc
            else:  # lăn ngang
                new_pos1 = (r1, c1 + dc)
                new_pos2 = (r1, c1 + 2 * dc)
                new_ori = Orientation.LYING_H  # thành nằm ngang
            new_pos1, new_pos2 = sorted([new_pos1, new_pos2])

        elif ori == Orientation.LYING_H:  # đang nằm ngang
            if dr != 0:  # lăn dọc
                new_pos1 = (r1 + dr, c1)
                new_pos2 = (r2 + dr, c2)
            else:  # lăn ngang
                new_c = c1 - 1 if dc == -1 else c2 + 1
                new_pos1 = new_pos2 = (r1, new_c)
                new_ori = Orientation.STANDING  # thành đứng

        elif ori == Orientation.LYING_V:  # đang nằm dọc
            if dc != 0:  # lăn ngang
                new_pos1 = (r1, c1 + dc)
                new_pos2 = (r2, c2 + dc)
            else:  # lăn dọc
                new_r = r1 - 1 if dr == -1 else r2 + 1
                new_pos1 = new_pos2 = (new_r, c1)
                new_ori = Orientation.STANDING  # thành đứng

        elif ori == Orientation.SPLIT:  # đang tách
            if new_active == 0:
                new_pos1 = (r1 + dr, c1 + dc)
            else:
                new_pos2 = (r2 + dr, c2 + dc)

            # kiểm tra để hợp lại thành một khối
            dr_diff = abs(new_pos1[0] - new_pos2[0])
            dc_diff = abs(new_pos1[1] - new_pos2[1])

            if dr_diff + dc_diff == 1:  # hai khối nằm sát nhau
                new_pos1, new_pos2 = sorted([new_pos1, new_pos2])
                if dr_diff == 1:
                    new_ori = Orientation.LYING_V
                else:
                    new_ori = Orientation.LYING_H
                new_active = -1
        else:
            return None

        return GameState(new_pos1, new_pos2, new_ori, new_active, state.bridges_status)

    def fall_result(self, state: GameState, action: Action) -> GameState | None:
        """Trả về tư thế khối ngay lúc rơi nếu `action` làm khối rơi, ngược lại trả về None.

        Một nước lăn bị engine từ chối (lăn ra void, ra ngoài bảng, lên cầu đang đóng,
        đứng thẳng trên ô fragile, hoặc switch đóng cầu ngay dưới khối) nghĩa là khối rơi.
        Hàm này chỉ dùng cho GUI; solver vẫn chỉ đi qua get_successors() như cũ.
        """
        if action == Action.SPACE:
            return None
        moved = self.roll_block(state, action)
        if moved is None:
            return None
        if any(valid_action == action for valid_action, _, _ in self.get_successors(state)):
            return None
        return moved

    def check_validity(self, state: GameState) -> bool:
        """Kiểm tra mọi ô khối đang chiếm đều có chỗ đứng trong màn hiện tại."""
        occupied = set(occupied_cells(state))
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
            if grid[row][col] == TileType.FRAGILE and state.orientation == Orientation.STANDING:
                return False

        return True

    @staticmethod
    def _state_from_blocks(
        blocks: Tuple[Coord, ...],
        is_split: bool,
        active_cube: int,
        bridge_mask: Tuple[bool, ...],
    ) -> GameState | None:
        """Biến kết quả của apply_tile_effects() thành một GameState hoàn chỉnh."""
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


class GameSession:
    def __init__(self, problem: BloxorzProblem):
        self.problem = problem
        self.current_state = problem.initial_state
        self.history: List[GameState] = []  # lịch sử để undo
        self.moves = 0
        self.status = PLAYING  # PLAYING, WON hoặc LOST

    def apply_action(self, action: Action) -> bool:
        """Nhận phím bấm, hỏi FSM xem có đi được không; nếu được thì cập nhật."""
        if self.status != PLAYING:
            return False

        # hỏi FSM: từ state hiện tại, mỗi hướng đi sẽ ra state nào
        successors = self.problem.get_successors(self.current_state)

        for valid_action, next_state, _ in successors:
            if valid_action == action:
                # phím bấm hợp lệ: lưu lịch sử rồi đi tiếp
                self.history.append(self.current_state)
                self.current_state = next_state
                if action != Action.SPACE:  # đổi khối không tính là một nước đi
                    self.moves += 1

                # kiểm tra thắng
                if self.problem.is_goal(self.current_state):
                    self.status = WON
                return True

        # Nước đi làm rơi hoặc không hợp lệ thì FSM không trả về, nên giữ nguyên state.
        # Muốn xử lý thua (rơi) thì gọi fall() thay vì bỏ qua nước đi.
        return False

    def fall(self, action: Action) -> GameState | None:
        """Nếu action làm khối rơi: đặt status = LOST và trả về tư thế lúc rơi.

        current_state giữ nguyên (khối chưa bao giờ đứng được ở tư thế rơi),
        nên restart() hoặc undo() đều đưa game về trạng thái hợp lệ.
        """
        if self.status != PLAYING:
            return None
        fallen = self.problem.fall_result(self.current_state, action)
        if fallen is not None:
            self.status = LOST
        return fallen

    def undo(self) -> None:
        """Quay lại nước đi trước đó."""
        if self.history:
            self.current_state = self.history.pop()
            self.moves -= 1
            self.status = PLAYING

    def restart(self) -> None:
        """Chơi lại từ đầu."""
        self.current_state = self.problem.initial_state
        self.history.clear()
        self.moves = 0
        self.status = PLAYING

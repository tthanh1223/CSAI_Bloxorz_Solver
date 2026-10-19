import heapq
from itertools import count
from typing import Iterable, List, Tuple
 
from src.contract import SearchProblem, SearchSolver, SolverResult, State
from src.engine.state import Orientation, SearchNode
from src.engine.switches import SwitchType
from src.solvers.profiler import run_with_profiler
from src.solvers.uninformed import save_path
 
Coord = Tuple[int, int]
 
 
def _occupied_cells(state: State) -> Tuple[Coord, ...]:
    """Các ô mà khối (hoặc 2 khối nhỏ khi bị tách) đang chiếm."""
    if state.orientation == Orientation.STANDING:
        return (state.pos1,)
    return (state.pos1, state.pos2)
 
 
def _rolls_lower_bound(cells: Iterable[Coord], target: Coord) -> int:
    """ceil(D / 2), với D = khoảng cách Manhattan LỚN NHẤT từ các ô đang chiếm đến target."""
    tr, tc = target
    d = max(abs(r - tr) + abs(c - tc) for r, c in cells)
    return (d + 1) // 2  # chia 2 làm tròn lên
 
 
def _split_switch_cells(problem: SearchProblem) -> Tuple[Coord, ...]:
    """Vị trí các split switch trong màn (nơi khối có thể bị teleport)."""
    return tuple(
        coord
        for coord, switch in problem.stage_data.switches.items()
        if switch.type == SwitchType.SPLIT
    )
 
 
def heuristic_manhattan(state: State, problem: SearchProblem, split_cells=None) -> float:
    cells = _occupied_cells(state)
    if split_cells is None:
        split_cells = _split_switch_cells(problem)
 
    h = _rolls_lower_bound(cells, problem.stage_data.goal)
    for s in split_cells:
        h = min(h, _rolls_lower_bound(cells, s))
    return float(h)
 
 
def heuristic_zero(state: State, problem: SearchProblem, split_cells=None) -> float:
    """h = 0: A* lúc này chính là UCS. Dùng để so sánh trong phần thực nghiệm."""
    return 0.0
 
 
class AStar(SearchSolver):
    """A* với tập closed (visited) và bảng best_g.
 
    heuristic: hàm h(state, problem, split_cells) -> float
    """
 
    def __init__(self, heuristic=heuristic_manhattan):
        self.heuristic = heuristic
 
    def solve(self, problem: SearchProblem) -> SolverResult:
        heuristic = self.heuristic
 
        def _astar():
            split_cells = _split_switch_cells(problem)  # tính 1 lần cho cả màn
 
            def h(state):
                return heuristic(state, problem, split_cells)
 
            start = problem.initial_state
            start_node = SearchNode(state=start, parent=None, action=None, g=0, h=h(start))
 
            tie = count()  # phá hòa khi f và h bằng nhau (heapq không so sánh được node)
            # Phần tử heap: (f, h, thứ tự thêm vào, node)
            # Khi f bằng nhau, ưu tiên node có h nhỏ hơn (gần đích hơn).
            frontier: List = [(start_node.f, start_node.h, next(tie), start_node)]
            best_g = {start: 0.0}  # chi phí nhỏ nhất đã biết để tới mỗi state
            closed = set()         # state đã mở rộng xong
            expanded_nodes = 0
 
            while frontier:
                _, _, _, node = heapq.heappop(frontier)
                state = node.state
 
                # Bỏ qua bản ghi cũ: state này đã được mở rộng với g tốt hơn
                if state in closed:
                    continue
                closed.add(state)
                expanded_nodes += 1
 
                # Goal test khi LẤY RA (không phải khi sinh ra) để đảm bảo tối ưu
                if problem.is_goal(state):
                    return True, save_path(node), expanded_nodes, float(node.g)
 
                for action, next_state, cost in problem.get_successors(state):
                    if next_state in closed:
                        continue
                    new_g = node.g + cost
                    if new_g < best_g.get(next_state, float("inf")):
                        best_g[next_state] = new_g
                        child = SearchNode(
                            state=next_state,
                            parent=node,
                            action=action,
                            g=new_g,
                            h=h(next_state),
                        )
                        heapq.heappush(frontier, (child.f, child.h, next(tie), child))
 
            return False, [], expanded_nodes, 0.0
 
        return run_with_profiler(_astar)
 

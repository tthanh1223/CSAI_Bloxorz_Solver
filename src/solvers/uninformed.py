import heapq
from collections import deque
from typing import Dict, Set

from src.contract import SearchProblem, SearchSolver, SolverResult
from src.engine.loader import TileType
from src.engine.problem import occupied_cells
from src.engine.state import Action, GameState, SearchNode
from src.solvers.common import not_found, root_node, save_path
from src.solvers.profiler import run_with_profiler

SWITCH_SPACE_COST = 0.0
STEP_COST = 1.0
BRIDGE_TOGGLE_COST = 2.0
FRAGILE_COST = 3.0


class BFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _bfs():
            start_node = root_node(problem)
            frontier: deque[SearchNode] = deque([start_node])
            visited: Set[GameState] = {start_node.state}
            expanded_nodes = 0
            while frontier:
                node = frontier.popleft()
                expanded_nodes += 1
                if problem.is_goal(node.state):
                    return True, save_path(node), expanded_nodes, float(node.g)
                for action, next_state, cost in problem.get_successors(node.state):
                    if next_state not in visited:
                        visited.add(next_state)
                        frontier.append(SearchNode(next_state, node, action, node.g + cost))
            return not_found(expanded_nodes)
        return run_with_profiler(_bfs)

class DFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _ids():
            expanded_nodes = 0
            depth_limit = 0
            while True:
                found, path, exp, cost, cutoff = _dfs(problem, depth_limit)
                expanded_nodes += exp
                if found:
                    return True, path, expanded_nodes, cost
                if not cutoff:
                    # Không nhánh nào bị dừng vì giới hạn độ sâu: mọi đường đi đã
                    # được duyệt hết, nên tăng giới hạn cũng không giúp được gì.
                    return not_found(expanded_nodes)
                depth_limit += 1
        def _dfs(problem, max_depth):
            start_node = root_node(problem)
            stack = [(start_node, frozenset([start_node.state]))]
            expanded_nodes = 0
            cutoff = False  # True nếu có nút không được mở rộng vì chạm max_depth
            while stack:
                node, path_states = stack.pop()
                expanded_nodes += 1
                if problem.is_goal(node.state):
                    return True, save_path(node), expanded_nodes, float(node.g), cutoff
                if node.g >= max_depth:
                    cutoff = True
                else:
                    for action, next_state, cost in problem.get_successors(node.state):
                        if next_state not in path_states:
                            child = SearchNode(next_state, node, action, node.g + cost)
                            stack.append((child, path_states | {next_state}))
            return False, [], expanded_nodes, 0.0, cutoff
        return run_with_profiler(_ids)


class UCS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def get_cost(state, next_state, action) -> float:
            cost = STEP_COST
            if action == Action.SPACE:
                return SWITCH_SPACE_COST
            stage_data = problem.stage_data

            for (r, c) in occupied_cells(next_state):
                if stage_data.grid[r][c] == TileType.FRAGILE:
                    cost = max(cost, FRAGILE_COST)
            if next_state.bridges_status != state.bridges_status:
                cost = max(cost, BRIDGE_TOGGLE_COST)
            return cost

        def _ucs():
            start_node = root_node(problem)
            counter = 0
            heap = [(0, counter, start_node)]
            visited: Dict[GameState, float] = {}
            expanded_nodes = 0

            while heap:
                g, _, node = heapq.heappop(heap)
                expanded_nodes += 1

                if node.state in visited and visited[node.state] <= g:
                    expanded_nodes -= 1
                    continue

                visited[node.state] = g

                if problem.is_goal(node.state):
                    return True, save_path(node), expanded_nodes, float(g)
                for action, next_state, _ in problem.get_successors(node.state):
                    new_g = g + get_cost(node.state, next_state, action)

                    if next_state not in visited or visited[next_state] > new_g:
                        counter += 1
                        child = SearchNode(next_state, node, action, new_g)
                        heapq.heappush(heap, (new_g, counter, child))

            return not_found(expanded_nodes)

        return run_with_profiler(_ucs)

from src.contract import SearchProblem, SearchSolver, SolverResult
from src.engine.loader import TileType
from src.solvers.profiler import run_with_profiler
from collections import deque
import heapq
from src.engine.state import SearchNode, Action
def save_path(node: SearchNode):
    path = []
    current = node
    while current.parent is not None:
        path.append(current.action.value)
        current = current.parent
    path.reverse()
    return path

class BFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _bfs():
            start_node = SearchNode(
                state=problem.initial_state,
                parent=None,
                action=None,
                g=0,
            )
            frontier: deque[SearchNode] = deque([start_node])
            visited: set = set()
            visited.add(start_node.state)
            expanded_nodes = 0
            while frontier:
                node = frontier.popleft()
                expanded_nodes += 1
                if problem.is_goal(node.state):
                    path = save_path(node)
                    return True, path, expanded_nodes, float(node.g)
                for action, next_state, cost in problem.get_successors(node.state):
                    if next_state not in visited:
                        visited.add(next_state)
                        child = SearchNode(
                            state=next_state,
                            parent=node,
                            action=action,
                            g=node.g + cost,
                        )
                        frontier.append(child)
            return False, [], 0, 0.0
        return run_with_profiler(_bfs)

class DFS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def _ids():
            expanded_nodes = 0
            depth_limit = 0
            while True:
                found, path, exp, cost = _dfs(problem, depth_limit)
                expanded_nodes += exp
                if found:
                    return True, path, expanded_nodes, cost
                depth_limit += 1
        def _dfs(problem, max_depth):
            start_node = SearchNode(
                state=problem.initial_state,
                parent=None,
                action=None,
                g=0,
            )
            stack = [(start_node, frozenset([start_node.state]))]
            expanded_nodes = 0
            while stack:
                node, path_states = stack.pop()
                expanded_nodes += 1
                if problem.is_goal(node.state):
                    return True, save_path(node), expanded_nodes, float(node.g)
                if node.g < max_depth:
                    for action, next_state, cost in problem.get_successors(node.state):
                        if next_state not in path_states:
                            child = SearchNode(
                                state=next_state,
                                parent=node,
                                action=action,
                                g=node.g + cost,
                            )
                            stack.append((child, path_states | {next_state}))
            return False, [], 0, 0.0
        return run_with_profiler(_ids)

import heapq
# Import các class cần thiết nếu file chưa có (VD: Action, TileType, _blocks_for_state)

class UCS(SearchSolver):
    def solve(self, problem: SearchProblem) -> SolverResult:
        def get_cost(state, next_state, action) -> float:
            cost = 1.0
            if action == Action.SPACE: 
                return 0.0
            stage_data = problem.stage_data  
            occupied = problem._blocks_for_state(next_state)
            
            for (r, c) in occupied:
                if stage_data.grid[r][c] == TileType.FRAGILE:
                    cost = max(cost, 3.0)
            if next_state.bridges_status != state.bridges_status:
                cost = max(cost, 2.0)
            return cost

        def _ucs():
            start_node = SearchNode(
                state=problem.initial_state,
                parent=None,
                action=None,
                g=0,
            )
            counter = 0
            heap = [(0, counter, start_node)]
            visited: dict = {}
            expanded_nodes = 0
            
            while heap:
                g, _, node = heapq.heappop(heap)
                expanded_nodes += 1
                
                if node.state in visited and visited[node.state] <= g:
                    expanded_nodes -= 1
                    continue
                    
                visited[node.state] = g
                
                if problem.is_goal(node.state):
                    path = save_path(node)
                    return True, path, expanded_nodes, float(g)   
                for action, next_state, default_cost in problem.get_successors(node.state):
                    real_cost = get_cost(node.state, next_state, action)
                    new_g = g + real_cost
                    
                    if next_state not in visited or visited[next_state] > new_g:
                        counter += 1
                        child = SearchNode(
                            state=next_state,
                            parent=node,
                            action=action,
                            g=new_g,
                        )
                        heapq.heappush(heap, (new_g, counter, child))
                        
            return False, [], 0, 0.0
            
        return run_with_profiler(_ucs)
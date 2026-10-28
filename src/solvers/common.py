from typing import List, Tuple

from src.contract import SearchProblem
from src.engine.state import SearchNode


def save_path(node: SearchNode) -> List[str]:
    path = []
    current = node
    while current.parent is not None:
        path.append(current.action.value)
        current = current.parent
    path.reverse()
    return path


def root_node(problem: SearchProblem, h: float = 0.0) -> SearchNode:
    return SearchNode(state=problem.initial_state, parent=None, action=None, g=0, h=h)


def not_found(expanded_nodes: int) -> Tuple[bool, List[str], int, float]:
    return False, [], expanded_nodes, 0.0

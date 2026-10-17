from typing import Dict, List, Tuple

from src.contract import Coord


class StageData:
    def __init__(self) -> None:
        self.grid: List[List[str]] = []  # '1': floor, '0': void, 'S': start, 'G': goal, 'F': fragile
        self.start_coord: Coord = (0, 0)
        self.goal_coord: Coord = (0, 0)
        self.switches: List[dict] = []
        self.bridges: Dict[str, List[Coord]] = {}
        self.initial_bridge_mask: Tuple[bool, ...] = ()


def load_stage(json_filepath: str) -> StageData:
    """Read a JSON stage and return its StageData representation."""
    raise NotImplementedError

import json
from enum import Enum
from typing import Dict, List, Tuple

from src.engine.switches import BRIDGE_ACTIONS, BRIDGE_SWAP, SwitchData, SwitchType
from src.engine.state import Coord, GameState, Orientation


class TileType(Enum):
    FLOOR = '1'
    VOID = '0'
    START = 'S'
    GOAL = 'G'
    FRAGILE = 'F'
    BRIDGE = 'B'


class StageData:
    def __init__(self) -> None:
        self.grid: List[List[TileType]] = []
        self.start: Coord = (0, 0)
        self.goal: Coord = (0, 0)
        self.switches: Dict[Coord, SwitchData] = {}
        self.bridges: Dict[str, List[Coord]] = {}
        self.initial_bridge_mask: Tuple[bool, ...] = ()


def initial_state(stage: StageData) -> GameState:
    return GameState(stage.start, stage.start, Orientation.STANDING, 0, stage.initial_bridge_mask)


def load_stage(json_filepath: str) -> StageData:
    """Đọc một file JSON màn chơi và trả về StageData tương ứng."""
    with open(json_filepath, encoding="utf-8") as stage_file:
        raw_data = json.load(stage_file)

    if not isinstance(raw_data, dict):
        raise ValueError("Stage JSON must contain an object at its root.")

    raw_grid = raw_data.get("grid")
    if not isinstance(raw_grid, list) or not raw_grid:
        raise ValueError("Stage must contain a non-empty 'grid'.")

    grid: List[List[TileType]] = []
    for row_index, raw_row in enumerate(raw_grid):
        if not isinstance(raw_row, list) or not raw_row:
            raise ValueError(f"Grid row {row_index} must be a non-empty list.")
        row: List[TileType] = []
        for col_index, tile_code in enumerate(raw_row):
            try:
                row.append(TileType(tile_code))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid tile {tile_code!r} at ({row_index}, {col_index})."
                ) from error
        grid.append(row)

    if any(len(row) != len(grid[0]) for row in grid):
        raise ValueError("All rows in the stage grid must have the same length.")

    def parse_coord(value: object, field_name: str) -> Coord:
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 2
            or any(not isinstance(part, int) or isinstance(part, bool) for part in value)
        ):
            raise ValueError(f"'{field_name}' must be a pair of integer coordinates.")
        coord = (value[0], value[1])
        row, col = coord
        if row < 0 or row >= len(grid) or col < 0 or col >= len(grid[row]):
            raise ValueError(f"'{field_name}' coordinate {coord} is outside the grid.")
        return coord

    def find_tile(tile: TileType) -> Coord | None:
        for row_index, row in enumerate(grid):
            for col_index, cell in enumerate(row):
                if cell == tile:
                    return row_index, col_index
        return None

    start_value = raw_data.get("start_pos", find_tile(TileType.START))
    goal_value = raw_data.get("goal_pos", find_tile(TileType.GOAL))
    if start_value is None:
        raise ValueError("Stage must define 'start_pos' or contain an 'S' tile.")
    if goal_value is None:
        raise ValueError("Stage must define 'goal_pos' or contain a 'G' tile.")

    stage = StageData()
    stage.grid = grid
    stage.start = parse_coord(start_value, "start_pos")
    stage.goal = parse_coord(goal_value, "goal_pos")

    raw_bridges = raw_data.get("bridges", {})
    if not isinstance(raw_bridges, dict):
        raise ValueError("'bridges' must be an object mapping bridge ids to coordinates.")

    try:
        bridge_items = sorted(raw_bridges.items(), key=lambda item: int(item[0]))
    except (TypeError, ValueError) as error:
        raise ValueError("Bridge ids must be non-negative integer strings.") from error
    bridge_id_to_index: Dict[int, int] = {}
    for bridge_index, (bridge_id, raw_cells) in enumerate(bridge_items):
        numeric_id = int(bridge_id)
        if numeric_id < 0 or numeric_id in bridge_id_to_index:
            raise ValueError(f"Invalid or duplicate bridge id: {bridge_id!r}.")
        if not isinstance(raw_cells, list) or not raw_cells:
            raise ValueError(f"Bridge {bridge_id!r} must contain at least one coordinate.")
        bridge_id_to_index[numeric_id] = bridge_index
        stage.bridges[str(bridge_id)] = [
            parse_coord(cell, f"bridges[{bridge_id!r}]") for cell in raw_cells
        ]

    raw_mask = raw_data.get(
        "initial_bridges_status",
        raw_data.get("initial_bridge_mask", [False] * len(bridge_items)),
    )
    if (
        not isinstance(raw_mask, list)
        or len(raw_mask) != len(bridge_items)
        or any(not isinstance(status, bool) for status in raw_mask)
    ):
        raise ValueError(
            "'initial_bridges_status' must contain one boolean per bridge."
        )
    stage.initial_bridge_mask = tuple(raw_mask)

    raw_switches = raw_data.get("switches", {})
    if not isinstance(raw_switches, dict):
        raise ValueError("'switches' must be an object mapping coordinates to switch data.")

    for coord_text, raw_switch in raw_switches.items():
        if not isinstance(coord_text, str):
            raise ValueError(f"Invalid switch coordinate key: {coord_text!r}.")
        try:
            row_text, col_text = coord_text.split(",")
            switch_coord = parse_coord(
                (int(row_text), int(col_text)), f"switches[{coord_text!r}]"
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid switch coordinate key: {coord_text!r}.") from error
        if not isinstance(raw_switch, dict):
            raise ValueError(f"Switch at {switch_coord} must be an object.")
        try:
            switch_type = SwitchType(raw_switch["type"])
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError(f"Invalid switch type at {switch_coord}.") from error

        raw_actions = raw_switch.get("actions", [])
        if not isinstance(raw_actions, list):
            raise ValueError(f"Actions for switch at {switch_coord} must be a list.")
        bridge_actions: List[Tuple[int, str]] = []
        for raw_action in raw_actions:
            if (
                not isinstance(raw_action, (list, tuple))
                or len(raw_action) != 2
                or not isinstance(raw_action[0], int)
                or isinstance(raw_action[0], bool)
                or raw_action[1] not in BRIDGE_ACTIONS
            ):
                raise ValueError(f"Invalid bridge action at switch {switch_coord}: {raw_action!r}.")
            bridge_id, action_name = raw_action
            if bridge_id not in bridge_id_to_index:
                raise ValueError(
                    f"Switch at {switch_coord} references unknown bridge {bridge_id}."
                )
            bridge_actions.append((bridge_id_to_index[bridge_id], action_name))

        target_pos1 = target_pos2 = None
        if switch_type == SwitchType.SPLIT:
            target_pos1 = parse_coord(
                raw_switch.get("target_pos1"), f"switches[{coord_text!r}].target_pos1"
            )
            target_pos2 = parse_coord(
                raw_switch.get("target_pos2"), f"switches[{coord_text!r}].target_pos2"
            )

        stage.switches[switch_coord] = SwitchData(
            type=switch_type,
            linked_bridges=tuple(index for index, _ in bridge_actions),
            is_toggle=all(action == BRIDGE_SWAP for _, action in bridge_actions),
            bridge_actions=tuple(bridge_actions),
            target_pos1=target_pos1,
            target_pos2=target_pos2,
        )

    return stage

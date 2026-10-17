from typing import Tuple

from src.contract import Coord
from src.engine.loader import StageData


def apply_tile_effects(
    next_blocks: Tuple[Coord, ...],
    is_split: bool,
    current_mask: Tuple[bool, ...],
    stage_data: StageData,
) -> Tuple[Tuple[Coord, ...], bool, Tuple[bool, ...]]:
    """Apply switch effects to a moved block configuration."""
    return next_blocks, is_split, current_mask

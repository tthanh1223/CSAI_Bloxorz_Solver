from dataclasses import dataclass
from typing import Tuple
from enum import Enum
Coord = Tuple[int, int]


@dataclass(frozen=True)
class GameState:
    """Hashable state representation used by visited sets and solver queues."""

    blocks: Tuple[Coord, ...]
    is_split: bool
    bridge_mask: Tuple[bool, ...]


# Backwards-compatible name used by the existing engine and solver contracts.
State = GameState

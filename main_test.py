import argparse
from pathlib import Path

from src.engine.loader import StageData, load_stage
from src.engine.state import GameState, Orientation


def print_stage_map(stage: StageData) -> None:
    """Print a loaded stage as a readable, indexed grid."""
    if not stage.grid:
        print("(empty map)")
        return

    cell_width = max(2, max(len(str(row_index)) for row_index in range(len(stage.grid))))
    print("    " + " ".join(f"{col:>{cell_width}}" for col in range(len(stage.grid[0]))))
    for row_index, row in enumerate(stage.grid):
        cells = []
        for col_index, tile in enumerate(row):
            coord = (row_index, col_index)
            if coord == stage.start:
                symbol = "S"
            elif coord == stage.goal:
                symbol = "G"
            else:
                symbol = tile.value
            cells.append(f"{symbol:>{cell_width}}")
        print(f"{row_index:>2}  " + " ".join(cells))

    print(f"\nStart: {stage.start} | Goal: {stage.goal}")
    if stage.switches:
        print(f"Switches: {stage.switches}")
    if stage.bridges:
        print(f"Bridges: {stage.bridges}")
    print("Legend: 1=floor, 0=void, S=start, G=goal, F=fragile, B=bridge")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bloxorz project entry point")
    parser.add_argument(
        "--print-map",
        action="store_true",
        help="load stage 01 and print its map, then exit",
    )
    args = parser.parse_args()

    levels_dir = Path(__file__).parent / "levels"
    stage_paths = [levels_dir / f"stage_{number:02}.json" for number in range(1, 4)]
    stage_data = load_stage(str(stage_paths[0]))
    if args.print_map:
        print_stage_map(stage_data)
        return

    # Import the GUI only for interactive play so --print-map stays lightweight.
    from src.engine.problem import BloxorzProblem, GameSession
    from src.gui.app import BloxorzApp

    initial_state = GameState(
        pos1=stage_data.start,
        pos2=stage_data.start,
        orientation=Orientation.STANDING,
        active_cube=0,
        bridges_status=stage_data.initial_bridge_mask,
    )
    problem = BloxorzProblem(stage_data, initial_state)
    session = GameSession(problem)
    app = BloxorzApp(session, stage_paths)
    app.run()


if __name__ == "__main__":
    main()

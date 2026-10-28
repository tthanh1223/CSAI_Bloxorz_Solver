from pathlib import Path

from src.engine.loader import initial_state, load_stage
from src.engine.problem import BloxorzProblem, GameSession
from src.gui.app import BloxorzApp
from src.gui.themes import apply_theme


def main() -> None:
    stage_paths = sorted((Path(__file__).parent / "levels").glob("stage_*.json"))
    stage = load_stage(str(stage_paths[0]))
    app = BloxorzApp(GameSession(BloxorzProblem(stage, initial_state(stage))), stage_paths)
    apply_theme(app, "dream")
    app.in_main_menu = True
    app.run()


if __name__ == "__main__":
    main()

from pathlib import Path

from src.engine.loader import load_stage
from src.engine.problem import BloxorzProblem, GameSession
from src.solvers.uninformed import BFS, DFS, UCS
from src.solvers.astar import AStar
from src.gui.app import BloxorzApp


def main() -> None:
    stage_path = Path(__file__).parent / "levels" / "stage_01.json"
    stage_data = load_stage(str(stage_path))
    problem = BloxorzProblem(stage_data)
    session = GameSession(problem)
    solvers = {"BFS": BFS(), "DFS": DFS(), "UCS": UCS(), "A*": AStar()}
    app = BloxorzApp(session, solvers)
    app.run()


if __name__ == "__main__":
    main()

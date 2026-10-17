from src.contract import SearchSolver
from src.engine.problem import GameSession


class BloxorzApp:
    def __init__(self, session: GameSession, solvers: dict[str, SearchSolver]):
        self.session = session
        self.solvers = solvers
        # TODO: initialize the Pygame window and load assets.

    def draw_grid(self) -> None:
        raise NotImplementedError

    def draw_block(self) -> None:
        raise NotImplementedError

    def handle_input(self) -> None:
        raise NotImplementedError

    def run(self) -> None:
        raise NotImplementedError

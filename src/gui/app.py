from __future__ import annotations

import pygame
from pathlib import Path

from src.engine.loader import StageData, TileType, load_stage
from src.engine.problem import BloxorzProblem, GameSession
from src.engine.state import Action, GameState, Orientation


class BloxorzApp:
    """Small keyboard-playable Pygame view for the current stage/session."""

    WINDOW_SIZE = (900, 680)
    BACKGROUND = (22, 27, 38)
    PANEL = (31, 38, 52)
    FLOOR = (72, 87, 108)
    VOID = (15, 19, 28)
    GOAL = (45, 170, 123)
    FRAGILE = (183, 120, 54)
    BRIDGE_ON = (65, 138, 190)
    BLOCK = (244, 190, 75)
    BLOCK_ACTIVE = (255, 220, 110)
    TEXT = (235, 240, 248)
    MUTED = (160, 173, 192)

    def __init__(self, session: GameSession, stage_paths: list[Path] | None = None):
        self.session = session
        self.stage: StageData = session.problem.stage_data
        self.stage_paths = stage_paths or []
        self.stage_index = 0
        self.screen: pygame.Surface | None = None
        self.font: pygame.font.Font | None = None
        self.small_font: pygame.font.Font | None = None
        self._set_board_layout()
        self.message = "Use arrow keys to roll the block. Z: undo, R: restart."
        self.message_color = self.MUTED

    def _set_board_layout(self) -> None:
        rows = len(self.stage.grid)
        cols = max((len(row) for row in self.stage.grid), default=1)
        self.cell_size = max(28, min(64, 570 // max(rows, cols, 1)))
        self.board_width = cols * self.cell_size
        self.board_height = rows * self.cell_size
        self.board_x = 42
        self.board_y = max(72, (self.WINDOW_SIZE[1] - self.board_height) // 2)

    def run(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode(self.WINDOW_SIZE)
        pygame.display.set_caption(f"Bloxorz — Stage {self.stage_index + 1:02}")
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 23)
        clock = pygame.time.Clock()
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        self.handle_key(event.key)

            self.draw()
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

    def handle_key(self, key: int) -> None:
        if self.session.status == "WON":
            if key == pygame.K_RETURN:
                self.next_stage()
            elif key == pygame.K_r:
                self.session.restart()
                self.message = "Stage restarted."
                self.message_color = self.MUTED
            return

        controls = {
            pygame.K_UP: Action.UP,
            pygame.K_DOWN: Action.DOWN,
            pygame.K_LEFT: Action.LEFT,
            pygame.K_RIGHT: Action.RIGHT,
            pygame.K_SPACE: Action.SPACE,
        }
        if key == pygame.K_r:
            self.session.restart()
            self.message = "Stage restarted."
            self.message_color = self.MUTED
            return
        if key == pygame.K_z:
            self.session.undo()
            self.message = "Undid the last move." if self.session.history else "No move to undo."
            self.message_color = self.MUTED
            return

        action = controls.get(key)
        if action is None:
            return
        if self.session.apply_action(action):
            if self.session.status == "WON":
                if self.stage_index + 1 < len(self.stage_paths):
                    self.message = "Stage cleared! Press ENTER for the next stage."
                elif self.stage_paths:
                    self.message = "All 3 stages complete! Press R to replay this stage."
                else:
                    self.message = "You win! Press R to play again."
                self.message_color = self.GOAL
            else:
                self.message = "Move accepted."
                self.message_color = self.TEXT
        else:
            self.message = "That move is blocked."
            self.message_color = (238, 111, 105)

    def next_stage(self) -> None:
        next_index = self.stage_index + 1
        if next_index >= len(self.stage_paths):
            self.message = "All 3 stages are complete! Press R to replay this stage."
            self.message_color = self.GOAL
            return

        self.stage_index = next_index
        self.stage = load_stage(str(self.stage_paths[self.stage_index]))
        initial_state = GameState(
            pos1=self.stage.start,
            pos2=self.stage.start,
            orientation=Orientation.STANDING,
            active_cube=0,
            bridges_status=self.stage.initial_bridge_mask,
        )
        self.session = GameSession(BloxorzProblem(self.stage, initial_state))
        self._set_board_layout()
        self.message = "New stage! Arrow keys to move."
        self.message_color = self.TEXT
        pygame.display.set_caption(f"Bloxorz — Stage {self.stage_index + 1:02}")

    def draw(self) -> None:
        assert self.screen is not None and self.font is not None and self.small_font is not None
        screen = self.screen
        screen.fill(self.BACKGROUND)

        title = self.font.render("BLOXORZ", True, self.TEXT)
        screen.blit(title, (42, 24))
        stage_label = f"Stage {self.stage_index + 1:02}"
        if self.stage_paths:
            stage_label += f" / {len(self.stage_paths):02}"
        subtitle = self.small_font.render(f"{stage_label}  •  Arrow keys to move", True, self.MUTED)
        screen.blit(subtitle, (190, 31))

        self.draw_grid()
        self.draw_block(self.session.current_state)

        panel_x = self.board_x + self.board_width + 30
        panel = pygame.Rect(panel_x, self.board_y, 900 - panel_x - 28, self.board_height)
        pygame.draw.rect(screen, self.PANEL, panel, border_radius=14)
        self.draw_text("HOW TO PLAY", (panel.x + 18, panel.y + 20), self.TEXT)
        instructions = [
            "↑  ↓  ←  →   Roll",
            "SPACE       Switch cube",
            "Z           Undo",
            "R           Restart",
            "ESC         Quit",
        ]
        for index, line in enumerate(instructions):
            self.draw_text(line, (panel.x + 18, panel.y + 62 + index * 32), self.MUTED, small=True)

        state = self.session.current_state
        state_lines = [
            f"Moves: {self.session.moves}",
            f"Position: {state.pos1}",
            f"Orientation: {state.orientation.value}",
            f"Status: {self.session.status}",
        ]
        state_y = panel.y + 250
        for index, line in enumerate(state_lines):
            self.draw_text(line, (panel.x + 18, state_y + index * 30), self.TEXT if index == 0 else self.MUTED, small=True)

        message = self.small_font.render(self.message, True, self.message_color)
        screen.blit(message, (42, min(self.WINDOW_SIZE[1] - 34, self.board_y + self.board_height + 16)))

    def draw_grid(self) -> None:
        assert self.screen is not None and self.small_font is not None
        bridge_cells = {
            cell: index
            for index, cells in enumerate(self.stage.bridges.values())
            for cell in cells
        }
        for row_index, row in enumerate(self.stage.grid):
            for col_index, tile in enumerate(row):
                coord = (row_index, col_index)
                x = self.board_x + col_index * self.cell_size
                y = self.board_y + row_index * self.cell_size
                rect = pygame.Rect(x + 2, y + 2, self.cell_size - 4, self.cell_size - 4)
                color = self.VOID
                label = ""
                bridge_index = bridge_cells.get(coord)
                if bridge_index is not None:
                    active = bridge_index < len(self.session.current_state.bridges_status) and self.session.current_state.bridges_status[bridge_index]
                    color = self.BRIDGE_ON if active else self.VOID
                    label = "BR" if active else ""
                elif coord == self.stage.start:
                    color, label = self.FLOOR, "S"
                elif coord == self.stage.goal:
                    color, label = self.GOAL, "G"
                elif tile == TileType.VOID:
                    color = self.VOID
                elif tile == TileType.FRAGILE:
                    color, label = self.FRAGILE, "F"
                elif tile == TileType.BRIDGE:
                    color = self.BRIDGE_ON
                else:
                    color = self.FLOOR

                pygame.draw.rect(self.screen, color, rect, border_radius=6)
                switch = self.stage.switches.get(coord)
                if switch is not None:
                    label = {"SOFT": "O", "HEAVY": "X", "SPLIT": "↔"}.get(switch.type.value, "?")
                if label:
                    text = self.small_font.render(label, True, self.TEXT)
                    self.screen.blit(text, text.get_rect(center=rect.center))

        # Column and row indices make it easier to compare the display to JSON coordinates.
        for col in range(len(self.stage.grid[0])):
            label = self.small_font.render(str(col), True, self.MUTED)
            self.screen.blit(label, (self.board_x + col * self.cell_size + 7, self.board_y - 22))
        for row in range(len(self.stage.grid)):
            label = self.small_font.render(str(row), True, self.MUTED)
            self.screen.blit(label, (self.board_x - 23, self.board_y + row * self.cell_size + 7))

    def draw_block(self, state: GameState) -> None:
        assert self.screen is not None
        blocks = (state.pos1,) if state.orientation == Orientation.STANDING else (state.pos1, state.pos2)
        for index, (row, col) in enumerate(blocks):
            x = self.board_x + col * self.cell_size
            y = self.board_y + row * self.cell_size
            rect = pygame.Rect(x + 7, y + 7, self.cell_size - 14, self.cell_size - 14)
            active = state.orientation == Orientation.SPLIT and index == state.active_cube
            color = self.BLOCK_ACTIVE if active else self.BLOCK
            pygame.draw.rect(self.screen, color, rect, border_radius=9)
            pygame.draw.rect(self.screen, (255, 238, 185), rect, width=2, border_radius=9)

    def draw_text(self, text: str, position: tuple[int, int], color: tuple[int, int, int], *, small: bool = False) -> None:
        assert self.screen is not None
        font = self.small_font if small else self.font
        assert font is not None
        self.screen.blit(font.render(text, True, color), position)

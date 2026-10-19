"""Capture real desktop app states with a real solver; no mock results.

Run from repo root: python scripts/capture_gui.py
Captures the displayed SDL framebuffer after a live window flip.
"""
from pathlib import Path
import sys
import time
import os
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from src.gui.app import BloxorzApp, initial_state
from src.engine.loader import load_stage
from src.engine.problem import GameSession, BloxorzProblem


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'docs' / 'screenshots'
    output.mkdir(parents=True, exist_ok=True)
    pygame.init()
    paths = sorted((root / 'levels').glob('stage_*.json'))
    stage = load_stage(str(paths[0]))
    app = BloxorzApp(GameSession(BloxorzProblem(stage, initial_state(stage))), paths)
    app.screen = pygame.display.set_mode(app.WINDOW_SIZE, pygame.RESIZABLE)
    pygame.display.set_caption('Bloxorz - GUI review')

    def capture(name):
        # Capture the actual live SDL display, not a mockup or offscreen scene.
        app.draw()
        pygame.display.flip()
        for _ in range(6):
            pygame.event.pump()
            time.sleep(.04)
        pygame.image.save(pygame.display.get_surface(), str(output / f'{name}.png'))
        print(name, flush=True)

    try:
        capture('01_play')
        app.command('solve')
        capture('02_searching')
        deadline = time.monotonic() + 30
        while app.busy and time.monotonic() < deadline:
            pygame.event.pump()
            app.update(.016)
            app.draw()
            pygame.display.flip()
            time.sleep(.016)
        if not app.result or not app.result.found:
            raise RuntimeError('Real solver did not produce a solution.')
        capture('03_solution')
        app.command('solution')
        app.seek(3)
        capture('04_replay')
        app.command('settings')
        capture('05_settings')
        app.command('close_menu')
        app.restart()
        app.screen = pygame.display.set_mode((960, 720), pygame.RESIZABLE)
        app.large_text = True
        capture('06_compact')
        app.large_text = False
        app.screen = pygame.display.set_mode(app.WINDOW_SIZE, pygame.RESIZABLE)
        app.command('choose')
        capture('07_stage_picker')
        app.command('close_menu')
        app.command('algorithm_menu')
        capture('08_algorithm_menu')
        app.command('help')
        capture('09_help')
    finally:
        app.gateway.close()
        pygame.quit()


if __name__ == '__main__':
    main()

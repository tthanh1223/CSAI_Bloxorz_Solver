"""Capture real windows for all themes; one real worker solver validates replay."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from src.gui.app import BloxorzApp,initial_state
from src.gui.themes import apply_theme
from src.gui.contracts import MotionFrame
from src.engine.loader import load_stage
from src.engine.problem import BloxorzProblem,GameSession


def write_index(output):
    states=('play','roll','lying','replay','settings','compact','stage_picker','algorithm_menu','help','searching','solution')
    lines=['# Bloxorz: current screenshots','',
           '33 real-window captures: 11 states for each theme. All images live in this folder.',
           '1180 × 800, except compact views at 960 × 720. Solver results come from the real worker.','',
           '| State | Dream City | Paper Blueprint | Forest Ruins |','|---|---|---|---|']
    for i,state in enumerate(states,1):
        links=[f'[Open]({theme}_{i:02}_{state}.png)' for theme in ('dream','blueprint','forest')]
        lines.append('| '+state.replace('_',' ')+' | '+' | '.join(links)+' |')
    for theme in ('dream','blueprint','forest'):
        lines.extend(['',f'## {theme.title()}',f'![{theme}]({theme}_01_play.png)'])
    (output/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    root=Path(__file__).resolve().parents[1]
    output=root/'docs'/'screenshots';output.mkdir(parents=True,exist_ok=True)
    paths=sorted((root/'levels').glob('stage_*.json'))
    stage=load_stage(str(paths[0]))
    pygame.init()
    app=BloxorzApp(GameSession(BloxorzProblem(stage,initial_state(stage))),paths)
    app.screen=pygame.display.set_mode((1180,800),pygame.RESIZABLE)
    pygame.display.set_caption('Bloxorz - three theme review')
    def capture(name):
        app.draw();pygame.display.flip()
        for _ in range(4):pygame.event.pump();time.sleep(.03)
        pygame.image.save(app.screen,str(output/f'{name}.png'))
        print(name,flush=True)
    try:
        app.solve()
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:
            pygame.event.pump();app.update(.016);time.sleep(.016)
        if app.busy or not app.result or not app.result.found:raise RuntimeError('Real worker failed to solve')
        path=app.result.path
        for name in ('dream','blueprint','forest'):
            app.restart();apply_theme(app,name)
            app.screen=pygame.display.set_mode((1180,800),pygame.RESIZABLE)
            capture(f'{name}_01_play')
            before=app.session.current_state
            action,after,_=app.session.problem.get_successors(before)[0]
            app.apply_action(action)
            app.animation.frame=MotionFrame(before,after,action,.5)
            capture(f'{name}_02_roll')
            app.update(1)
            capture(f'{name}_03_lying')
            app.load_replay(before,path);app.seek(3)
            capture(f'{name}_04_replay')
            app.command('settings');capture(f'{name}_05_settings')
            app.command('close_menu');app.restart()
            app.screen=pygame.display.set_mode((960,720),pygame.RESIZABLE)
            capture(f'{name}_06_compact')
            app.screen=pygame.display.set_mode((1180,800),pygame.RESIZABLE)
            app.command('choose');capture(f'{name}_07_stage_picker')
            app.command('close_menu')
            app.command('algorithm_menu');capture(f'{name}_08_algorithm_menu')
            app.command('help');capture(f'{name}_09_help')
            app.command('close_menu')
            app.command('solve');capture(f'{name}_10_searching')
            deadline=time.monotonic()+30
            while app.busy and time.monotonic()<deadline:
                pygame.event.pump();app.update(.016);time.sleep(.016)
            if app.busy or not app.result or not app.result.found:raise RuntimeError('Theme solver failed')
            capture(f'{name}_11_solution')
        write_index(output)
        print('All themes and real-solver replay captured.',flush=True)
    finally:
        app.gateway.close();pygame.quit()


if __name__=='__main__':main()

"""Actual renderer snapshots of legal standing/lying/rolling states."""
import argparse
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',choices=('before','after'),required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=root/'docs'/'screenshots'/'block_material'/args.label;output.mkdir(parents=True,exist_ok=True)
    paths=sorted((root/'levels').glob('stage_*.json'));stage=load_stage(str(paths[0]))
    pygame.init()
    app=BloxorzApp(GameSession(BloxorzProblem(stage,initial_state(stage))),paths)
    app.screen=pygame.display.set_mode((1180,800))
    pygame.display.set_caption('Bloxorz - block material review')
    def capture(name):
        app.draw();pygame.display.flip()
        pygame.event.pump();time.sleep(.04)
        pygame.image.save(app.screen,str(output/f'{name}.png'));print(name,flush=True)
    try:
        for name in ('dream','blueprint','forest'):
            app.restart();apply_theme(app,name)
            capture(f'{name}_standing')
            before=app.session.current_state
            action,after,_=app.session.problem.get_successors(before)[0]
            assert app.apply_action(action)
            app.animation.frame=MotionFrame(before,after,action,.5)
            capture(f'{name}_rolling')
            app.update(1)
            capture(f'{name}_lying')
        if args.label=='after':
            for name in ('dream','blueprint','forest'):
                sheet=pygame.Surface((1180,872));sheet.fill((24,30,35))
                font=pygame.font.Font(None,24)
                for row,pose in enumerate(('standing','lying')):
                    for col,label in enumerate(('before','after')):
                        path=output.parent/label/f'{name}_{pose}.png'
                        image=pygame.image.load(str(path))
                        x,y=col*590,row*436
                        sheet.blit(font.render(f'{name.upper()} / {pose.upper()} / {label.upper()}',True,(238,233,220)),(x+16,y+10))
                        sheet.blit(pygame.transform.smoothscale(image,(590,400)),(x,y+36))
                pygame.image.save(sheet,str(output.parent/f'{name}_comparison.png'))
    finally:
        app.gateway.close();pygame.quit()


if __name__=='__main__':main()

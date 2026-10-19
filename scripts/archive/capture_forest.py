"""Capture the running Forest variant and exercise animation / resize / switches."""
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from src.gui.app import BloxorzApp, initial_state
from src.gui.forest import enable_forest
from src.gui.contracts import MotionFrame
from src.engine.state import Action
from src.engine.loader import load_stage
from src.engine.problem import GameSession, BloxorzProblem


def main():
    root=Path(__file__).resolve().parents[1]
    paths=sorted((root/'levels').glob('stage_*.json'))
    stage=load_stage(str(paths[0]))
    app=BloxorzApp(GameSession(BloxorzProblem(stage,initial_state(stage))),paths)
    pygame.init()
    try:
        app.screen=pygame.display.set_mode((1180,800),pygame.RESIZABLE)
        pygame.display.set_caption('Bloxorz - Forest Ruins preview')
        enable_forest(app)
        app.draw(); pygame.display.flip()
        output=root/'docs'/'screenshots'; output.mkdir(exist_ok=True,parents=True)
        pygame.image.save(app.screen,str(output/'forest_opengl.png'))
        start=time.perf_counter()
        before=app.session.current_state
        problem=app.session.problem
        frames=0
        for action in (Action.UP,Action.DOWN,Action.LEFT,Action.RIGHT):
            after=problem.roll_block(before,action)
            if after is None:continue
            for t in (.0,.25,.5,.75,1.):
                app.renderer.draw(pygame.Surface((820,560)),before,MotionFrame(before,after,action,t))
                frames+=1
        print(f'{frames} animated frames: {(time.perf_counter()-start)/frames*1000:.1f} ms/frame')
        app.renderer.zoom=1.4; app.renderer.pan=(30,-20)
        app.renderer.draw(pygame.Surface((640,480)),before)
        for path in paths:
            other=load_stage(str(path)); app.renderer.set_stage(other)
            app.renderer.draw(pygame.Surface((820,560)),initial_state(other))
        print(f'Rendered {len(paths)} stages; GL error: {app.renderer.ctx.error}')
        for _ in range(10):pygame.event.pump(); time.sleep(.03)
    finally:
        app.gateway.close()
        if hasattr(app.renderer,'close'):app.renderer.close()
        pygame.quit()


if __name__=='__main__':main()

"""Repeatable CPU render benchmark; --live includes a real window and display flip."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--theme',choices=('dream','blueprint','forest'),default='dream')
    args=parser.parse_args()
    if not args.live:os.environ['SDL_VIDEODRIVER']='dummy'
    os.environ['SDL_AUDIODRIVER']='dummy'
    import pygame
    from src.gui.app import BloxorzApp,initial_state
    from src.gui.contracts import MotionFrame
    from src.engine.loader import load_stage
    from src.engine.problem import BloxorzProblem,GameSession
    pygame.init()
    paths=sorted((ROOT/'levels').glob('stage_*.json'))
    stage=load_stage(str(paths[0]))
    app=BloxorzApp(GameSession(BloxorzProblem(stage,initial_state(stage))),paths)
    app.screen=pygame.display.set_mode((1180,800))
    from src.gui.themes import apply_theme
    apply_theme(app,args.theme)
    counts={}
    originals={}
    for module,names in ((pygame.draw,('polygon','aalines','line','rect','circle','arc')),
                         (pygame.gfxdraw,('textured_polygon',))):
        for name in names:
            original=getattr(module,name)
            originals[(module,name)]=original
            def tracked(*a,_fn=original,_key=name,**kw):
                counts[_key]=counts.get(_key,0)+1
                return _fn(*a,**kw)
            setattr(module,name,tracked)
    result={'theme':args.theme,'mode':'live window + flip' if args.live else 'dummy SDL CPU-only, no display latency',
            'size':[1180,800],'python':sys.version.split()[0],'pygame':pygame.version.ver}
    def sample(label,fn):
        for i in range(12):fn(i)
        counts.clear(); times=[]
        for i in range(90):
            pygame.event.pump()
            start=perf_counter(); fn(i)
            if args.live:pygame.display.flip()
            times.append((perf_counter()-start)*1000)
        ordered=sorted(times)
        result[label]={'mean_ms':round(statistics.mean(times),3),'p95_ms':round(ordered[int(len(times)*.95)],3),
                       'max_ms':round(max(times),3),'cpu_render_fps':round(1000/statistics.mean(times),1),
                       'python_primitive_calls_per_frame':round(sum(counts.values())/90,1)}
    try:
        before=app.session.current_state
        action,after,_=app.session.problem.get_successors(before)[0]
        def moving(i):
            app.animation.frame=MotionFrame(before,after,action,(i%60)/60)
            app.animation.busy=True
            app.draw()
        sample('animated_full_gui',moving)
        app.animation.reset()
        sample('idle_full_gui',lambda i:app.draw())
        events=[]
        for _ in range(90):
            start=perf_counter(); app.handle_event(pygame.event.Event(pygame.MOUSEMOTION,pos=(600,100),rel=(0,0),buttons=(0,0,0)))
            events.append((perf_counter()-start)*1000)
        result['input_handler_ms']={'mean':round(statistics.mean(events),4),'max':round(max(events),4),
                                    'note':'synthetic mouse event dispatch only; not physical input-to-photon'}
        moves=[]
        for _ in range(20):
            app.restart()
            start=perf_counter();app.handle_event(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RIGHT))
            moves.append((perf_counter()-start)*1000)
        result['accepted_move_handler_ms']={'mean':round(statistics.mean(moves),4),'max':round(max(moves),4),
                                            'note':'synthetic key event through engine + animation scheduling; excludes device/display latency'}
        result['renderer_stats']=getattr(app.renderer,'stats',{})
        result['gpu_draw_calls']='not available: Pygame software Surface pipeline; primitive count excludes blits'
        output=ROOT/args.output
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        for (module,name),fn in originals.items():setattr(module,name,fn)
        app.gateway.close(); pygame.quit()


if __name__=='__main__':main()

import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from pathlib import Path
from time import monotonic, sleep
import pygame
import pytest
from src.engine.loader import load_stage
from src.engine.problem import BloxorzProblem, GameSession
from src.engine.state import Action, GameState, Orientation
from src.gui.app import BloxorzApp, initial_state
from src.gui.contracts import MotionFrame, ReplayStatus, SolverRequest, SolverStatus, SolverResponse, SolverResultView
from src.gui.renderer3d import state_meshes, motion_meshes, IsometricRenderer, cuboid, cuboid_samples, in_front, fall_meshes
from src.gui.renderer3d import INTRO_DROP_START, INTRO_IMPACTS, INTRO_SECONDS, intro_drop
from src.gui.animation import RollAnimation
from src.gui.replay import PathReplay
from src.gui.solver_gateway import ProcessSolverGateway
from src.solvers.uninformed import BFS

ROOT = Path(__file__).resolve().parents[1]


class FakeGateway:
    def __init__(self): self.response = None
    def submit(self, request): self.request = request
    def cancel(self, request_id): pass
    def poll(self):
        result, self.response = self.response, None
        return result
    def close(self): pass


def app_fixture():
    paths = sorted((ROOT / 'levels').glob('stage_*.json'))
    stage = load_stage(str(paths[0]))
    app = BloxorzApp(GameSession(BloxorzProblem(stage, initial_state(stage))), paths, FakeGateway())
    return app


def test_render_cache_invalidation_and_animation_reuse():
    pygame.init()
    app=app_fixture()
    renderer=app.renderer
    surface=pygame.Surface((820,630),pygame.SRCALPHA)
    before=app.session.current_state
    action,after,_=app.session.problem.get_successors(before)[0]
    renderer.draw(surface,before)
    builds=renderer.stats['static_builds']
    for progress in (.1,.25,.5,.75,.99):
        renderer.draw(surface,after,MotionFrame(before,after,action,progress))
    assert renderer.stats['static_builds']==builds
    renderer.draw(surface,after)
    renderer.draw(surface,after)
    assert renderer.stats['frame_cache_hits']>0
    renderer.zoom=1.2
    renderer.draw(surface,after)
    assert renderer.stats['static_builds']==builds+1
    renderer.high_contrast=True
    renderer.draw(surface,after)
    assert renderer.stats['static_builds']==builds+2
    renderer.set_stage(app.stage)
    renderer.draw(surface,after)
    assert renderer.stats['static_builds']==builds+3
    pygame.quit()


def test_cached_ui_motion_matches_full_composition():
    from src.gui.presentation import _draw
    pygame.init()
    app=app_fixture()
    app.screen=pygame.display.set_mode((1180,800))
    before=app.session.current_state
    action,after,_=app.session.problem.get_successors(before)[0]
    app.animation.busy=True
    app.animation.frame=MotionFrame(before,after,action,.2)
    app.draw()
    app.animation.frame=MotionFrame(before,after,action,.7)
    app.draw()
    cached=pygame.image.tobytes(app.screen,'RGB')
    _draw(app)
    assert pygame.image.tobytes(app.screen,'RGB')==cached
    assert app.draw() is False
    pygame.quit()


def test_one_buffered_move_obeys_engine_and_restart_clears_it():
    app=app_fixture()
    assert app.apply_action(Action.RIGHT)
    accepted=app.session.current_state
    app.handle_key(pygame.K_DOWN)
    assert app.session.current_state==accepted
    expected=GameSession(BloxorzProblem(app.stage,accepted))
    expected.apply_action(Action.DOWN)
    app.update(.5)
    assert app.session.current_state==expected.current_state
    assert app.pending_action is None
    app.pending_action=Action.LEFT
    app.restart()
    assert app.pending_action is None


def test_bridge_cache_and_split_rendering():
    from dataclasses import replace
    from src.engine.loader import StageData,TileType
    pygame.init()
    stage=StageData()
    stage.grid=[[TileType.FLOOR]*6 for _ in range(6)]
    stage.goal=(5,5)
    stage.bridges={'gate':[(2,2)]}
    state=GameState((1,1),(4,4),Orientation.SPLIT,0,(False,))
    renderer=IsometricRenderer();renderer.set_stage(stage)
    surface=pygame.Surface((640,480),pygame.SRCALPHA)
    renderer.draw(surface,state)
    off=pygame.image.tobytes(surface,'RGBA')
    renderer.draw(surface,replace(state,bridges_status=(True,)))
    assert renderer.stats['static_builds']==2
    assert pygame.image.tobytes(surface,'RGBA')!=off
    active=replace(state,active_cube=1,bridges_status=(True,))
    renderer.draw(surface,active)
    assert renderer.stats['static_builds']==2
    pygame.quit()


def solution(app):
    return tuple(Action(a) for a in BFS().solve(app.session.problem).path)


@pytest.mark.parametrize('name',['dream','blueprint','forest'])
def test_theme_switch_keeps_state_and_cached_animation(name):
    from src.gui.themes import apply_theme
    from src.gui.presentation import _draw
    pygame.init()
    app=app_fixture()
    app.screen=pygame.display.set_mode((1180,800))
    before=app.session.current_state
    try:
        apply_theme(app,name)
        app.draw()
        assert app.session.current_state==before
        assert {'theme','solve','undo','restart','hint'} <= {b.key for b in app.buttons}
        action,after,_=app.session.problem.get_successors(before)[0]
        app.animation.busy=True
        app.animation.frame=MotionFrame(before,after,action,.2)
        app.draw()
        builds=app.renderer.stats['static_builds']
        app.animation.frame=MotionFrame(before,after,action,.7)
        app.draw()
        cached=pygame.image.tobytes(app.screen,'RGB')
        _draw(app)
        assert pygame.image.tobytes(app.screen,'RGB')==cached
        assert app.renderer.stats['static_builds']==builds
        app.command('theme')
        assert app.session.current_state==before
        assert app.theme_name!=name
    finally:
        apply_theme(app,'dream')
        pygame.quit()


def test_bevel_template_winding_is_consistent():
    from src.gui.renderer3d import _bevel_template
    points,faces=_bevel_template(.035)
    for face in faces:
        a,b,c=(points[i] for i in face[:3])
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        center=[sum(points[i][k] for i in face)/len(face)-.5 for k in range(3)]
        assert sum(n[k]*center[k] for k in range(3))<0


def test_champagne_lighting_and_uniform_short_edge_bevel():
    from src.gui.renderer3d import cuboid,bevel_mesh
    renderer=IsometricRenderer()
    corners=cuboid(0,0,0,1,1,2)
    points,_=bevel_mesh(corners,.04,uniform=True)
    assert sorted(set(round(p[2],5) for p in points))==[0,.04,1.96,2]
    colors=[color for _,_,color,_ in renderer._faces(corners,(205,181,137),player=True)]
    values=[sum(color)/3 for color in colors]
    assert len(values)==3
    assert values[0]==max(values)  # top is the first visible main face
    assert max(values)>min(values)*1.3
    assert all(color[0]/max(1,color[1])<1.4 for color in colors)


@pytest.mark.parametrize('orientation,p2', [(Orientation.STANDING, (5, 5)),
    (Orientation.LYING_H, (5, 6)), (Orientation.LYING_V, (6, 5))])
@pytest.mark.parametrize('action', [Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT])
def test_roll_geometry_matches_engine(orientation, p2, action):
    before = GameState((5, 5), p2, orientation, 0, ())
    after = BloxorzProblem.roll_block(before, action)
    actual = motion_meshes(MotionFrame(before, after, action, 1))[0][0]
    expected = state_meshes(after)[0][0]
    assert sorted(tuple(round(c, 6) for c in p) for p in actual) == sorted(expected)


def test_animation_time_reset_and_overlap():
    app = app_fixture()
    before = app.session.current_state
    action, after, _ = app.session.problem.get_successors(before)[0]
    animation = RollAnimation(.2)
    animation.start(before, after, action)
    with pytest.raises(RuntimeError): animation.start(before, after, action)
    animation.update(.1)
    assert animation.frame.progress == pytest.approx(.5)
    animation.update(.1)
    assert not animation.busy and animation.frame is None


def test_replay_cursor_and_copy():
    replay = PathReplay()
    state = app_fixture().session.current_state
    path = [Action.RIGHT, Action.DOWN]
    replay.load(state, path)
    path.clear()
    replay.play()
    replay.pause()
    assert replay.step() == Action.RIGHT and replay.status == ReplayStatus.PAUSED
    assert replay.step() == Action.DOWN and replay.status == ReplayStatus.FINISHED
    assert replay.step() is None
    replay.load(state, [])
    assert replay.status == ReplayStatus.FINISHED


def test_solve_replay_seek_stop_save_load(tmp_path):
    app = app_fixture()
    path = solution(app)
    app.load_replay(app.session.current_state, path)
    app.replay.play()
    for _ in range(1000):
        app.update(.1)
        if app.replay.status == ReplayStatus.FINISHED and not app.animation.busy: break
    assert app.session.status == 'WON'
    assert app.actions == list(path)
    app.seek(2)
    assert app.replay.index == 2 and not app.animation.busy
    save = tmp_path / 'session.json'
    app.save(save)
    app.restart()
    app.load(save)
    assert app.replay.index == 2 and app.actions == list(path[:2])
    app.stop_replay()
    assert app.replay.status == ReplayStatus.EMPTY
    app.undo()
    assert app.actions == list(path[:1])


def test_stale_solver_result_does_not_replace_stage():
    app = app_fixture()
    app.solve()
    old_id = app.active_request
    app.select_stage(1)
    state = app.session.current_state
    app.gateway.response = SolverResponse(old_id, SolverStatus.SOLVED, SolverResultView('BFS', True))
    app.update(.1)
    assert app.result is None and app.stage_index == 1 and app.session.current_state == state


def test_invalid_save_and_path_leave_session_untouched(tmp_path):
    app = app_fixture()
    original = app.session
    path = tmp_path / 'bad.json'
    path.write_text('{"version": 77}')
    app.load(path)
    assert app.session is original
    with pytest.raises(ValueError):
        app.load_replay(app.session.current_state, [Action.UP] * 30)
    assert app.session is original


def wait_result(gateway, seconds=15):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        response = gateway.poll()
        if response is not None: return response
        sleep(.02)
    pytest.fail('Worker did not finish')


@pytest.mark.parametrize('algorithm', ['BFS', 'IDS', 'UCS', 'ASTAR'])
def test_real_worker_solution(algorithm):
    app = app_fixture()
    gateway = ProcessSolverGateway()
    try:
        gateway.submit(SolverRequest(1, algorithm, app.stage, app.session.current_state, 10))
        response = wait_result(gateway)
        assert response.status == SolverStatus.SOLVED
        for action in response.result.path:
            assert app.session.apply_action(action)
        assert app.session.status == 'WON'
    finally: gateway.close()
    assert not gateway.retired and gateway.process is None


def test_worker_timeout_cancel_and_error():
    app = app_fixture()
    gateway = ProcessSolverGateway()
    try:
        gateway.submit(SolverRequest(1, 'IDS', app.stage, app.session.current_state, .000001))
        assert wait_result(gateway).status == SolverStatus.TIMEOUT
        gateway.submit(SolverRequest(2, 'BFS', app.stage, app.session.current_state))
        gateway.cancel(2)
        assert wait_result(gateway).status == SolverStatus.CANCELLED
        gateway.submit(SolverRequest(3, 'unknown', app.stage, app.session.current_state))
        assert wait_result(gateway).status == SolverStatus.ERROR
    finally: gateway.close()


def test_render_all_stages_and_panel(tmp_path):
    pygame.init()
    app = app_fixture()
    app.screen = pygame.display.set_mode((1180, 800))
    app.font = pygame.font.Font(None, 28)
    app.title_font = pygame.font.Font(None, 38)
    for i in range(len(app.stage_paths)):
        app.select_stage(i)
        app.draw()
        assert app.renderer._faces(state_meshes(app.session.current_state)[0][0], (255, 200, 50))
        for button in app.buttons:
            assert app.screen.get_rect().contains(button.rect)
    app.select_stage(0)
    app.draw()
    pygame.image.save(app.screen, str(tmp_path / 'gui_preview.png'))
    app.command('choose')
    app.draw()
    assert any(button.key == 'stage:0' for button in app.buttons)
    pygame.quit()


def test_split_transition_and_space_undo():
    from src.engine.loader import StageData, TileType
    from src.engine.switches import SwitchData, SwitchType
    stage = StageData()
    stage.grid = [[TileType.FLOOR] * 8 for _ in range(8)]
    stage.goal = (7, 7)
    stage.switches[(2, 4)] = SwitchData(SwitchType.SPLIT, target_pos1=(1, 1), target_pos2=(4, 4))
    before = GameState((2, 2), (2, 3), Orientation.LYING_H, 0, ())
    app = BloxorzApp(GameSession(BloxorzProblem(stage, before)), gateway=FakeGateway())
    assert app.apply_action(Action.RIGHT)
    after = app.session.current_state
    assert after.orientation == Orientation.SPLIT
    meshes = motion_meshes(MotionFrame(before, after, Action.RIGHT, 1))
    assert meshes == state_meshes(after)
    app.update(1)
    assert app.apply_action(Action.SPACE)
    app.update(1)
    assert app.session.current_state.active_cube == 1
    assert app.session.moves == 1
    app.undo()
    assert app.session.moves == 1 and app.session.current_state.active_cube == 0


def test_mouse_keyboard_resize_and_pause():
    pygame.init()
    app = app_fixture()
    app.screen = pygame.display.set_mode((1180, 800))
    app.font = pygame.font.Font(None, 28)
    app.title_font = pygame.font.Font(None, 38)
    path = solution(app)
    app.load_replay(app.session.current_state, path)
    app.draw()
    button = next(b for b in app.buttons if b.key == 'play')
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center))
    assert app.replay.status == ReplayStatus.PLAYING
    app.update(.01)
    cursor = app.replay.index
    app.handle_key(pygame.K_p)
    app.update(1)
    assert app.replay.index == cursor and not app.animation.busy
    app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=1000, h=800))
    app.draw()
    assert all(app.screen.get_rect().contains(b.rect) for b in app.buttons)
    app.handle_key(pygame.K_r)
    assert app.replay.status == ReplayStatus.EMPTY and app.session.moves == 0
    app.handle_key(pygame.K_RIGHT)
    assert app.animation.busy
    app.select_stage(1)
    assert not app.animation.busy and app.session.moves == 0
    pygame.quit()


@pytest.mark.parametrize('size', [(960, 720), (1180, 800), (1440, 900)])
@pytest.mark.parametrize('large', [False, True])
def test_redesign_modes_and_layout(size, large):
    from src.gui import theme
    pygame.init()
    app = app_fixture()
    app.screen = pygame.display.set_mode(size)
    app.large_text = large
    path = solution(app)
    start = app.session.current_state
    def check():
        app.draw()
        for button in app.buttons:
            assert app.screen.get_rect().contains(button.rect), button.key
            assert theme.font('body', large).size(button.label)[0] <= button.rect.width - 8, button.label
        for i, button in enumerate(app.buttons):
            for other in app.buttons[i + 1:]:
                assert not button.rect.colliderect(other.rect), (button.key, other.key)
        return {b.key for b in app.buttons}
    keys = check()
    assert {'undo', 'restart', 'hint', 'solve'} <= keys
    assert not {'save', 'load', 'play', 'step', 'sound'} & keys
    app.command('algorithm_menu')
    assert 'algorithm:BFS' in check()
    app.command('algorithm:BFS')
    app.command('settings')
    assert {'save', 'load', 'sound', 'animate', 'camera'} <= check()
    state = app.session.current_state
    app.handle_key(pygame.K_RIGHT)
    assert app.session.current_state == state
    app.command('close_menu')
    app.command('help')
    check()
    app.command('close_menu')
    app.command('choose')
    assert 'stage:0' in check()
    app.command('close_menu')
    app.solve()
    keys = check()
    assert 'cancel' in keys and 'solve' not in keys
    app.gateway.response = SolverResponse(app.active_request, SolverStatus.SOLVED,
        SolverResultView('BFS', True, path))
    app.update(.01)
    assert 'solution' in check()
    app.command('details')
    check()
    app.load_replay(start, path)
    keys = check()
    assert {'play', 'step', 'back', 'stop', 'speed'} <= keys
    assert not {'undo', 'restart', 'hint', 'solve'} & keys
    app.command('stop')
    assert 'undo' in check()
    pygame.quit()


def test_fall_animates_then_restarts_stage():
    app = app_fixture()
    start = app.session.current_state
    assert app.apply_action(Action.UP) is False          # stage 01: rolls off the top edge
    assert app.session.status == 'LOST'
    assert app.animation.busy and app.animation.frame.falling
    app.pending_action = Action.DOWN                    # key pressed while falling is dropped
    app.update(app.FALL_SECONDS / 2)
    assert app.session.status == 'LOST'
    app.update(app.FALL_SECONDS)
    assert app.session.status == 'PLAYING' and app.session.current_state == start
    assert app.actions == [] and app.pending_action is None
    app.animate = False
    app.apply_action(Action.UP)
    app.update(.01)
    assert app.session.status == 'PLAYING'


def test_fall_frames_render_and_view_toggle(tmp_path):
    pygame.init()
    app = app_fixture()
    surface = pygame.Surface((760, 600))
    for view in ('original', 'iso'):
        app.renderer.set_view(view)
        assert app.renderer.camera.view == view
        before = app.session.current_state
        fallen = app.session.problem.fall_result(before, Action.UP)
        for progress in (0, .2, .3, .5, .8, .99):
            app.renderer.draw(surface, before, MotionFrame(before, fallen, Action.UP, progress, True))
        pygame.image.save(surface, str(tmp_path / f'fall_{view}.png'))
    app.command('view')
    assert app.renderer.view == 'original'  # V toggles original <-> iso
    pygame.quit()


def reachable_falls(stage, limit=60):
    """(before, illegal pose, action) of falls from the first `limit` states."""
    problem = BloxorzProblem(stage, initial_state(stage))
    seen = [initial_state(stage)]
    for state in seen:
        if len(seen) >= limit:
            break
        legal = {action: after for action, after, _ in problem.get_successors(state)}
        seen.extend(after for after in legal.values() if after not in seen)
        for action in (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT):
            fallen = BloxorzProblem.roll_block(state, action)
            if action not in legal and fallen is not None:
                yield state, fallen, action


def test_falling_block_never_goes_into_a_tile():
    """Off an edge, down a hole or through a broken fragile tile: the block
    tips over the edge and tumbles away, and no part of it enters a tile."""
    import collections
    paths = sorted((ROOT / 'levels').glob('stage_*.json'))
    renderer = IsometricRenderer()
    plans = collections.Counter()
    for index in (0, 3, 32):  # plain edges, fragile tiles, a hole in the board
        renderer.set_stage(load_stage(str(paths[index])))
        for view in ('original', 'iso'):
            renderer.set_view(view)
            for before, fallen, action in reachable_falls(renderer.stage):
                motion = MotionFrame(before, fallen, action, .5, True)
                tip = renderer._tip(fallen, action)
                plan = renderer._fall_plan(motion, tip)
                plans[plan] += 1
                assert tip is None or not renderer._fall_hits_tiles(motion, tip, plan), (index, before, action)
    assert plans['tumble'] > plans['straight'] > 0


def test_tiles_in_front_of_the_block_hide_it():
    pygame.init()
    app = app_fixture()
    renderer = app.renderer
    tile = cuboid(2.03, 2.03, -.55, .94, .94, .55)
    for view in ('original', 'iso'):
        renderer.set_view(view)
        camera = renderer.camera
        assert in_front(cuboid(2, 2, 0, 1, 1, 2), tile, camera)        # standing on it
        assert not in_front(cuboid(2, 2, -3, 1, 1, 1), tile, camera)   # below it
        assert in_front(cuboid(3, 2, -1, 1, 1, 1), tile, camera)       # past its near side
        assert not in_front(cuboid(1, 2, -1, 1, 1, 1), tile, camera)   # past its far side
    renderer.set_view('original')
    surface = pygame.Surface((830, 630), pygame.SRCALPHA)
    mask = app.session.current_state.bridges_status

    def fall_frame(start, action, progress):
        before = GameState(start, start, Orientation.STANDING, 0, mask)
        motion = MotionFrame(before, BloxorzProblem.roll_block(before, action), action, progress, True)
        surface.fill((0, 0, 0, 0))
        renderer.draw(surface, before, motion)
        return motion

    # Off the far edge: the board hides the block, not even a tint shows through.
    fall_frame((1, 1), Action.UP, .8)
    base = renderer._base
    for x in range(0, 830, 3):
        for y in range(0, 630, 3):
            if base.get_at((x, y)).a == 255:
                assert surface.get_at((x, y)) == base.get_at((x, y)), (x, y)
    # Off the near edge (toward the viewer): the block is in front of the tiles
    # it fell from (row 4), also where it is below the board top.
    def opaque(sprites, x, y, alpha=255):
        return any(spr.get_rect(topleft=xy).collidepoint(x, y) and spr.get_at((x - xy[0], y - xy[1])).a >= alpha
                   for spr, xy in sprites)
    edge = [(spr, xy) for _, spr, xy, cell, *_ in renderer._tile_sprites if cell[0] == 4]
    others = [(spr, xy) for _, spr, xy, cell, *_ in renderer._tile_sprites if cell[0] != 4]
    checked = 0
    for progress in [i / 40 for i in range(12, 40)]:
        motion = fall_frame((3, 9), Action.DOWN, progress)
        tip = renderer._tip(motion.after, motion.action)
        corners = fall_meshes(motion, tip, renderer._fall_plan(motion, tip))[0][0]
        centre = [sum(p[i] for p in corners) / 8 for i in range(3)]
        inner = [tuple(m + (v - m) * .8 for v, m in zip(p, centre)) for p in corners]  # off the outline
        for point in cuboid_samples(inner, 8):
            x, y = (round(v) for v in renderer.project(point))
            if point[2] < 0 and opaque(edge, x, y) and not opaque(others, x, y, alpha=1):
                assert surface.get_at((x, y)) != renderer._base.get_at((x, y)), (progress, point)
                checked += 1
    assert checked > 10
    pygame.quit()


def win_manually(app):
    path = solution(app)
    for action in path:
        while app.animation.busy:
            app.update(.02)
        assert app.apply_action(action)
    return path


def test_manual_win_sinks_then_offers_next_stage():
    app = app_fixture()
    win_manually(app)
    assert app.session.status == 'WON' and app.win_phase == 'roll'
    for _ in range(15):
        app.update(.02)
    assert app.win_phase == 'sink' and app.animation.frame.sinking
    for _ in range(200):
        app.update(.02)
        if app.win_phase == 'choice':
            break
    # Waits for the player instead of loading the next stage by itself.
    assert app.win_phase == 'choice' and app.stage_index == 0 and app.session.status == 'WON'
    app.undo()
    assert app.session.status == 'WON'
    app.command('next_stage')
    assert app.stage_index == 1 and app.session.status == 'PLAYING'
    assert app.session.moves == 0 and app.win_phase is None and not app.stage_cleared


def test_manual_win_replay_returns_to_choice():
    app = app_fixture()
    path = win_manually(app)
    for _ in range(200):
        app.update(.02)
        if app.win_phase == 'choice':
            break
    assert app.win_phase == 'choice'
    app.command('win_replay')
    assert app.replay.status == ReplayStatus.PLAYING and app.win_phase is None
    assert app.replay.path == tuple(path) and app.session.moves == 0
    for _ in range(600):
        app.update(.05)
    assert app.replay.status == ReplayStatus.FINISHED and app.stage_index == 0
    app.seek(1)
    app.command('stop')
    assert app.replay.status == ReplayStatus.EMPTY and app.win_phase == 'choice'
    assert app.session.status == 'WON' and app.actions == list(path)
    app.handle_key(pygame.K_RETURN)
    assert app.stage_index == 1


def test_replay_win_does_not_change_stage():
    app = app_fixture()
    app.load_replay(app.session.current_state, solution(app))
    app.replay.play()
    for _ in range(600):
        app.update(.05)
    assert app.session.status == 'WON' and app.stage_index == 0


def test_sound_events_follow_gameplay():
    class Recorder:
        def __init__(self): self.log = []
        def play(self, name='roll', volume=1.0): self.log.append(name)
    app = app_fixture()
    app.sound, app.sound_enabled, app.animate = Recorder(), True, False
    assert app.apply_action(Action.UP) is False          # stage 01: falls off the top edge
    assert app.sound.log == ['fall']
    app.update(.01)
    for action in solution(app):
        app.apply_action(action)
    assert app.sound.log[-1] == 'win' and app.sound.log.count('roll') >= 1


def test_stage_intro_block_drops_and_bounces():
    """The block falls under gravity, bounces lower each time and comes to
    rest; each bounce thuds more softly, and every intro frame draws."""
    assert intro_drop(INTRO_DROP_START - .01) is None  # not released yet
    steps = [i / 480 for i in range(round(INTRO_DROP_START * 480), round(INTRO_SECONDS * 480) + 1)]
    heights = [intro_drop(t)[0] for t in steps]
    assert heights[0] > 5 and heights[-1] == 0.0 and intro_drop(INTRO_SECONDS) == (0.0, 0.0)
    peaks = [b for a, b, c in zip(heights, heights[1:], heights[2:]) if a < b >= c and b > .01]
    assert len(peaks) >= 2 and .5 < peaks[0] < 1.5 and peaks == sorted(peaks, reverse=True)
    first_hit = INTRO_IMPACTS[0][0]
    assert intro_drop(first_hit + .03)[1] > .05  # squashed for a moment on impact
    assert all(height == 0.0 for height in heights[-10:])  # at rest before the intro ends

    class Recorder:
        def __init__(self): self.log = []
        def play(self, name='roll', volume=1.0): self.log.append((name, volume))
    pygame.init()
    app = app_fixture()
    app.screen = pygame.Surface((1180, 742))
    app.sound, app.sound_enabled, app.animate = Recorder(), True, True
    app.restart()
    for _ in range(200):
        app.update(1 / 60)
        app.draw()
        if app.intro_t is None:
            break
    assert app.intro_t is None
    thuds = [volume for name, volume in app.sound.log if name == 'roll']
    assert len(thuds) == len(INTRO_IMPACTS) and thuds[0] == 1.0 and thuds == sorted(thuds, reverse=True)
    pygame.quit()


def test_fragile_tile_breaks_when_block_stands_on_it():
    pygame.init()
    app = app_fixture()
    app.select_stage(3)  # stage 04 has fragile tiles
    before = GameState((5, 7), (5, 8), Orientation.LYING_H, 0, ())
    fallen = app.session.problem.fall_result(before, Action.RIGHT)
    assert fallen.orientation == Orientation.STANDING and fallen.pos1 == (5, 9)
    renderer = app.renderer
    assert renderer._broken_tile(fallen) == (5, 9)
    assert renderer._broken_tile(before) is None  # lying blocks never break tiles
    surface = pygame.Surface((760, 600))
    renderer.draw(surface, before, MotionFrame(before, fallen, Action.RIGHT, .1, True))
    assert renderer._static_key[-1] is None  # still rolling onto the tile
    renderer.draw(surface, before, MotionFrame(before, fallen, Action.RIGHT, .6, True))
    assert renderer._static_key[-1] == (5, 9)  # the board is rebuilt without it
    pygame.quit()


def test_switch_press_rolls_at_normal_speed_then_bridge_flies():
    import collections
    pygame.init()
    app = app_fixture()
    app.select_stage(1)  # stage 02: a soft switch opens a bridge
    problem, start = app.session.problem, app.session.current_state
    previous, queue, goal = {start: None}, collections.deque([start]), None
    while queue and goal is None:
        state = queue.popleft()
        for action, nxt, _ in problem.get_successors(state):
            if nxt in previous:
                continue
            previous[nxt] = (state, action)
            if nxt.bridges_status != state.bridges_status:
                goal = nxt
                break
            queue.append(nxt)
    path, node = [], goal
    while previous[node]:
        node, action = previous[node]
        path.append(action)
    path.reverse()
    for action in path[:-1]:
        assert app.apply_action(action)
        while app.animation.busy:
            app.update(.01)
    assert app.apply_action(path[-1])
    # The roll that presses the switch is as fast as any other roll.
    assert abs(app.animation.duration_sec - app.ROLL_SECONDS) < 1e-9
    assert app.bridge_fx is None  # the bridge waits for the block to land...
    queued = app.bridge_view()
    assert queued is not None and queued[2] == 0.0  # ...and is shown at its starting pose
    changed = [i for i, (a, b) in enumerate(zip(queued[0], queued[1])) if a != b]
    bridge_cells = {cell for cell, i in app.renderer.bridge_cells.items() if i in changed}
    surface = pygame.Surface((830, 630), pygame.SRCALPHA)
    app.update(app.ROLL_SECONDS * .8)  # past the point where the board used to switch over
    app.renderer.draw(surface, app.session.current_state, app.animation.frame, bridges=app.bridge_view())
    on_board = {cell for _, _, _, cell, *_ in app.renderer._tile_sprites}
    assert bridge_cells and not bridge_cells & on_board  # no early pop-in of the new bridge
    rolled = app.ROLL_SECONDS * .8
    while app.animation.busy:
        app.update(.01)
        rolled += .01
    assert rolled <= app.ROLL_SECONDS + .02
    old, new, progress = app.bridge_fx
    assert old != new and progress == 0.0
    surface = pygame.Surface((830, 630), pygame.SRCALPHA)
    flown = 0.0
    while app.bridge_fx is not None:
        app.renderer.draw(surface, app.session.current_state, app.animation.frame, bridges=app.bridge_fx)
        app.update(.02)
        flown += .02
    assert abs(flown - app.BRIDGE_SECONDS) < .05
    # The block can move again right away; the bridge never blocks input.
    app.undo()
    assert app.bridge_fx is None and app.session.current_state.bridges_status == old
    pygame.quit()


def test_win_sequence_draws_every_frame_and_board_stays_gone():
    """Draw the whole win sequence (sink, falling tiles, dialog) like the game
    does, on a 1x screen and through the Retina present() path."""
    pygame.init()

    class RetinaWindow:  # a 2x window surface, like a MacBook screen
        def __init__(self, size):
            self.size, self.surface = size, pygame.Surface((size[0] * 2, size[1] * 2))

        def get_surface(self):
            return self.surface

        def flip(self):
            pass

    for retina in (False, True):
        app = app_fixture()
        app.screen = pygame.Surface((1180, 742))
        if retina:
            app.window, app.hidpi = RetinaWindow((1180, 742)), 2
        win_manually(app)
        phases = []
        for _ in range(400):
            app.update(1 / 60)
            if app.draw() and retina:
                app.present()
            phases.append(app.win_phase)
            if app.win_phase == 'choice':
                break
        assert {'sink', 'disassemble', 'choice'} <= set(phases)
        # The block sank and the tiles fell away: nothing comes back up.
        assert app.board_outro() == 1.0
        frame = pygame.Surface((830, 630), pygame.SRCALPHA)
        app.renderer.draw(frame, app.session.current_state, None, outro_t=app.board_outro())
        assert frame.get_bounding_rect().width == 0  # an empty board
        app.command('next_stage')
        assert app.board_outro() is None and app.stage_index == 1
    pygame.quit()


def test_frame_pacer_targets_even_60_fps():
    from src.gui.app import FramePacer
    # 60 FPS on 60/120/240 Hz screens (every frame shows for the same number of
    # refreshes); 72 FPS on 144 Hz.
    assert abs(FramePacer(60).frame_s - 1 / 60) < 1e-9
    assert abs(FramePacer(120).frame_s - 1 / 60) < 1e-9
    assert abs(FramePacer(240).frame_s - 1 / 60) < 1e-9
    assert abs(FramePacer(144).frame_s - 1 / 72) < 1e-9
    assert abs(FramePacer(0).frame_s - 1 / 60) < 1e-9  # unknown rate

    class Window:
        flips = 0

        def flip(self):
            self.flips += 1

    pacer, window = FramePacer(120), Window()
    pacer.wait_and_flip(window, drew=True)
    pacer.wait_and_flip(window, drew=False)  # nothing new: wait, but do not flip
    assert window.flips == 1


def test_switch_boards_are_ready_before_the_press():
    """Pressing a switch must not compose a board on the spot (that was a hitch):
    boards for bridge layouts a move or two away are composed while idle."""
    import collections
    from src.gui.renderer3d import _Bridges
    pygame.init()
    app = app_fixture()
    app.screen = pygame.Surface((1180, 742))
    app.select_stage(4)  # stage 05: its first switch closes an open bridge
    problem, start = app.session.problem, app.session.current_state
    previous, queue, goal = {start: None}, collections.deque([start]), None
    while queue and goal is None:
        state = queue.popleft()
        for action, nxt, _ in problem.get_successors(state):
            if nxt in previous:
                continue
            previous[nxt] = (state, action)
            if nxt.bridges_status != state.bridges_status:
                goal = nxt
                break
            queue.append(nxt)
    path, node = [], goal
    while previous[node]:
        node, action = previous[node]
        path.append(action)
    path.reverse()
    for action in path[:-1]:
        assert app.apply_action(action)
        while app.animation.busy:
            app.update(1 / 60)
            app.draw()
    for _ in range(60):  # a second of standing next to the switch
        app.update(1 / 60)
        app.draw()
    before = app.session.current_state.bridges_status
    during = tuple(a and b for a, b in zip(before, goal.bridges_status))
    renderer = app.renderer
    for status in (during, goal.bridges_status):
        key = renderer._base_key(renderer._active_cells(_Bridges(status)))
        assert key in renderer._base_cache, status
    composed = []
    original = renderer._compose_board
    renderer._compose_board = lambda *args: (composed.append(args), original(*args))[1]
    assert app.apply_action(path[-1])
    app.update(1 / 60)
    app.draw()  # the frame the switch is pressed
    assert not composed
    pygame.quit()

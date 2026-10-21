"""GUI orchestration: engine is the only source of game rules."""
from __future__ import annotations
import json
from pathlib import Path
import pygame
from src.engine.loader import load_stage
from src.engine.problem import BloxorzProblem, GameSession
from src.engine.state import Action, GameState, Orientation
from src.gui.animation import RollAnimation
from src.gui.replay import PathReplay
from src.gui.renderer3d import IsometricRenderer, VIEWS
from src.gui.solver_gateway import ProcessSolverGateway
from src.gui.contracts import SolverRequest, SolverStatus, ReplayStatus
from src.gui import theme
from src.gui.presentation import draw as draw_presentation, sharp_board

ROOT = Path(__file__).resolve().parents[2]
SAVE_PATH = ROOT / 'data' / 'gui_session.json'


def initial_state(stage):
    return GameState(stage.start, stage.start, Orientation.STANDING, 0, stage.initial_bridge_mask)


def state_dict(state):
    return dict(pos1=list(state.pos1), pos2=list(state.pos2), orientation=state.orientation.value,
                active_cube=state.active_cube, bridges_status=list(state.bridges_status))


def read_state(data):
    for name in ('pos1', 'pos2'):
        if not isinstance(data[name], list) or len(data[name]) != 2 or any(type(x) is not int for x in data[name]):
            raise ValueError('Invalid coordinates.')
    if type(data['active_cube']) is not int or any(type(x) is not bool for x in data['bridges_status']):
        raise ValueError('Invalid state.')
    state = GameState(tuple(data['pos1']), tuple(data['pos2']), Orientation(data['orientation']),
                      data['active_cube'], tuple(data['bridges_status']))
    dr = abs(state.pos1[0] - state.pos2[0])
    dc = abs(state.pos1[1] - state.pos2[1])
    valid = {Orientation.STANDING: dr + dc == 0, Orientation.LYING_H: dr == 0 and dc == 1,
             Orientation.LYING_V: dr == 1 and dc == 0,
             Orientation.SPLIT: dr + dc >= 1 and state.active_cube in (0, 1)}
    if not valid[state.orientation]:
        raise ValueError('Invalid block orientation.')
    return state


class BloxorzApp:
    WINDOW_SIZE = (1180, 800)
    FALL_SECONDS = 0.9  # roll to the edge, tip over and drop, then restart
    WIN_SECONDS = 0.8   # sink into the goal hole, then load the next stage

    def __init__(self, session, stage_paths=None, gateway=None):
        self.session = session
        self.stage = session.problem.stage_data
        self.stage_paths = list(stage_paths or [])
        self.stage_index = 0
        self.renderer = IsometricRenderer()
        self.renderer.set_stage(self.stage)
        self.animation = RollAnimation()
        self.replay = PathReplay()
        self.gateway = gateway or ProcessSolverGateway()
        self.record_start = session.current_state
        self.actions = []
        self.request_id = 0
        self.active_request = None
        self.solve_start = None
        self.hint_mode = False
        self.algorithm = 'ASTAR'
        self.solve_current = True
        self.solver_status = SolverStatus.IDLE
        self.result = None
        self.speed = 1.0
        self.wait = 0.0
        self.animate = True
        self.sound_enabled = True  # on by default; Settings > Sound turns it off
        self.high_contrast = False
        self.large_text = False
        self.sound = None
        self.zoom = 1.0
        self.pan = [0, 0]
        self.dragging = False
        self.stage_picker = False
        self.picker_page = 0
        self.menu = None
        self.dropdown_open = False
        self.details_open = False
        self.modal_rect = pygame.Rect(0, 0, 0, 0)
        self.dropdown_rect = pygame.Rect(0, 0, 0, 0)
        self.message = 'Roll with arrows or WASD. Reach G standing upright.'
        self.screen = None  # logical (1x) frame the UI is laid out on
        self.window = None  # run(): HiDPI window; its surface may be 2x the screen
        self.hidpi = 1
        self._hi_base = self._hi_board = None
        self.buttons = []
        self.seek_rect = pygame.Rect(0, 0, 0, 0)
        self.board_rect = pygame.Rect(0, 0, 1, 1)
        self.font = self.small_font = self.title_font = None
        self.pending_action = None
        # Win sequence (manual play only): 'roll' -> 'sink' -> 'choice' (replay or next stage).
        self.win_phase = None
        self.stage_cleared = False  # survives replaying the winning moves

    @property
    def busy(self):
        return self.active_request is not None

    def invalidate(self):
        self.pending_action = None
        if self.active_request is not None:
            self.gateway.cancel(self.active_request)
        self.active_request = None
        self.request_id += 1
        self.animation.reset()
        self.replay.reset()
        self.result = None
        self.solver_status = SolverStatus.IDLE
        self.wait = 0
        self.stage_cleared = False

    def new_session(self, state):
        self.win_phase = None  # any reload/restart/replay cancels the win sequence
        self.session = GameSession(BloxorzProblem(self.stage, state))
        if self.session.problem.is_goal(state):
            self.session.status = 'WON'
        self.record_start = state
        self.actions = []

    def select_stage(self, index):
        if not 0 <= index < len(self.stage_paths):
            return
        try:
            stage = load_stage(str(self.stage_paths[index]))
        except (ValueError, OSError) as error:
            self.message = f'Cannot load stage: {error}'
            return
        self.invalidate()
        self.stage, self.stage_index = stage, index
        self.new_session(initial_state(stage))
        self.renderer.set_stage(stage)
        self.zoom, self.pan = 1.0, [0, 0]
        self.stage_picker = False
        self.message = 'Stage loaded. Arrow keys / WASD to roll.'

    def restart(self):
        self.invalidate()
        self.new_session(initial_state(self.stage))
        self.message = 'Stage restarted.'

    def apply_action(self, action, replay=False):
        if self.busy or self.animation.busy:
            return False
        if not replay and self.replay.status != ReplayStatus.EMPTY:
            self.message = 'Exit replay to play manually.'
            return False
        if self.session.status == 'WON':
            return False  # stage already finished; the win sequence takes over
        before = self.session.current_state
        if not self.session.apply_action(action):
            fallen = None if replay else self.session.fall(action)
            if fallen is not None:
                self.start_fall(before, fallen, action)
            else:
                self.message = 'Blocked. Keep the whole block on solid ground.'
            return False
        self.actions.append(action)
        self.session.moves = sum(a != Action.SPACE for a in self.actions)
        if self.animate:
            self.animation.duration_sec = 0.18 / self.speed
            self.animation.start(before, self.session.current_state, action)
        self.result = self.result if replay else None
        if not replay:
            self.solver_status = SolverStatus.IDLE
            if self.session.status == 'WON':
                self.win_phase = 'roll'  # update() starts the sink once the roll ends
        after = self.session.current_state
        if action != Action.SPACE:
            self.play_sfx('roll')
        if after.bridges_status != before.bridges_status:
            self.play_sfx('switch')
        if after.orientation == Orientation.SPLIT and before.orientation != Orientation.SPLIT:
            self.play_sfx('split')
        if self.session.status == 'WON':
            self.play_sfx('win')
        self.message = 'Rolling...' if self.animation.busy else 'Move accepted.'
        return True

    def start_fall(self, before, fallen, action):
        """The block rolled off the board (session.status is now 'LOST').

        Play the fall animation; update() restarts the stage once it ends.
        Without animation the restart happens on the next update().
        """
        self.pending_action = None
        self.result = None
        self.solver_status = SolverStatus.IDLE
        self.message = 'You fell off the board!'
        self.play_sfx('fall')
        if self.animate:
            self.animation.duration_sec = self.FALL_SECONDS
            self.animation.start(before, fallen, action, falling=True)

    def play_sfx(self, name):
        """Play one sound effect (see src/gui/sfx.py) if sound is on."""
        if self.sound_enabled and self.sound:
            self.sound.play(name)

    def finish_fall(self):
        self.restart()
        self.message = 'You fell off. Stage restarted - try again!'

    def advance_win(self):
        """Called every update(): drive the win sequence one step forward."""
        if self.win_phase in (None, 'choice') or self.animation.busy:
            return
        if self.session.status != 'WON':  # e.g. undone before the sink started
            self.win_phase = None
            return
        if self.win_phase == 'roll' and self.animate:
            goal = self.session.current_state
            self.animation.duration_sec = self.WIN_SECONDS
            self.animation.start(goal, goal, self.actions[-1], sinking=True)
            self.win_phase = 'sink'
            self.message = 'Stage complete!'
            return
        # Sink finished (or animation is off): let the player replay or move on.
        self.win_phase = 'choice'
        self.stage_cleared = True
        self.message = 'Stage complete!'

    def next_stage(self):
        moves = self.session.moves
        if self.stage_index + 1 < len(self.stage_paths):
            self.select_stage(self.stage_index + 1)
            self.message = (f'Stage {self.stage_index:02} done in {moves} moves. '
                            f'Now playing stage {self.stage_index + 1:02}.')
        else:
            self.message = f'Last stage done in {moves} moves - you finished every stage!'

    def replay_win(self):
        """Watch the winning moves from the start; Exit replay returns to the choice."""
        self.load_replay(self.record_start, tuple(self.actions))
        self.replay.play()
        self.message = 'Replaying your moves.'

    def undo(self):
        if (self.busy or self.animation.busy or self.replay.status != ReplayStatus.EMPTY
                or self.win_phase == 'choice'):
            return
        if not self.actions:
            self.message = 'No move to undo.'
            return
        self.session.undo()
        self.actions.pop()
        self.session.moves = sum(a != Action.SPACE for a in self.actions)
        self.result = None
        self.solver_status = SolverStatus.IDLE
        self.message = 'Last move undone.'

    def solve(self, hint=False):
        if self.busy or self.animation.busy or self.replay.status != ReplayStatus.EMPTY:
            return
        self.request_id += 1
        self.solve_start = self.session.current_state if hint or self.solve_current else initial_state(self.stage)
        request = SolverRequest(self.request_id, self.algorithm, self.stage, self.solve_start, 30.0)
        try:
            self.gateway.submit(request)
        except Exception as error:
            self.message = f'Cannot start solver: {error}'
            return
        self.active_request = request.request_id
        self.hint_mode = hint
        self.result = None
        self.solver_status = SolverStatus.RUNNING
        self.message = 'Finding a hint...' if hint else 'Searching (30 second limit)...'

    def load_replay(self, start, path):
        # Validate the whole path before replacing the current session.
        probe = GameSession(BloxorzProblem(self.stage, start))
        if not probe.problem.check_validity(start):
            raise ValueError('Replay initial state is unsupported.')
        for action in path:
            if not probe.apply_action(action):
                raise ValueError('Replay contains an invalid move.')
        self.animation.reset()
        self.new_session(start)
        self.replay.load(start, path)
        self.wait = 0
        self.message = 'Press Play or Next to watch the solution.'

    def replay_step(self):
        if self.animation.busy or self.busy:
            return
        action = self.replay.step()
        if action is not None and not self.apply_action(action, replay=True):
            self.replay.reset()
            self.message = 'Replay stopped: invalid move.'

    def seek(self, index):
        if self.busy or self.replay.initial_state is None:
            return
        start, path = self.replay.initial_state, self.replay.path
        index = max(0, min(len(path), index))
        self.animation.reset()
        self.new_session(start)
        for action in path[:index]:
            if not self.session.apply_action(action):
                self.replay.reset()
                self.message = 'Replay stopped: invalid path.'
                return
            self.actions.append(action)
        self.session.moves = sum(a != Action.SPACE for a in self.actions)
        self.replay.load(start, path)
        self.replay.index = index
        self.replay.status = ReplayStatus.FINISHED if index == len(path) else ReplayStatus.PAUSED
        self.wait = 0
        self.message = f'Replay at move {index}/{len(path)}.'

    def stop_replay(self):
        if self.animation.busy:
            self.animation.reset()
        if self.stage_cleared and self.replay.initial_state is not None:
            # Watching a finished stage: jump back to the goal and offer the choice again.
            self.seek(self.replay.length)
            self.replay.reset()
            self.win_phase = 'choice'
            self.message = 'Stage complete!'
            return
        self.replay.reset()
        self.message = 'Continue playing from here.'

    def save(self, path=SAVE_PATH):
        if self.busy or self.animation.busy:
            self.message = 'Wait for the current action before saving.'
            return
        if not self.stage_paths:
            self.message = 'This stage has no file to save.'
            return
        data = {'version': 1, 'stage': self.stage_paths[self.stage_index].name,
                'initial_state': state_dict(self.record_start), 'actions': [a.value for a in self.actions],
                'replay': None, 'settings': {'animate': self.animate, 'sound': self.sound_enabled,
                'contrast': self.high_contrast, 'large_text': self.large_text, 'speed': self.speed,
                'view': self.renderer.view}}
        if self.replay.initial_state is not None:
            data['replay'] = {'initial_state': state_dict(self.replay.initial_state),
                'path': [a.value for a in self.replay.path], 'index': self.replay.index}
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temporary.replace(path)
            self.message = 'Session saved.'
        except OSError as error:
            self.message = f'Save failed: {error}'

    def load(self, path=SAVE_PATH):
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('Save must be an object.')
            if data['version'] != 1:
                raise ValueError('Unsupported save version.')
            index = next(i for i, p in enumerate(self.stage_paths) if p.name == data['stage'])
            stage = load_stage(str(self.stage_paths[index]))
            start = read_state(data['initial_state'])
            actions = tuple(Action(a) for a in data['actions'])
            problem = BloxorzProblem(stage, start)
            if len(start.bridges_status) != len(stage.bridges) or not problem.check_validity(start):
                raise ValueError('Saved state does not fit stage.')
            probe = GameSession(problem)
            for action in actions:
                if not probe.apply_action(action):
                    raise ValueError('Saved path is invalid.')
            replay_data = data.get('replay')
            if replay_data:
                replay_start = read_state(replay_data['initial_state'])
                replay_path = tuple(Action(a) for a in replay_data['path'])
                cursor = replay_data['index']
                if type(cursor) is not int or not 0 <= cursor <= len(replay_path):
                    raise ValueError('Invalid replay cursor.')
                if replay_start != start or actions != replay_path[:cursor]:
                    raise ValueError('Replay and session disagree.')
                check = GameSession(BloxorzProblem(stage, replay_start))
                for action in replay_path:
                    if not check.apply_action(action):
                        raise ValueError('Invalid replay path.')
            settings = data.get('settings', {})
            if not isinstance(settings, dict):
                raise ValueError('Invalid settings.')
            speed = float(settings.get('speed', 1))
            if speed not in (0.5, 1, 2, 4):
                raise ValueError('Invalid playback speed.')
            view = settings.get('view', self.renderer.view)
            if view == 'front':  # removed view; older saves fall back to the default
                view = VIEWS[0]
            if view not in VIEWS:
                raise ValueError('Invalid camera view.')
        except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
            self.message = f'Load failed: {error}'
            return
        self.invalidate()
        self.stage, self.stage_index = stage, index
        self.renderer.set_stage(stage)
        self.new_session(start)
        self.session = probe
        self.actions = list(actions)
        self.session.moves = sum(a != Action.SPACE for a in actions)
        if self.session.problem.is_goal(self.session.current_state):
            self.session.status = 'WON'
        if replay_data:
            self.replay.load(replay_start, replay_path)
            self.replay.index = cursor
            self.replay.status = ReplayStatus.FINISHED if cursor == len(replay_path) else ReplayStatus.PAUSED
        self.animate = bool(settings.get('animate', True))
        self.sound_enabled = bool(settings.get('sound', True)) and self.sound is not None
        self.high_contrast = bool(settings.get('contrast', False))
        self.large_text = bool(settings.get('large_text', False))
        self.speed = speed
        self.renderer.set_view(view)
        self.zoom, self.pan = 1.0, [0, 0]
        self.stage_picker = False
        self.message = 'Session loaded.'

    def update(self, dt):
        self.animation.update(dt)
        if self.session.status == 'LOST' and not self.animation.busy:
            self.finish_fall()
        self.advance_win()
        response = self.gateway.poll()
        if response is not None and response.request_id == self.active_request:
            self.active_request = None
            self.solver_status, self.result = response.status, response.result
            if response.status == SolverStatus.SOLVED:
                if self.hint_mode:
                    self.message = ('Hint: ' + response.result.path[0].value.lower()) if response.result.path else 'Already at goal.'
                else:
                    self.message = 'Your solution is ready.'
            else:
                self.message = response.result.error or response.status.value.replace('_', ' ')
        if (self.pending_action is not None and not self.animation.busy and not self.busy
                and self.replay.status == ReplayStatus.EMPTY and not (self.menu or self.stage_picker or self.dropdown_open)):
            action,self.pending_action=self.pending_action,None
            self.apply_action(action)
        if self.replay.status == ReplayStatus.PLAYING and not self.animation.busy:
            self.wait -= dt
            if self.wait <= 0:
                self.replay_step()
                self.wait = 0.12 / self.speed
        if (self.session.status == 'WON' and self.win_phase is None and not self.animation.busy
                and not self.busy and self.replay.status != ReplayStatus.EMPTY):
            self.message = ('Replay finished. Exit replay to continue.' if self.stage_cleared
                            else 'Stage complete. Choose another stage above.')

    def handle_key(self, key):
        if self.stage_picker or self.menu or self.dropdown_open:
            if key == pygame.K_ESCAPE:
                self.stage_picker = False
                self.menu = None
                self.dropdown_open = False
            return
        shortcuts = {pygame.K_r: 'restart', pygame.K_z: 'undo', pygame.K_p: 'play',
                     pygame.K_F5: 'save', pygame.K_F9: 'load', pygame.K_PERIOD: 'step',
                     pygame.K_COMMA: 'back', pygame.K_HOME: 'camera', pygame.K_v: 'view'}
        if self.win_phase == 'choice' and key == pygame.K_p:
            self.command('win_replay')
            return
        if key in shortcuts:
            self.command(shortcuts[key])
            return
        if key == pygame.K_RETURN and self.session.status == 'WON':
            self.next_stage()
            return
        mapping = {pygame.K_UP: Action.UP, pygame.K_w: Action.UP, pygame.K_DOWN: Action.DOWN,
                   pygame.K_s: Action.DOWN, pygame.K_LEFT: Action.LEFT, pygame.K_a: Action.LEFT,
                   pygame.K_RIGHT: Action.RIGHT, pygame.K_d: Action.RIGHT, pygame.K_SPACE: Action.SPACE}
        if key in mapping:
            if self.animation.busy and not self.busy and self.replay.status == ReplayStatus.EMPTY:
                self.pending_action=mapping[key]
            else:self.apply_action(mapping[key])

    def command(self, key):
        if key == 'theme':
            from src.gui.themes import cycle_theme
            cycle_theme(self)
            return
        if key in ('settings', 'help'):
            self.pending_action = None
            self.menu = key
            self.dropdown_open = False
            self.replay.pause()
            return
        if key == 'close_menu':
            self.menu = None
            self.stage_picker = False
            return
        if key == 'algorithm_menu':
            self.dropdown_open = not self.dropdown_open
            return
        if key in ('source_start', 'source_current'):
            self.solve_current = key == 'source_current'
            return
        if key == 'details':
            self.details_open = not self.details_open
            return
        if key == 'new_search':
            self.result = None
            self.solver_status = SolverStatus.IDLE
            self.details_open = False
            return
        if key == 'rewind':
            self.seek(0)
            return
        if key in ('load', 'recording'):
            self.menu = None
        if key.startswith('stage:'):
            self.select_stage(int(key.split(':')[1]))
        elif key == 'choose':
            self.stage_picker = not self.stage_picker
            self.picker_page = self.stage_index // 20
            if self.stage_picker:
                self.replay.pause()
        elif key == 'page_prev':
            self.picker_page = max(0, self.picker_page - 1)
        elif key == 'page_next':
            self.picker_page = min((len(self.stage_paths) - 1) // 20, self.picker_page + 1)
        elif key == 'next_stage': self.next_stage()
        elif key == 'win_replay' and self.actions and not self.busy: self.replay_win()
        elif key == 'restart': self.restart()
        elif key == 'undo': self.undo()
        elif key == 'solve': self.solve()
        elif key == 'hint': self.solve(True)
        elif key == 'cancel' and self.busy:
            self.gateway.cancel(self.active_request)
        elif key.startswith('algorithm:') and not self.busy:
            self.algorithm = key.split(':')[1]
            self.dropdown_open = False
        elif key == 'source' and not self.busy:
            self.solve_current = not self.solve_current
        elif key == 'solution' and self.result and self.result.found and not self.busy:
            self.load_replay(self.solve_start, self.result.path)
        elif key == 'recording' and self.actions and not self.busy:
            self.load_replay(self.record_start, tuple(self.actions))
        elif key == 'play' and not self.busy:
            if self.replay.status == ReplayStatus.PLAYING:
                self.replay.pause()
            else:
                if self.replay.status == ReplayStatus.FINISHED:
                    self.seek(0)
                self.replay.play()
        elif key == 'step':
            self.replay.pause()
            self.replay_step()
        elif key == 'back': self.seek(self.replay.index - 1)
        elif key == 'stop': self.stop_replay()
        elif key == 'speed':
            self.speed = {0.5: 1, 1: 2, 2: 4, 4: 0.5}[self.speed]
        elif key == 'save': self.save()
        elif key == 'load': self.load()
        elif key == 'camera': self.zoom, self.pan = 1.0, [0, 0]
        elif key == 'view':
            view = VIEWS[(VIEWS.index(self.renderer.view) + 1) % len(VIEWS)]
            self.renderer.set_view(view)
            self.message = {'original': 'Original game view.', 'iso': 'Classic isometric view.'}[view]
        elif key == 'animate':
            self.animate = not self.animate
            if not self.animate: self.animation.reset()
        elif key == 'sound':
            if self.sound is None:
                self.message = 'Audio device unavailable.'
            else: self.sound_enabled = not self.sound_enabled
        elif key == 'contrast': self.high_contrast = not self.high_contrast
        elif key == 'text': self.large_text = not self.large_text

    def draw(self):
        return draw_presentation(self)

    def present(self):
        """Show the last drawn frame in the window.

        A Retina window has 2x the pixels of the logical screen. The UI frame
        is scaled up to fill it, and the board is drawn on top at the full
        resolution, so tiles and block are sharp instead of blurred by the OS.
        """
        hi = self.window.get_surface()
        if hi.get_size() == self.screen.get_size():
            hi.blit(self.screen, (0, 0))
        elif not sharp_board(self):
            pygame.transform.smoothscale(self.screen, hi.get_size(), hi)
        else:
            ui = self._presentation_cache[2]
            if self._hi_base is None or self._hi_base[0] is not ui or self._hi_base[1].get_size() != hi.get_size():
                self._hi_base = (ui, pygame.transform.smoothscale(ui, hi.get_size()))
            hi.blit(self._hi_base[1], (0, 0))
            scale = hi.get_width() / self.screen.get_width()
            rect = pygame.Rect(round(self.board_rect.x * scale), round(self.board_rect.y * scale),
                               round(self.board_rect.w * scale), round(self.board_rect.h * scale))
            if self._hi_board is None or self._hi_board.get_size() != rect.size:
                self._hi_board = pygame.Surface(rect.size, pygame.SRCALPHA)
            self.renderer.zoom, self.renderer.pan = self.zoom, (self.pan[0] * scale, self.pan[1] * scale)
            self.renderer.pixel_scale = scale
            self.renderer.draw(self._hi_board, self.session.current_state, self.animation.frame)
            hi.blit(self._hi_board, rect)
        self.window.flip()

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self.handle_key(event.key)
        elif event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE) and self.window is not None:
            self.screen = pygame.Surface(self.window.size)
            self._presentation_cache = self._hi_base = None
        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode((max(theme.MIN_SIZE[0], event.w), max(theme.MIN_SIZE[1], event.h)), pygame.RESIZABLE)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for button in reversed(self.buttons):
                    if button.enabled and button.rect.collidepoint(event.pos):
                        self.command(button.key)
                        return
                if self.stage_picker or self.menu:
                    if not self.modal_rect.collidepoint(event.pos):
                        self.command('close_menu')
                    return
                if self.dropdown_open:
                    self.dropdown_open = False
                    return
                if self.seek_rect.inflate(0, 12).collidepoint(event.pos) and self.replay.length:
                    self.seek(round((event.pos[0] - self.seek_rect.x) / self.seek_rect.width * self.replay.length))
            elif event.button == 3 and self.board_rect.collidepoint(event.pos) and not (self.stage_picker or self.menu or self.dropdown_open):
                self.dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging and not (self.stage_picker or self.menu):
            self.pan[0] += event.rel[0]
            self.pan[1] += event.rel[1]
        elif event.type == pygame.MOUSEWHEEL and not (self.stage_picker or self.menu or self.dropdown_open) and self.board_rect.collidepoint(pygame.mouse.get_pos()):
            self.zoom = max(0.5, min(2.5, self.zoom + event.y * 0.1))

    def run(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        # allow_high_dpi: on Retina screens the window surface gets 2x pixels (see present()).
        self.window = pygame.Window('Bloxorz 3D - Search Lab', self.WINDOW_SIZE, resizable=True, allow_high_dpi=True)
        self.window.minimum_size = theme.MIN_SIZE
        self.screen = pygame.Surface(self.window.size)
        self.hidpi = self.window.get_surface().get_width() / self.window.size[0]
        self.font = pygame.font.Font(None, 28)
        self.title_font = pygame.font.Font(None, 38)
        if pygame.mixer.get_init():
            from src.gui.sfx import SoundBank
            self.sound = SoundBank()
        else:
            self.sound_enabled = False  # no audio device: Settings should say Off
        clock = pygame.time.Clock()
        try:
            running = True
            while running:
                dt = min(clock.tick(60) / 1000, 0.1)
                for event in pygame.event.get():
                    if event.type in (pygame.QUIT, pygame.WINDOWCLOSE) or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not (self.stage_picker or self.menu or self.dropdown_open
                                                                                                                or self.win_phase == 'choice')):
                        running = False
                    else:
                        self.handle_event(event)
                self.update(dt)
                if self.draw():
                    self.present()
        finally:
            self.gateway.close()
            if hasattr(self.renderer, 'close'):
                self.renderer.close()
            pygame.quit()

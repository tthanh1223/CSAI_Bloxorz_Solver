"""Điều phối GUI: engine là nguồn duy nhất của luật chơi."""
from __future__ import annotations
import collections
import json
import math
import time
from pathlib import Path
import pygame
from src.engine.loader import initial_state, load_stage
from src.engine.problem import LOST, WON, BloxorzProblem, GameSession
from src.engine.state import Action, GameState, Orientation
from src.gui.animation import RollAnimation
from src.gui.replay import PathReplay
from src.gui.renderer3d import IsometricRenderer, VIEWS, INTRO_SECONDS, INTRO_IMPACTS, SHOCKWAVE_SECONDS
from src.gui.solver_gateway import ProcessSolverGateway
from src.gui.contracts import SolverRequest, SolverStatus, ReplayStatus
from src.gui import theme
from src.gui.presentation import (STAGES_PER_PAGE, board_effects, camera_shake, draw as draw_presentation,
                                  draw_header_emblem, sharp_board)
from src.gui.themes import cycle_theme

ROOT = Path(__file__).resolve().parents[2]
SAVE_PATH = ROOT / 'data' / 'gui_session.json'
BGM_TRACKS = (theme.ASSETS_DIR / 'bgm' / 'the_mountain-retro-game-593063.mp3',
              theme.ASSETS_DIR / 'bgm' / 'cheerful_puzzle.wav')  # dùng file đầu tiên tồn tại
SOLVER_TIMEOUT = 30.0
REPLAY_STEP_SECONDS = 0.12
REPLAY_SPEEDS = {0.5: 1, 1: 2, 2: 4, 4: 0.5}  # tốc độ hiện tại -> tốc độ kế tiếp
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.5, 2.5, 0.1


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


def _slider_ratio(rect, x):
    return max(0.0, min(1.0, (x - rect.x) / max(1, rect.w)))


class FramePacer:
    """Hiển thị frame đều nhịp, khớp với tần số làm tươi của màn hình.

    Trên macOS window.flip() chờ lần làm tươi kế tiếp. Màn ProMotion làm tươi
    120 Hz, nhanh hơn thời gian vẽ một frame khi có chuyển động (~7-10 ms), nên
    frame sẽ lúc chiếm một lúc chiếm hai lần làm tươi và chuyển động bị giật.
    Thay vào đó mọi frame được cùng số lần làm tươi (60 FPS trên 120 Hz): trước
    khi flip ta chờ tới ngay trước lần làm tươi phù hợp. Nơi flip không chờ
    (không có vsync), cùng mốc thời gian đó chỉ đơn giản giãn frame theo đồng hồ.
    """

    def __init__(self, refresh_hz=60):
        refresh_hz = refresh_hz if refresh_hz and refresh_hz > 0 else 60
        self.frame_s = max(1, int(refresh_hz) // 55) / refresh_hz  # 60 FPS trên màn 60/120/240 Hz
        self.flip_waits = collections.deque(maxlen=30)
        self.last_flip = time.perf_counter()

    def wait_and_flip(self, window, drew=True):
        waits = sorted(self.flip_waits)
        vsync = len(waits) >= 10 and waits[len(waits) // 2] > .0005
        # Có vsync thì nhắm ngay trước lần làm tươi cần tới; sau đó flip sẽ chờ nó.
        deadline = self.last_flip + self.frame_s - (.002 if vsync else 0.0)
        remaining = deadline - time.perf_counter()
        if remaining > .002:
            time.sleep(remaining - .0015)  # ngủ thô trước, rồi quay vòng để chính xác
        while time.perf_counter() < deadline:
            pass
        if drew:
            start = time.perf_counter()
            window.flip()
            self.last_flip = time.perf_counter()
            self.flip_waits.append(self.last_flip - start)
        else:
            self.last_flip = max(deadline, time.perf_counter())


class BloxorzApp:
    WINDOW_SIZE = (1080, 620)
    FALL_SECONDS = 0.9  # lăn tới mép, lật qua và rơi, rồi chơi lại
    ROLL_SECONDS = 0.18   # một lần lăn; như nhau dù có bấm công tắc hay không
    BRIDGE_SECONDS = 0.45  # cầu của công tắc bay vào / vỡ ra, sau khi khối tiếp đất
    WIN_SECONDS = 0.7   # khối chìm vào lỗ đích
    OUTRO_SECONDS = 0.9  # sau đó các ô rơi đi, lan dần ra từ ô đích

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
        self.sound_enabled = True  # bật sẵn; Settings > Sound để tắt
        self.bgm_volume: float = 0.10
        self.sfx_volume: float = 0.85
        self.active_slider: str | None = None
        self.bgm_slider_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.sfx_slider_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
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
        self.screen = None  # frame logic (1x) để dàn UI
        self.window = None  # run(): cửa sổ HiDPI; surface của nó có thể gấp đôi screen
        self.hidpi = 1
        self._hi_base = self._hi_board = None
        self._hi_ui_shown = None  # frame UI vừa được chép trọn vào cửa sổ (xem present())
        self.bridge_fx = None  # (cầu cũ, cầu mới, tiến độ) khi cầu đang chạy animation
        self._queued_bridges = None  # được đặt khi bấm công tắc, bắt đầu khi lần lăn tiếp đất
        self.buttons = []
        self.seek_rect = pygame.Rect(0, 0, 0, 0)
        self.board_rect = pygame.Rect(0, 0, 1, 1)
        self.metric_rects = []
        self.pending_action = None
        # Chuỗi thắng (chỉ khi tự chơi): 'roll' -> 'sink' -> 'choice' (xem lại hoặc qua màn).
        self.win_phase = None
        self.stage_cleared: bool = False
        self.intro_t: float | None = None
        self.outro_t: float | None = None
        self.board_cleared = False  # xem board_outro()
        self.trauma: float = 0.0
        self.shockwave: tuple[float, float, float] | None = None
        self.in_main_menu: bool = False
        self.solver_open: bool = False
        self.drawer_t: float = 0.0
        self.menu_t: float = 0.0
        self.visual_style = self.theme_name = 'dream'  # do themes.apply_theme() đặt
        self.running = False
        self._planned_for = None
        # Cache và trạng thái từng frame do presentation.py quản lý.
        self._ticks = 0
        self._presentation_cache = None
        self._scene_cache = None
        self._board_surface = None
        self._veil_cache = None
        self._emblem = None

    def add_trauma(self, amount: float):
        self.trauma = min(1.0, self.trauma + amount)

    def _count_moves(self):
        self.session.moves = sum(a != Action.SPACE for a in self.actions)

    @property
    def busy(self):
        return self.active_request is not None

    def set_bgm_volume(self, vol: float):
        self.bgm_volume = max(0.0, min(1.0, vol))
        if vol > 0.0:
            self.sound_enabled = True
        if pygame.mixer.get_init():
            try:
                pygame.mixer.music.set_volume(self.bgm_volume if self.sound_enabled else 0.0)
            except Exception:
                pass

    def set_sfx_volume(self, vol: float):
        self.sfx_volume = max(0.0, min(1.0, vol))
        if vol > 0.0:
            self.sound_enabled = True
        if self.sound:
            self.sound.set_volume(self.sfx_volume if self.sound_enabled else 0.0)

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
        self.intro_t = None
        self.outro_t = None

    def new_session(self, state):
        self.win_phase = None  # mọi lần load/restart/replay đều huỷ chuỗi thắng
        self.bridge_fx = self._queued_bridges = None  # cầu được hiển thị đúng trạng thái hiện tại
        self.board_cleared = False  # True khi bàn của màn đã thắng đã rơi hết
        self.session = GameSession(BloxorzProblem(self.stage, state))
        if self.session.problem.is_goal(state):
            self.session.status = WON
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
        self.in_main_menu = False
        self.menu = None
        self.message = 'Stage loaded. Arrow keys / WASD to roll.'
        if self.animate:
            self.intro_t = 0.0

    def restart(self):
        self.invalidate()
        self.new_session(initial_state(self.stage))
        self.message = 'Stage restarted.'
        if self.animate:
            self.intro_t = 0.0

    def apply_action(self, action, replay=False):
        if self.busy or self.animation.busy:
            return False
        self.intro_t = None
        if not replay and self.replay.status != ReplayStatus.EMPTY:
            self.message = 'Exit replay to play manually.'
            return False
        if self.session.status == WON:
            return False  # màn đã xong; chuỗi thắng sẽ tiếp quản
        before = self.session.current_state
        if not self.session.apply_action(action):
            fallen = None if replay else self.session.fall(action)
            if fallen is not None:
                self.start_fall(before, fallen, action)
            else:
                self.message = 'Blocked. Keep the whole block on solid ground.'
            return False
        self.actions.append(action)
        self._count_moves()
        if self.animate:
            # Khối luôn lăn với tốc độ bình thường. Nếu lần lăn này bấm công tắc,
            # animation của cầu bắt đầu khi khối tiếp đất (update()).
            self.animation.duration_sec = self.ROLL_SECONDS / self.speed
            self.animation.start(before, self.session.current_state, action)
            if self.session.current_state.bridges_status != before.bridges_status:
                self._queued_bridges = (before.bridges_status, self.session.current_state.bridges_status)
        self.result = self.result if replay else None
        if not replay:
            self.solver_status = SolverStatus.IDLE
            if self.session.status == WON:
                self.win_phase = 'roll'  # update() bắt đầu chìm khi lần lăn kết thúc
        after = self.session.current_state
        if action != Action.SPACE:
            self.play_sfx('roll')
        else:
            self.play_sfx('switch')
        if after.bridges_status != before.bridges_status:
            self.play_sfx('switch')
        if after.orientation == Orientation.SPLIT and before.orientation != Orientation.SPLIT:
            self.play_sfx('split')
        elif before.orientation == Orientation.SPLIT and after.orientation != Orientation.SPLIT:
            self.play_sfx('split')
            mid_r = (after.pos1[0] + after.pos2[0]) / 2.0
            mid_c = (after.pos1[1] + after.pos2[1]) / 2.0
            self.shockwave = (mid_r, mid_c, 0.0)
        if self.session.status == WON:
            self.play_sfx('win')
        self.message = 'Rolling...' if self.animation.busy else 'Move accepted.'
        return True

    def start_fall(self, before, fallen, action):
        """Khối lăn ra khỏi bàn (session.status lúc này là LOST).

        Chạy animation rơi; update() chơi lại màn khi animation kết thúc.
        Không có animation thì chơi lại ở lần update() kế tiếp.
        """
        self.pending_action = None
        self.result = None
        self.solver_status = SolverStatus.IDLE
        self.message = 'You fell off the board!'
        self.play_sfx('fall')
        self.add_trauma(0.12)
        if self.animate:
            self.animation.duration_sec = self.FALL_SECONDS
            self.animation.start(before, fallen, action, falling=True)

    def play_sfx(self, name, volume=1.0):
        """Phát một hiệu ứng âm thanh (xem src/gui/sfx.py) nếu âm thanh đang bật."""
        if self.sound_enabled and self.sound:
            self.sound.play(name, volume)

    def finish_fall(self):
        self.restart()
        self.message = 'You fell off. Stage restarted - try again!'

    def advance_win(self):
        """Gọi ở mỗi update(): đẩy chuỗi thắng tiến thêm một bước."""
        if self.win_phase in (None, 'choice', 'disassemble') or self.animation.busy:
            return
        if self.session.status != WON:  # ví dụ: đã undo trước khi bắt đầu chìm
            self.win_phase = None
            return
        if self.win_phase == 'roll' and self.animate:
            goal = self.session.current_state
            self.animation.duration_sec = self.WIN_SECONDS
            self.animation.start(goal, goal, self.actions[-1], sinking=True)
            self.win_phase = 'sink'
            self.message = 'Stage complete!'
            return
        if self.win_phase == 'sink' and self.animate:
            self.win_phase = 'disassemble'
            self.outro_t = 0.0
            return
        # Chìm xong (hoặc tắt animation): cho người chơi xem lại hoặc qua màn.
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
        """Xem lại các nước thắng từ đầu; Exit replay quay về hộp lựa chọn."""
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
        self.bridge_fx = self._queued_bridges = None
        self.actions.pop()
        self._count_moves()
        self.result = None
        self.solver_status = SolverStatus.IDLE
        self.message = 'Last move undone.'

    def solve(self, hint=False):
        if self.busy or self.animation.busy or self.replay.status != ReplayStatus.EMPTY:
            return
        self.request_id += 1
        self.solve_start = self.session.current_state if hint or self.solve_current else initial_state(self.stage)
        request = SolverRequest(self.request_id, self.algorithm, self.stage, self.solve_start, SOLVER_TIMEOUT)
        try:
            self.gateway.submit(request)
        except Exception as error:
            self.message = f'Cannot start solver: {error}'
            return
        self.active_request = request.request_id
        self.hint_mode = hint
        if not hint:
            self.solver_open = True
            self.details_open = True
        self.result = None
        self.solver_status = SolverStatus.RUNNING
        self.message = 'Finding a hint...' if hint else f'Searching ({SOLVER_TIMEOUT:g} second limit)...'

    def load_replay(self, start, path):
        # Kiểm tra cả đường đi trước khi thay session hiện tại.
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
        self._count_moves()
        self.replay.load(start, path)
        self.replay.index = index
        self.replay.status = ReplayStatus.FINISHED if index == len(path) else ReplayStatus.PAUSED
        self.wait = 0
        self.message = f'Replay at move {index}/{len(path)}.'

    def stop_replay(self):
        if self.animation.busy:
            self.animation.reset()
        if self.stage_cleared and self.replay.initial_state is not None:
            # Đang xem lại màn đã xong: nhảy về ô đích và hiện lại hộp lựa chọn.
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
        p = Path(path)
        if not p.exists():
            self.message = 'No saved session found.'
            return
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
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
            if speed not in REPLAY_SPEEDS:
                raise ValueError('Invalid playback speed.')
            view = settings.get('view', self.renderer.view)
            if view == 'front':  # góc nhìn đã bỏ; save cũ dùng góc nhìn mặc định
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
        self._count_moves()
        if self.session.problem.is_goal(self.session.current_state):
            self.session.status = WON
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
        self.in_main_menu = False
        self.message = 'Session loaded.'

    def update(self, dt):
        self.animation.update(dt)
        self._plan_bridge_boards()
        # Dòng thời gian của cầu: (trạng thái cũ, trạng thái mới, tiến độ 0..1), độc lập với lần lăn.
        if self.bridge_fx is not None:
            old, new, progress = self.bridge_fx
            progress += dt * self.speed / self.BRIDGE_SECONDS
            self.bridge_fx = (old, new, progress) if progress < 1 else None
        if self._queued_bridges is not None and not self.animation.busy:
            self.bridge_fx = (*self._queued_bridges, 0.0)
            self._queued_bridges = None
        if self.trauma > 0.0:
            self.trauma = max(0.0, self.trauma - dt * 1.8)
        if self.shockwave is not None:
            r, c, st = self.shockwave
            st += dt
            self.shockwave = (r, c, st) if st < SHOCKWAVE_SECONDS else None
        if self.intro_t is not None:
            before = self.intro_t * INTRO_SECONDS
            self.intro_t += dt / INTRO_SECONDS
            for hit, speed in INTRO_IMPACTS:  # khối thả xuống tiếp đất: mỗi lần nảy một tiếng thịch
                if before < hit <= self.intro_t * INTRO_SECONDS:
                    self.play_sfx('roll', volume=speed)
            if self.intro_t >= 1.0:
                self.intro_t = None
                self._presentation_cache = None
        if self.win_phase == 'disassemble' and self.outro_t is not None:
            self.outro_t += dt / self.OUTRO_SECONDS
            if self.outro_t >= 1.0:
                self.outro_t = None
                self.board_cleared = True  # khối và các ô biến mất hẳn phía sau hộp thoại
                self.win_phase = 'choice'
                self.stage_cleared = True
                self.message = 'Stage complete!'
        if self.session.status == LOST and not self.animation.busy:
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
            action, self.pending_action = self.pending_action, None
            self.apply_action(action)
        if self.replay.status == ReplayStatus.PLAYING and not self.animation.busy:
            self.wait -= dt
            if self.wait <= 0:
                self.replay_step()
                self.wait = REPLAY_STEP_SECONDS / self.speed
        target_drawer = 1.0 if self.solver_open else 0.0
        self.drawer_t += (target_drawer - self.drawer_t) * min(1.0, dt * 14.0)
        if abs(self.drawer_t - target_drawer) < 0.002:
            self.drawer_t = target_drawer
        target_menu = 1.0 if self.in_main_menu else 0.0
        self.menu_t += (target_menu - self.menu_t) * min(1.0, dt * 9.0)

        if (self.session.status == WON and self.win_phase is None and not self.animation.busy
                and not self.busy and self.replay.status != ReplayStatus.EMPTY):
            self.message = ('Replay finished. Exit replay to continue.' if self.stage_cleared
                            else 'Stage complete. Choose another stage above.')

    def handle_key(self, key):
        if self.in_main_menu:
            if key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self.command('continue_game')
                return
            if key == pygame.K_n:
                self.command('new_game')
                return
            if key == pygame.K_s:
                self.command('choose')
                return
            if key == pygame.K_t:
                self.command('theme')
                return
            if key == pygame.K_q:
                self.command('exit_game')
                return
            return
        if self.stage_picker or self.menu or self.dropdown_open:
            if key == pygame.K_ESCAPE:
                self.stage_picker = False
                self.menu = None
                self.dropdown_open = False
            return
        if key == pygame.K_TAB:
            self.command('toggle_solver')
            return
        if key == pygame.K_ESCAPE:
            if self.solver_open:
                self.command('close_solver')
            else:
                self.command('main_menu')
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
        if key == pygame.K_RETURN and self.session.status == WON:
            self.next_stage()
            return
        mapping = {pygame.K_UP: Action.UP, pygame.K_w: Action.UP, pygame.K_DOWN: Action.DOWN,
                   pygame.K_s: Action.DOWN, pygame.K_LEFT: Action.LEFT, pygame.K_a: Action.LEFT,
                   pygame.K_RIGHT: Action.RIGHT, pygame.K_d: Action.RIGHT, pygame.K_SPACE: Action.SPACE}
        if key in mapping:
            if self.animation.busy and not self.busy and self.replay.status == ReplayStatus.EMPTY:
                self.pending_action = mapping[key]
            else:
                self.apply_action(mapping[key])

    def command(self, key):
        if key == 'main_menu':
            self.in_main_menu = not self.in_main_menu
            self.solver_open = False
            self.menu = None
            self.stage_picker = False
            return
        if key == 'new_game':
            self.in_main_menu = False
            self.select_stage(0)
            self.restart()
            return
        if key == 'continue_game':
            self.in_main_menu = False
            return
        if key in ('toggle_solver', 'solve'):
            self.solver_open = not self.solver_open
            if self.solver_open:
                self.details_open = True
            return
        if key == 'close_solver':
            self.solver_open = False
            return
        if key == 'exit_game':
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if key == 'theme':
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
            self.solver_open = True
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
            self.in_main_menu = False
            self.stage_picker = False
            self.menu = None
        elif key == 'choose':
            self.stage_picker = not self.stage_picker
            self.picker_page = self.stage_index // STAGES_PER_PAGE
            if self.stage_picker:
                self.replay.pause()
        elif key == 'page_prev':
            self.picker_page = max(0, self.picker_page - 1)
        elif key == 'page_next':
            self.picker_page = min((len(self.stage_paths) - 1) // STAGES_PER_PAGE, self.picker_page + 1)
        elif key == 'next_stage':
            self.next_stage()
        elif key == 'win_replay' and self.actions and not self.busy:
            self.replay_win()
        elif key == 'restart':
            self.restart()
        elif key == 'undo':
            self.undo()
        elif key == 'solve_now':
            self.solve()
        elif key == 'hint':
            self.solve(True)
        elif key == 'cancel' and self.busy:
            self.gateway.cancel(self.active_request)
        elif key.startswith('algorithm:') and not self.busy:
            self.algorithm = key.split(':')[1]
            self.dropdown_open = False
        elif key == 'solution' and self.result and self.result.found and not self.busy:
            self.load_replay(self.solve_start, self.result.path)
            self.replay.play()
        elif key == 'recording' and self.actions and not self.busy:
            self.load_replay(self.record_start, tuple(self.actions))
        elif key == 'play' and not self.busy:
            self._toggle_play()
        elif key == 'step':
            self.replay.pause()
            self.replay_step()
        elif key == 'back':
            self.seek(self.replay.index - 1)
        elif key == 'stop':
            self.stop_replay()
        elif key == 'speed':
            self.speed = REPLAY_SPEEDS[self.speed]
        elif key == 'save':
            self.save()
        elif key == 'load':
            self.load()
        elif key == 'camera':
            self.zoom, self.pan = 1.0, [0, 0]
        elif key == 'view':
            self._cycle_view()
        elif key == 'animate':
            self.animate = not self.animate
            if not self.animate:
                self.animation.reset()
        elif key == 'sound':
            self._toggle_sound()
        elif key == 'contrast':
            self.high_contrast = not self.high_contrast
        elif key == 'text':
            self.large_text = not self.large_text

    def _toggle_play(self):
        if self.replay.status == ReplayStatus.PLAYING:
            self.replay.pause()
        else:
            if self.replay.status == ReplayStatus.FINISHED:
                self.seek(0)
            self.replay.play()

    def _cycle_view(self):
        view = VIEWS[(VIEWS.index(self.renderer.view) + 1) % len(VIEWS)]
        self.renderer.set_view(view)
        self.message = {'original': 'Original game view.', 'iso': 'Classic isometric view.'}[view]

    def _toggle_sound(self):
        if self.sound is None:
            self.message = 'Audio device unavailable.'
            return
        self.sound_enabled = not self.sound_enabled
        if not pygame.mixer.get_init():
            return
        try:
            if self.sound_enabled:
                pygame.mixer.music.unpause()
                pygame.mixer.music.set_volume(self.bgm_volume)
                self.sound.set_volume(self.sfx_volume)
            else:
                pygame.mixer.music.pause()
                self.sound.set_volume(0.0)
        except Exception:
            pass

    def draw(self):
        return draw_presentation(self)

    def _plan_bridge_boards(self):
        """Báo cho renderer các bố cục cầu có thể gặp trong tối đa hai nước tới, để nó
        dựng sẵn các bàn đó trước khi công tắc được bấm (không khựng khi cầu hiện ra
        hoặc biến mất). Chỉ tính lại khi state thay đổi."""
        state = self.session.current_state
        if self._planned_for == state:
            return
        self._planned_for = state
        problem = self.session.problem
        wanted, seen, frontier = [], {state}, [state]
        for _ in range(2):  # nước gần nhất trước
            following = []
            for here in frontier:
                for _, there, _ in problem.get_successors(here):
                    if there.bridges_status != here.bridges_status:
                        # Bàn trong lúc cầu chạy animation (bỏ các cầu đang đổi), rồi bàn sau đó.
                        during = tuple(a and b for a, b in zip(here.bridges_status, there.bridges_status))
                        for status in (during, there.bridges_status):
                            if status != state.bridges_status and status not in wanted:
                                wanted.append(status)
                    if there not in seen:
                        seen.add(there)
                        following.append(there)
            frontier = following
        self.renderer.want_boards(wanted)

    def board_outro(self):
        """Tiến độ outro thắng cho renderer: đang chạy, 1.0 khi bàn đã rơi hết
        (bàn trống cho tới khi người chơi đi tiếp), ngược lại None."""
        if self.outro_t is not None:
            return self.outro_t
        return 1.0 if self.board_cleared else None

    def bridge_view(self):
        """Renderer cần vẽ cầu thế nào: animation cầu đang chạy, hoặc, khi lần lăn
        bấm công tắc vẫn chưa xong, tư thế ban đầu của nó (để cầu mới không hiện ra
        trước khi khối tiếp đất)."""
        if self.bridge_fx is not None:
            return self.bridge_fx
        if self._queued_bridges is not None:
            return (*self._queued_bridges, 0.0)
        return None

    def present(self, flip=True):
        """Hiển thị frame vừa vẽ lên cửa sổ (flip=False: để bên gọi tự flip).

        Cửa sổ Retina có số pixel gấp đôi screen logic. Frame UI được phóng to
        cho vừa, còn bàn chơi được vẽ đè lên ở độ phân giải đầy đủ, nên ô và khối
        sắc nét thay vì bị hệ điều hành làm mờ. Khi UI không đổi thì chỉ làm mới
        vùng của bàn chơi.

        Bàn chơi được vẽ trên một lớp trong suốt riêng: các hiệu ứng phát sáng,
        vệt và hạt của renderer dùng màu bán trong suốt, chỉ đúng trên surface có
        alpha từng pixel (surface của cửa sổ không có).
        """
        hi = self.window.get_surface()
        if hi.get_size() == self.screen.get_size():
            hi.blit(self.screen, (0, 0))
            self._hi_ui_shown = None
        elif not sharp_board(self):
            pygame.transform.smoothscale(self.screen, hi.get_size(), hi)
            self._hi_ui_shown = None
        else:
            ui = self._presentation_cache[2]
            if self._hi_base is None or self._hi_base[0] is not ui or self._hi_base[1].get_size() != hi.get_size():
                self._hi_base = (ui, pygame.transform.smoothscale(ui, hi.get_size()))
            scale = hi.get_width() / self.screen.get_width()
            rect = pygame.Rect(round(self.board_rect.x * scale), round(self.board_rect.y * scale),
                               round(self.board_rect.w * scale), round(self.board_rect.h * scale))
            if self.trauma > 0.01:  # cùng kiểu rung camera như đường vẽ 1x
                shake_x, shake_y = camera_shake(self.trauma, pygame.time.get_ticks())
                rect.move_ip(round(shake_x * scale), round(shake_y * scale))
            rect = rect.clamp(hi.get_rect())
            if self._hi_ui_shown is not ui:
                hi.blit(self._hi_base[1], (0, 0))
                self._hi_ui_shown = ui
            else:  # UI không đổi: chỉ khôi phục vùng của bàn chơi (cộng lề rung)
                area = rect.inflate(round(16 * scale), round(16 * scale)).clip(hi.get_rect())
                hi.blit(self._hi_base[1], area.topleft, area)
            self.renderer.zoom, self.renderer.pan = self.zoom, (self.pan[0] * scale, self.pan[1] * scale)
            self.renderer.pixel_scale = scale
            if self._hi_board is None or self._hi_board.get_size() != rect.size:
                self._hi_board = pygame.Surface(rect.size, pygame.SRCALPHA)
            self._hi_board.fill((0, 0, 0, 0))
            # clear=False: frame chuyển động được dựng thẳng lên lớp này.
            self.renderer.draw(self._hi_board, self.session.current_state, self.animation.frame,
                               clear=False, **board_effects(self))
            hi.blit(self._hi_board, rect)
            emblem = self._emblem
            if emblem is not None:  # khối lập phương nhấp nhô ở header, vẽ sắc nét mỗi frame
                bx, cy, style = emblem
                area = pygame.Rect(round((bx - 12) * scale), round((cy - 12) * scale),
                                   round(24 * scale), round(28 * scale)).clip(hi.get_rect())
                hi.blit(self._hi_base[1], area.topleft, area)
                draw_header_emblem(hi, bx, cy + math.sin(pygame.time.get_ticks() * 0.005) * 2.8, style, scale)
        if flip:
            self.window.flip()

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self.handle_key(event.key)
        elif event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE) and self.window is not None:
            self.screen = pygame.Surface(self.window.size)
            self._presentation_cache = self._hi_base = self._hi_ui_shown = None
        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode((max(theme.MIN_SIZE[0], event.w), max(theme.MIN_SIZE[1], event.h)), pygame.RESIZABLE)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.menu == 'settings':
                    if self.bgm_slider_rect.inflate(0, 16).collidepoint(event.pos):
                        self.active_slider = 'bgm'
                        self.set_bgm_volume(_slider_ratio(self.bgm_slider_rect, event.pos[0]))
                        return
                    if self.sfx_slider_rect.inflate(0, 16).collidepoint(event.pos):
                        self.active_slider = 'sfx'
                        self.set_sfx_volume(_slider_ratio(self.sfx_slider_rect, event.pos[0]))
                        return
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
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.active_slider = None
            elif event.button == 3:
                self.dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.active_slider == 'bgm':
                self.set_bgm_volume(_slider_ratio(self.bgm_slider_rect, event.pos[0]))
            elif self.active_slider == 'sfx':
                self.set_sfx_volume(_slider_ratio(self.sfx_slider_rect, event.pos[0]))
            elif self.dragging and not (self.stage_picker or self.menu):
                self.pan[0] += event.rel[0]
                self.pan[1] += event.rel[1]
        elif event.type == pygame.MOUSEWHEEL and not (self.stage_picker or self.menu or self.dropdown_open) and self.board_rect.collidepoint(pygame.mouse.get_pos()):
            self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + event.y * ZOOM_STEP))

    def run(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        # allow_high_dpi: trên màn Retina surface của cửa sổ có gấp đôi pixel (xem present()).
        self.window = pygame.Window('Bloxorz 3D - Search Lab', self.WINDOW_SIZE, resizable=True, allow_high_dpi=True)
        self.window.minimum_size = theme.MIN_SIZE
        self.screen = pygame.Surface(self.window.size)
        self.hidpi = self.window.get_surface().get_width() / self.window.size[0]
        if pygame.mixer.get_init():
            from src.gui.sfx import SoundBank
            self.sound = SoundBank(volume=self.sfx_volume)
            bgm_path = next((path for path in BGM_TRACKS if path.exists()), None)
            if bgm_path is not None:
                try:
                    pygame.mixer.music.load(str(bgm_path))
                    pygame.mixer.music.set_volume(self.bgm_volume if self.sound_enabled else 0.0)
                    pygame.mixer.music.play(-1)
                except Exception:
                    pass
        else:
            self.sound_enabled = False  # không có thiết bị âm thanh: Settings phải hiện Off
        try:
            rates = pygame.display.get_desktop_refresh_rates()
        except (AttributeError, pygame.error):
            rates = []
        pacer = FramePacer(rates[0] if rates else 60)
        last = time.perf_counter()
        try:
            self.running = True
            while self.running:
                now = time.perf_counter()
                dt = min(now - last, 0.1)  # thời gian trôi chính xác, không làm tròn mili giây
                last = now
                for event in pygame.event.get():
                    if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                        self.running = False
                    else:
                        self.handle_event(event)
                self.update(dt)
                drew = self.draw()
                if drew:
                    self.present(flip=False)
                pacer.wait_and_flip(self.window, drew)
        finally:
            self.running = False
            self.gateway.close()
            pygame.quit()

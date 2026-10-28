"""Bố cục ưu tiên phần chơi. Mọi phần hiển thị phụ thuộc state đều nằm ở đây."""
from dataclasses import dataclass
import math
import pygame
from src.gui import theme as T
from src.gui.ui import Button, text, draw_glass_panel, draw_bento_card, draw_vector_icon, lerp_color
from src.gui.contracts import ReplayStatus, SolverStatus
from src.engine.state import Orientation
from src.gui.dreamscape import background
from src.gui.themes import NAMES

STAGES_PER_PAGE = 20
SOLVER_LABELS = {'ASTAR': 'A*'}
SOLVER_FAILURES = {SolverStatus.ERROR: 'Search failed. Please retry.', SolverStatus.TIMEOUT: 'Search time limit reached.',
                   SolverStatus.NO_SOLUTION: 'No solution found.', SolverStatus.CANCELLED: 'Search cancelled.'}


def solver_label(algorithm):
    return SOLVER_LABELS.get(algorithm, algorithm)


def camera_shake(trauma, ticks):
    intensity = trauma ** 1.5
    return math.sin(ticks * 0.048) * 2.5 * intensity, math.cos(ticks * 0.062) * 1.8 * intensity


def board_effects(app):
    return dict(intro_t=app.intro_t, outro_t=app.board_outro(), shockwave=app.shockwave, bridges=app.bridge_view())


def scene(app):
    style = app.visual_style
    size = app.screen.get_size()
    key = (size, style, id(app.stage), app.stage_index)
    cached = app._scene_cache
    if cached and cached[0] == key:
        return cached[1]
    cells = tuple((r, c) for r, row in enumerate(app.stage.grid) for c, tile in enumerate(row) if tile.value != '0') if style in ('blueprint', 'forest') else ()
    result = background(size, style, cells, app.stage_index)
    app._scene_cache = (key, result)
    return result


def sharp_board(app):
    """Trên cửa sổ HiDPI (Retina), bàn chơi không nằm trong frame UI 1x mà được
    BloxorzApp.present() vẽ ở độ phân giải đầy đủ, để ô và khối sắc nét. Các hộp
    thoại và panel phủ lên (kể cả ngăn AI Solver) vẫn dùng bàn 1x vì chúng chồng
    lên và ghép trực tiếp với bàn chơi."""
    replaying = app.replay.status != ReplayStatus.EMPTY
    is_drawer_visible = (app.solver_open or replaying or app.busy or app.dropdown_open or abs(app.drawer_t) > 0.005)
    return (app.hidpi > 1
            and not (app.menu or app.stage_picker or app.win_phase == 'choice' or app.in_main_menu
                     or is_drawer_visible))


def draw(app):
    """Cache phần UI đã dựng, độc lập với bàn chơi có animation."""
    mouse = pygame.mouse.get_pos()
    hovered = tuple(b.key for b in app.buttons if b.enabled and b.rect.collidepoint(mouse))
    hovered_metrics = tuple(i for i, r in enumerate(app.metric_rects) if r.collidepoint(mouse))
    is_split = app.session.current_state.orientation == Orientation.SPLIT
    drawer_animating = abs(app.drawer_t - (1.0 if app.solver_open else 0.0)) > 0.005
    menu_animating = abs(app.menu_t - (1.0 if app.in_main_menu else 0.0)) > 0.005
    animating_ui = ((app.running and not sharp_board(app)) or bool(hovered) or bool(hovered_metrics) or app.busy
                    or bool(app.win_phase) or app.active_slider is not None
                    or app.trauma > 0.01 or app.shockwave is not None
                    or is_split or drawer_animating or menu_animating or app.in_main_menu)
    time_tick = (pygame.time.get_ticks() // 16) if animating_ui else 0
    app._ticks = time_tick * 16
    slider_state = (app.bgm_volume, app.sfx_volume, app.active_slider)
    renderer_view = app.renderer.view
    ui_key = (app.visual_style, app.screen.get_size(), renderer_view, app.large_text, app.high_contrast,
              app.stage_index, app.session.moves, app.session.status, app.busy, app.animation.busy,
              app.replay.status, app.replay.index, app.replay.length, app.speed, app.message,
              app.algorithm, app.solve_current, id(app.result), app.details_open, app.solver_status,
              app.stage_picker, app.picker_page, app.menu, app.dropdown_open, app.sound_enabled, app.animate,
              bool(app.actions), hovered, hovered_metrics, pygame.mouse.get_pressed(), slider_state,
              app.in_main_menu, app.solver_open, round(app.drawer_t, 2), time_tick)
    animating_idle_beacon = (app.animation.frame is None and not bool(app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice' or app.in_main_menu))
    animating_board = (app.intro_t is not None or app.outro_t is not None
                       or app.bridge_view() is not None
                       or app.trauma > 0.01 or app.shockwave is not None
                       or is_split or animating_idle_beacon or drawer_animating)
    eff_pan = tuple(app.pan)
    board_key = (app.session.current_state, app.animation.frame, app.zoom, eff_pan, animating_board, renderer_view)
    cached = app._presentation_cache
    if cached and cached[0] == ui_key and not (app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice'):
        if not animating_board and cached[1] == board_key:
            return False
        if sharp_board(app):
            app._presentation_cache = (ui_key, board_key, cached[2])
            return True
        app.screen.blit(cached[2], (0, 0))
        shift_x = round(-(T.PANEL_WIDTH + 24) // 2 * app.drawer_t)
        rect = app.board_rect.move(shift_x, 0)
        if app.trauma > 0.01:
            shake_x, shake_y = camera_shake(app.trauma, pygame.time.get_ticks())
            rect = rect.move(round(shake_x), round(shake_y))
        app.screen.blit(scene(app), rect, rect)
        board = app._board_surface
        app.renderer.zoom, app.renderer.pan = app.zoom, eff_pan
        app.renderer.high_contrast = app.high_contrast
        app.renderer.pixel_scale = 1
        app.renderer.draw(board, app.session.current_state, app.animation.frame, **board_effects(app))
        app.screen.blit(board, rect)
        if not animating_board:
            app._presentation_cache = (ui_key, board_key, cached[2])
        return True
    _draw(app)
    app._presentation_cache = (ui_key, board_key, app.screen.copy())
    return True


_CONFETTI_CACHE = {}


def draw_confetti(screen, ticks, w, h):
    """Hiệu ứng pháo giấy ăn mừng 60 FPS với sprite dựng sẵn."""
    confetti_colors = (
        (255, 185, 205),  # Hồng pastel
        (255, 215, 60),   # Vàng rực
        (120, 220, 245),  # Xanh lơ nhạt
        (255, 145, 95),   # Cam đào
        (165, 235, 170),  # Xanh bạc hà
        (225, 160, 240),  # Tím oải hương
        (255, 255, 255),  # Trắng lấp lánh
    )
    t = ticks * 0.001
    for i in range(85):
        seed = i * 2903 + 57
        speed = 1.6 + (seed % 28) * 0.10
        x_base = (seed * 43) % w
        phase = (seed % 100) / 14.0
        rot_spd = 2.8 + (seed % 15) * 0.28
        col = confetti_colors[i % len(confetti_colors)]

        # Quỹ đạo rơi
        y = int((t * speed * 130 + (seed % 900)) % (h + 80)) - 40
        x = int(x_base + math.sin(t * 2.4 + phase) * 38)

        # Xoay lộn nhào 3D
        flip = math.cos(t * rot_spd + phase)
        pw = max(1, int(11 * abs(flip)))
        ph = 7

        c_key = (col, pw, ph)
        conf_surf = _CONFETTI_CACHE.get(c_key)
        if conf_surf is None:
            conf_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
            conf_surf.fill((*col, 220))
            if pw > 4:
                pygame.draw.line(conf_surf, (255, 255, 255, 180), (0, 0), (pw, 0), 1)
            _CONFETTI_CACHE[c_key] = conf_surf
        screen.blit(conf_surf, (x - pw // 2, y - ph // 2))


def draw_bloxorz_logo(screen, cx, cy, ticks, style, display, heading):
    """Vẽ biểu tượng khối Bloxorz 3D với viên kim cương lơ lửng và vòng quỹ đạo, nằm trong quầng elip."""
    pulse = 0.5 + 0.5 * math.sin(ticks * 0.0035)

    # 1. Quầng elip phát sáng bao quanh (biểu tượng và chữ nằm trọn bên trong)
    halo_w, halo_h = 410, 152
    halo_surf = pygame.Surface((halo_w, halo_h), pygame.SRCALPHA)
    for layer in range(4):
        rw = halo_w - layer * 32
        rh = halo_h - layer * 16
        alpha = int((42 + 28 * pulse) / (layer + 1.15))
        glow_color = (*T.ACCENT[:3], alpha)
        pygame.draw.ellipse(halo_surf, glow_color, ((halo_w - rw) // 2, (halo_h - rh) // 2, rw, rh))
    ring_col = (*T.ACCENT[:3], int(75 + 40 * pulse))
    pygame.draw.ellipse(halo_surf, ring_col, (4, 4, halo_w - 8, halo_h - 8), 1)
    screen.blit(halo_surf, (cx - halo_w // 2, cy - 66))

    # 2. Biểu tượng khối người chơi 3D mượt 60FPS (khối 1x1 với vân terrazzo như trong game)
    float_y = math.sin(ticks * 0.003) * 3.5
    bx, by = cx, cy - 14 + float_y

    # Quầng sáng dịu phía sau khối
    aura_r = 32
    cube_aura = pygame.Surface((aura_r * 2 + 16, aura_r * 2 + 16), pygame.SRCALPHA)
    pygame.draw.circle(cube_aura, (*T.ACCENT[:3], int(65 + 35 * pulse)), (aura_r + 8, aura_r + 8), aura_r + 4)
    screen.blit(cube_aura, (bx - aura_r - 8, by - aura_r - 2))

    # Hình học khối người chơi 1x1 isometric
    bw, bh_face = 20, 11
    block_h = 22
    top_pts = [(bx, by - bh_face), (bx + bw, by - 1), (bx, by + bh_face - 2), (bx - bw, by - 1)]
    left_pts = [(bx - bw, by - 1), (bx, by + bh_face - 2), (bx, by + block_h), (bx - bw, by + block_h - bh_face + 1)]
    right_pts = [(bx, by + bh_face - 2), (bx + bw, by - 1), (bx + bw, by + block_h - bh_face + 1), (bx, by + block_h)]

    top_col = lerp_color(T.ACCENT, (255, 240, 248), 0.75) if style == 'dream' else ((225, 245, 255) if style == 'blueprint' else (240, 255, 230))
    left_col = lerp_color(T.ACCENT, (215, 140, 175) if style == 'dream' else ((60, 150, 215) if style == 'blueprint' else (90, 175, 105)), 0.50)
    right_col = lerp_color(T.ACCENT, (135, 65, 100) if style == 'dream' else ((25, 80, 140) if style == 'blueprint' else (45, 105, 55)), 0.80)

    pygame.draw.polygon(screen, left_col, left_pts)
    pygame.draw.polygon(screen, right_col, right_pts)
    pygame.draw.polygon(screen, top_col, top_pts)

    # Đốm vân terrazzo (giống khối người chơi trong game)
    speckles = [
        (-12, 4, 1), (-5, 12, 1), (-8, 18, 2), (-15, 11, 1),
        (5, 7, 1), (12, 14, 1), (7, 19, 2), (14, 8, 1),
        (-6, -4, 1), (6, -2, 1), (0, 3, 2), (8, 2, 1)
    ]
    sp_col = (255, 255, 255, 190)
    for sx, sy, sr in speckles:
        pygame.draw.circle(screen, sp_col, (round(bx + sx), round(by + sy)), sr)

    # Đường chia giữa phát sáng và cạnh vát phản chiếu
    seam_y = by + block_h // 2 + 1
    pygame.draw.line(screen, (*T.ACCENT[:3], 160), (bx - bw, seam_y - bh_face + 1), (bx, seam_y))
    pygame.draw.line(screen, (*T.ACCENT[:3], 130), (bx, seam_y), (bx + bw, seam_y - bh_face + 1))
    pygame.draw.lines(screen, (255, 255, 255, 240), True, top_pts, 1)
    pygame.draw.line(screen, (255, 255, 255, 180), (bx, by + bh_face - 2), (bx, by + block_h), 1)

    # 3. Viên kim cương beacon 3D lơ lửng trên khối, có vòng quỹ đạo
    diamond_y = by - 24 + math.sin(ticks * 0.005) * 2.5
    d_top = (bx, diamond_y - 8)
    d_bot = (bx, diamond_y + 8)
    d_left = (bx - 7, diamond_y)
    d_right = (bx + 7, diamond_y)
    d_front = (bx, diamond_y + 3)

    # Các mặt kim cương
    pygame.draw.polygon(screen, (255, 255, 255), [d_top, d_left, d_front])
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (255, 255, 255), 0.5), [d_top, d_front, d_right])
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (80, 20, 50), 0.4), [d_front, d_left, d_bot])
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (40, 10, 30), 0.7), [d_front, d_right, d_bot])

    # Vòng quỹ đạo quanh viên kim cương
    ring_rx, ring_ry = 18, 5
    ring_surf = pygame.Surface((ring_rx * 2 + 4, ring_ry * 2 + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(ring_surf, (*T.ACCENT[:3], int(160 + 75 * pulse)), (2, 2, ring_rx * 2, ring_ry * 2), 1)
    # Đốm sáng chạy trên quỹ đạo
    orb_angle = ticks * 0.006
    orb_x = ring_rx + 2 + round(math.cos(orb_angle) * ring_rx)
    orb_y = ring_ry + 2 + round(math.sin(orb_angle) * ring_ry)
    pygame.draw.circle(ring_surf, (255, 255, 255), (orb_x, orb_y), 2)
    screen.blit(ring_surf, (bx - ring_rx - 2, diamond_y - ring_ry - 2))

    # Các tia lấp lánh phản chiếu
    spark_phase = (ticks * 0.005) % (math.pi * 2)
    for i, (sx, sy) in enumerate(((bx - bw, by - 1), (bx + bw, by - 1), (bx, by + bh_face - 2), (bx, diamond_y - 8))):
        s_size = 2.4 + 1.4 * math.sin(spark_phase + i * 2.0)
        if s_size > 2.0:
            pygame.draw.line(screen, (255, 255, 255), (sx - s_size, sy), (sx + s_size, sy), 1)
            pygame.draw.line(screen, (255, 255, 255), (sx, sy - s_size), (sx, sy + s_size), 1)

    # 4. Chữ nổi "BLOXORZ" + nhãn [ 3D ] kính mờ (bên trong elip)
    t_surf = display.render("BLOXORZ", True, T.TEXT)
    shadow_col = (0, 0, 0, 75) if style != 'dream' else (160, 120, 140, 65)
    t_shadow = display.render("BLOXORZ", True, shadow_col)

    badge_w, badge_h = 48, 26
    total_w = t_surf.get_width() + 12 + badge_w
    t_x = cx - total_w // 2
    t_y = cy + 20

    # Bóng chữ và chữ phía trước
    screen.blit(t_shadow, (t_x, t_y + 2))
    screen.blit(t_surf, (t_x, t_y))

    # Nhãn viên thuốc [ 3D ] kính mờ
    badge_rect = pygame.Rect(t_x + t_surf.get_width() + 12, t_y + (t_surf.get_height() - badge_h) // 2, badge_w, badge_h)
    draw_glass_panel(screen, badge_rect, style=style, border_radius=13, shadow=False, fill_alpha=120)
    badge_3d = heading.render("3D", True, T.ACCENT)
    screen.blit(badge_3d, badge_3d.get_rect(center=badge_rect.center))


def draw_main_menu(app):
    """Màn hình mở đầu kiểu kính mờ (glassmorphism) theo thiết kế tham khảo."""
    screen = app.screen
    w, h = screen.get_size()
    style = app.visual_style
    screen.blit(scene(app), (0, 0))

    # Viền tối mờ xung quanh
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    vignette.fill((8, 16, 26, 75) if style != 'dream' else (255, 238, 244, 45))
    screen.blit(vignette, (0, 0))

    body = T.font('body', app.large_text)
    heading = T.font('heading', app.large_text)
    display = T.font('display', app.large_text)
    caption = T.font('caption', app.large_text)

    # Thẻ kính mờ ở giữa - đứng yên, ổn định và căn giữa
    mw = min(480, w - 40)
    mh = min(540, h - 40)
    card_rect = pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)
    draw_glass_panel(screen, card_rect, style=style, border_radius=28, shadow=True, fill_alpha=190 if style == 'dream' else 215)

    # Khi có hộp thoại (Settings/Help/Stage), ẩn hẳn các thành phần phía sau để chữ không bị bóng ma
    modal_active = bool(app.stage_picker or app.menu)
    if not modal_active:
        draw_bloxorz_logo(screen, card_rect.centerx, card_rect.y + 70, app._ticks, style, display, heading)

        btn_w = mw - 72
        btn_x = card_rect.x + 36
        start_y = card_rect.y + 160
        btn_gap = 14

        def menu_btn(key, label, y, kind='pill', height=46, icon=None, btn_font=body):
            b = Button(key, label, pygame.Rect(btn_x, y, btn_w, height), True, False, kind, icon=icon)
            app.buttons.append(b)
            b.draw(screen, btn_font)

        # Nút New Game nổi bật: chữ lớn hơn, màu đậm hơn, quầng sáng "thở"
        play_label = f"Continue Stage {app.stage_index + 1:02}" if (app.actions or app.stage_index > 0) else "New Game"
        menu_btn('continue_game', play_label, start_y, kind='primary', height=52, icon='play', btn_font=heading)
        menu_btn('choose', "Select Stage", start_y + 52 + btn_gap, kind='pill', height=46, icon='view')
        menu_btn('settings', "Audio & Settings", start_y + 52 + btn_gap + (46 + btn_gap), kind='pill', height=46, icon='settings')
        menu_btn('help', "How to Play & Controls", start_y + 52 + btn_gap + (46 + btn_gap) * 2, kind='pill', height=46, icon='help')

        # Nút đổi theme và nút Exit Game cạnh nhau ở đáy thẻ
        theme_name = NAMES.get(style, style)
        bw = (btn_w - 12) // 2
        b_th = Button('theme', f'Theme: {theme_name}', pygame.Rect(btn_x, card_rect.bottom - 48, bw, 36), True, False, 'pill', icon='theme')
        b_ex = Button('exit_game', 'Exit Game', pygame.Rect(btn_x + bw + 12, card_rect.bottom - 48, bw, 36), True, False, 'pill', icon='close')
        app.buttons.append(b_th)
        app.buttons.append(b_ex)
        b_th.draw(screen, caption)
        b_ex.draw(screen, caption)

    # Hướng dẫn phím tắt ở đáy màn hình
    hint = caption.render("Space / Enter: Play  ·  Esc: Game  ·  T: Theme  ·  S: Settings  ·  H: Help  ·  Q: Exit", True, T.MUTED)
    screen.blit(hint, hint.get_rect(center=(w // 2, h - 20)))


def draw_header_emblem(surface, bx, by, style, scale=1):
    """Khối lập phương 3D nhỏ cạnh chữ BLOXORZ; (bx, by) là tâm của nó theo pixel logic."""
    def at(dx, dy):
        return ((bx + dx) * scale, (by + dy) * scale)
    top = [at(0, -7), at(9, -2), at(0, 2), at(-9, -2)]
    left = [at(-9, -2), at(0, 2), at(0, 11), at(-9, 6)]
    right = [at(0, 2), at(9, -2), at(9, 6), at(0, 11)]
    pygame.draw.polygon(surface, lerp_color(T.ACCENT, (22, 32, 48) if style != 'dream' else (185, 122, 155), 0.35), left)
    pygame.draw.polygon(surface, lerp_color(T.ACCENT, (8, 12, 22) if style != 'dream' else (135, 72, 105), 0.65), right)
    pygame.draw.polygon(surface, lerp_color(T.ACCENT, (255, 255, 255), 0.58), top)
    pygame.draw.lines(surface, (255, 255, 255, 200), True, top, max(1, round(scale)))
    # Tia lấp lánh trên đỉnh khối nhỏ
    pygame.draw.circle(surface, (255, 255, 255), (round(bx * scale), round((by - 7) * scale)), max(1, round(scale)))


@dataclass
class _Frame:
    app: object
    screen: pygame.Surface
    w: int
    h: int
    style: str
    mouse: tuple
    ticks: int
    body: pygame.font.Font
    heading: pygame.font.Font
    mono: pygame.font.Font
    mono_lg: pygame.font.Font
    caption: pygame.font.Font

    def label(self, value, x, y, color=None, f=None, max_width=None):
        text(self.screen, f or self.body, value, (x, y), T.TEXT if color is None else color, max_width)

    def button(self, key, value, x, y, width, enabled=True, kind='secondary', selected=False, height=None, icon=None):
        b = Button(key, value, pygame.Rect(x, y, width, T.BUTTON_HEIGHT if height is None else height),
                   enabled, selected, kind, icon=icon)
        self.app.buttons.append(b)
        b.draw(self.screen, self.body)
        return b


def _frame(app):
    w, h = app.screen.get_size()
    large = app.large_text
    return _Frame(app, app.screen, w, h, app.visual_style, pygame.mouse.get_pos(), app._ticks,
                  T.font('body', large), T.font('heading', large), T.font('mono', large),
                  T.font('mono_lg', large), T.font('caption', large))


def _draw(app):
    app._emblem = None  # đặt ở dưới khi present() cần vẽ biểu tượng ở header
    f = _frame(app)
    screen, w, h, style = f.screen, f.w, f.h, f.style
    app.buttons = []
    app.metric_rects = []
    app.seek_rect = pygame.Rect(0, 0, 0, 0)

    # Kiểm tra trạng thái menu chính
    if app.in_main_menu:
        draw_main_menu(app)
        _draw_modals(f, idle=True)
        return

    screen.blit(scene(app), (0, 0))
    _draw_top_veil(app, screen, w, style)

    replaying = app.replay.status != ReplayStatus.EMPTY
    idle = not app.busy and not app.animation.busy and app.intro_t is None and app.outro_t is None
    manual = idle and not replaying

    # Ngăn solver: có hiện không và animation chuyển cảnh
    is_drawer_visible = (app.solver_open or replaying or app.busy or app.dropdown_open)
    panel_x = w - T.PANEL_WIDTH - 24 if is_drawer_visible else w
    center_w = panel_x if is_drawer_visible else w

    _draw_board(app, f, panel_x - 16 if is_drawer_visible else w)
    _draw_header(f)
    _draw_toast(f, center_w, replaying)
    _draw_dock(f, center_w, replaying, idle)
    if is_drawer_visible:
        _draw_solver_drawer(f, panel_x, replaying, idle, manual)

    # Mưa pháo giấy ăn mừng khi thắng
    if app.win_phase in ('sink', 'disassemble', 'choice'):
        draw_confetti(screen, pygame.time.get_ticks(), w, h)

    _draw_modals(f, idle)


def _draw_top_veil(app, screen, w, style):
    # Dải mờ thanh điều hướng phía trên (có cache)
    veil_cache = app._veil_cache
    if veil_cache is None or veil_cache[0] != (w, style):
        veil = pygame.Surface((w, 80), pygame.SRCALPHA)
        if style == 'dream':
            for yy in range(80):
                pygame.draw.line(veil, (253, 222, 209, round(225 * (1 - yy / 80) ** .45)), (0, yy), (w, yy))
        elif style == 'forest':
            veil.fill((14, 27, 20, 110))
        app._veil_cache = ((w, style), veil)
    else:
        veil = veil_cache[1]

    if style in ('dream', 'forest'):
        screen.blit(veil, (0, 0))
    else:
        pygame.draw.line(screen, T.LINE, (24, 78), (w - 24, 78))


def _draw_board(app, f, visible_w):
    # Khung nhìn bàn chơi: bắt đầu đúng y=80 dưới dải mờ và kết thúc trước toast/dock phía dưới
    w, h = f.w, f.h
    shift_x = round(-(T.PANEL_WIDTH + 24) // 2 * app.drawer_t)
    app.board_rect = pygame.Rect(0, 80, visible_w, h - 182)
    board = app._board_surface
    if board is None or board.get_size() != (w, h - 182):
        board = pygame.Surface((w, h - 182), pygame.SRCALPHA)
        app._board_surface = board

    app.renderer.zoom, app.renderer.pan = app.zoom, tuple(app.pan)
    app.renderer.high_contrast = app.high_contrast
    if not sharp_board(app):
        app.renderer.pixel_scale = 1
        app.renderer.draw(board, app.session.current_state, app.animation.frame, **board_effects(app))
        draw_x, draw_y = 0, 80
        if app.trauma > 0.01:
            shake_x, shake_y = camera_shake(app.trauma, f.ticks)
            draw_x += round(shake_x)
            draw_y += round(shake_y)
        clip_rect = pygame.Rect(max(0, -shift_x), 0, min(visible_w, w - max(0, -shift_x)), h - 182)
        f.screen.blit(board, (draw_x, draw_y), clip_rect)


def _hover_capsule(f, rect, phase=0.0):
    f.app.metric_rects.append(rect)
    hover = rect.collidepoint(f.mouse)
    drawn = rect.move(round(math.sin(f.ticks * 0.008 + phase) * 1.5), round(math.cos(f.ticks * 0.008 + phase) * 1.5)) if hover else rect
    draw_glass_panel(f.screen, drawn, style=f.style, border_radius=21, shadow=False)
    if hover:
        pygame.draw.rect(f.screen, (*T.ACCENT[:3], 130), drawn, 1, border_radius=21)
    return drawn


def _draw_header(f):
    # 1. Một hàng header thống nhất trong game (y = 16, cao 42)
    app, screen, w = f.app, f.screen, f.w
    header_y = 16
    header_h = 42

    # Trái: khung logo với viên pha lê động và lắc nhẹ khi hover
    logo_w = 162
    draw_logo_rect = _hover_capsule(f, pygame.Rect(16, header_y, logo_w, header_h))

    # Biểu tượng 3D nhỏ nhấp nhô mượt (luôn nhấp nhô).
    # Trên cửa sổ Retina, present() vẽ nó mỗi frame ở độ phân giải đầy đủ, nên
    # không phải dựng lại UI đã cache mỗi frame chỉ vì nhấp nhô.
    mini_bx = draw_logo_rect.x + 22
    if sharp_board(app):
        app._emblem = (mini_bx, draw_logo_rect.centery, f.style)
    else:
        draw_header_emblem(screen, mini_bx, draw_logo_rect.centery + math.sin(f.ticks * 0.005) * 2.8, f.style)
    logo_title = f.heading.render("BLOXORZ", True, T.TEXT)
    screen.blit(logo_title, (draw_logo_rect.x + 38, draw_logo_rect.y + (header_h - logo_title.get_height()) // 2))

    # Khung nút Menu
    menu_btn_x = 16 + logo_w + 10
    f.button('main_menu', 'Menu', menu_btn_x, header_y, 88, kind='pill', height=header_h, icon='menu')

    # Khung số nước đi, lắc nhẹ khi hover (gọn, chỉ tập trung vào số nước)
    stat_x = menu_btn_x + 88 + 10
    draw_stat_rect = _hover_capsule(f, pygame.Rect(stat_x, header_y, 126, header_h), phase=1.2)
    stat_surf = f.body.render(f"{app.session.moves} MOVES", True, T.TEXT)
    screen.blit(stat_surf, stat_surf.get_rect(center=draw_stat_rect.center))

    # Các nút điều hướng bên phải header (gồm cả nút Exit)
    nav_right = w - 16
    f.button('exit_game', 'Exit', nav_right - 72, header_y, 72, kind='pill', height=header_h, icon='close')
    f.button('help', 'Help', nav_right - 72 - 8 - 84, header_y, 84, kind='pill', height=header_h, icon='help')
    f.button('settings', 'Settings', nav_right - 72 - 8 - 84 - 8 - 110, header_y, 110, kind='pill', height=header_h, icon='settings')
    theme_text = {'dream': 'Dream City', 'forest': 'Forest Ruins', 'blueprint': 'Blueprint'}.get(f.style, f.style)
    f.button('theme', theme_text, nav_right - 72 - 8 - 84 - 8 - 110 - 8 - 140, header_y, 140, kind='pill', height=header_h, icon='theme')
    f.button('choose', f'Stage {app.stage_index + 1:02}', nav_right - 72 - 8 - 84 - 8 - 110 - 8 - 140 - 8 - 124, header_y, 124, bool(app.stage_paths), kind='pill', height=header_h, icon='view')


def _draw_toast(f, center_w, replaying):
    # Thông báo toast căn giữa: luôn nằm TRÊN dock phía dưới (y = h - 96, cao 26)
    app = f.app
    message = app.message
    hidden = ('Rolling...', 'Move accepted.', 'Stage loaded. Arrow keys / WASD to roll.',
              'Roll with arrows or WASD. Reach G standing upright.')
    if message in hidden:
        message = 'Use arrow keys or WASD to roll the block.' if not app.actions and not replaying else ''
    if app.busy:
        message = ''
    if message:
        m_w = min(center_w - 48, max(280, f.caption.size(message)[0] + 44))
        m_x = (center_w - m_w) // 2
        toast_rect = pygame.Rect(m_x, f.h - 96, m_w, 26)
        draw_glass_panel(f.screen, toast_rect, style=f.style, border_radius=13, shadow=False, fill_alpha=185)
        m_surf = f.caption.render(message, True, T.TEXT)
        f.screen.blit(m_surf, m_surf.get_rect(center=toast_rect.center))


def _draw_dock(f, center_w, replaying, idle):
    # Dock dưới đáy căn giữa (y = h - 60, cao 44) - ổn định, không nháy hay nhảy khi đi
    app, h, button = f.app, f.h, f.button
    if not replaying:
        dock_w = 96 + 102 + 94 + 118 + 36
        dock_x = max(16, (center_w - dock_w) // 2)
        button('undo', 'Undo', dock_x, h - 60, 96, bool(app.actions), kind='dock_item', icon='undo', height=44)
        button('restart', 'Restart', dock_x + 96 + 12, h - 60, 102, True, kind='dock_item', icon='restart', height=44)
        button('hint', 'Hint', dock_x + 96 + 102 + 24, h - 60, 94, not app.busy, kind='dock_item', icon='hint', height=44)
        if not app.busy:
            button('solve', 'AI Solver', dock_x + 96 + 102 + 94 + 36, h - 60, 118, True,
                   kind='primary' if app.solver_open else 'dock_item', selected=app.solver_open, icon='solve', height=44)
        return
    left = max(16, (center_w - 480) // 2)
    button('back', 'Back', left, h - 60, 72, app.replay.index > 0, kind='dock_item', icon='back', height=44)
    button('play', 'Pause' if app.replay.status == ReplayStatus.PLAYING else 'Play',
           left + 78, h - 60, 92, not app.busy, 'primary', icon='play' if app.replay.status != ReplayStatus.PLAYING else 'pause', height=44)
    button('step', 'Next', left + 176, h - 60, 72, idle and app.replay.index < app.replay.length, kind='dock_item', icon='step', height=44)
    button('speed', f'{app.speed:g}×', left + 254, h - 60, 60, kind='dock_item', height=44)
    timeline_x = left + 322
    seek_w = max(44, center_w - 40 - timeline_x)
    app.seek_rect = pygame.Rect(timeline_x, h - 41, seek_w, 6)
    pygame.draw.rect(f.screen, T.LINE, app.seek_rect, border_radius=3)
    ratio = app.replay.index / max(1, app.replay.length)
    fill = app.seek_rect.copy()
    fill.width = int(fill.width * ratio)
    pygame.draw.rect(f.screen, T.ACCENT, fill, border_radius=3)
    pygame.draw.circle(f.screen, T.ACCENT, (app.seek_rect.x + fill.width, app.seek_rect.centery), 5)
    f.label(f'{app.replay.index} / {app.replay.length}', timeline_x + seek_w + 10, h - 47, T.MUTED, f=f.caption)


def _draw_solver_drawer(f, panel_x, replaying, idle, manual):
    # Ngăn solver bên phải (vẽ khi đang mở / đang hoạt động)
    app, h = f.app, f.h
    if replaying:
        card_h = 360 if (app.stage_cleared and app.stage_index + 1 < len(app.stage_paths)) else 312
    elif app.busy:
        card_h = 254
    elif app.result and app.result.found:
        card_h = 446 if app.details_open else 336
    else:
        if app.dropdown_open or app.solver_status in SOLVER_FAILURES:
            card_h = 368
        else:
            card_h = 326
    if app.large_text:
        card_h += 8
    card_h = min(card_h, h - 96)

    card_y = max(76, min(h - card_h - 70, (h - card_h) // 2))
    card_rect = pygame.Rect(panel_x - 16, card_y, T.PANEL_WIDTH + 32, card_h)
    draw_glass_panel(f.screen, card_rect, f.style, border_radius=22, shadow=False)

    x, pw, y = panel_x, T.PANEL_WIDTH, card_y
    pygame.draw.line(f.screen, T.LINE, (x + 8, y + 40), (x + pw - 8, y + 40))

    # Nút đóng ngăn solver
    if not app.busy and not replaying:
        f.button('close_solver', '✕', card_rect.right - 38, y + 8, 30, height=30, kind='close_btn', icon='close')

    if replaying:
        _drawer_replay(f, x, y, pw)
    elif app.busy:
        _drawer_searching(f, x, y, pw)
    elif app.result and app.result.found:
        _drawer_result(f, x, y, pw, idle)
    else:
        _drawer_form(f, x, y, pw, manual)


def _drawer_replay(f, x, y, pw):
    app, label, button = f.app, f.label, f.button
    label('Watch solution', x, y + 4, f=f.heading)
    label('One move at a time.', x, y + 36, T.MUTED, f=f.caption)
    label(f'{app.replay.index} / {app.replay.length}', x, y + 78, f=f.mono_lg)
    label('moves played', x, y + 116, T.MUTED, f=f.caption)
    button('stop', 'Exit replay', x, y + 162, pw, kind='dock_item', icon='stop')
    button('rewind', 'Back to start', x, y + 210, pw, kind='quiet')
    if app.stage_cleared and app.stage_index + 1 < len(app.stage_paths):
        button('next_stage', 'Next stage   >', x, y + 258, pw, not app.busy, 'primary')


def _drawer_searching(f, x, y, pw):
    label = f.label
    label('Finding a path', x, y + 4, f=f.heading)
    label(solver_label(f.app.algorithm), x, y + 36, T.MUTED, f=f.caption)
    center = (x + 12, y + 104)
    angle = pygame.time.get_ticks() / 350
    pygame.draw.circle(f.screen, T.LINE, center, 10, 2)
    pygame.draw.arc(f.screen, T.ACCENT, (center[0] - 10, center[1] - 10, 20, 20), angle, angle + 4, 2)
    label('Exploring possible moves…', x + 32, y + 92, T.MUTED, max_width=pw - 32)
    f.button('cancel', 'Cancel search', x, y + 152, pw)


def _drawer_result(f, x, y, pw, idle):
    app, screen, button = f.app, f.screen, f.button
    m = app.result.metrics
    f.label('A way forward', x + 4, y + 6, f=f.heading)

    # Thẻ tóm tắt lời giải nổi bật, nhấc lên và lắc nhẹ khi hover
    sol_rect = pygame.Rect(x, y + 44, pw, 58)
    app.metric_rects.append(sol_rect)
    sol_hover = sol_rect.collidepoint(f.mouse)
    draw_sol = sol_rect.move(round(math.sin(f.ticks * 0.008) * 1.5), -3 + round(math.cos(f.ticks * 0.008) * 1.0)) if sol_hover else sol_rect

    draw_glass_panel(screen, draw_sol, style=f.style, border_radius=16, shadow=sol_hover, fill_alpha=185 if sol_hover else 160)
    if sol_hover:
        sol_glow = pygame.Surface((draw_sol.width + 10, draw_sol.height + 10), pygame.SRCALPHA)
        pygame.draw.rect(sol_glow, (*T.ACCENT[:3], 45), sol_glow.get_rect(), border_radius=20)
        screen.blit(sol_glow, (draw_sol.x - 5, draw_sol.y - 5))
    pygame.draw.rect(screen, (*T.ACCENT[:3], 200 if sol_hover else 120), draw_sol, 1, border_radius=16)
    text(screen, f.caption, "OPTIMAL SOLUTION READY", (draw_sol.x + 14, draw_sol.y + 10), T.ACCENT)
    text(screen, f.heading, f"{m.solution_length} Moves  ·  {solver_label(app.result.algorithm)}", (draw_sol.x + 14, draw_sol.y + 28), T.TEXT)

    button('solution', 'Watch solution', x, y + 116, pw, idle, 'primary', icon='play')
    button('details', ('−' if app.details_open else '+') + '  Result details', x, y + 168, pw, kind='dock_item')
    offset = y + 222
    if app.details_open:
        bw = (pw - 8) // 2
        bh = 50
        r_time = pygame.Rect(x, offset, bw, bh)
        r_ram = pygame.Rect(x + bw + 8, offset, bw, bh)
        r_exp = pygame.Rect(x, offset + bh + 8, bw, bh)
        r_cost = pygame.Rect(x + bw + 8, offset + bh + 8, bw, bh)
        app.metric_rects.extend([r_time, r_ram, r_exp, r_cost])
        caption, mono = f.caption, f.mono
        draw_bento_card(screen, r_time, 'TIME', f'{m.time_sec:.3f}', 's', f.style, caption, mono, caption)
        draw_bento_card(screen, r_ram, 'RAM', f'{m.peak_memory_mb:.2f}', 'MB', f.style, caption, mono, caption)
        draw_bento_card(screen, r_exp, 'EXPANDED', f'{m.expanded_nodes}', '', f.style, caption, mono, caption)
        draw_bento_card(screen, r_cost, 'COST', f'{m.total_cost:g}', '', f.style, caption, mono, caption)
        offset += (bh * 2 + 16)
    button('new_search', 'Try another algorithm', x, offset + 10, pw, idle, 'quiet')


def _drawer_form(f, x, y, pw, manual):
    app, label, button = f.app, f.label, f.button
    label('S O L V E R', x + 8, y + 4, f=f.heading)
    label('ALGORITHM', x, y + 42, T.MUTED, f=f.caption)
    button('algorithm_menu', solver_label(app.algorithm) + '   ', x, y + 68, pw, manual)
    label('START FROM', x, y + 128, T.MUTED, f=f.caption)
    src_btn_w = (pw - 12) // 2
    button('source_start', 'Start', x, y + 154, src_btn_w, manual, selected=not app.solve_current)
    button('source_current', 'Current', x + src_btn_w + 12, y + 154, src_btn_w, manual, selected=app.solve_current)
    button('solve_now', 'Solve   >', x, y + 224, pw, manual, 'primary')
    if app.solver_status in SOLVER_FAILURES:
        label(SOLVER_FAILURES[app.solver_status], x, y + 276, T.MUTED, max_width=pw)
    if app.dropdown_open:
        app.dropdown_rect = pygame.Rect(x, y + 114, pw, 4 * 44 + 16)
        draw_glass_panel(f.screen, app.dropdown_rect, f.style, border_radius=12)
        app.buttons = [b for b in app.buttons if not b.rect.colliderect(app.dropdown_rect)]
        for i, (key, title) in enumerate((('BFS', 'BFS'), ('IDS', 'IDS'), ('UCS', 'UCS'), ('ASTAR', 'A*'))):
            button('algorithm:' + key, title, x + 8, y + 122 + i * 44, pw - 16,
                   kind='quiet', selected=app.algorithm == key)


def _draw_modals(f, idle):
    app, screen, w, h = f.app, f.screen, f.w, f.h
    # Hộp thoại chọn sau khi thắng
    if app.win_phase == 'choice' and not (app.stage_picker or app.menu):
        _draw_win_modal(f)

    # Các menu (chọn màn, Settings, Help)
    if not (app.stage_picker or app.menu):
        return
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    # Lớp phủ kính mờ đậm để chữ của menu phía sau không lộ ra
    shade.fill((5, 12, 17, 242) if f.style != 'dream' else (35, 18, 28, 230))
    screen.blit(shade, (0, 0))
    app.buttons = []
    app.seek_rect = pygame.Rect(0, 0, 0, 0)

    mw = 608 if app.stage_picker else (710 if app.menu == 'help' else 480)
    mh = 464 if app.stage_picker else (540 if app.menu == 'help' else 590)
    app.modal_rect = pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)
    r = app.modal_rect
    draw_glass_panel(screen, r, style=f.style, border_radius=26, shadow=True, fill_alpha=215 if f.style == 'dream' else 235)

    title = 'Choose a stage' if app.stage_picker else ('Settings & Audio' if app.menu == 'settings' else 'How to Play & Controls')
    f.label(title, r.x + 32, r.y + 24, f=f.heading)
    # Nút đóng tròn nổi bật
    f.button('close_menu', '✕', r.right - 54, r.y + 20, 36, height=36, kind='close_btn', icon='close')

    if app.stage_picker:
        _draw_stage_picker(f, r)
    elif app.menu == 'settings':
        _draw_settings(f, r, idle)
    else:
        _draw_help(f, r, mw)


def _draw_win_modal(f):
    app, w, h = f.app, f.w, f.h
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    shade.fill((5, 12, 17, 160))
    f.screen.blit(shade, (0, 0))
    app.buttons = []
    app.seek_rect = pygame.Rect(0, 0, 0, 0)
    app.modal_rect = pygame.Rect((w - 480) // 2, (h - 272) // 2, 480, 272)
    r = app.modal_rect
    last = app.stage_index + 1 >= len(app.stage_paths)
    draw_glass_panel(f.screen, r, style=f.style, border_radius=24, shadow=True)
    f.label('Stage complete!', r.x + 32, r.y + 24, f=f.heading)
    f.label(f'Stage {app.stage_index + 1:02} cleared in {app.session.moves} moves.', r.x + 32, r.y + 72, T.MUTED)
    f.button('win_replay', 'Replay my moves', r.x + 32, r.y + 136, 200, kind='pill')
    if last:
        f.button('restart', 'Play again', r.x + 248, r.y + 136, 200, kind='primary', height=40)
    else:
        f.button('next_stage', 'Next stage   >', r.x + 248, r.y + 136, 200, kind='primary', height=40)

    keys = 'P: replay  ·  R: play again' if last else 'P: replay  ·  Enter: next stage  ·  R: restart'
    f.label(keys, r.x + 32, r.bottom - 56, T.MUTED, max_width=416)


def _draw_stage_picker(f, r):
    app, button = f.app, f.button
    first = app.picker_page * STAGES_PER_PAGE
    for i, path in enumerate(app.stage_paths[first:first + STAGES_PER_PAGE]):
        index = first + i
        button(f'stage:{index}', f'{index + 1:02}', r.x + 32 + (i % 4) * 136,
               r.y + 88 + (i // 4) * 56, 128, selected=index == app.stage_index, kind='pill', height=42)
    button('page_prev', 'Previous', r.x + 32, r.bottom - 64, 152, app.picker_page > 0, 'quiet')
    button('page_next', 'Next', r.right - 184, r.bottom - 64, 152,
           (app.picker_page + 1) * STAGES_PER_PAGE < len(app.stage_paths), 'quiet')


def _draw_slider(f, title, name, x, track_x, y, width, volume):
    rect = pygame.Rect(track_x, y - 8, width, 20)
    f.label(title, x, y - 8)
    pygame.draw.line(f.screen, T.LINE, (track_x, y), (track_x + width, y), 4)
    fill_w = int(width * volume)
    if fill_w > 0:
        pygame.draw.line(f.screen, T.ACCENT, (track_x, y), (track_x + fill_w, y), 4)
    knob_x = track_x + fill_w
    hover = rect.inflate(0, 12).collidepoint(f.mouse) or f.app.active_slider == name
    if hover:
        pygame.draw.circle(f.screen, (*T.ACCENT[:3], 80), (knob_x, y), 11)
    pygame.draw.circle(f.screen, T.ACCENT, (knob_x, y), 7 if not hover else 8)
    pygame.draw.circle(f.screen, (255, 255, 255), (knob_x, y), 3)
    f.label(f'{int(volume * 100)}%', track_x + width + 14, y - 8, T.MUTED, f=f.mono)
    return rect


def _draw_settings(f, r, idle):
    app, screen, label, button = f.app, f.screen, f.label, f.button
    xx, yy = r.x + 32, r.y + 76
    button('save', 'Save session · F5', xx, yy, 196, idle, kind='pill', icon='save')
    button('load', 'Load session · F9', xx + 212, yy, 196, kind='pill', icon='load')

    label('Master Sound', xx, yy + 58)
    button('sound', 'On' if app.sound_enabled else 'Off', r.right - 120, yy + 50, 88, selected=app.sound_enabled, kind='pill')

    track_x = xx + 130
    app.bgm_slider_rect = _draw_slider(f, 'Music (BGM)', 'bgm', xx, track_x, yy + 102, 175, app.bgm_volume)
    app.sfx_slider_rect = _draw_slider(f, 'Sound FX', 'sfx', xx, track_x, yy + 138, 175, app.sfx_volume)

    pygame.draw.line(screen, T.LINE, (xx, yy + 168), (r.right - 32, yy + 168), 1)

    # Thẻ giới thiệu AI Solver nổi bật
    solver_card = pygame.Rect(xx, yy + 182, r.width - 64, 54)
    draw_glass_panel(screen, solver_card, style=f.style, border_radius=16, shadow=False, fill_alpha=175)
    pygame.draw.rect(screen, (*T.ACCENT[:3], 180), solver_card, 2, border_radius=16)
    glow = pygame.Surface((solver_card.width + 12, solver_card.height + 12), pygame.SRCALPHA)
    pygame.draw.rect(glow, (*T.ACCENT[:3], 35), glow.get_rect(), border_radius=22)
    screen.blit(glow, (solver_card.x - 6, solver_card.y - 6))

    draw_vector_icon(screen, 'solve', (solver_card.x + 24, solver_card.centery), T.ACCENT, size=18)
    label('AI SOLVER PANEL', solver_card.x + 44, solver_card.centery - 10, color=T.TEXT, f=f.heading)
    button('toggle_solver', 'On' if app.solver_open else 'Off', solver_card.right - 98, solver_card.y + 7, 88,
           selected=app.solver_open, kind='primary' if app.solver_open else 'pill', height=40, icon='solve')

    for i, (key, m_title, enabled) in enumerate((
            ('animate', 'Animation', app.animate),
            ('contrast', 'High Contrast', app.high_contrast),
            ('text', 'Large Text', app.large_text))):
        row_y = yy + 248 + i * 40
        label(m_title, xx, row_y + 8)
        button(key, 'On' if enabled else 'Off', r.right - 120, row_y, 88, selected=enabled, kind='pill')

    # View & Camera: nút viên thuốc có viền và icon vector cho dễ bấm
    view_label = 'View: Original' if app.renderer.view == 'original' else 'View: Classic'
    button('view', view_label + ' · V', xx, r.bottom - 100, 196, kind='pill', icon='view', height=40)
    button('camera', 'Reset camera', xx + 212, r.bottom - 100, 196, kind='pill', icon='restart', height=40)
    button('recording', 'Replay my moves', xx, r.bottom - 50, 408, idle and bool(app.actions), kind='pill', height=38)


def _draw_help(f, r, mw):
    # 4 thẻ Bento tương tác cho phần HƯỚNG DẪN CHƠI
    grid_w = (mw - 64 - 16) // 2
    grid_h = 204
    c1_x, c2_x = r.x + 32, r.x + 32 + grid_w + 16
    r1_y, r2_y = r.y + 76, r.y + 76 + grid_h + 14

    # Thẻ 1: Mục tiêu & luật
    _draw_help_card(f, c1_x, r1_y, grid_w, grid_h, "GOAL & OBJECTIVE", "play", [
        ("STAND", "Stand 1×1×2 block upright in goal"),
        ("EDGES", "Falling off restarts current stage"),
        ("ORANGE", "Fragile tiles break if upright!"),
    ])

    # Thẻ 2: Điều khiển & di chuyển
    _draw_help_card(f, c2_x, r1_y, grid_w, grid_h, "CONTROLS & MOVES", "step", [
        ("WASD", "Roll block in 4 directions"),
        ("SPACE", "Switch active cube when split"),
        ("Z / U", "Undo move  ·  R: Restart stage"),
    ])

    # Thẻ 3: Công tắc & cầu
    _draw_help_card(f, c1_x, r2_y, grid_w, grid_h, "SWITCHES & BRIDGES", "settings", [
        ("SOFT O", "Pressed flat or upright"),
        ("HEAVY X", "Only activated upright!"),
        ("SPLIT <>", "Splits into two 1×1 cubes"),
    ])

    # Thẻ 4: Camera & góc nhìn
    _draw_help_card(f, c2_x, r2_y, grid_w, grid_h, "CAMERA & VIEW", "view", [
        ("SCROLL", "Zoom in / out smoothly"),
        ("R-DRAG", "Pan & inspect board"),
        ("V KEY", "Toggle Classic / Original view"),
    ])


def _draw_help_card(f, cx, cy, grid_w, grid_h, card_title, icon_name, items):
    screen, style, mouse, caption = f.screen, f.style, f.mouse, f.caption
    card_r = pygame.Rect(cx, cy, grid_w, grid_h)
    f.app.metric_rects.append(card_r)
    card_hover = card_r.collidepoint(mouse)
    draw_r = card_r
    if card_hover:
        ticks = pygame.time.get_ticks()
        sway_x = round(math.sin(ticks * 0.007 + cx) * 1.8)
        lift_y = -4 + round(math.cos(ticks * 0.008 + cy) * 1.2)
        draw_r = card_r.move(sway_x, lift_y)

    draw_glass_panel(screen, draw_r, style=style, border_radius=18, shadow=card_hover, fill_alpha=110 if card_hover else 95)
    if card_hover:
        glow = pygame.Surface((draw_r.width + 10, draw_r.height + 10), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*T.ACCENT[:3], 35), glow.get_rect(), border_radius=22)
        screen.blit(glow, (draw_r.x - 5, draw_r.y - 5))
        pygame.draw.rect(screen, (*T.ACCENT[:3], 150), draw_r, 1, border_radius=18)

    # Nhãn tiêu đề
    icon_rect = pygame.Rect(draw_r.x + 12, draw_r.y + 12, 28, 28)
    draw_glass_panel(screen, icon_rect, style=style, border_radius=8, shadow=False, fill_alpha=120)
    draw_vector_icon(screen, icon_name, icon_rect.center, T.ACCENT, size=13)
    f.label(card_title, draw_r.x + 48, draw_r.y + 16, color=T.TEXT, f=f.heading)
    pygame.draw.line(screen, (*T.LINE[:3], 60), (draw_r.x + 12, draw_r.y + 46), (draw_r.x + grid_w - 12, draw_r.y + 46), 1)

    item_y = draw_r.y + 52
    for key_tag, desc in items:
        chip_rect = pygame.Rect(draw_r.x + 10, item_y, grid_w - 20, 36)
        chip_hover = chip_rect.collidepoint(mouse)

        chip_bg = pygame.Surface((chip_rect.width, chip_rect.height), pygame.SRCALPHA)
        bg_col = (*T.ACCENT[:3], 35) if chip_hover else (255, 255, 255, 25 if style == 'dream' else 15)
        pygame.draw.rect(chip_bg, bg_col, chip_bg.get_rect(), border_radius=10)
        rim_col = T.ACCENT if chip_hover else (*T.LINE[:3], 50)
        pygame.draw.rect(chip_bg, rim_col, chip_bg.get_rect(), 1, border_radius=10)
        screen.blit(chip_bg, chip_rect.topleft)

        tag_w = caption.size(key_tag)[0] + 12
        tag_rect = pygame.Rect(chip_rect.x + 8, chip_rect.y + 6, max(36, tag_w), 24)
        tag_bg = (*T.ACCENT[:3], 180) if chip_hover else (*T.LINE[:3], 120)
        pygame.draw.rect(screen, tag_bg, tag_rect, border_radius=6)
        t_surf = caption.render(key_tag, True, T.INK if chip_hover else T.TEXT)
        screen.blit(t_surf, t_surf.get_rect(center=tag_rect.center))

        desc_col = T.TEXT if chip_hover else T.MUTED
        f.label(desc, tag_rect.right + 8, chip_rect.centery - 7, color=desc_col, f=caption, max_width=grid_w - tag_w - 36)
        item_y += 42

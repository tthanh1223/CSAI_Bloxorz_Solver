"""Game-first layout. All state-dependent presentation lives here."""
import math
import pygame
from src.gui import theme as T
from src.gui.ui import Button, text
from src.gui.contracts import ReplayStatus, SolverStatus
from src.engine.state import Orientation
from src.gui.dreamscape import background


def scene(app):
    style = getattr(app, 'visual_style', 'dream')
    size = app.screen.get_size()
    if style == 'forest_gl':
        result = pygame.Surface(size)
        result.fill(T.BG)
        return result
    key = (size, style, id(app.stage), app.stage_index)
    cached = getattr(app, '_scene_cache', None)
    if cached and cached[0] == key:
        return cached[1]
    cells = tuple((r, c) for r, row in enumerate(app.stage.grid) for c, tile in enumerate(row) if tile.value != '0') if style == 'blueprint' else ()
    result = background(size, style, cells, app.stage_index)
    app._scene_cache = (key, result)
    return result


def draw(app):
    """Cache the composed UI independently of the animated board."""
    mouse = pygame.mouse.get_pos()
    hovered = tuple(b.key for b in app.buttons if b.enabled and b.rect.collidepoint(mouse))
    hovered_metrics = tuple(i for i, r in enumerate(getattr(app, 'metric_rects', [])) if r.collidepoint(mouse))
    is_split = getattr(getattr(app.session, 'current_state', None), 'orientation', None) == Orientation.SPLIT
    animating_ui = (bool(hovered) or bool(hovered_metrics) or app.busy
                    or bool(app.win_phase) or getattr(app, 'active_slider', None) is not None
                    or getattr(app, 'trauma', 0.0) > 0.01 or getattr(app, 'shockwave', None) is not None
                    or is_split)
    time_tick = (pygame.time.get_ticks() // 16) if animating_ui else 0
    slider_state = (getattr(app, 'bgm_volume', 0.10), getattr(app, 'sfx_volume', 0.85), getattr(app, 'active_slider', None))
    ui_key = (getattr(app, 'visual_style', 'dream'), app.screen.get_size(), app.large_text, app.high_contrast,
              app.stage_index, app.session.moves, app.session.status, app.busy, app.animation.busy,
              app.replay.status, app.replay.index, app.replay.length, app.speed, app.message,
              app.algorithm, app.solve_current, id(app.result), app.details_open, app.solver_status,
              app.stage_picker, app.picker_page, app.menu, app.dropdown_open, app.sound_enabled, app.animate,
              bool(app.actions), hovered, hovered_metrics, pygame.mouse.get_pressed(), slider_state,
              time_tick)
    animating_idle_beacon = (app.animation.frame is None and not bool(app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice'))
    animating_board = (getattr(app, 'intro_t', None) is not None or getattr(app, 'outro_t', None) is not None
                       or getattr(app, 'trauma', 0.0) > 0.01 or getattr(app, 'shockwave', None) is not None
                       or is_split or animating_idle_beacon)
    board_key = (app.session.current_state, app.animation.frame, app.zoom, tuple(app.pan), animating_board)
    cached = getattr(app, '_presentation_cache', None)
    if cached and cached[0] == ui_key and not (app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice'):
        if not animating_board and cached[1] == board_key:
            return False
        app.screen.blit(cached[2], (0, 0))
        rect = app.board_rect
        if getattr(app, 'trauma', 0.0) > 0.01:
            intensity = app.trauma ** 1.5
            ticks = pygame.time.get_ticks()
            shake_x = round(math.sin(ticks * 0.048) * 2.5 * intensity)
            shake_y = round(math.cos(ticks * 0.062) * 1.8 * intensity)
            rect = app.board_rect.move(shake_x, shake_y)
        app.screen.blit(scene(app), rect, rect)
        board = app._board_surface
        app.renderer.zoom, app.renderer.pan = app.zoom, tuple(app.pan)
        app.renderer.high_contrast = app.high_contrast
        app.renderer.draw(board, app.session.current_state, app.animation.frame,
                          intro_t=getattr(app, 'intro_t', None), outro_t=getattr(app, 'outro_t', None),
                          shockwave=getattr(app, 'shockwave', None))
        app.screen.blit(board, rect)
        if not animating_board:
            app._presentation_cache = (ui_key, board_key, cached[2])
        return True
    _draw(app)
    app._presentation_cache = (ui_key, board_key, app.screen.copy())
    return True


def draw_confetti(screen, ticks, w, h):
    """Silky smooth 60 FPS physics celebratory confetti particle explosion."""
    confetti_colors = (
        (255, 185, 205),  # Pastel Rose Pink
        (255, 215, 60),   # Radiant Gold
        (120, 220, 245),  # Ethereal Cyan
        (255, 145, 95),   # Coral Peach
        (165, 235, 170),  # Mint Green
        (225, 160, 240),  # Lavender Violet
        (255, 255, 255),  # Pure Sparkle
    )
    t = ticks * 0.001
    for i in range(85):
        seed = i * 2903 + 57
        speed = 1.6 + (seed % 28) * 0.10
        x_base = (seed * 43) % w
        phase = (seed % 100) / 14.0
        rot_spd = 2.8 + (seed % 15) * 0.28
        col = confetti_colors[i % len(confetti_colors)]

        # Falling trajectory
        y = int((t * speed * 130 + (seed % 900)) % (h + 80)) - 40
        x = int(x_base + math.sin(t * 2.4 + phase) * 38)

        # 3D tumbling rotation
        flip = math.cos(t * rot_spd + phase)
        pw = max(1, int(11 * abs(flip)))
        ph = 7

        conf_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        conf_surf.fill((*col, 220))
        if pw > 4:
            pygame.draw.line(conf_surf, (255, 255, 255, 180), (0, 0), (pw, 0), 1)
        screen.blit(conf_surf, (x - pw // 2, y - ph // 2))


def draw_frosted_glass_panel(screen: pygame.Surface, rect: pygame.Rect, style: str, border_radius: int = 22) -> None:
    """Render authentic optical-blur frosted glass panel with specular highlights and soft shadow."""
    rect = rect.clamp(screen.get_rect())
    w, h = rect.size
    if w <= 8 or h <= 8:
        return

    # 1. Optical Background Blur: sample current scene pixels before drawing shadow
    sub = screen.subsurface(rect).copy()
    bw = max(4, w // 4)
    bh = max(4, h // 4)
    small = pygame.transform.smoothscale(sub, (bw, bh))
    blurred_raw = pygame.transform.smoothscale(small, (w, h))

    # Rounded mask with smooth corners
    blurred = pygame.Surface((w, h), pygame.SRCALPHA)
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=border_radius)
    blurred.blit(blurred_raw, (0, 0))
    blurred.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # 2. Ambient Bottom Contact Shadow (strictly within rect.x boundary so it never bleeds into board_rect)
    bot_shadow = pygame.Surface((w, 8), pygame.SRCALPHA)
    for sy in range(8):
        a = int(34 * (1.0 - sy / 8.0) ** 1.5)
        pygame.draw.line(bot_shadow, (0, 0, 0, a), (border_radius, sy), (w - border_radius, sy))
    screen.blit(bot_shadow, (rect.x, rect.bottom))

    # 3. Translucent Frosted Glass Tint & Specular Rim Light
    tint = pygame.Surface((w, h), pygame.SRCALPHA)
    if style == 'dream':
        t_col = (255, 246, 250, 142)
        border_col = (255, 255, 255, 185)
        specular_col = (255, 255, 255, 220)
        inner_glow = (255, 235, 242, 55)
    elif style in ('forest', 'forest_gl'):
        t_col = (18, 30, 24, 155)
        border_col = (120, 170, 140, 155)
        specular_col = (210, 245, 225, 175)
        inner_glow = (140, 195, 160, 40)
    else:  # blueprint
        t_col = (12, 30, 50, 160)
        border_col = (60, 150, 205, 165)
        specular_col = (165, 230, 255, 195)
        inner_glow = (80, 180, 230, 35)

    pygame.draw.rect(tint, t_col, tint.get_rect(), border_radius=border_radius)
    pygame.draw.rect(tint, inner_glow, tint.get_rect().inflate(-2, -2), 1, border_radius=max(1, border_radius - 1))
    pygame.draw.rect(tint, border_col, tint.get_rect(), 1, border_radius=border_radius)
    if w > border_radius * 2:
        pygame.draw.line(tint, specular_col, (border_radius, 1), (w - border_radius, 1), 1)

    blurred.blit(tint, (0, 0))
    screen.blit(blurred, rect.topleft)


def _draw(app):
    screen = app.screen
    w, h = screen.get_size()
    body = T.font('body', app.large_text)
    heading = T.font('heading', app.large_text)
    display = T.font('display', app.large_text)
    mono = T.font('mono', app.large_text)
    mono_lg = T.font('mono_lg', app.large_text)
    caption = T.font('caption', app.large_text)

    def label(value, x, y, color=T.TEXT, f=body, max_width=None):
        text(screen, f, value, (x, y), color, max_width)

    def button(key, value, x, y, width, enabled=True, kind='secondary', selected=False, height=T.BUTTON_HEIGHT):
        b = Button(key, value, pygame.Rect(x, y, width, height), enabled, selected, kind)
        app.buttons.append(b)
        b.draw(screen, body)
        return b

    app.buttons = []
    app.seek_rect = pygame.Rect(0, 0, 0, 0)
    style = getattr(app, 'visual_style', 'dream')
    forest = style in ('forest', 'forest_gl')
    screen.blit(scene(app), (0, 0))

    # Top navigation veil
    veil = pygame.Surface((w, 80), pygame.SRCALPHA)
    for yy in range(80):
        pygame.draw.line(veil, (253, 222, 209, round(225 * (1 - yy / 80) ** .45)), (0, yy), (w, yy))
    if style == 'dream':
        screen.blit(veil, (0, 0))
    elif forest:
        veil.fill((14, 27, 20, 110))
        screen.blit(veil, (0, 0))
    else:
        pygame.draw.line(screen, T.LINE, (24, 78), (w - 24, 78))

    panel_x = w - T.PANEL_WIDTH - 24
    app.board_rect = pygame.Rect(0, 80, panel_x - 16, h - 176)
    board = getattr(app, '_board_surface', None)
    if board is None or board.get_size() != app.board_rect.size:
        board = pygame.Surface(app.board_rect.size, pygame.SRCALPHA)
        app._board_surface = board
    app.renderer.zoom, app.renderer.pan = app.zoom, tuple(app.pan)
    app.renderer.high_contrast = app.high_contrast
    app.renderer.draw(board, app.session.current_state, app.animation.frame,
                      intro_t=getattr(app, 'intro_t', None), outro_t=getattr(app, 'outro_t', None),
                      shockwave=getattr(app, 'shockwave', None))
    draw_rect = app.board_rect
    if getattr(app, 'trauma', 0.0) > 0.01:
        intensity = app.trauma ** 1.5
        ticks = pygame.time.get_ticks()
        shake_x = round(math.sin(ticks * 0.048) * 2.5 * intensity)
        shake_y = round(math.cos(ticks * 0.062) * 1.8 * intensity)
        draw_rect = app.board_rect.move(shake_x, shake_y)
    screen.blit(board, draw_rect)

    idle = not app.busy and not app.animation.busy and getattr(app, 'intro_t', None) is None and getattr(app, 'outro_t', None) is None
    replaying = app.replay.status != ReplayStatus.EMPTY
    manual = idle and not replaying

    # Dynamic card height hugs content to eliminate all redundant empty space
    if replaying:
        card_h = 360 if (app.stage_cleared and app.stage_index + 1 < len(app.stage_paths)) else 312
    elif app.busy:
        card_h = 254
    elif app.result and app.result.found:
        card_h = 436 if app.details_open else 328
    else:
        if app.dropdown_open or app.solver_status in (SolverStatus.ERROR, SolverStatus.TIMEOUT, SolverStatus.NO_SOLUTION, SolverStatus.CANCELLED):
            card_h = 368
        else:
            card_h = 326
    if getattr(app, 'large_text', False):
        card_h += 8
    card_h = min(card_h, h - 96)

    # Right panel frosted glass container
    card_rect = pygame.Rect(panel_x - 16, 80, T.PANEL_WIDTH + 32, card_h)
    draw_frosted_glass_panel(screen, card_rect, style, border_radius=22)

    # High-contrast frosted glass container badge for logo & move counter
    badge_rect = pygame.Rect(20, 10, 192, 58)
    badge = pygame.Surface(badge_rect.size, pygame.SRCALPHA)
    if style == 'blueprint':
        pygame.draw.rect(badge, (12, 32, 52, 230), badge.get_rect(), border_radius=16)
        pygame.draw.rect(badge, (56, 142, 185, 190), badge.get_rect(), 1, border_radius=16)
        title_col = (245, 250, 255)
        moves_col = (145, 210, 240)
    elif forest:
        pygame.draw.rect(badge, (16, 28, 20, 235), badge.get_rect(), border_radius=16)
        pygame.draw.rect(badge, (76, 115, 86, 185), badge.get_rect(), 1, border_radius=16)
        title_col = (250, 245, 235)
        moves_col = (200, 225, 180)
    else:  # dream city
        pygame.draw.rect(badge, (255, 246, 250, 235), badge.get_rect(), border_radius=16)
        pygame.draw.rect(badge, (228, 182, 198, 210), badge.get_rect(), 1, border_radius=16)
        pygame.draw.line(badge, (255, 255, 255, 180), (16, 1), (badge_rect.w - 16, 1), 1)
        title_col = (46, 32, 42)
        moves_col = (112, 82, 98)
    screen.blit(badge, badge_rect.topleft)

    label('B L O X O R Z', badge_rect.x + 18, badge_rect.y + 7, title_col, f=heading)
    label(f'{app.session.moves} MOVES', badge_rect.x + 20, badge_rect.y + 35, moves_col, f=caption)
    button('theme', {'dream': '01 / DREAM CITY', 'forest': '02 / FOREST RUINS',
                     'blueprint': '03 / PAPER BLUEPRINT', 'forest_gl': 'FOREST / OPENGL'}.get(style, style),
           316, 20, 268, style != 'forest_gl', kind='quiet')
    button('choose', f'Stage {app.stage_index + 1:02}', panel_x - 32, 20, 128, bool(app.stage_paths), 'quiet')
    button('help', '?', w - 152, 20, 40, kind='quiet')
    button('settings', 'Settings', w - 108, 20, 88, kind='quiet')

    # Centered Floating Controls (Bottom Bar) - Clean pills with NO rectangular background container
    btn_y = h - 56
    if not replaying:
        btn_w = 108
        btn_gap = 14
        total_w = btn_w * 3 + btn_gap * 2
        start_x = app.board_rect.centerx - total_w // 2

        button('undo', 'Undo', start_x, btn_y, btn_w, manual and bool(app.actions), kind='pill')
        button('restart', 'Restart', start_x + btn_w + btn_gap, btn_y, btn_w, True, kind='pill')
        button('hint', 'Hint', start_x + (btn_w + btn_gap) * 2, btn_y, btn_w, manual, kind='pill')
    else:
        dock_h = 48
        dock_w = min(580, max(490, panel_x - 24))
        dock_x = app.board_rect.centerx - dock_w // 2
        dock_y = h - 60
        dock_surf = pygame.Surface((dock_w, dock_h), pygame.SRCALPHA)
        pygame.draw.rect(dock_surf, (*T.PANEL, 235 if forest else 244), dock_surf.get_rect(), border_radius=24)
        pygame.draw.rect(dock_surf, (*T.LINE, 180), dock_surf.get_rect(), 1, border_radius=24)
        screen.blit(dock_surf, (dock_x, dock_y))

        btn_dock_y = dock_y + 6
        button('back', 'Back', dock_x + 16, btn_dock_y, 70, app.replay.index > 0, kind='dock_item', height=36)
        button('play', 'Pause' if app.replay.status == ReplayStatus.PLAYING else 'Play',
               dock_x + 92, btn_dock_y, 86, not app.busy, 'primary', height=36)
        button('step', 'Next', dock_x + 184, btn_dock_y, 70, idle and app.replay.index < app.replay.length, kind='dock_item', height=36)
        button('speed', f'{app.speed:g}×', dock_x + 260, btn_dock_y, 50, kind='dock_item', height=36)

        timeline_x = dock_x + 318
        seek_w = max(44, dock_w - 388)
        app.seek_rect = pygame.Rect(timeline_x, dock_y + 21, seek_w, 6)
        pygame.draw.rect(screen, T.LINE, app.seek_rect, border_radius=3)
        ratio = app.replay.index / max(1, app.replay.length)
        fill = app.seek_rect.copy()
        fill.width = int(fill.width * ratio)
        pygame.draw.rect(screen, T.ACCENT, fill, border_radius=3)
        pygame.draw.circle(screen, T.ACCENT, (app.seek_rect.x + fill.width, app.seek_rect.centery), 5)
        label(f'{app.replay.index}/{app.replay.length}', timeline_x + seek_w + 10, dock_y + 15, T.MUTED, f=caption)

    # Toast status message (Clean floating chip above controls - Never overlaps buttons)
    message = app.message
    hidden = ('Rolling...', 'Move accepted.', 'Stage loaded. Arrow keys / WASD to roll.',
              'Roll with arrows or WASD. Reach G standing upright.')
    if message in hidden:
        message = 'Use arrow keys or WASD to roll the block.' if not app.actions and not replaying else ''
    if app.busy:
        message = ''
    if message:
        tw = caption.size(message)[0]
        pill_w = tw + 28
        pill_x = max(24, min(panel_x - pill_w - 16, app.board_rect.centerx - pill_w // 2))
        pill_y = h - 92
        pill_surf = pygame.Surface((pill_w, 26), pygame.SRCALPHA)
        pygame.draw.rect(pill_surf, (*T.PANEL, 230 if forest else 242), pill_surf.get_rect(), border_radius=13)
        pygame.draw.rect(pill_surf, (*T.LINE, 180), pill_surf.get_rect(), 1, border_radius=13)
        screen.blit(pill_surf, (pill_x, pill_y))
        label(message, pill_x + 14, pill_y + 4, T.TEXT, f=caption)

    # Right Bento Dashboard Panel
    x, pw, y = panel_x, T.PANEL_WIDTH, 120
    if replaying:
        label('Your moves' if app.stage_cleared else 'Watch solution', x, y, f=heading)
        label('One move at a time.', x, y + 36, T.MUTED, f=caption)
        label(f'{app.replay.index} / {app.replay.length}', x, y + 78, f=mono_lg)
        label('moves played', x, y + 116, T.MUTED, f=caption)
        button('stop', 'Exit replay', x, y + 162, pw)
        button('rewind', 'Back to start', x, y + 210, pw, kind='quiet')
        if app.stage_cleared and app.stage_index + 1 < len(app.stage_paths):
            button('next_stage', 'Next stage   >', x, y + 258, pw, not app.busy, 'primary')
    elif app.busy:
        label('Finding a path', x, y, f=heading)
        label({'ASTAR': 'A*'}.get(app.algorithm, app.algorithm), x, y + 36, T.MUTED)
        ticks = pygame.time.get_ticks()
        center = (x + 14, y + 104)

        # High-tech Sonar Expanding Ripples
        for i in range(2):
            phase = ((ticks * 0.0016 + i * 0.5) % 1.0)
            r = int(5 + phase * 16)
            alpha = int(180 * (1.0 - phase))
            ripple = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(ripple, (*T.ACCENT[:3], alpha), (r + 1, r + 1), r, 1)
            screen.blit(ripple, (center[0] - r - 1, center[1] - r - 1))

        # Rotating Radar Beam & Core Dot
        angle = ticks / 280.0
        sweep_len = 11
        end_pt = (round(center[0] + math.cos(angle) * sweep_len), round(center[1] + math.sin(angle) * sweep_len))
        pygame.draw.circle(screen, T.LINE, center, 12, 1)
        pygame.draw.aaline(screen, T.ACCENT_HOVER, center, end_pt)
        pygame.draw.circle(screen, T.ACCENT, center, 3)

        # 7-bar Harmonic Equalizer Spectrum simulating heuristic exploration
        for bar_idx in range(7):
            bx = x + 34 + bar_idx * 5
            bh = 3 + int(abs(math.sin(ticks * 0.0075 + bar_idx * 0.82)) * 12)
            by = y + 104 - bh // 2
            pygame.draw.rect(screen, T.ACCENT, (bx, by, 3, bh), border_radius=1)

        # Trailing animated dots
        dots = '.' * (1 + (ticks // 320) % 3)
        label(f'Searching state space{dots}', x + 76, y + 94, T.MUTED, max_width=pw - 76)
        button('cancel', 'Cancel search', x, y + 152, pw)
    elif app.result and app.result.found:
        m = app.result.metrics
        label('A way forward', x, y, f=heading)
        label(f'{m.solution_length} moves', x, y + 38, f=display)
        alg_label = {'ASTAR': 'A*'}.get(app.result.algorithm, app.result.algorithm)
        label(f'{m.time_sec:.3f} s  ·  {alg_label}', x, y + 80, T.MUTED, f=caption)
        button('solution', 'Watch solution', x, y + 116, pw, idle, 'primary')
        button('details', ('−' if app.details_open else '+') + '  Result details', x, y + 166, pw, selected=app.details_open)
        offset = y + 214
        if app.details_open:
            # 2x2 Bento Metrics Grid with interactive hover elevation and luminous glow
            bw = (pw - 8) // 2
            bh = 46
            mouse = pygame.mouse.get_pos()
            cards = [
                (pygame.Rect(x, offset, bw, bh), 'TIME', f'{m.time_sec:.3f} s'),
                (pygame.Rect(x + bw + 8, offset, bw, bh), 'RAM', f'{m.peak_memory_mb:.2f} MB'),
                (pygame.Rect(x, offset + bh + 8, bw, bh), 'EXPANDED', f'{m.expanded_nodes}'),
                (pygame.Rect(x + bw + 8, offset + bh + 8, bw, bh), 'COST', f'{m.total_cost:g}'),
            ]
            app.metric_rects = [base_rect for base_rect, _, _ in cards]
            for base_rect, tag, val in cards:
                card_hover = base_rect.collidepoint(mouse)
                draw_b = base_rect.move(0, -2) if card_hover else base_rect
                card_surf = pygame.Surface(draw_b.size, pygame.SRCALPHA)
                if card_hover:
                    shadow = pygame.Surface((draw_b.w + 6, draw_b.h + 6), pygame.SRCALPHA)
                    pygame.draw.rect(shadow, (0, 0, 0, 40), shadow.get_rect(), border_radius=10)
                    screen.blit(shadow, (draw_b.x - 3, draw_b.y + 1))

                    bg_col = (*T.HOVER[:3], 240) if len(T.HOVER) == 3 else T.HOVER
                    pygame.draw.rect(card_surf, bg_col, card_surf.get_rect(), border_radius=8)
                    pygame.draw.rect(card_surf, (*T.ACCENT[:3], 210), card_surf.get_rect(), 1, border_radius=8)
                    pygame.draw.line(card_surf, (255, 255, 255, 90), (8, 1), (draw_b.w - 8, 1), 1)
                else:
                    pygame.draw.rect(card_surf, T.SURFACE, card_surf.get_rect(), border_radius=8)
                    pygame.draw.rect(card_surf, T.LINE, card_surf.get_rect(), 1, border_radius=8)
                screen.blit(card_surf, draw_b)
                label(tag, draw_b.x + 8, draw_b.y + 6, T.ACCENT if card_hover else T.MUTED, f=caption)
                label(val, draw_b.x + 8, draw_b.y + 22, tuple(min(255, c + 35) for c in T.TEXT) if card_hover else T.TEXT, f=mono)

            offset += (bh * 2 + 16)
        else:
            app.metric_rects = []
        button('new_search', 'Try another algorithm', x, offset + 12, pw, idle, 'quiet')
    else:
        label('S O L V E R', x + 8, y - 8, f=heading)
        label('ALGORITHM', x, y + 42, T.MUTED, f=caption)
        button('algorithm_menu', {'ASTAR': 'A*'}.get(app.algorithm, app.algorithm) + '   ', x, y + 68, pw, manual)
        label('START FROM', x, y + 128, T.MUTED, f=caption)
        button('source_start', 'Start', x, y + 154, 126, manual, selected=not app.solve_current)
        button('source_current', 'Current', x + 134, y + 154, 126, manual, selected=app.solve_current)
        button('solve', 'Solve   >', x, y + 224, pw, manual, 'primary')
        if app.solver_status in (SolverStatus.ERROR, SolverStatus.TIMEOUT, SolverStatus.NO_SOLUTION, SolverStatus.CANCELLED):
            status = {SolverStatus.ERROR: 'Search failed. Please retry.', SolverStatus.TIMEOUT: 'Search time limit reached.',
                      SolverStatus.NO_SOLUTION: 'No solution found.', SolverStatus.CANCELLED: 'Search cancelled.'}
            label(status[app.solver_status], x, y + 276, T.MUTED, max_width=pw)
        if app.dropdown_open:
            app.dropdown_rect = pygame.Rect(x, y + 114, pw, 4 * 44 + 16)
            dd_rect = app.dropdown_rect.clamp(screen.get_rect())
            draw_frosted_glass_panel(screen, dd_rect, style, border_radius=12)
            app.buttons = [b for b in app.buttons if not b.rect.colliderect(app.dropdown_rect)]
            for i, (key, title) in enumerate((('BFS', 'BFS'), ('IDS', 'IDS'), ('UCS', 'UCS'), ('ASTAR', 'A*'))):
                button('algorithm:' + key, title, x + 8, y + 122 + i * 44, pw - 16,
                       kind='quiet', selected=app.algorithm == key)

    # Celebratory win confetti shower
    if app.win_phase in ('sink', 'disassemble', 'choice'):
        draw_confetti(screen, pygame.time.get_ticks(), w, h)

    # Win choice modal
    if app.win_phase == 'choice' and not (app.stage_picker or app.menu):
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((5, 12, 17, 140))
        screen.blit(shade, (0, 0))
        app.buttons = []
        app.seek_rect = pygame.Rect(0, 0, 0, 0)
        app.modal_rect = pygame.Rect((w - 480) // 2, (h - 272) // 2, 480, 272)
        r = app.modal_rect
        last = app.stage_index + 1 >= len(app.stage_paths)
        pygame.draw.rect(screen, T.PANEL, r, border_radius=16)
        label('Stage complete!', r.x + 32, r.y + 24, f=heading)
        label(f'Stage {app.stage_index + 1:02} cleared in {app.session.moves} moves.', r.x + 32, r.y + 72, T.MUTED)
        button('win_replay', 'Replay my moves', r.x + 32, r.y + 136, 200)
        if last:
            button('restart', 'Play again', r.x + 248, r.y + 136, 200, kind='primary')
        else:
            button('next_stage', 'Next stage   >', r.x + 248, r.y + 136, 200, kind='primary')

        keys = 'P: replay  ·  R: play again' if last else 'P: replay  ·  Enter: next stage  ·  R: restart'
        label(keys, r.x + 32, r.bottom - 56, T.MUTED, max_width=416)

    # Menus
    if app.stage_picker or app.menu:
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((5, 12, 17, 176))
        screen.blit(shade, (0, 0))
        app.buttons = []
        app.seek_rect = pygame.Rect(0, 0, 0, 0)
        mw = 608 if app.stage_picker else 480
        mh = 464 if app.stage_picker else 580 if app.menu == 'settings' else 432
        app.modal_rect = pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)
        r = app.modal_rect
        pygame.draw.rect(screen, T.PANEL, r, border_radius=16)
        title = 'Choose a stage' if app.stage_picker else 'Settings' if app.menu == 'settings' else 'How to play'
        label(title, r.x + 32, r.y + 24, f=heading)
        button('close_menu', 'Close', r.right - 104, r.y + 16, 80, kind='quiet')
        if app.stage_picker:
            for i, path in enumerate(app.stage_paths[app.picker_page * 20:app.picker_page * 20 + 20]):
                index = app.picker_page * 20 + i
                button(f'stage:{index}', f'{index + 1:02}', r.x + 32 + (i % 4) * 136,
                       r.y + 88 + (i // 4) * 56, 128, selected=index == app.stage_index)
            button('page_prev', 'Previous', r.x + 32, r.bottom - 64, 152, app.picker_page > 0, 'quiet')
            button('page_next', 'Next', r.right - 184, r.bottom - 64, 152,
                   (app.picker_page + 1) * 20 < len(app.stage_paths), 'quiet')
        elif app.menu == 'settings':
            xx, yy = r.x + 32, r.y + 76
            button('save', 'Save session · F5', xx, yy, 196, idle)
            button('load', 'Load session · F9', xx + 212, yy, 196)

            # Master Sound Toggle
            label('Master Sound', xx, yy + 58)
            button('sound', 'On' if app.sound_enabled else 'Off', r.right - 120, yy + 50, 88, selected=app.sound_enabled)

            # BGM Volume Slider
            mouse = pygame.mouse.get_pos()
            slider_w = 175
            track_x = xx + 130
            bgm_y = yy + 102
            app.bgm_slider_rect = pygame.Rect(track_x, bgm_y - 8, slider_w, 20)
            label('Music (BGM)', xx, bgm_y - 8)
            pygame.draw.line(screen, T.LINE, (track_x, bgm_y), (track_x + slider_w, bgm_y), 4)
            bgm_fill_w = int(slider_w * app.bgm_volume)
            if bgm_fill_w > 0:
                pygame.draw.line(screen, T.ACCENT, (track_x, bgm_y), (track_x + bgm_fill_w, bgm_y), 4)
            knob_x = track_x + bgm_fill_w
            bgm_hover = app.bgm_slider_rect.inflate(0, 12).collidepoint(mouse) or app.active_slider == 'bgm'
            if bgm_hover:
                pygame.draw.circle(screen, (*T.ACCENT[:3], 80), (knob_x, bgm_y), 11)
            pygame.draw.circle(screen, T.ACCENT, (knob_x, bgm_y), 7 if not bgm_hover else 8)
            pygame.draw.circle(screen, (255, 255, 255), (knob_x, bgm_y), 3)
            label(f'{int(app.bgm_volume * 100)}%', track_x + slider_w + 14, bgm_y - 8, T.MUTED, f=mono)

            # SFX Volume Slider
            sfx_y = yy + 138
            app.sfx_slider_rect = pygame.Rect(track_x, sfx_y - 8, slider_w, 20)
            label('Sound FX', xx, sfx_y - 8)
            pygame.draw.line(screen, T.LINE, (track_x, sfx_y), (track_x + slider_w, sfx_y), 4)
            sfx_fill_w = int(slider_w * app.sfx_volume)
            if sfx_fill_w > 0:
                pygame.draw.line(screen, T.ACCENT, (track_x, sfx_y), (track_x + sfx_fill_w, sfx_y), 4)
            knob_sfx_x = track_x + sfx_fill_w
            sfx_hover = app.sfx_slider_rect.inflate(0, 12).collidepoint(mouse) or app.active_slider == 'sfx'
            if sfx_hover:
                pygame.draw.circle(screen, (*T.ACCENT[:3], 80), (knob_sfx_x, sfx_y), 11)
            pygame.draw.circle(screen, T.ACCENT, (knob_sfx_x, sfx_y), 7 if not sfx_hover else 8)
            pygame.draw.circle(screen, (255, 255, 255), (knob_sfx_x, sfx_y), 3)
            label(f'{int(app.sfx_volume * 100)}%', track_x + slider_w + 14, sfx_y - 8, T.MUTED, f=mono)

            # Separator line
            pygame.draw.line(screen, T.LINE, (xx, yy + 172), (r.right - 32, yy + 172), 1)

            for i, (key, title, enabled) in enumerate((
                    ('animate', 'Animation', app.animate),
                    ('contrast', 'Contrast', app.high_contrast),
                    ('text', 'Large text', app.large_text))):
                label(title, xx, yy + 192 + i * 44)
                button(key, 'On' if enabled else 'Off', r.right - 120, yy + 184 + i * 44, 88, selected=enabled)

            view_label = 'View: Original' if app.renderer.view == 'original' else 'View: Classic'
            button('view', view_label + ' · V', xx, r.bottom - 110, 196, kind='quiet')
            button('camera', 'Reset camera', xx + 212, r.bottom - 110, 196, kind='quiet')
            button('recording', 'Replay my moves', xx, r.bottom - 58, 408, idle and bool(app.actions), 'quiet')
        else:
            lines = ['Stand the block upright in the dark goal.', 'Arrows / WASD: roll · Space: switch cube',
                     'Z: undo · R: restart · Esc: close menu', 'Scroll: zoom · Right-drag: pan the camera',
                     'V: switch camera view · Falling off restarts',
                     'Circle: soft switch · X: heavy switch', 'Brackets: split switch · Crack: fragile tile',
                     'Outlined bridge: off · Light cube: active']
            for i, line in enumerate(lines):
                label(line, r.x + 32, r.y + 88 + i * 40, T.TEXT if i == 0 else T.MUTED, max_width=mw - 64)

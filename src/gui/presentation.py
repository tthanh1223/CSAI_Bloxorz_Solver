"""Game-first layout. All state-dependent presentation lives here."""
import math
import pygame
from src.gui import theme as T
from src.gui.ui import Button, text, draw_glass_panel, draw_bento_card, draw_vector_icon, lerp_color
from src.gui.contracts import ReplayStatus, SolverStatus
from src.engine.state import Orientation
from src.gui.dreamscape import background
from src.gui.themes import NAMES


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
    cells = tuple((r, c) for r, row in enumerate(app.stage.grid) for c, tile in enumerate(row) if tile.value != '0') if style in ('blueprint', 'forest') else ()
    result = background(size, style, cells, app.stage_index)
    app._scene_cache = (key, result)
    return result


def sharp_board(app):
    """On a HiDPI (Retina) window the board is left out of the 1x UI frame and
    drawn at full resolution by BloxorzApp.present(), so tiles and block stay
    sharp. Modals keep the 1x board, since they shade it."""
    return (getattr(app, 'hidpi', 1) > 1 and getattr(app, 'visual_style', 'dream') != 'forest_gl'
            and not (app.menu or app.stage_picker or app.win_phase == 'choice' or getattr(app, 'in_main_menu', False)))


def draw(app):
    """Cache the composed UI independently of the animated board."""
    mouse = pygame.mouse.get_pos()
    hovered = tuple(b.key for b in app.buttons if b.enabled and b.rect.collidepoint(mouse))
    hovered_metrics = tuple(i for i, r in enumerate(getattr(app, 'metric_rects', [])) if r.collidepoint(mouse))
    is_split = getattr(getattr(app.session, 'current_state', None), 'orientation', None) == Orientation.SPLIT
    drawer_animating = abs(getattr(app, 'drawer_t', 0.0) - (1.0 if getattr(app, 'solver_open', False) else 0.0)) > 0.005
    menu_animating = abs(getattr(app, 'menu_t', 0.0) - (1.0 if getattr(app, 'in_main_menu', False) else 0.0)) > 0.005
    animating_ui = (bool(hovered) or bool(hovered_metrics) or app.busy
                    or bool(app.win_phase) or getattr(app, 'active_slider', None) is not None
                    or getattr(app, 'trauma', 0.0) > 0.01 or getattr(app, 'shockwave', None) is not None
                    or is_split or drawer_animating or menu_animating)
    time_tick = (pygame.time.get_ticks() // 16) if animating_ui else 0
    slider_state = (getattr(app, 'bgm_volume', 0.10), getattr(app, 'sfx_volume', 0.85), getattr(app, 'active_slider', None))
    ui_key = (getattr(app, 'visual_style', 'dream'), app.screen.get_size(), app.large_text, app.high_contrast,
              app.stage_index, app.session.moves, app.session.status, app.busy, app.animation.busy,
              app.replay.status, app.replay.index, app.replay.length, app.speed, app.message,
              app.algorithm, app.solve_current, id(app.result), app.details_open, app.solver_status,
              app.stage_picker, app.picker_page, app.menu, app.dropdown_open, app.sound_enabled, app.animate,
              bool(app.actions), hovered, hovered_metrics, pygame.mouse.get_pressed(), slider_state,
              getattr(app, 'in_main_menu', False), getattr(app, 'solver_open', False),
              round(getattr(app, 'drawer_t', 0.0), 2), round(getattr(app, 'camera_pan_x', 0.0), 1),
              time_tick)
    animating_idle_beacon = (app.animation.frame is None and not bool(app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice' or getattr(app, 'in_main_menu', False)))
    animating_board = (getattr(app, 'intro_t', None) is not None or getattr(app, 'outro_t', None) is not None
                       or (hasattr(app, 'bridge_view') and app.bridge_view() is not None)
                       or getattr(app, 'trauma', 0.0) > 0.01 or getattr(app, 'shockwave', None) is not None
                       or is_split or animating_idle_beacon or drawer_animating)
    eff_pan = (app.pan[0] + getattr(app, 'camera_pan_x', 0.0), app.pan[1])
    board_key = (app.session.current_state, app.animation.frame, app.zoom, tuple(eff_pan), animating_board)
    cached = getattr(app, '_presentation_cache', None)
    if cached and cached[0] == ui_key and not (app.menu or app.stage_picker or app.dropdown_open or app.win_phase == 'choice'):
        if not animating_board and cached[1] == board_key:
            return False
        if sharp_board(app):
            app._presentation_cache = (ui_key, board_key, cached[2])
            return True
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
        app.renderer.zoom, app.renderer.pan = app.zoom, eff_pan
        app.renderer.high_contrast = app.high_contrast
        app.renderer.pixel_scale = 1
        app.renderer.draw(board, app.session.current_state, app.animation.frame,
                          intro_t=getattr(app, 'intro_t', None), outro_t=app.board_outro() if hasattr(app, 'board_outro') else None,
                          shockwave=getattr(app, 'shockwave', None), bridges=app.bridge_view() if hasattr(app, 'bridge_view') else None)
        app.screen.blit(board, rect)
        if not animating_board:
            app._presentation_cache = (ui_key, board_key, cached[2])
        return True
    _draw(app)
    app._presentation_cache = (ui_key, board_key, app.screen.copy())
    return True


_CONFETTI_CACHE = {}
_FROSTED_GLASS_CACHE = {}


def draw_confetti(screen, ticks, w, h):
    """Silky smooth 60 FPS physics celebratory confetti particle explosion with pre-cached sprites."""
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

        c_key = (col, pw, ph)
        conf_surf = _CONFETTI_CACHE.get(c_key)
        if conf_surf is None:
            conf_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
            conf_surf.fill((*col, 220))
            if pw > 4:
                pygame.draw.line(conf_surf, (255, 255, 255, 180), (0, 0), (pw, 0), 1)
            _CONFETTI_CACHE[c_key] = conf_surf
        screen.blit(conf_surf, (x - pw // 2, y - ph // 2))


def draw_frosted_glass_panel(screen: pygame.Surface, rect: pygame.Rect, style: str, border_radius: int = 22, app=None) -> None:
    """Render authentic optical-blur frosted glass panel with specular highlights and soft shadow."""
    rect = rect.clamp(screen.get_rect())
    w, h = rect.size
    if w <= 8 or h <= 8:
        return

    stage_id = getattr(app, 'stage_index', 0) if app else 0
    cache_key = (w, h, rect.topleft, style, border_radius, stage_id)
    cached = _FROSTED_GLASS_CACHE.get(cache_key)
    if cached is not None:
        blurred, bot_shadow = cached
        screen.blit(bot_shadow, (rect.x, rect.bottom))
        screen.blit(blurred, rect.topleft)
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
    if len(_FROSTED_GLASS_CACHE) > 16:
        _FROSTED_GLASS_CACHE.clear()
    _FROSTED_GLASS_CACHE[cache_key] = (blurred, bot_shadow)
    screen.blit(bot_shadow, (rect.x, rect.bottom))
    screen.blit(blurred, rect.topleft)


draw_frosted_glass_panel = draw_glass_panel


def draw_bloxorz_logo(screen, cx, cy, ticks, style, display, heading, caption):
    """Render high-end dimensional isometric jewel logo with glowing halo ellipse, glistening 3D crystal emblem, and aura."""
    pulse = 0.5 + 0.5 * math.sin(ticks * 0.0032)

    # 1. Enclosing Radiant Elliptical Halo (Logo and emblem sit completely inside)
    halo_w, halo_h = 370, 140
    halo_surf = pygame.Surface((halo_w, halo_h), pygame.SRCALPHA)
    for layer in range(4):
        rw = halo_w - layer * 34
        rh = halo_h - layer * 16
        alpha = int((38 + 26 * pulse) / (layer + 1.15))
        glow_color = (*T.ACCENT[:3], alpha)
        pygame.draw.ellipse(halo_surf, glow_color, ((halo_w - rw) // 2, (halo_h - rh) // 2, rw, rh))
    # Crisp holographic perimeter ring
    ring_col = (*T.ACCENT[:3], int(65 + 35 * pulse))
    pygame.draw.ellipse(halo_surf, ring_col, (4, 4, halo_w - 8, halo_h - 8), 1)
    screen.blit(halo_surf, (cx - halo_w // 2, cy - 42))

    # 2. Silky Smooth 60FPS Isometric 3D Crystal Block Emblem
    # Gentle, non-laggy sinusoidal float
    emblem_y = cy - 14 + math.sin(ticks * 0.0028) * 3.2
    bx, by = cx, emblem_y

    # Brilliant Diamond Aura behind crystal cube
    aura_r = 28
    cube_aura = pygame.Surface((aura_r * 2 + 16, aura_r * 2 + 16), pygame.SRCALPHA)
    pygame.draw.circle(cube_aura, (*T.ACCENT[:3], int(65 + 40 * pulse)), (aura_r + 8, aura_r + 8), aura_r + 4)
    screen.blit(cube_aura, (bx - aura_r - 8, by - aura_r - 4))

    # Rhomboid top face
    top_pts = [(bx, by - 14), (bx + 18, by - 5), (bx, by + 4), (bx - 18, by - 5)]
    # Left vertical face
    left_pts = [(bx - 18, by - 5), (bx, by + 4), (bx, by + 26), (bx - 18, by + 17)]
    # Right vertical face
    right_pts = [(bx, by + 4), (bx + 18, by - 5), (bx + 18, by + 17), (bx, by + 26)]

    top_col = lerp_color(T.ACCENT, (255, 255, 255), 0.58)
    left_col = lerp_color(T.ACCENT, (22, 32, 48) if style != 'dream' else (185, 122, 155), 0.35)
    right_col = lerp_color(T.ACCENT, (8, 12, 22) if style != 'dream' else (135, 72, 105), 0.65)

    pygame.draw.polygon(screen, left_col, left_pts)
    pygame.draw.polygon(screen, right_col, right_pts)
    pygame.draw.polygon(screen, top_col, top_pts)

    # Crystal facet edge glints & specular lines
    pygame.draw.lines(screen, (255, 255, 255, 225), True, top_pts, 1)
    pygame.draw.line(screen, (255, 255, 255, 185), (bx, by + 4), (bx, by + 26), 1)

    # Shimmering Holographic Diamond Waist Ring (Orbiting waist ring like in-game companion diamond)
    ring_y = by + 10
    ring_rect = pygame.Rect(bx - 26, ring_y - 8, 52, 16)
    ring_pts = [
        (bx - 26, ring_y),
        (bx - 14, ring_y - 6),
        (bx + 14, ring_y - 6),
        (bx + 26, ring_y),
        (bx + 14, ring_y + 6),
        (bx - 14, ring_y + 6),
    ]
    pygame.draw.lines(screen, (*T.ACCENT[:3], int(150 + 80 * pulse)), True, ring_pts, 1)

    # Twinkling 4-point star glints on the crystal vertices
    spark_phase = (ticks * 0.005) % (math.pi * 2)
    for i, (sx, sy) in enumerate(((bx - 18, by - 5), (bx + 18, by - 5), (bx, by + 4))):
        s_size = 2.5 + 1.5 * math.sin(spark_phase + i * 2.1)
        if s_size > 2.0:
            pygame.draw.line(screen, (255, 255, 255), (sx - s_size, sy), (sx + s_size, sy), 1)
            pygame.draw.line(screen, (255, 255, 255), (sx, sy - s_size), (sx, sy + s_size), 1)

    # Floating beacon diamond on top of the block
    beacon_y = by - 24 + math.sin(ticks * 0.005) * 2.2
    beacon_pts = [(bx, beacon_y - 6), (bx + 5, beacon_y), (bx, beacon_y + 6), (bx - 5, beacon_y)]
    pygame.draw.polygon(screen, (255, 255, 255), beacon_pts)
    beacon_glow = pygame.Surface((20, 20), pygame.SRCALPHA)
    pygame.draw.circle(beacon_glow, (*T.ACCENT[:3], int(120 + 70 * pulse)), (10, 10), 8)
    screen.blit(beacon_glow, (bx - 10, beacon_y - 10))

    # 3. Dimensional Typography: "BLOXORZ" + Frosted Glass [ 3D ] Capsule Badge
    t_surf = display.render("BLOXORZ", True, T.TEXT)
    shadow_col = (0, 0, 0, 75) if style != 'dream' else (160, 120, 140, 65)
    t_shadow = display.render("BLOXORZ", True, shadow_col)

    badge_w, badge_h = 48, 26
    total_w = t_surf.get_width() + 12 + badge_w
    t_x = cx - total_w // 2
    t_y = cy + 34

    # Shadow layer
    screen.blit(t_shadow, (t_x, t_y + 2))
    # Crisp front layer
    screen.blit(t_surf, (t_x, t_y))

    # Frosted [ 3D ] pill badge
    badge_rect = pygame.Rect(t_x + t_surf.get_width() + 12, t_y + (t_surf.get_height() - badge_h) // 2, badge_w, badge_h)
    draw_glass_panel(screen, badge_rect, style=style, border_radius=13, shadow=False, fill_alpha=120)
    badge_3d = heading.render("3D", True, T.ACCENT)
    screen.blit(badge_3d, badge_3d.get_rect(center=badge_rect.center))

    # 4. Refined Subtitle
    sub_surf = caption.render("—   SPATIAL LOGIC & SEARCH SIMULATION   —", True, T.MUTED)
    screen.blit(sub_surf, sub_surf.get_rect(center=(cx, cy + 74)))


def draw_main_menu(app):
    """Frosted Glassmorphism landing experience matching high-aesthetic reference design."""
    screen = app.screen
    w, h = screen.get_size()
    style = getattr(app, 'visual_style', 'dream')
    screen.blit(scene(app), (0, 0))

    # Soft ambient vignette
    vignette = pygame.Surface((w, h), pygame.SRCALPHA)
    vignette.fill((8, 16, 26, 75) if style != 'dream' else (255, 238, 244, 45))
    screen.blit(vignette, (0, 0))

    body = T.font('body', app.large_text)
    heading = T.font('heading', app.large_text)
    display = T.font('display', app.large_text)
    caption = T.font('caption', app.large_text)

    # Central Frosted Glass Card
    mw = min(480, w - 40)
    mh = min(540, h - 40)
    card_rect = pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)
    draw_glass_panel(screen, card_rect, style=style, border_radius=28, shadow=True, fill_alpha=190 if style == 'dream' else 215)

    # When modal is active (Settings/Help/Stage), suppress background elements completely to avoid any text ghosting
    modal_active = bool(app.stage_picker or app.menu)
    if not modal_active:
        ticks = pygame.time.get_ticks()
        draw_bloxorz_logo(screen, card_rect.centerx, card_rect.y + 44, ticks, style, display, heading, caption)

        btn_w = mw - 72
        btn_x = card_rect.x + 36
        start_y = card_rect.y + 160
        btn_gap = 14

        def menu_btn(key, label, y, kind='pill', height=46, icon=None, btn_font=body):
            b = Button(key, label, pygame.Rect(btn_x, y, btn_w, height), True, False, kind, icon=icon)
            app.buttons.append(b)
            b.draw(screen, btn_font)

        # Prominent New Game button: larger font, richer color effects, breathing aura
        play_label = f"Continue Stage {app.stage_index + 1:02}" if (app.actions or app.stage_index > 0) else "New Game"
        menu_btn('continue_game', play_label, start_y, kind='primary', height=52, icon='play', btn_font=heading)
        menu_btn('choose', "Select Stage", start_y + 52 + btn_gap, kind='pill', height=46, icon='view')
        menu_btn('settings', "Audio & Settings", start_y + 52 + btn_gap + (46 + btn_gap), kind='pill', height=46, icon='settings')
        menu_btn('help', "How to Play & Controls", start_y + 52 + btn_gap + (46 + btn_gap) * 2, kind='pill', height=46, icon='help')

        # Theme quick cycler at bottom of card
        theme_name = NAMES.get(style, style)
        b_th = Button('theme', f'Theme: {theme_name}', pygame.Rect(btn_x, card_rect.bottom - 46, btn_w, 34), True, False, 'pill', icon='theme')
        app.buttons.append(b_th)
        b_th.draw(screen, caption)

    # Keyboard shortcut guide at bottom of screen
    hint = caption.render("Space / Enter: Play  ·  Esc: Game  ·  T: Theme  ·  S: Settings  ·  H: Help", True, T.MUTED)
    screen.blit(hint, hint.get_rect(center=(w // 2, h - 20)))


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

    def button(key, value, x, y, width, enabled=True, kind='secondary', selected=False, height=T.BUTTON_HEIGHT, icon=None):
        b = Button(key, value, pygame.Rect(x, y, width, height), enabled, selected, kind, icon=icon)
        app.buttons.append(b)
        b.draw(screen, body)
        return b

    app.buttons = []
    app.seek_rect = pygame.Rect(0, 0, 0, 0)
    style = getattr(app, 'visual_style', 'dream')
    forest = style in ('forest', 'forest_gl')

    # Check Main Menu State
    if getattr(app, 'in_main_menu', False):
        draw_main_menu(app)
        _draw_modals(app, screen, w, h, style, heading, body, mono, caption, idle=True)
        return

    screen.blit(scene(app), (0, 0))

    # Top navigation veil (pre-cached)
    veil_cache = getattr(app, '_veil_cache', None)
    if veil_cache is None or veil_cache[0] != (w, style):
        veil = pygame.Surface((w, 80), pygame.SRCALPHA)
        if style == 'dream':
            for yy in range(80):
                pygame.draw.line(veil, (253, 222, 209, round(225 * (1 - yy / 80) ** .45)), (0, yy), (w, yy))
        elif forest:
            veil.fill((14, 27, 20, 110))
        app._veil_cache = ((w, style), veil)
    else:
        veil = veil_cache[1]

    if style == 'dream' or forest:
        screen.blit(veil, (0, 0))
    else:
        pygame.draw.line(screen, T.LINE, (24, 78), (w - 24, 78))

    replaying = app.replay.status != ReplayStatus.EMPTY
    idle = not app.busy and not app.animation.busy and getattr(app, 'intro_t', None) is None and getattr(app, 'outro_t', None) is None
    manual = idle and not replaying

    # Solver drawer visibility & animated transition
    is_drawer_visible = (getattr(app, 'solver_open', False) or replaying or app.busy or getattr(app, 'dropdown_open', False))
    panel_x = w - T.PANEL_WIDTH - 24 if is_drawer_visible else w
    center_w = panel_x if is_drawer_visible else w

    # Map viewport: starts strictly at y=80 below top veil and ends before bottom toast/dock
    app.board_rect = pygame.Rect(0, 80, panel_x - 16 if is_drawer_visible else w, h - 182)
    board = getattr(app, '_board_surface', None)
    if board is None or board.get_size() != app.board_rect.size:
        board = pygame.Surface(app.board_rect.size, pygame.SRCALPHA)
        app._board_surface = board

    eff_pan = (app.pan[0] + getattr(app, 'camera_pan_x', 0.0), app.pan[1])
    app.renderer.zoom, app.renderer.pan = app.zoom, eff_pan
    app.renderer.high_contrast = app.high_contrast
    if not sharp_board(app):
        app.renderer.pixel_scale = 1
        app.renderer.draw(board, app.session.current_state, app.animation.frame,
                          intro_t=getattr(app, 'intro_t', None), outro_t=app.board_outro() if hasattr(app, 'board_outro') else None,
                          shockwave=getattr(app, 'shockwave', None), bridges=app.bridge_view() if hasattr(app, 'bridge_view') else None)
        draw_rect = app.board_rect
        if getattr(app, 'trauma', 0.0) > 0.01:
            intensity = app.trauma ** 1.5
            ticks = pygame.time.get_ticks()
            shake_x = round(math.sin(ticks * 0.048) * 2.5 * intensity)
            shake_y = round(math.cos(ticks * 0.062) * 1.8 * intensity)
            draw_rect = app.board_rect.move(shake_x, shake_y)
        screen.blit(board, draw_rect)

    # 1. Single Unified In-game Header Row (y = 16, height = 42)
    header_y = 16
    header_h = 42

    # Left: Logo capsule with miniature animated crystal jewel
    logo_w = 146
    logo_rect = pygame.Rect(16, header_y, logo_w, header_h)
    draw_glass_panel(screen, logo_rect, style=style, border_radius=21, shadow=False)
    mini_bx, mini_by = 16 + 22, header_y + 21
    mini_top = [(mini_bx, mini_by - 7), (mini_bx + 9, mini_by - 2), (mini_bx, mini_by + 2), (mini_bx - 9, mini_by - 2)]
    mini_left = [(mini_bx - 9, mini_by - 2), (mini_bx, mini_by + 2), (mini_bx, mini_by + 11), (mini_bx - 9, mini_by + 6)]
    mini_right = [(mini_bx, mini_by + 2), (mini_bx + 9, mini_by - 2), (mini_bx + 9, mini_by + 6), (mini_bx, mini_by + 11)]
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (22, 32, 48) if style != 'dream' else (185, 122, 155), 0.35), mini_left)
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (8, 12, 22) if style != 'dream' else (135, 72, 105), 0.65), mini_right)
    pygame.draw.polygon(screen, lerp_color(T.ACCENT, (255, 255, 255), 0.58), mini_top)
    pygame.draw.lines(screen, (255, 255, 255, 200), True, mini_top, 1)
    logo_title = heading.render("BLOXORZ", True, T.TEXT)
    screen.blit(logo_title, (mini_bx + 16, header_y + (header_h - logo_title.get_height()) // 2))

    # Menu button capsule
    menu_btn_x = 16 + logo_w + 10
    button('main_menu', 'Menu', menu_btn_x, header_y, 88, kind='pill', height=header_h, icon='menu')

    # Stage and Moves info capsule
    stat_x = menu_btn_x + 88 + 10
    stat_w = 196
    stat_rect = pygame.Rect(stat_x, header_y, stat_w, header_h)
    draw_glass_panel(screen, stat_rect, style=style, border_radius=21, shadow=False)
    stat_text = f"STAGE {app.stage_index + 1:02}  ·  {app.session.moves} MOVES"
    stat_surf = body.render(stat_text, True, T.TEXT)
    screen.blit(stat_surf, stat_surf.get_rect(center=stat_rect.center))

    # Navigation buttons on the right of the header
    nav_right = w - 16
    button('help', 'Help', nav_right - 84, header_y, 84, kind='pill', height=header_h, icon='help')
    button('settings', 'Settings', nav_right - 84 - 8 - 110, header_y, 110, kind='pill', height=header_h, icon='settings')
    theme_text = {'dream': 'Dream City', 'forest': 'Forest Ruins', 'blueprint': 'Blueprint', 'forest_gl': 'OpenGL'}.get(style, style)
    button('theme', theme_text, nav_right - 84 - 8 - 110 - 8 - 140, header_y, 140, style != 'forest_gl', kind='pill', height=header_h, icon='theme')
    button('choose', f'Stage {app.stage_index + 1:02}', nav_right - 84 - 8 - 110 - 8 - 140 - 8 - 124, header_y, 124, bool(app.stage_paths), kind='pill', height=header_h, icon='view')

    # Centered Toast notification: Strictly stacked ABOVE bottom dock (y = h - 96, height = 26)
    message = app.message
    hidden = ('Rolling...', 'Move accepted.', 'Stage loaded. Arrow keys / WASD to roll.',
              'Roll with arrows or WASD. Reach G standing upright.')
    if message in hidden:
        message = 'Use arrow keys or WASD to roll the block.' if not app.actions and not replaying else ''
    if app.busy:
        message = ''
    if message:
        m_w = min(center_w - 48, max(280, caption.size(message)[0] + 44))
        m_x = (center_w - m_w) // 2
        toast_rect = pygame.Rect(m_x, h - 96, m_w, 26)
        draw_glass_panel(screen, toast_rect, style=style, border_radius=13, shadow=False, fill_alpha=185)
        m_surf = caption.render(message, True, T.TEXT)
        screen.blit(m_surf, m_surf.get_rect(center=toast_rect.center))

    # Centered Bottom Dock (y = h - 60, height = 44) - Completely stable, no flickering or jumping on moves
    if not replaying:
        dock_w = 96 + 102 + 94 + 118 + 36
        dock_x = max(16, (center_w - dock_w) // 2)
        button('undo', 'Undo', dock_x, h - 60, 96, bool(app.actions), kind='dock_item', icon='undo', height=44)
        button('restart', 'Restart', dock_x + 96 + 12, h - 60, 102, True, kind='dock_item', icon='restart', height=44)
        button('hint', 'Hint', dock_x + 96 + 102 + 24, h - 60, 94, not app.busy, kind='dock_item', icon='hint', height=44)
        if not app.busy:
            button('solve', 'AI Solver', dock_x + 96 + 102 + 94 + 36, h - 60, 118, True,
                   kind='primary' if getattr(app, 'solver_open', False) else 'dock_item', selected=getattr(app, 'solver_open', False), icon='solve', height=44)
    else:
        left = max(16, (center_w - 480) // 2)
        button('back', 'Back', left, h - 60, 72, app.replay.index > 0, kind='dock_item', icon='back', height=44)
        button('play', 'Pause' if app.replay.status == ReplayStatus.PLAYING else 'Play',
               left + 78, h - 60, 92, not app.busy, 'primary', icon='play' if app.replay.status != ReplayStatus.PLAYING else 'pause', height=44)
        button('step', 'Next', left + 176, h - 60, 72, idle and app.replay.index < app.replay.length, kind='dock_item', icon='step', height=44)
        button('speed', f'{app.speed:g}×', left + 254, h - 60, 60, kind='dock_item', height=44)
        timeline_x = left + 322
        seek_w = max(44, center_w - 40 - timeline_x)
        app.seek_rect = pygame.Rect(timeline_x, h - 41, seek_w, 6)
        pygame.draw.rect(screen, T.LINE, app.seek_rect, border_radius=3)
        ratio = app.replay.index / max(1, app.replay.length)
        fill = app.seek_rect.copy()
        fill.width = int(fill.width * ratio)
        pygame.draw.rect(screen, T.ACCENT, fill, border_radius=3)
        pygame.draw.circle(screen, T.ACCENT, (app.seek_rect.x + fill.width, app.seek_rect.centery), 5)
        label(f'{app.replay.index} / {app.replay.length}', timeline_x + seek_w + 10, h - 47, T.MUTED, f=caption)

    # Right Solver Drawer (Rendered cleanly when opened / active)
    if is_drawer_visible:
        if replaying:
            card_h = 360 if (app.stage_cleared and app.stage_index + 1 < len(app.stage_paths)) else 312
        elif app.busy:
            card_h = 254
        elif app.result and app.result.found:
            card_h = 446 if app.details_open else 336
        else:
            if app.dropdown_open or app.solver_status in (SolverStatus.ERROR, SolverStatus.TIMEOUT, SolverStatus.NO_SOLUTION, SolverStatus.CANCELLED):
                card_h = 368
            else:
                card_h = 326
        if getattr(app, 'large_text', False):
            card_h += 8
        card_h = min(card_h, h - 96)

        card_rect = pygame.Rect(panel_x - 16, 80, T.PANEL_WIDTH + 32, card_h)
        draw_glass_panel(screen, card_rect, style, border_radius=22, shadow=False)

        x, pw, y = panel_x, T.PANEL_WIDTH, 80
        pygame.draw.line(screen, T.LINE, (x + 8, y + 40), (x + pw - 8, y + 40))

        # Close solver drawer button (Working close button!)
        if not app.busy and not replaying:
            button('close_solver', '✕', card_rect.right - 38, y + 8, 30, height=30, kind='close_btn', icon='close')

        if replaying:
            label('Watch solution', x, y + 4, f=heading)
            label('One move at a time.', x, y + 36, T.MUTED, f=caption)
            label(f'{app.replay.index} / {app.replay.length}', x, y + 78, f=mono_lg)
            label('moves played', x, y + 116, T.MUTED, f=caption)
            button('stop', 'Exit replay', x, y + 162, pw, kind='dock_item', icon='stop')
            button('rewind', 'Back to start', x, y + 210, pw, kind='quiet')
            if app.stage_cleared and app.stage_index + 1 < len(app.stage_paths):
                button('next_stage', 'Next stage   >', x, y + 258, pw, not app.busy, 'primary')
        elif app.busy:
            label('Finding a path', x, y + 4, f=heading)
            label({'ASTAR': 'A*'}.get(app.algorithm, app.algorithm), x, y + 36, T.MUTED, f=caption)
            center = (x + 12, y + 104)
            angle = pygame.time.get_ticks() / 350
            pygame.draw.circle(screen, T.LINE, center, 10, 2)
            pygame.draw.arc(screen, T.ACCENT, (center[0] - 10, center[1] - 10, 20, 20), angle, angle + 4, 2)
            label('Exploring possible moves…', x + 32, y + 92, T.MUTED, max_width=pw - 32)
            button('cancel', 'Cancel search', x, y + 152, pw)
        elif app.result and app.result.found:
            m = app.result.metrics
            label('A way forward', x + 4, y + 6, f=heading)

            # Elegant Featured Solution Summary Card
            sol_rect = pygame.Rect(x, y + 44, pw, 58)
            draw_glass_panel(screen, sol_rect, style=style, border_radius=16, shadow=False, fill_alpha=160)
            pygame.draw.rect(screen, (*T.ACCENT[:3], 120), sol_rect, 1, border_radius=16)
            text(screen, caption, "OPTIMAL SOLUTION READY", (sol_rect.x + 14, sol_rect.y + 10), T.ACCENT)
            alg_label = {'ASTAR': 'A*'}.get(app.result.algorithm, app.result.algorithm)
            text(screen, heading, f"{m.solution_length} Moves  ·  {alg_label}", (sol_rect.x + 14, sol_rect.y + 28), T.TEXT)

            button('solution', 'Watch solution', x, y + 116, pw, idle, 'primary', icon='play')
            button('details', ('−' if app.details_open else '+') + '  Result details', x, y + 168, pw, kind='dock_item')
            offset = y + 222
            if app.details_open:
                bw = (pw - 8) // 2
                bh = 50
                draw_bento_card(screen, pygame.Rect(x, offset, bw, bh), 'TIME', f'{m.time_sec:.3f}', 's', style, caption, mono, caption)
                draw_bento_card(screen, pygame.Rect(x + bw + 8, offset, bw, bh), 'RAM', f'{m.peak_memory_mb:.2f}', 'MB', style, caption, mono, caption)
                draw_bento_card(screen, pygame.Rect(x, offset + bh + 8, bw, bh), 'EXPANDED', f'{m.expanded_nodes}', '', style, caption, mono, caption)
                draw_bento_card(screen, pygame.Rect(x + bw + 8, offset + bh + 8, bw, bh), 'COST', f'{m.total_cost:g}', '', style, caption, mono, caption)
                offset += (bh * 2 + 16)
            button('new_search', 'Try another algorithm', x, offset + 10, pw, idle, 'quiet')
        else:
            label('S O L V E R', x + 8, y + 4, f=heading)
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
                draw_glass_panel(screen, app.dropdown_rect, style, border_radius=12)
                app.buttons = [b for b in app.buttons if not b.rect.colliderect(app.dropdown_rect)]
                for i, (key, title) in enumerate((('BFS', 'BFS'), ('IDS', 'IDS'), ('UCS', 'UCS'), ('ASTAR', 'A*'))):
                    button('algorithm:' + key, title, x + 8, y + 122 + i * 44, pw - 16,
                           kind='quiet', selected=app.algorithm == key)

    # Celebratory win confetti shower
    if app.win_phase in ('sink', 'disassemble', 'choice'):
        draw_confetti(screen, pygame.time.get_ticks(), w, h)

    _draw_modals(app, screen, w, h, style, heading, body, mono, caption, idle)


def _draw_modals(app, screen, w, h, style, heading, body, mono, caption, idle):
    def label(value, x, y, color=T.TEXT, f=body, max_width=None):
        text(screen, f, value, (x, y), color, max_width)

    def button(key, value, x, y, width, enabled=True, kind='secondary', selected=False, height=T.BUTTON_HEIGHT, icon=None):
        b = Button(key, value, pygame.Rect(x, y, width, height), enabled, selected, kind, icon=icon)
        app.buttons.append(b)
        b.draw(screen, body)
        return b

    # Win choice modal
    if app.win_phase == 'choice' and not (app.stage_picker or app.menu):
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((5, 12, 17, 160))
        screen.blit(shade, (0, 0))
        app.buttons = []
        app.seek_rect = pygame.Rect(0, 0, 0, 0)
        app.modal_rect = pygame.Rect((w - 480) // 2, (h - 272) // 2, 480, 272)
        r = app.modal_rect
        last = app.stage_index + 1 >= len(app.stage_paths)
        draw_glass_panel(screen, r, style=style, border_radius=24, shadow=True)
        label('Stage complete!', r.x + 32, r.y + 24, f=heading)
        label(f'Stage {app.stage_index + 1:02} cleared in {app.session.moves} moves.', r.x + 32, r.y + 72, T.MUTED)
        button('win_replay', 'Replay my moves', r.x + 32, r.y + 136, 200, kind='pill')
        if last:
            button('restart', 'Play again', r.x + 248, r.y + 136, 200, kind='primary', height=40)
        else:
            button('next_stage', 'Next stage   >', r.x + 248, r.y + 136, 200, kind='primary', height=40)

        keys = 'P: replay  ·  R: play again' if last else 'P: replay  ·  Enter: next stage  ·  R: restart'
        label(keys, r.x + 32, r.bottom - 56, T.MUTED, max_width=416)

    # Menus (Stage Picker, Settings, Help)
    if app.stage_picker or app.menu:
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        # Deep frosted glass shade to prevent ANY background menu text from bleeding through
        shade.fill((5, 12, 17, 242) if style != 'dream' else (35, 18, 28, 230))
        screen.blit(shade, (0, 0))
        app.buttons = []
        app.seek_rect = pygame.Rect(0, 0, 0, 0)

        mw = 608 if app.stage_picker else (710 if app.menu == 'help' else 480)
        mh = 464 if app.stage_picker else (540 if app.menu == 'help' else 590)
        app.modal_rect = pygame.Rect((w - mw) // 2, (h - mh) // 2, mw, mh)
        r = app.modal_rect
        draw_glass_panel(screen, r, style=style, border_radius=26, shadow=True, fill_alpha=215 if style == 'dream' else 235)

        title = 'Choose a stage' if app.stage_picker else ('Settings & Audio' if app.menu == 'settings' else 'How to Play & Controls')
        label(title, r.x + 32, r.y + 24, f=heading)
        # Prominent circular close button
        button('close_menu', '✕', r.right - 54, r.y + 20, 36, height=36, kind='close_btn', icon='close')

        if app.stage_picker:
            for i, path in enumerate(app.stage_paths[app.picker_page * 20:app.picker_page * 20 + 20]):
                index = app.picker_page * 20 + i
                button(f'stage:{index}', f'{index + 1:02}', r.x + 32 + (i % 4) * 136,
                       r.y + 88 + (i // 4) * 56, 128, selected=index == app.stage_index, kind='pill', height=42)
            button('page_prev', 'Previous', r.x + 32, r.bottom - 64, 152, app.picker_page > 0, 'quiet')
            button('page_next', 'Next', r.right - 184, r.bottom - 64, 152,
                   (app.picker_page + 1) * 20 < len(app.stage_paths), 'quiet')
        elif app.menu == 'settings':
            xx, yy = r.x + 32, r.y + 76
            button('save', 'Save session · F5', xx, yy, 196, idle, kind='pill', icon='save')
            button('load', 'Load session · F9', xx + 212, yy, 196, kind='pill', icon='load')

            label('Master Sound', xx, yy + 58)
            button('sound', 'On' if app.sound_enabled else 'Off', r.right - 120, yy + 50, 88, selected=app.sound_enabled, kind='pill')

            # BGM Slider
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

            # SFX Slider
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

            pygame.draw.line(screen, T.LINE, (xx, yy + 168), (r.right - 32, yy + 168), 1)

            # Prominent Featured AI Solver Showcase Card
            solver_card = pygame.Rect(xx, yy + 182, r.width - 64, 54)
            draw_glass_panel(screen, solver_card, style=style, border_radius=16, shadow=False, fill_alpha=175)
            pygame.draw.rect(screen, (*T.ACCENT[:3], 180), solver_card, 2, border_radius=16)
            glow = pygame.Surface((solver_card.width + 12, solver_card.height + 12), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*T.ACCENT[:3], 35), glow.get_rect(), border_radius=22)
            screen.blit(glow, (solver_card.x - 6, solver_card.y - 6))

            draw_vector_icon(screen, 'solve', (solver_card.x + 24, solver_card.centery), T.ACCENT, size=18)
            label('AI SOLVER PANEL', solver_card.x + 44, solver_card.centery - 10, color=T.TEXT, f=heading)
            is_solver_open = getattr(app, 'solver_open', False)
            button('toggle_solver', 'On' if is_solver_open else 'Off', solver_card.right - 98, solver_card.y + 7, 88,
                   selected=is_solver_open, kind='primary' if is_solver_open else 'pill', height=40, icon='solve')

            for i, (key, m_title, enabled) in enumerate((
                    ('animate', 'Animation', app.animate),
                    ('contrast', 'High Contrast', app.high_contrast),
                    ('text', 'Large Text', app.large_text))):
                row_y = yy + 248 + i * 40
                label(m_title, xx, row_y + 8)
                button(key, 'On' if enabled else 'Off', r.right - 120, row_y, 88, selected=enabled, kind='pill')

            # View & Camera: Using framed pill buttons with vector icons for prominent clickability
            view_label = 'View: Original' if app.renderer.view == 'original' else 'View: Classic'
            button('view', view_label + ' · V', xx, r.bottom - 100, 196, kind='pill', icon='view', height=40)
            button('camera', 'Reset camera', xx + 212, r.bottom - 100, 196, kind='pill', icon='restart', height=40)
            button('recording', 'Replay my moves', xx, r.bottom - 50, 408, idle and bool(app.actions), kind='pill', height=38)
        else:
            # Interactive 4 Bento Category Cards for HOW TO PLAY
            grid_w = (mw - 64 - 16) // 2
            grid_h = 204
            c1_x, c2_x = r.x + 32, r.x + 32 + grid_w + 16
            r1_y, r2_y = r.y + 76, r.y + 76 + grid_h + 14
            mouse = pygame.mouse.get_pos()

            def draw_help_card(cx, cy, card_title, icon_name, items):
                card_r = pygame.Rect(cx, cy, grid_w, grid_h)
                draw_glass_panel(screen, card_r, style=style, border_radius=18, shadow=False, fill_alpha=95)
                # Header badge
                icon_rect = pygame.Rect(cx + 12, cy + 12, 28, 28)
                draw_glass_panel(screen, icon_rect, style=style, border_radius=8, shadow=False, fill_alpha=120)
                draw_vector_icon(screen, icon_name, icon_rect.center, T.ACCENT, size=13)
                label(card_title, cx + 48, cy + 16, color=T.TEXT, f=heading)
                pygame.draw.line(screen, (*T.LINE[:3], 60), (cx + 12, cy + 46), (cx + grid_w - 12, cy + 46), 1)

                item_y = cy + 52
                for key_tag, desc in items:
                    chip_rect = pygame.Rect(cx + 10, item_y, grid_w - 20, 36)
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
                    label(desc, tag_rect.right + 8, chip_rect.centery - 7, color=desc_col, f=caption, max_width=grid_w - tag_w - 36)
                    item_y += 42

            # Card 1: Objective & Rules
            draw_help_card(c1_x, r1_y, "GOAL & OBJECTIVE", "play", [
                ("STAND", "Stand 1×1×2 block upright in goal"),
                ("EDGES", "Falling off restarts current stage"),
                ("ORANGE", "Fragile tiles break if upright!"),
            ])

            # Card 2: Controls & Movement
            draw_help_card(c2_x, r1_y, "CONTROLS & MOVES", "step", [
                ("WASD", "Roll block in 4 directions"),
                ("SPACE", "Switch active cube when split"),
                ("Z / U", "Undo move  ·  R: Restart stage"),
            ])

            # Card 3: Switches & Bridges
            draw_help_card(c1_x, r2_y, "SWITCHES & BRIDGES", "settings", [
                ("SOFT O", "Pressed flat or upright"),
                ("HEAVY X", "Only activated upright!"),
                ("SPLIT <>", "Splits into two 1×1 cubes"),
            ])

            # Card 4: Camera & Views
            draw_help_card(c2_x, r2_y, "CAMERA & VIEW", "view", [
                ("SCROLL", "Zoom in / out smoothly"),
                ("R-DRAG", "Pan & inspect board"),
                ("V KEY", "Toggle Classic / Original view"),
            ])



"""Game-first layout. All state-dependent presentation lives here."""
import math
import pygame
from src.gui import theme as T
from src.gui.ui import Button, text
from src.gui.contracts import ReplayStatus, SolverStatus
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
    ui_key = (getattr(app, 'visual_style', 'dream'), app.screen.get_size(), app.large_text, app.high_contrast,
              app.stage_index, app.session.moves, app.session.status, app.busy, app.animation.busy,
              app.replay.status, app.replay.index, app.replay.length, app.speed, app.message,
              app.algorithm, app.solve_current, id(app.result), app.details_open, app.solver_status,
              app.stage_picker, app.picker_page, app.menu, app.dropdown_open, app.sound_enabled, app.animate,
              bool(app.actions), hovered, pygame.mouse.get_pressed(),
              pygame.time.get_ticks() // 100 if app.busy else 0)
    board_key = (app.session.current_state, app.animation.frame, app.zoom, tuple(app.pan))
    cached = getattr(app, '_presentation_cache', None)
    if cached and cached[0] == ui_key and not (app.menu or app.stage_picker or app.dropdown_open):
        if cached[1] == board_key:
            return False
        app.screen.blit(cached[2], (0, 0))
        rect = app.board_rect
        app.screen.blit(scene(app), rect, rect)
        board = app._board_surface
        app.renderer.zoom, app.renderer.pan = app.zoom, tuple(app.pan)
        app.renderer.draw(board, app.session.current_state, app.animation.frame)
        app.screen.blit(board, rect)
        app._presentation_cache = (ui_key, board_key, cached[2])
        return True
    _draw(app)
    app._presentation_cache = (ui_key, board_key, app.screen.copy())
    return True


def _draw(app):
    screen = app.screen
    w, h = screen.get_size()
    body = T.font('body', app.large_text)
    heading = T.font('heading', app.large_text)
    display = T.font('display', app.large_text)
    mono = T.font('mono', app.large_text)
    mono_lg = T.font('mono_lg', app.large_text)
    caption = T.font('caption', app.large_text)

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
    app.board_rect = pygame.Rect(0, 80, panel_x - 16, h - 170)
    board = getattr(app, '_board_surface', None)
    if board is None or board.get_size() != app.board_rect.size:
        board = pygame.Surface(app.board_rect.size, pygame.SRCALPHA)
        app._board_surface = board
    app.renderer.zoom, app.renderer.pan = app.zoom, tuple(app.pan)
    app.renderer.high_contrast = app.high_contrast
    app.renderer.draw(board, app.session.current_state, app.animation.frame)
    screen.blit(board, app.board_rect)

    # Right panel background container
    panel = pygame.Surface((T.PANEL_WIDTH + 32, h - 100), pygame.SRCALPHA)
    if style == 'blueprint':
        pygame.draw.rect(panel, (*T.PANEL, 238), panel.get_rect(), border_radius=20)
        pygame.draw.rect(panel, (*T.LINE, 180), panel.get_rect(), 1, border_radius=20)
    else:
        pygame.draw.rect(panel, (*T.PANEL, 228 if forest else 244), panel.get_rect(), border_radius=22)
        border_col = (*T.LINE, 160) if forest else (255, 255, 255, 140)
        pygame.draw.rect(panel, border_col, panel.get_rect(), 1, border_radius=22)
    screen.blit(panel, (panel_x - 16, 76))

    def label(value, x, y, color=T.TEXT, f=body, max_width=None):
        text(screen, f, value, (x, y), color, max_width)

    def button(key, value, x, y, width, enabled=True, kind='secondary', selected=False):
        b = Button(key, value, pygame.Rect(x, y, width, T.BUTTON_HEIGHT), enabled, selected, kind)
        app.buttons.append(b)
        b.draw(screen, body)
        return b

    # Quiet, single-line navigation
    label('B L O X O R Z', 32, 18, f=heading)
    label(f'{app.session.moves} MOVES', 34, 48, (215, 230, 225) if forest or style == 'blueprint' else T.MUTED, f=caption)
    button('theme', {'dream': '04 / DREAM CITY', 'blueprint': '05 / PAPER BLUEPRINT',
                     'forest': '02 / FOREST RUINS', 'forest_gl': 'FOREST / OPENGL'}.get(style, style),
           316, 20, 268, style != 'forest_gl', kind='quiet')
    button('choose', f'Stage {app.stage_index + 1:02}', panel_x - 32, 20, 128, bool(app.stage_paths), 'quiet')
    button('help', '?', w - 152, 20, 40, kind='quiet')
    button('settings', 'Settings', w - 108, 20, 88, kind='quiet')


    idle = not app.busy and not app.animation.busy
    replaying = app.replay.status != ReplayStatus.EMPTY
    manual = idle and not replaying

    # Centered Floating Control Dock (Bottom Bar - Image 3 Inspired)
    dock_y = h - 68
    if not replaying:
        dock_w = 340
        dock_x = app.board_rect.centerx - dock_w // 2
        dock_surf = pygame.Surface((dock_w, 52), pygame.SRCALPHA)
        dock_surf.fill((*T.PANEL, 218 if forest else 236))
        pygame.draw.rect(dock_surf, (*T.LINE, 180), dock_surf.get_rect(), 1, border_radius=26)
        screen.blit(dock_surf, (dock_x, dock_y))

        button('undo', 'Undo', dock_x + 8, dock_y + 6, 102, manual and bool(app.actions), kind='dock_item')
        button('restart', 'Restart', dock_x + 118, dock_y + 6, 104, True, kind='dock_item')
        button('hint', 'Hint', dock_x + 230, dock_y + 6, 102, manual, kind='dock_item')
    else:
        dock_w = min(530, max(390, panel_x - 32))
        dock_x = app.board_rect.centerx - dock_w // 2
        dock_surf = pygame.Surface((dock_w, 52), pygame.SRCALPHA)
        dock_surf.fill((*T.PANEL, 218 if forest else 236))
        pygame.draw.rect(dock_surf, (*T.LINE, 180), dock_surf.get_rect(), 1, border_radius=26)
        screen.blit(dock_surf, (dock_x, dock_y))

        button('back', 'Back', dock_x + 8, dock_y + 6, 64, app.replay.index > 0, kind='dock_item')
        button('play', 'Pause' if app.replay.status == ReplayStatus.PLAYING else 'Play',
               dock_x + 78, dock_y + 6, 96, not app.busy, 'primary')
        button('step', 'Next', dock_x + 180, dock_y + 6, 64, idle and app.replay.index < app.replay.length, kind='dock_item')
        button('speed', f'{app.speed:g}×', dock_x + 250, dock_y + 6, 54, kind='dock_item')

        timeline_x = dock_x + 312
        seek_w = max(44, dock_w - 386)
        app.seek_rect = pygame.Rect(timeline_x, dock_y + 23, seek_w, 6)
        pygame.draw.rect(screen, T.LINE, app.seek_rect, border_radius=3)
        ratio = app.replay.index / max(1, app.replay.length)
        fill = app.seek_rect.copy()
        fill.width = int(fill.width * ratio)
        pygame.draw.rect(screen, T.ACCENT, fill, border_radius=3)
        pygame.draw.circle(screen, T.ACCENT, (app.seek_rect.x + fill.width, app.seek_rect.centery), 5)
        label(f'{app.replay.index}/{app.replay.length}', timeline_x + seek_w + 10, dock_y + 16, T.MUTED, f=caption)

    # Toast line
    message = app.message
    hidden = ('Rolling...', 'Move accepted.', 'Stage loaded. Arrow keys / WASD to roll.',
              'Roll with arrows or WASD. Reach G standing upright.')
    if message in hidden:
        message = 'Use arrow keys or WASD to roll the block.' if not app.actions and not replaying else ''
    if app.busy:
        message = ''
    if message:
        footer = pygame.Surface((panel_x - 40, 26), pygame.SRCALPHA)
        pygame.draw.rect(footer, (*T.PANEL, 200), footer.get_rect(), border_radius=8)
        screen.blit(footer, (24, h - 34))
    label(message, 32, h - 32, T.TEXT, max_width=panel_x - 48)

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
        center = (x + 12, y + 104)
        angle = pygame.time.get_ticks() / 350
        pygame.draw.circle(screen, T.LINE, center, 10, 2)
        pygame.draw.arc(screen, T.ACCENT, (center[0] - 10, center[1] - 10, 20, 20), angle, angle + 4, 2)
        label('Exploring possible moves…', x + 32, y + 92, T.MUTED, max_width=pw - 32)
        button('cancel', 'Cancel search', x, y + 152, pw)
    elif app.result and app.result.found:
        m = app.result.metrics
        label('A way forward', x, y, f=heading)
        label(f'{m.solution_length} moves', x, y + 38, f=display)
        alg_label = {'ASTAR': 'A*'}.get(app.result.algorithm, app.result.algorithm)
        label(f'{m.time_sec:.3f} s  ·  {alg_label}', x, y + 80, T.MUTED, f=caption)
        button('solution', 'Watch solution', x, y + 116, pw, idle, 'primary')
        button('details', ('−' if app.details_open else '+') + '  Result details', x, y + 166, pw, kind='quiet')
        offset = y + 214
        if app.details_open:
            # 2x2 Bento Metrics Grid
            bw = (pw - 8) // 2
            bh = 46
            b1 = pygame.Rect(x, offset, bw, bh)
            pygame.draw.rect(screen, T.SURFACE, b1, border_radius=8)
            pygame.draw.rect(screen, T.LINE, b1, 1, border_radius=8)
            label('TIME', b1.x + 8, b1.y + 6, T.MUTED, f=caption)
            label(f'{m.time_sec:.3f} s', b1.x + 8, b1.y + 22, T.TEXT, f=mono)

            b2 = pygame.Rect(x + bw + 8, offset, bw, bh)
            pygame.draw.rect(screen, T.SURFACE, b2, border_radius=8)
            pygame.draw.rect(screen, T.LINE, b2, 1, border_radius=8)
            label('RAM', b2.x + 8, b2.y + 6, T.MUTED, f=caption)
            label(f'{m.peak_memory_mb:.2f} MB', b2.x + 8, b2.y + 22, T.TEXT, f=mono)

            b3 = pygame.Rect(x, offset + bh + 8, bw, bh)
            pygame.draw.rect(screen, T.SURFACE, b3, border_radius=8)
            pygame.draw.rect(screen, T.LINE, b3, 1, border_radius=8)
            label('EXPANDED', b3.x + 8, b3.y + 6, T.MUTED, f=caption)
            label(f'{m.expanded_nodes}', b3.x + 8, b3.y + 22, T.TEXT, f=mono)

            b4 = pygame.Rect(x + bw + 8, offset + bh + 8, bw, bh)
            pygame.draw.rect(screen, T.SURFACE, b4, border_radius=8)
            pygame.draw.rect(screen, T.LINE, b4, 1, border_radius=8)
            label('COST', b4.x + 8, b4.y + 6, T.MUTED, f=caption)
            label(f'{m.total_cost:g}', b4.x + 8, b4.y + 22, T.TEXT, f=mono)

            offset += (bh * 2 + 16)
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
            pygame.draw.rect(screen, T.PANEL, app.dropdown_rect, border_radius=8)
            app.buttons = [b for b in app.buttons if not b.rect.colliderect(app.dropdown_rect)]
            for i, (key, title) in enumerate((('BFS', 'BFS'), ('IDS', 'IDS'), ('UCS', 'UCS'), ('ASTAR', 'A*'))):
                button('algorithm:' + key, title, x + 8, y + 122 + i * 44, pw - 16,
                       kind='quiet', selected=app.algorithm == key)

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
        mh = 464 if app.stage_picker else 536 if app.menu == 'settings' else 432
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
            xx, yy = r.x + 32, r.y + 88
            button('save', 'Save session · F5', xx, yy, 200, idle)
            button('load', 'Load session · F9', xx + 216, yy, 200)
            for i, (key, title, enabled) in enumerate((('sound', 'Sound', app.sound_enabled),
                    ('animate', 'Animation', app.animate), ('contrast', 'Contrast', app.high_contrast),
                    ('text', 'Large text', app.large_text))):
                label(title, xx, yy + 72 + i * 48)
                button(key, 'On' if enabled else 'Off', r.right - 120, yy + 64 + i * 48, 88, selected=enabled)
            view_label = 'View: Original' if app.renderer.view == 'original' else 'View: Classic'
            button('view', view_label + ' · V', xx, r.bottom - 120, 200, kind='quiet')
            button('camera', 'Reset camera', xx + 216, r.bottom - 120, 200, kind='quiet')
            button('recording', 'Replay my moves', xx, r.bottom - 64, 416, idle and bool(app.actions), 'quiet')
        else:
            lines = ['Stand the block upright in the dark goal.', 'Arrows / WASD: roll · Space: switch cube',
                     'Z: undo · R: restart · Esc: close menu', 'Scroll: zoom · Right-drag: pan the camera',
                     'V: switch camera view · Falling off restarts',
                     'Circle: soft switch · X: heavy switch', 'Brackets: split switch · Crack: fragile tile',
                     'Outlined bridge: off · Light cube: active']
            for i, line in enumerate(lines):
                label(line, r.x + 32, r.y + 88 + i * 40, T.TEXT if i == 0 else T.MUTED, max_width=mw - 64)

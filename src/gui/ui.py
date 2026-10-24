"""Commercial-grade vector UI primitives and tactile micro-interactions."""
from dataclasses import dataclass
import math
import pygame
from src.gui.theme import BG, PANEL, TEXT, MUTED, ACCENT
from src.gui import theme


def text(surface, font, value, pos, color=TEXT, max_width=None):
    """Render anti-aliased text with optional ellipsis truncation."""
    value = str(value)
    if max_width is not None and font.size(value)[0] > max_width:
        while value and font.size(value + '…')[0] > max_width:
            value = value[:-1]
        value += '…'
    surface.blit(font.render(value, True, color), pos)


def draw_vector_icon(surface, name, center, color, size=16):
    """Draw crisp mathematical procedural vector icons."""
    cx, cy = center
    hs = size / 2

    if name in ('undo', 'rewind'):
        # Crisp modern undo arrow: pointing left, rounded curve sweeping down-right
        tip_x, tip_y = cx - 5, cy - 2
        pygame.draw.polygon(surface, color, [
            (tip_x, tip_y),
            (tip_x + 5, tip_y - 4),
            (tip_x + 5, tip_y + 4)
        ])
        pygame.draw.line(surface, color, (tip_x + 4, tip_y), (cx + 1, tip_y), 2)
        r = 4.0
        curve_pts = []
        for i in range(9):
            ang = math.pi * 0.5 - (math.pi * 0.5) * (i / 8)
            px = cx + 1 + r * math.cos(ang)
            py = tip_y + r - r * math.sin(ang)
            curve_pts.append((round(px), round(py)))
        pygame.draw.lines(surface, color, False, curve_pts, 2)
        pygame.draw.line(surface, color, (cx + 1 + round(r), tip_y + round(r)), (cx + 1 + round(r), cy + 4), 2)

    elif name in ('restart', 'refresh'):
        # Clockwise 3/4 circle refresh arrow
        r = hs * 0.82
        arc_rect = pygame.Rect(cx - r, cy - r, 2 * r, 2 * r)
        pygame.draw.arc(surface, color, arc_rect, -math.pi * 0.45, math.pi * 1.15, 2)
        tip_x = cx + r * math.cos(math.pi * 1.15)
        tip_y = cy - r * math.sin(math.pi * 1.15)
        pygame.draw.polygon(surface, color, [
            (tip_x - 4, tip_y - 3),
            (tip_x + 3, tip_y - 4),
            (tip_x, tip_y + 4),
        ])

    elif name in ('hint', 'bulb'):
        # Elegant vector lightbulb with glow
        r = hs * 0.62
        pygame.draw.circle(surface, color, (round(cx), round(cy - 2)), round(r), 2)
        base_y = cy + r - 1
        pygame.draw.line(surface, color, (cx - 3, base_y), (cx + 3, base_y), 2)
        pygame.draw.line(surface, color, (cx - 2, base_y + 3), (cx + 2, base_y + 3), 2)
        # Inner filament dot
        pygame.draw.circle(surface, color, (round(cx), round(cy - 2)), 1)

    elif name == 'play':
        pts = [
            (cx - hs * 0.55, cy - hs * 0.85),
            (cx + hs * 0.85, cy),
            (cx - hs * 0.55, cy + hs * 0.85),
        ]
        pygame.draw.polygon(surface, color, pts)

    elif name == 'pause':
        w = max(2, round(hs * 0.42))
        gap = max(2, round(hs * 0.38))
        h = round(hs * 1.6)
        r1 = pygame.Rect(round(cx - gap - w), round(cy - h / 2), w, h)
        r2 = pygame.Rect(round(cx + gap), round(cy - h / 2), w, h)
        pygame.draw.rect(surface, color, r1, border_radius=2)
        pygame.draw.rect(surface, color, r2, border_radius=2)

    elif name in ('step', 'next'):
        # Right chevron with bar
        pts = [(cx - 3, cy - hs * 0.7), (cx + 3, cy), (cx - 3, cy + hs * 0.7)]
        pygame.draw.lines(surface, color, False, pts, 2)
        pygame.draw.line(surface, color, (cx + 6, cy - hs * 0.7), (cx + 6, cy + hs * 0.7), 2)

    elif name == 'back':
        # Left chevron with bar
        pts = [(cx + 3, cy - hs * 0.7), (cx - 3, cy), (cx + 3, cy + hs * 0.7)]
        pygame.draw.lines(surface, color, False, pts, 2)
        pygame.draw.line(surface, color, (cx - 6, cy - hs * 0.7), (cx - 6, cy + hs * 0.7), 2)

    elif name in ('stop', 'exit'):
        sz = round(hs * 1.2)
        r = pygame.Rect(round(cx - sz / 2), round(cy - sz / 2), sz, sz)
        pygame.draw.rect(surface, color, r, border_radius=3)

    elif name in ('menu', 'home'):
        for offset_y in (-4, 0, 4):
            pygame.draw.line(surface, color, (cx - 5, cy + offset_y), (cx + 5, cy + offset_y), 2)

    elif name in ('settings', 'gear'):
        pygame.draw.circle(surface, color, (round(cx), round(cy)), round(hs * 0.72), 2)
        for ang_deg in (0, 60, 120, 180, 240, 300):
            rad = math.radians(ang_deg)
            x1 = cx + (hs * 0.65) * math.cos(rad)
            y1 = cy + (hs * 0.65) * math.sin(rad)
            x2 = cx + (hs * 0.98) * math.cos(rad)
            y2 = cy + (hs * 0.98) * math.sin(rad)
            pygame.draw.line(surface, color, (round(x1), round(y1)), (round(x2), round(y2)), 2)

    elif name == 'help':
        pygame.draw.circle(surface, color, (round(cx), round(cy)), round(hs * 0.82), 2)
        pygame.draw.circle(surface, color, (round(cx), round(cy + 4)), 1)
        pygame.draw.arc(surface, color, pygame.Rect(round(cx - 3), round(cy - 5), 6, 6), 0, math.pi, 2)

    elif name in ('theme', 'palette'):
        r = hs * 0.85
        pygame.draw.circle(surface, color, (round(cx), round(cy)), round(r), 2)
        for dx, dy in ((-2.5, -2.5), (2.5, -2.5), (0, 2.5)):
            pygame.draw.circle(surface, color, (round(cx + dx), round(cy + dy)), 1)

    elif name in ('solve', 'ai'):
        pts = [
            (cx + 1, cy - hs * 0.85),
            (cx - 4, cy + 0.5),
            (cx - 0.5, cy + 0.5),
            (cx - 1, cy + hs * 0.85),
            (cx + 4, cy - 0.5),
            (cx + 0.5, cy - 0.5),
        ]
        pygame.draw.polygon(surface, color, pts)

    elif name == 'view':
        cr = hs * 0.75
        p_c = (cx, cy)
        p_t = (cx, cy - cr)
        p_b = (cx, cy + cr)
        dx = cr * 0.866
        dy = cr * 0.5
        p_tl = (cx - dx, cy - dy)
        p_tr = (cx + dx, cy - dy)
        p_bl = (cx - dx, cy + dy)
        p_br = (cx + dx, cy + dy)
        pygame.draw.lines(surface, color, True, [p_t, p_tr, p_br, p_b, p_bl, p_tl], 1)
        pygame.draw.line(surface, color, p_c, p_t, 1)
        pygame.draw.line(surface, color, p_c, p_bl, 1)
        pygame.draw.line(surface, color, p_c, p_br, 1)

    elif name in ('close', 'x'):
        s = hs * 0.65
        pygame.draw.line(surface, color, (cx - s, cy - s), (cx + s, cy + s), 2)
        pygame.draw.line(surface, color, (cx - s, cy + s), (cx + s, cy - s), 2)

    elif name in ('load', 'folder'):
        fw, fh = hs * 1.5, hs * 1.1
        fx, fy = cx - fw / 2, cy - fh / 2
        pygame.draw.rect(surface, color, pygame.Rect(round(fx), round(fy), round(fw * 0.45), 3), border_radius=1)
        pygame.draw.rect(surface, color, pygame.Rect(round(fx), round(fy + 2), round(fw), round(fh)), 1, border_radius=2)


_GLASS_PANEL_CACHE = {}


def draw_glass_panel(surface, rect, style='dream', border_radius=24, shadow=True, fill_alpha=None, specular=True):
    """Render procedural Frosted Glassmorphism card with ambient shadow, translucent tint, and specular rim."""
    w, h = rect.size
    if w <= 8 or h <= 8:
        return
    cache_key = (w, h, style, border_radius, shadow, fill_alpha, specular)
    cached = _GLASS_PANEL_CACHE.get(cache_key)
    if cached is None:
        shadow_surf = None
        if shadow:
            pad = 14
            shadow_surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
            for layer in range(pad, 0, -2):
                alpha = int(22 * (1.0 - layer / pad) ** 1.8)
                layer_rect = pygame.Rect(pad - layer, pad - layer + 4, w + layer * 2, h + layer * 2)
                pygame.draw.rect(shadow_surf, (0, 0, 0, alpha), layer_rect, border_radius=border_radius + layer)

        panel_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if style == 'dream':
            base_col = (255, 246, 250, fill_alpha if fill_alpha is not None else 145)
            rim_bright = (255, 255, 255, 220)
            rim_soft = (255, 255, 255, 120)
            inner_glow = (255, 235, 245, 50)
        elif style in ('forest', 'forest_gl'):
            base_col = (18, 32, 25, fill_alpha if fill_alpha is not None else 165)
            rim_bright = (210, 248, 228, 195)
            rim_soft = (110, 160, 130, 120)
            inner_glow = (130, 185, 150, 40)
        else:  # blueprint
            base_col = (14, 32, 52, fill_alpha if fill_alpha is not None else 180)
            rim_bright = (175, 235, 255, 215)
            rim_soft = (55, 130, 185, 130)
            inner_glow = (75, 175, 225, 40)

        pygame.draw.rect(panel_surf, base_col, panel_surf.get_rect(), border_radius=border_radius)
        if inner_glow[3] > 0:
            pygame.draw.rect(panel_surf, inner_glow, panel_surf.get_rect().inflate(-2, -2), 1, border_radius=max(1, border_radius - 1))

        pygame.draw.rect(panel_surf, rim_soft, panel_surf.get_rect(), 1, border_radius=border_radius)
        if specular and w > border_radius * 2:
            spec_top = pygame.Surface((w, 2), pygame.SRCALPHA)
            pygame.draw.line(spec_top, rim_bright, (border_radius, 0), (w - border_radius, 0), 1)
            panel_surf.blit(spec_top, (0, 0))
            if h > border_radius * 2:
                spec_left = pygame.Surface((2, h), pygame.SRCALPHA)
                pygame.draw.line(spec_left, rim_bright, (0, border_radius), (0, h - border_radius), 1)
                panel_surf.blit(spec_left, (0, 0))

        if len(_GLASS_PANEL_CACHE) > 32:
            _GLASS_PANEL_CACHE.clear()
        cached = (shadow_surf, panel_surf)
        _GLASS_PANEL_CACHE[cache_key] = cached

    shadow_surf, panel_surf = cached
    if shadow_surf is not None:
        surface.blit(shadow_surf, (rect.x - 14, rect.y - 14))
    surface.blit(panel_surf, rect.topleft)


def draw_bento_card(surface, rect, label, value, unit="", style='dream', font_lbl=None, font_val=None, font_unit=None):
    """Render a 2x2 Bento Metric Card with solid frosted glass styling, hover glow, and centered typography."""
    mouse_pos = pygame.mouse.get_pos()
    is_hover = rect.collidepoint(mouse_pos)
    draw_r = rect
    if is_hover:
        ticks = pygame.time.get_ticks()
        sway_x = round(math.sin(ticks * 0.008 + rect.x) * 1.5)
        lift_y = -3 + round(math.cos(ticks * 0.008 + rect.y) * 1.0)
        draw_r = rect.move(sway_x, lift_y)

    alpha = 185 if style == 'dream' else 215
    draw_glass_panel(surface, draw_r, style=style, border_radius=14, shadow=False, fill_alpha=alpha, specular=True)
    border_col = theme.ACCENT if is_hover else ((255, 255, 255, 80) if style == 'dream' else (*theme.LINE[:3], 90))
    pygame.draw.rect(surface, border_col, draw_r, 1, border_radius=14)
    if is_hover:
        glow = pygame.Surface((draw_r.width + 8, draw_r.height + 8), pygame.SRCALPHA)
        pygame.draw.rect(glow, (*theme.ACCENT[:3], 35), glow.get_rect(), border_radius=18)
        surface.blit(glow, (draw_r.x - 4, draw_r.y - 4))

    lbl_color = theme.ACCENT if is_hover else theme.MUTED
    if font_lbl:
        text(surface, font_lbl, label.upper(), (draw_r.x + 12, draw_r.y + 7), lbl_color)

    val_color = theme.TEXT
    if font_val:
        v_surf = font_val.render(str(value), True, val_color)
        u_surf = font_unit.render(f" {unit}", True, theme.MUTED) if (unit and font_unit) else None
        val_y = draw_r.y + 24
        surface.blit(v_surf, (draw_r.x + 12, val_y))
        if u_surf:
            surface.blit(u_surf, (draw_r.x + 12 + v_surf.get_width(), val_y + max(0, v_surf.get_height() - u_surf.get_height() - 2)))


_BUTTON_ANIM: dict[str, dict[str, float]] = {}


def lerp_color(c1, c2, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(round(a + (b - a) * t) for a, b in zip(c1[:3], c2[:3]))


@dataclass
class Button:
    key: str
    label: str
    rect: pygame.Rect
    enabled: bool = True
    selected: bool = False
    kind: str = 'secondary'
    icon: str | None = None

    def draw(self, surface, font):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.enabled and self.rect.collidepoint(mouse_pos)
        pressed = hover and pygame.mouse.get_pressed()[0]

        # Smooth interactive animation tracking (60fps ease)
        btn_id = f"{self.key}_{self.kind}"
        anim = _BUTTON_ANIM.setdefault(btn_id, {'hover': 0.0, 'press': 0.0, 'ripple': 0.0})
        anim['hover'] += ((1.0 if hover else 0.0) - anim['hover']) * 0.35
        anim['press'] += ((1.0 if pressed else 0.0) - anim['press']) * 0.50
        if pressed:
            anim['ripple'] = min(1.0, anim.get('ripple', 0.0) + 0.16)
        else:
            anim['ripple'] = max(0.0, anim.get('ripple', 0.0) - 0.08)
        if not hover and anim['hover'] < 0.002:
            anim['hover'] = 0.0
        if not pressed and anim['press'] < 0.002:
            anim['press'] = 0.0
        h_t = anim['hover']
        p_t = anim['press']
        rip_t = anim['ripple']

        # Physical translation: lift up smoothly on hover, depress down on click
        # Dynamic floating & swaying micro-animation on hover
        ticks = pygame.time.get_ticks()
        float_y = math.sin(ticks * 0.0065 + self.rect.x * 0.04) * 2.2
        sway_x = math.sin(ticks * 0.0035 + self.rect.y * 0.04) * 1.2

        dy = -round(h_t * 3.0 + float_y * h_t) + round(p_t * 3.5) if (h_t > 0 or p_t > 0) else 0
        dx = round(sway_x * h_t) if h_t > 0 else 0
        draw_rect = self.rect.move(dx, dy)
        radius = draw_rect.height // 2 if self.kind in ('pill', 'dock_item') else 12

        # Luminous ambient aura glow beneath button on hover
        if self.enabled and h_t > 0.05:
            glow_surf = pygame.Surface((draw_rect.width + 16, draw_rect.height + 16), pygame.SRCALPHA)
            glow_alpha = int(42 * h_t) if self.kind == 'primary' else int(25 * h_t)
            glow_col = (*theme.ACCENT[:3], glow_alpha)
            pygame.draw.rect(glow_surf, glow_col, glow_surf.get_rect(), border_radius=radius + 6)
            surface.blit(glow_surf, (draw_rect.x - 8, draw_rect.y - 8 + 2))

        # Soft dynamic drop shadow when lifted / enabled
        if self.enabled and self.kind != 'quiet':
            shadow_offset = round(2.5 + h_t * 4.0 - p_t * 2.0)
            shadow_rect = self.rect.move(dx, shadow_offset)
            shadow_surf = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, (0, 0, 0, int(22 + 55 * h_t)), shadow_surf.get_rect(), border_radius=radius)
            surface.blit(shadow_surf, shadow_rect)

        # Smooth color transitions
        if h_t == 0.0 and p_t == 0.0:
            if self.kind == 'primary':
                color = theme.ACCENT if self.enabled else theme.SURFACE
                foreground = theme.INK if self.enabled else theme.DISABLED
            elif self.kind == 'quiet':
                color = None
                foreground = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
            elif self.kind == 'dock_item':
                color = tuple((*theme.SURFACE, 200)) if len(theme.SURFACE) == 4 else theme.SURFACE
                foreground = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
            else:
                color = theme.SURFACE
                foreground = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
        else:
            if self.kind == 'primary':
                color = lerp_color(theme.ACCENT, theme.ACCENT_HOVER, h_t)
                if p_t > 0.01:
                    dark_accent = tuple(max(0, c - 26) for c in theme.ACCENT)
                    color = lerp_color(color, dark_accent, p_t)
                if not self.enabled:
                    color = theme.SURFACE
                foreground = theme.INK if self.enabled else theme.DISABLED
            elif self.kind == 'dock_item':
                base_col = tuple((*theme.SURFACE, 200)) if len(theme.SURFACE) == 4 else theme.SURFACE
                hover_col = tuple(min(255, c + 22) for c in theme.HOVER)
                press_col = tuple(min(255, c + 15) for c in theme.PRESSED)
                color = lerp_color(base_col, hover_col, h_t)
                if p_t > 0.01:
                    color = lerp_color(color, press_col, p_t)
                base_fg = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
                bright_fg = theme.ACCENT if self.selected else (tuple(min(255, c + 35) for c in theme.TEXT) if self.enabled else theme.DISABLED)
                foreground = lerp_color(base_fg, bright_fg, h_t)
            else:
                base_col = theme.SURFACE
                hover_col = theme.HOVER
                press_col = theme.PRESSED
                color = lerp_color(base_col, hover_col, h_t)
                if p_t > 0.01:
                    color = lerp_color(color, press_col, p_t)
                if self.kind == 'quiet':
                    if h_t < 0.02:
                        color = None
                    else:
                        color = tuple((*theme.ACCENT_HOVER[:3], int(60 * h_t)))
                base_fg = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
                bright_fg = theme.ACCENT if self.selected else (tuple(min(255, c + 40) for c in theme.TEXT) if self.enabled else theme.DISABLED)
                foreground = lerp_color(base_fg, bright_fg, h_t)

        # Draw tactile background
        if color:
            if len(color) == 4 and color[3] < 255 and not (surface.get_flags() & pygame.SRCALPHA):
                col_surf = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(col_surf, color, col_surf.get_rect(), border_radius=radius)
                surface.blit(col_surf, draw_rect)
            else:
                pygame.draw.rect(surface, color, draw_rect, border_radius=radius)

            if self.kind == 'primary' and self.enabled:
                # Polished glass top shine highlight
                gradient = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                for row in range(max(1, draw_rect.height // 2)):
                    alpha = int((45 + 35 * h_t) * (1.0 - row / (draw_rect.height / 2)))
                    pygame.draw.line(gradient, (255, 255, 255, alpha), (0, row), (draw_rect.width, row))
                mask = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
                gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surface.blit(gradient, draw_rect)
            elif self.kind != 'quiet':
                if self.enabled and h_t > 0.01:
                    # Luminous top-edge glass sheen on hover
                    sheen = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                    pygame.draw.line(sheen, (255, 255, 255, int(50 * h_t)), (radius, 1), (draw_rect.width - radius, 1), 1)
                    surface.blit(sheen, draw_rect)
                border_color = lerp_color(theme.LINE, theme.ACCENT, h_t) if (self.enabled and h_t > 0) else theme.LINE
                pygame.draw.rect(surface, border_color, draw_rect, 1, border_radius=radius)
            elif self.kind == 'quiet' and h_t > 0.05:
                quiet_border = (*theme.ACCENT[:3], int(130 * h_t))
                col_b = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(col_b, quiet_border, col_b.get_rect(), 1, border_radius=radius)
                surface.blit(col_b, draw_rect)

        # Tactile material click ripple
        if rip_t > 0.02 and self.enabled:
            rip_surf = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
            rip_r = max(4, int(draw_rect.width * 0.85 * rip_t))
            rip_alpha = int(75 * (1.0 - rip_t))
            rip_pos = (mouse_pos[0] - draw_rect.x, mouse_pos[1] - draw_rect.y)
            pygame.draw.circle(rip_surf, (255, 255, 255, rip_alpha), rip_pos, rip_r)
            rip_mask = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(rip_mask, (255, 255, 255, 255), rip_mask.get_rect(), border_radius=radius)
            rip_surf.blit(rip_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(rip_surf, draw_rect)

        if self.selected and self.kind != 'dock_item':
            pygame.draw.rect(surface, theme.ACCENT, draw_rect, 1, border_radius=12)

        # Draw icon and label
        has_vector_icon = bool(self.icon) or self.key in ('undo', 'restart', 'hint', 'play', 'step', 'back', 'stop',
                                                          'menu', 'settings', 'help', 'theme', 'solve', 'view', 'close', 'load')
        icon_name = self.icon or ('pause' if self.label == 'Pause' else self.key)

        if self.kind == 'close_btn' or self.key in ('close_menu', 'close', 'close_solver'):
            cx, cy = draw_rect.center
            r = min(draw_rect.width, draw_rect.height) // 2
            if h_t > 0.05:
                aura = pygame.Surface((r * 2 + 16, r * 2 + 16), pygame.SRCALPHA)
                pygame.draw.circle(aura, (255, 85, 105, int(75 * h_t)), (r + 8, r + 8), r + 6)
                surface.blit(aura, (cx - r - 8, cy - r - 8))
            bg_circle = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            circle_col = (255, 95, 115, int(70 + 130 * h_t)) if h_t > 0 else (255, 255, 255, 50)
            pygame.draw.circle(bg_circle, circle_col, (r, r), r)
            rim_col = (255, 255, 255, 220) if h_t == 0 else (255, 180, 195, 240)
            pygame.draw.circle(bg_circle, rim_col, (r, r), r, 1)
            surface.blit(bg_circle, (cx - r, cy - r))
            x_col = (255, 255, 255) if h_t > 0 else foreground
            draw_vector_icon(surface, 'close', (cx, cy), x_col, size=15)
        elif has_vector_icon and not self.label:
            # Centered icon only
            draw_vector_icon(surface, icon_name, draw_rect.center, foreground, size=15)
        elif has_vector_icon and (self.kind in ('dock_item', 'icon', 'pill', 'primary', 'secondary') or self.key in ('undo', 'restart', 'hint', 'solve', 'view', 'menu', 'theme', 'settings', 'help', 'continue_game')):
            # Centered (icon + gap + label + chevron) group
            is_dock = self.kind == 'dock_item'
            icon_size = 13 if is_dock else 14
            gap = 7
            lbl = font.render(self.label, True, foreground)
            lbl_w, lbl_h = lbl.get_size()

            has_chevron = self.key in ('choose', 'algorithm_menu')
            chev_space = (gap + 8) if has_chevron else 0

            avail_w = draw_rect.width - 16
            if icon_size + gap + lbl_w + chev_space > avail_w:
                lbl_max_w = max(10, avail_w - icon_size - gap - chev_space)
                lbl_text = self.label
                while lbl_text and font.size(lbl_text + '…')[0] > lbl_max_w:
                    lbl_text = lbl_text[:-1]
                lbl = font.render(lbl_text + ('…' if lbl_text != self.label else ''), True, foreground)
                lbl_w = lbl.get_width()

            total_content_w = icon_size + gap + lbl_w + chev_space
            start_x = round(draw_rect.centerx - total_content_w / 2)
            icon_cx = start_x + icon_size // 2
            draw_vector_icon(surface, icon_name, (icon_cx, draw_rect.centery), foreground, size=icon_size)
            lbl_rect = lbl.get_rect(midleft=(start_x + icon_size + gap, draw_rect.centery))
            surface.blit(lbl, lbl_rect)
            if has_chevron:
                ch_x = lbl_rect.right + gap + 4
                ch_y = draw_rect.centery
                pygame.draw.lines(surface, foreground, False, [(ch_x - 4, ch_y - 2), (ch_x, ch_y + 2), (ch_x + 4, ch_y - 2)], 1)
        else:
            # Centered label (with optional chevron)
            has_chevron = self.key in ('choose', 'algorithm_menu')
            lbl = font.render(self.label, True, foreground)
            if has_chevron:
                gap = 6
                total_w = lbl.get_width() + gap + 8
                start_x = round(draw_rect.centerx - total_w / 2)
                lbl_rect = lbl.get_rect(midleft=(start_x, draw_rect.centery))
                surface.blit(lbl, lbl_rect)
                ch_x = lbl_rect.right + gap + 4
                ch_y = draw_rect.centery
                pygame.draw.lines(surface, foreground, False, [(ch_x - 4, ch_y - 2), (ch_x, ch_y + 2), (ch_x + 4, ch_y - 2)], 1)
            else:
                surface.blit(lbl, lbl.get_rect(center=draw_rect.center))

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
        # Curved loop counter-clockwise arrow
        r = hs * 0.8
        arc_rect = pygame.Rect(cx - r, cy - r + 1, 2 * r, 2 * r)
        pygame.draw.arc(surface, color, arc_rect, math.pi * 0.25, math.pi * 1.55, 2)
        tip_x, tip_y = cx - r + 1, cy + 1
        pygame.draw.polygon(surface, color, [
            (tip_x - 3, tip_y + 4),
            (tip_x + 4, tip_y),
            (tip_x - 3, tip_y - 4),
        ])

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

        # Mechanical travel: shift down 2px when pressed
        draw_rect = self.rect.move(0, 2) if pressed else self.rect

        if self.kind == 'primary':
            color = theme.ACCENT_HOVER if hover else theme.ACCENT
            if pressed:
                color = tuple(max(0, c - 24) for c in theme.ACCENT)
            if not self.enabled:
                color = theme.SURFACE
            foreground = theme.INK if self.enabled else theme.DISABLED
        elif self.kind == 'dock_item':
            # Semi-translucent glass pill button inside floating dock
            if pressed:
                color = tuple(min(255, c + 15) for c in theme.PRESSED)
            elif hover:
                color = tuple(min(255, c + 20) for c in theme.HOVER)
            else:
                color = tuple((*theme.SURFACE, 180)) if len(theme.SURFACE) == 4 else theme.SURFACE
            foreground = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)
        else:
            color = theme.PRESSED if pressed else theme.HOVER if hover else theme.SURFACE
            if self.kind == 'quiet' and not hover:
                color = None
            foreground = theme.ACCENT if self.selected else (theme.TEXT if self.enabled else theme.DISABLED)

        # Draw tactile background
        if color:
            radius = draw_rect.height // 2 if self.kind in ('pill', 'dock_item') else 12
            pygame.draw.rect(surface, color, draw_rect, border_radius=radius)

            if self.kind == 'primary' and self.enabled:
                gradient = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                for row in range(draw_rect.height):
                    t = row / max(1, draw_rect.height - 1)
                    shade = tuple(min(255, int(c + (1 - t) * 18 - t * 6)) for c in color[:3])
                    pygame.draw.line(gradient, shade, (0, row), (draw_rect.width, row))
                mask = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
                gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surface.blit(gradient, draw_rect)
            elif self.kind != 'quiet':
                border_color = theme.ACCENT if hover and self.enabled else theme.LINE
                pygame.draw.rect(surface, border_color, draw_rect, 1, border_radius=radius)

        if self.selected and self.kind != 'dock_item':
            pygame.draw.rect(surface, theme.ACCENT, draw_rect, 1, border_radius=12)

        # Draw icon and label
        has_vector_icon = self.icon or self.key in ('undo', 'restart', 'hint', 'play', 'step', 'back', 'stop')
        icon_name = self.icon or self.key

        if has_vector_icon and self.kind in ('dock_item', 'icon'):
            # Draw icon on the left, label on the right
            icon_cx = draw_rect.x + 22
            icon_cy = draw_rect.centery
            draw_vector_icon(surface, icon_name, (icon_cx, icon_cy), foreground, size=16)
            lbl = font.render(self.label, True, foreground)
            lbl_rect = lbl.get_rect(midleft=(icon_cx + 14, draw_rect.centery))
            surface.blit(lbl, lbl_rect)
        else:
            # Centered label
            lbl = font.render(self.label, True, foreground)
            surface.blit(lbl, lbl.get_rect(center=draw_rect.center))

        if self.key in ('choose', 'algorithm_menu'):
            x, y = draw_rect.right - 16, draw_rect.centery
            pygame.draw.lines(surface, foreground, False, [(x - 4, y - 2), (x, y + 2), (x + 4, y - 2)], 1)

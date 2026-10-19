"""Shared text and button styling, without nested frames."""
from dataclasses import dataclass
import pygame
from src.gui.theme import BG, PANEL, TEXT, MUTED, ACCENT
from src.gui import theme


def text(surface, font, value, pos, color=TEXT, max_width=None):
    value = str(value)
    if max_width is not None and font.size(value)[0] > max_width:
        while value and font.size(value + '…')[0] > max_width:
            value = value[:-1]
        value += '…'
    surface.blit(font.render(value, True, color), pos)


@dataclass
class Button:
    key: str
    label: str
    rect: pygame.Rect
    enabled: bool = True
    selected: bool = False
    kind: str = 'secondary'

    def draw(self, surface, font):
        hover = self.enabled and self.rect.collidepoint(pygame.mouse.get_pos())
        pressed = hover and pygame.mouse.get_pressed()[0]
        if self.kind == 'primary':
            color = theme.ACCENT_HOVER if hover else ACCENT
            if pressed: color = (199, 148, 70)
            if not self.enabled: color = theme.SURFACE
            foreground = theme.INK if self.enabled else theme.DISABLED
        else:
            color = theme.PRESSED if pressed else theme.HOVER if hover else theme.SURFACE
            if self.kind == 'quiet' and not hover: color = None
            foreground = ACCENT if self.selected else TEXT if self.enabled else theme.DISABLED
        if color:
            pygame.draw.rect(surface, color, self.rect, border_radius=12)
            if self.kind=='primary' and self.enabled:
                gradient=pygame.Surface(self.rect.size,pygame.SRCALPHA)
                for row in range(self.rect.height):
                    t=row/max(1,self.rect.height-1)
                    shade=tuple(min(255,int(c+(1-t)*17-t*4)) for c in color)
                    pygame.draw.line(gradient,shade,(0,row),(self.rect.width,row))
                mask=pygame.Surface(self.rect.size,pygame.SRCALPHA)
                pygame.draw.rect(mask,(255,255,255,255),mask.get_rect(),border_radius=12)
                gradient.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
                surface.blit(gradient,self.rect)
            elif self.kind!='quiet':
                pygame.draw.rect(surface,theme.LINE,self.rect,1,border_radius=12)
        if self.selected:
            pygame.draw.rect(surface,ACCENT,self.rect,1,border_radius=12)
        label = font.render(self.label, True, foreground)
        surface.blit(label, label.get_rect(center=self.rect.center))
        if self.key in ('choose', 'algorithm_menu'):
            x, y = self.rect.right - 16, self.rect.centery
            pygame.draw.lines(surface, foreground, False, [(x - 4, y - 2), (x, y + 2), (x + 4, y - 2)], 1)

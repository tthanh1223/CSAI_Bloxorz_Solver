"""Shared visual tokens: muted architecture, one amber accent, 8px spacing."""
from functools import lru_cache
from pathlib import Path
import pygame

SPACE = 8
BUTTON_HEIGHT = 40
PANEL_WIDTH = 264
MIN_SIZE = (960, 720)
BG = (237, 181, 176)
PANEL = (255, 246, 237)
SURFACE = (247, 233, 229)
HOVER = (244, 218, 212)
PRESSED = (235, 202, 198)
TEXT = (112, 78, 99)
MUTED = (139, 105, 123)
DISABLED = (183, 158, 168)
LINE = (231, 208, 207)
ACCENT = (235, 151, 99)
ACCENT_HOVER = (247, 170, 118)
INK = (255, 251, 240)
FLOOR = (218, 226, 213)
BLOCK = (199, 174, 132)


@lru_cache(maxsize=6)
def _font(level='body', large=False):
    size = {'body': 17, 'heading': 22, 'display': 32}[level] + (2 if large else 0)
    # Segoe UI includes Vietnamese; DejaVu Sans is the Linux fallback.
    regular = Path('C:/Windows/Fonts/segoeui.ttf')
    path = str(regular) if regular.exists() else pygame.font.match_font('dejavusans,arial')
    return pygame.font.Font(path, size)


def font(level='body', large=False):
    result = _font(level, large)
    try:
        result.size('M')
    except pygame.error:
        _font.cache_clear()
        result = _font(level, large)
    return result

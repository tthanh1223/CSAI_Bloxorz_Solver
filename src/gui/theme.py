"""Shared visual tokens: muted architecture, one amber accent, 8px spacing."""
from functools import lru_cache
from pathlib import Path
import pygame

SPACE = 8
BUTTON_HEIGHT = 40
PANEL_WIDTH = 264
MIN_SIZE = (900, 560)
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
BLOCK = (242, 177, 132)

FONTS_DIR = Path(__file__).resolve().parents[2] / 'assets' / 'fonts'


@lru_cache(maxsize=16)
def _font(level='body', large=False):
    sizes = {
        'caption': 13,
        'body': 16,
        'heading': 22,
        'display': 30,
        'mono': 15,
        'mono_lg': 22,
    }
    size = sizes.get(level, 16) + (2 if large else 0)

    # 1. Try modern geometric & tabular font assets
    font_file = None
    if level == 'display':
        cand = FONTS_DIR / 'Outfit-Bold.ttf'
        if cand.exists():
            font_file = cand
    elif level == 'heading':
        cand = FONTS_DIR / 'Outfit-Bold.ttf'
        if not cand.exists():
            cand = FONTS_DIR / 'Outfit-Medium.ttf'
        if cand.exists():
            font_file = cand
    elif level in ('mono', 'mono_lg'):
        cand = FONTS_DIR / 'JetBrainsMono-Bold.ttf'
        if not cand.exists():
            cand = FONTS_DIR / 'JetBrainsMono-Regular.ttf'
        if cand.exists():
            font_file = cand
    else:  # 'body', 'caption'
        cand = FONTS_DIR / 'Outfit-Medium.ttf'
        if not cand.exists():
            cand = FONTS_DIR / 'Outfit-Regular.ttf'
        if not cand.exists():
            cand = FONTS_DIR / 'SpaceGrotesk-Medium.ttf'
        if cand.exists():
            font_file = cand

    if font_file is not None:
        try:
            return pygame.font.Font(str(font_file), size)
        except Exception:
            pass

    # 2. Graceful OS fallbacks
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


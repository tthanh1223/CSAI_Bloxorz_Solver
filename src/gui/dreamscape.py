"""Cached environment backdrop; gameplay is always rendered separately."""
from functools import lru_cache
from pathlib import Path
import math
import random
import pygame

ASSET = Path(__file__).resolve().parents[2] / 'assets' / 'dream_city_background.png'


@lru_cache(maxsize=3)
def background(size, style='dream', cells=(), stage_index=0):
    if style == 'blueprint':
        return blueprint(size, cells, stage_index)
    asset = ASSET.with_name('forest_ruins_background.png') if style == 'forest' else ASSET
    if asset.exists():
        image = pygame.image.load(str(asset))
        scale = max(size[0] / image.get_width(), size[1] / image.get_height())
        image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
        result = pygame.Surface(size)
        result.blit(image, ((size[0] - image.get_width()) // 2, (size[1] - image.get_height()) // 2))
        return result
    result = pygame.Surface(size)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        pygame.draw.line(result, tuple(round(a + (b - a) * t) for a, b in zip((251, 209, 191), (214, 155, 172))), (0, y), (size[0], y))
    return result


def blueprint(size, cells, stage_index):
    """Paper grain, real isometric drafting grid, compass cube badge, and floor plan."""
    w, h = size
    grain = pygame.Surface((256, 256))
    rng = random.Random(72)
    for y in range(256):
        for x in range(256):
            delta = rng.randrange(-4, 5)
            # Deep matte navy paper `#0E1E2E` base
            grain.set_at((x, y), (14 + delta, 30 + delta, 46 + delta))
    result = pygame.Surface(size)
    for y in range(0, h, 256):
        for x in range(0, w, 256):
            result.blit(grain, (x, y))

    guides = pygame.Surface(size, pygame.SRCALPHA)
    boundary = w - 300
    guides.set_clip((0, 70, boundary, h - 80))

    # Real technical isometric drafting lines (30-degree angles)
    cyan_line = (56, 178, 172, 38)
    for origin in range(-h * 2, w + h * 2, 96):
        for sign in (-1, 1):
            start = (origin, 70)
            end = (origin + sign * (h) * 2, h)
            for segment in range(0, 48, 2):
                a = segment / 48
                b = (segment + 1) / 48
                pygame.draw.line(guides, cyan_line,
                                 (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                                 (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b))
    guides.set_clip(None)

    # Drafting border marks and crosshairs
    cyan_bright = (152, 210, 224, 110)
    pygame.draw.line(guides, cyan_bright, (boundary, 70), (boundary, h - 50))
    for x, y in ((54, 120), (54, h - 140), (boundary, 70), (boundary, h - 50)):
        pygame.draw.line(guides, cyan_bright, (x - 12, y), (x + 12, y), 1)
        pygame.draw.line(guides, cyan_bright, (x, y - 12), (x, y + 12), 1)

    # Upper right: Isometric Drafting Compass Badge (from Reference Image 1)
    badge_cx, badge_cy = boundary - 120, 130
    if badge_cx > 380:
        badge_r = 30
        pygame.draw.circle(guides, (72, 140, 164, 130), (badge_cx, badge_cy), badge_r, 1)
        # Crosshairs through circle
        pygame.draw.line(guides, (72, 140, 164, 90), (badge_cx - badge_r - 14, badge_cy), (badge_cx + badge_r + 14, badge_cy), 1)
        pygame.draw.line(guides, (72, 140, 164, 90), (badge_cx, badge_cy - badge_r - 14), (badge_cx, badge_cy + badge_r + 14), 1)
        # Wireframe isometric cube inside
        cr = 13
        p_center = (badge_cx, badge_cy)
        p_top = (badge_cx, badge_cy - cr)
        p_bottom = (badge_cx, badge_cy + cr)
        dx = cr * math.cos(math.pi / 6)
        dy = cr * math.sin(math.pi / 6)
        p_tl = (badge_cx - dx, badge_cy - dy)
        p_tr = (badge_cx + dx, badge_cy - dy)
        p_bl = (badge_cx - dx, badge_cy + dy)
        p_br = (badge_cx + dx, badge_cy + dy)
        # Outer hexagon
        cube_color = (168, 222, 235, 180)
        pygame.draw.lines(guides, cube_color, True, [p_top, p_tr, p_br, p_bottom, p_bl, p_tl], 1)
        # Inner Y
        pygame.draw.line(guides, cube_color, p_center, p_top, 1)
        pygame.draw.line(guides, cube_color, p_center, p_bl, 1)
        pygame.draw.line(guides, cube_color, p_center, p_br, 1)

    result.blit(guides, (0, 0))

    font_path = Path(__file__).resolve().parents[2] / 'assets' / 'fonts' / 'SpaceGrotesk-Medium.ttf'
    font = pygame.font.Font(str(font_path) if font_path.exists() else pygame.font.match_font('segoeui'), 11)

    def label(value, lx, ly):
        result.blit(font.render(value, True, (134, 175, 192)), (lx, ly))

    if badge_cx > 380:
        label('ISOMETRIC', badge_cx + 42, badge_cy - 10)
        label('VIEW', badge_cx + 42, badge_cy + 4)

    label('ARCHITECTURAL MODEL', 72, 120)
    label('SCALE  1 : 1', 72, 138)

    if cells:
        rmin = min(r for r, c in cells)
        cmin = min(c for r, c in cells)
        span = max(max(r for r, c in cells) - rmin + 1, max(c for r, c in cells) - cmin + 1)
        unit = min(11, 88 // max(1, span))
        grid_top = 162
        for r, c in cells:
            pygame.draw.rect(result, (72, 140, 168), (72 + (c - cmin) * unit, grid_top + (r - rmin) * unit, unit, unit), 1)
        grid_bottom = grid_top + (max(r for r, c in cells) - rmin + 1) * unit
        label(f'STAGE  {stage_index + 1:02}  (REFERENCE)', 72, grid_bottom + 8)
        label('FLOOR PLAN', 72, grid_bottom + 22)

    return result

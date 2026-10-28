"""Phông nền môi trường có cache; phần chơi luôn được vẽ riêng."""
from functools import lru_cache
import math
import random
import pygame
from src.gui.theme import ASSETS_DIR, FONTS_DIR


def _cover(result, path):
    image = pygame.image.load(str(path))
    w, h = result.get_size()
    scale = max(w / image.get_width(), h / image.get_height())
    image = pygame.transform.smoothscale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    result.blit(image, ((w - image.get_width()) // 2, (h - image.get_height()) // 2))


@lru_cache(maxsize=3)
def background(size, style='dream', cells=(), stage_index=0):
    if style == 'blueprint':
        return blueprint(size, cells, stage_index)
    if style == 'forest':
        return forest_ruins(size, stage_index)
    new_asset = ASSETS_DIR / 'wide_dreamy_fantasy_landscape_scene_pastel_pink.png'
    asset = new_asset if new_asset.exists() else ASSETS_DIR / 'dream_city_background.png'
    if asset.exists():
        result = pygame.Surface(size)
        _cover(result, asset)
        return result
    result = pygame.Surface(size)
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        pygame.draw.line(result, tuple(round(a + (b - a) * t) for a, b in zip((251, 209, 191), (214, 155, 172))), (0, y), (size[0], y))
    return result


def forest_ruins(size, stage_index):
    """Phông nền tàn tích đá phủ rêu với tia nắng xuyên tán lá và tấm bản vẽ mặt bằng."""
    w, h = size
    result = pygame.Surface(size)
    asset = ASSETS_DIR / 'forest_ruins_background.png'
    if asset.exists():
        _cover(result, asset)
    else:
        # Dải màu ngọc lục bảo đậm của tàn tích cổ
        for y in range(h):
            t = y / max(1, h - 1)
            col = (round(12 + 10 * t), round(26 + 18 * t), round(20 + 14 * t))
            pygame.draw.line(result, col, (0, y), (w, y))

    # Tia nắng thể tích xuyên qua tán lá
    rays = pygame.Surface(size, pygame.SRCALPHA)
    for i, (rx, rw, ang) in enumerate(((w * 0.18, 90, 0.45), (w * 0.46, 120, 0.38), (w * 0.74, 85, 0.42))):
        pts = [
            (rx, 0),
            (rx + rw, 0),
            (rx + rw + h * ang, h),
            (rx + h * ang, h)
        ]
        alpha = 18 + (i % 2) * 8
        pygame.draw.polygon(rays, (255, 245, 200, alpha), pts)
    result.blit(rays, (0, 0))

    # Đom đóm / phấn hoa phát sáng trong rừng
    motes = pygame.Surface(size, pygame.SRCALPHA)
    rng = random.Random(1337 + stage_index)
    for _ in range(48):
        mx = rng.randint(20, w - 20)
        my = rng.randint(40, h - 40)
        mr = rng.choice((1, 2, 2, 3))
        ma = rng.randint(80, 210)
        col = (255, rng.randint(215, 245), rng.randint(120, 180), ma)
        pygame.draw.circle(motes, col, (mx, my), mr)
        if mr > 1:
            pygame.draw.circle(motes, (255, 255, 200, ma // 3), (mx, my), mr + 2)
    result.blit(motes, (0, 0))
    return result


def blueprint(size, cells, stage_index):
    """Vân giấy, lưới vẽ kỹ thuật isometric thật, huy hiệu la bàn hình khối và mặt bằng phủ toàn màn hình."""
    w, h = size
    grain = pygame.Surface((256, 256))
    rng = random.Random(72)
    for y in range(256):
        for x in range(256):
            delta = rng.randrange(-4, 5)
            # Nền giấy xanh navy mờ `#0E1E2E`
            grain.set_at((x, y), (14 + delta, 30 + delta, 46 + delta))
    result = pygame.Surface(size)
    for y in range(0, h, 256):
        for x in range(0, w, 256):
            result.blit(grain, (x, y))

    guides = pygame.Surface(size, pygame.SRCALPHA)
    boundary = w - 48
    guides.set_clip((0, 70, boundary, h - 80))

    # Đường vẽ kỹ thuật isometric thật (góc 30 độ)
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

    # Dấu viền bản vẽ và chữ thập ngắm
    cyan_bright = (152, 210, 224, 110)
    pygame.draw.line(guides, cyan_bright, (boundary, 70), (boundary, h - 50))
    for x, y in ((54, 120), (54, h - 140), (boundary, 70), (boundary, h - 50)):
        pygame.draw.line(guides, cyan_bright, (x - 12, y), (x + 12, y), 1)
        pygame.draw.line(guides, cyan_bright, (x, y - 12), (x, y + 12), 1)

    # Góc trên phải: huy hiệu la bàn vẽ kỹ thuật isometric (theo ảnh tham khảo 1)
    badge_cx, badge_cy = boundary - 120, 130
    if badge_cx > 380:
        badge_r = 30
        pygame.draw.circle(guides, (72, 140, 164, 130), (badge_cx, badge_cy), badge_r, 1)
        # Chữ thập xuyên qua vòng tròn
        pygame.draw.line(guides, (72, 140, 164, 90), (badge_cx - badge_r - 14, badge_cy), (badge_cx + badge_r + 14, badge_cy), 1)
        pygame.draw.line(guides, (72, 140, 164, 90), (badge_cx, badge_cy - badge_r - 14), (badge_cx, badge_cy + badge_r + 14), 1)
        # Khối lập phương khung dây bên trong
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
        # Lục giác bên ngoài
        cube_color = (168, 222, 235, 180)
        pygame.draw.lines(guides, cube_color, True, [p_top, p_tr, p_br, p_bottom, p_bl, p_tl], 1)
        # Chữ Y bên trong
        pygame.draw.line(guides, cube_color, p_center, p_top, 1)
        pygame.draw.line(guides, cube_color, p_center, p_bl, 1)
        pygame.draw.line(guides, cube_color, p_center, p_br, 1)

    result.blit(guides, (0, 0))

    font_path = FONTS_DIR / 'SpaceGrotesk-Medium.ttf'
    font = pygame.font.Font(str(font_path) if font_path.exists() else pygame.font.match_font('segoeui'), 11)

    def label(value, lx, ly):
        result.blit(font.render(value, True, (134, 175, 192)), (lx, ly))

    if badge_cx > 380:
        label('ISOMETRIC', badge_cx + 42, badge_cy - 10)
        label('VIEW', badge_cx + 42, badge_cy + 4)

    base_x = 48
    base_y = max(120, h - 185)
    label('ARCHITECTURAL MODEL', base_x, base_y)
    label('SCALE  1 : 1', base_x, base_y + 16)

    if cells:
        rmin = min(r for r, c in cells)
        cmin = min(c for r, c in cells)
        span = max(max(r for r, c in cells) - rmin + 1, max(c for r, c in cells) - cmin + 1)
        unit = min(9, 72 // max(1, span))
        grid_top = base_y + 36
        for r, c in cells:
            pygame.draw.rect(result, (72, 140, 168), (base_x + (c - cmin) * unit, grid_top + (r - rmin) * unit, unit, unit), 1)
        grid_bottom = grid_top + (max(r for r, c in cells) - rmin + 1) * unit
        label(f'STAGE  {stage_index + 1:02}  (REFERENCE)', base_x, grid_bottom + 8)
        label('FLOOR PLAN', base_x, grid_bottom + 22)

    return result

"""Ba phong cách hình ảnh trên cùng một renderer Pygame có cache."""
import pygame
from src.gui import theme as T

NAMES = {'dream': 'Dream City', 'forest': 'Forest Ruins', 'blueprint': 'Paper Blueprint'}
KEYS = ('BG', 'PANEL', 'SURFACE', 'HOVER', 'PRESSED', 'TEXT', 'MUTED', 'DISABLED', 'LINE', 'ACCENT', 'ACCENT_HOVER',
        'INK', 'FLOOR', 'BLOCK')
DREAM = (
    (243, 196, 192),  # BG
    (255, 248, 244),  # PANEL
    (250, 237, 233),  # SURFACE
    (253, 238, 236),  # HOVER (kem pastel nhạt)
    (246, 218, 224),  # PRESSED
    (86, 56, 74),     # TEXT
    (132, 98, 116),   # MUTED
    (186, 160, 172),  # DISABLED
    (235, 212, 210),  # LINE
    (242, 166, 192),  # ACCENT (hồng pastel dịu)
    (250, 195, 215),  # ACCENT_HOVER (hồng hoa pastel nhạt)
    (255, 252, 248),  # INK
    (226, 232, 224),  # FLOOR (nền terrazzo trắng ngà sáng, hợp với màn chính)
    (242, 146, 176),  # BLOCK (vàng hồng pastel rực)
)

BLUEPRINT = (
    (14, 30, 46),     # BG (giấy vẽ xanh navy mờ #0E1E2E)
    (18, 42, 64),     # PANEL
    (26, 54, 78),     # SURFACE
    (38, 72, 102),    # HOVER
    (46, 84, 116),    # PRESSED
    (248, 242, 230),  # TEXT (trắng kỹ thuật sắc nét)
    (152, 185, 200),  # MUTED
    (82, 112, 132),   # DISABLED
    (48, 86, 114),    # LINE (lưới vẽ màu lơ)
    (216, 88, 32),    # ACCENT (đất nung kiến trúc rực #D85820)
    (238, 110, 52),   # ACCENT_HOVER
    (255, 255, 255),  # INK
    (248, 244, 232),  # FLOOR (giấy can kiến trúc sáng, sắc nét)
    (226, 82, 28),    # BLOCK (cam đất nung kiến trúc rực)
)

FOREST = (
    (34, 47, 39),     # BG
    (19, 31, 25),     # PANEL
    (40, 54, 44),     # SURFACE
    (55, 70, 48),     # HOVER
    (63, 79, 52),     # PRESSED
    (239, 235, 205),  # TEXT
    (181, 191, 160),  # MUTED
    (113, 129, 107),  # DISABLED
    (75, 91, 72),     # LINE
    (220, 186, 91),   # ACCENT
    (240, 208, 111),  # ACCENT_HOVER
    (27, 37, 25),     # INK
    (164, 170, 146),  # FLOOR
    (222, 173, 62),   # BLOCK
)

PALETTES = {
    'dream': DREAM,
    'blueprint': BLUEPRINT,
    'forest': FOREST,
}


def _forest_stone_texture():
    atlas = T.ASSETS_DIR / 'forest_materials.png'
    if not atlas.exists():
        return None
    image = pygame.image.load(str(atlas))
    half = image.get_width() // 2
    texture = pygame.transform.smoothscale(image.subsurface((0, 0, half, image.get_height())), (192, 192))
    texture.fill((224, 239, 244), special_flags=pygame.BLEND_RGB_MULT)
    return texture


def apply_theme(app, name):
    if name not in PALETTES:
        raise ValueError('Unknown theme')
    for key, color in zip(KEYS, PALETTES[name]):
        setattr(T, key, color)
    app.visual_style = name
    app.theme_name = name
    app._presentation_cache = None
    app._scene_cache = None
    app.renderer.set_style(name, _forest_stone_texture() if name == 'forest' else None)


def cycle_theme(app):
    names = tuple(NAMES)
    current = getattr(app, 'theme_name', 'dream')
    apply_theme(app, names[(names.index(current) + 1) % len(names)])

"""Three art directions on the same cached Pygame renderer."""
from pathlib import Path
import pygame
from src.gui import theme as T

NAMES = {'dream': 'Dream City', 'forest': 'Forest Ruins', 'blueprint': 'Paper Blueprint'}
KEYS=('BG','PANEL','SURFACE','HOVER','PRESSED','TEXT','MUTED','DISABLED','LINE','ACCENT','ACCENT_HOVER','INK','FLOOR','BLOCK')
DREAM = (
    (243, 196, 192),  # BG
    (255, 248, 244),  # PANEL
    (250, 237, 233),  # SURFACE
    (253, 238, 236),  # HOVER (delicate creamy pastel)
    (246, 218, 224),  # PRESSED
    (86, 56, 74),     # TEXT
    (132, 98, 116),   # MUTED
    (186, 160, 172),  # DISABLED
    (235, 212, 210),  # LINE
    (242, 166, 192),  # ACCENT (soft dreamy pastel rose)
    (250, 195, 215),  # ACCENT_HOVER (light pastel blossom)
    (255, 252, 248),  # INK
    (226, 232, 224),  # FLOOR (luminous alabaster terrazzo base matching main)
    (242, 146, 176),  # BLOCK (radiant pastel rose gold)
)

BLUEPRINT = (
    (14, 30, 46),     # BG (matte navy drafting paper #0E1E2E)
    (18, 42, 64),     # PANEL
    (26, 54, 78),     # SURFACE
    (38, 72, 102),    # HOVER
    (46, 84, 116),    # PRESSED
    (248, 242, 230),  # TEXT (crisp technical white)
    (152, 185, 200),  # MUTED
    (82, 112, 132),   # DISABLED
    (48, 86, 114),    # LINE (cyan drafting grid)
    (216, 88, 32),    # ACCENT (vibrant architectural terracotta #D85820)
    (238, 110, 52),   # ACCENT_HOVER
    (255, 255, 255),  # INK
    (248, 244, 232),  # FLOOR (crisp luminous architectural vellum cardstock)
    (226, 82, 28),    # BLOCK (vibrant architectural terracotta orange)
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


def apply_theme(app,name):
    if name not in PALETTES:raise ValueError('Unknown theme')
    if getattr(app,'visual_style','')=='forest_gl':return
    from src.gui import ui
    for key,color in zip(KEYS,PALETTES[name]):
        setattr(T,key,color)
        if hasattr(ui,key):setattr(ui,key,color)
    app.visual_style=name
    app.theme_name=name
    app._presentation_cache=None
    app._scene_cache=None
    renderer=app.renderer
    renderer.style=name
    renderer.FLOOR=T.FLOOR;renderer.BLOCK=T.BLOCK;renderer.BACKGROUND=T.BG
    renderer._static_key=None;renderer._frame_key=None
    renderer.material_cache.clear();renderer._block_textures.clear()
    renderer.stone_texture=renderer.gold_texture=None
    atlas=Path(__file__).resolve().parents[2]/'assets'/'forest_materials.png'
    if name=='forest' and atlas.exists():
        image=pygame.image.load(str(atlas))
        half=image.get_width()//2
        renderer.stone_texture=pygame.transform.smoothscale(image.subsurface((0,0,half,image.get_height())),(192,192))
        renderer.stone_texture.fill((224,239,244),special_flags=pygame.BLEND_RGB_MULT)
        renderer.gold_texture=pygame.transform.smoothscale(image.subsurface((half,0,half,image.get_height())),(128,128))


def cycle_theme(app):
    names=tuple(NAMES)
    current=getattr(app,'theme_name','dream')
    apply_theme(app,names[(names.index(current)+1)%len(names)])

"""Three art directions on the same cached Pygame renderer."""
from pathlib import Path
import pygame
from src.gui import theme as T

NAMES={'dream':'Dream City','blueprint':'Paper Blueprint','forest':'Forest Ruins'}
KEYS=('BG','PANEL','SURFACE','HOVER','PRESSED','TEXT','MUTED','DISABLED','LINE','ACCENT','ACCENT_HOVER','INK','FLOOR','BLOCK')
DREAM = (
    (243, 196, 192),  # BG
    (255, 248, 244),  # PANEL
    (250, 237, 233),  # SURFACE
    (246, 222, 216),  # HOVER
    (238, 206, 201),  # PRESSED
    (86, 56, 74),     # TEXT
    (132, 98, 116),   # MUTED
    (186, 160, 172),  # DISABLED
    (235, 212, 210),  # LINE
    (236, 138, 92),   # ACCENT (warm coral terracotta)
    (248, 158, 114),  # ACCENT_HOVER
    (255, 252, 248),  # INK
    (210, 229, 225),  # FLOOR (celadon mint terrazzo #D2E5E1)
    (232, 162, 120),  # BLOCK (warm sunlit terracotta #E8A278)
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
    (234, 228, 211),  # FLOOR (warm off-white cardstock #EAE4D3)
    (216, 88, 32),    # BLOCK (vibrant terracotta orange #D85820)
)

FOREST = (
    (24, 36, 28),     # BG (deep emerald jungle canopy)
    (18, 28, 22),     # PANEL
    (34, 48, 38),     # SURFACE
    (48, 66, 52),     # HOVER
    (58, 78, 62),     # PRESSED
    (242, 238, 214),  # TEXT (ivory rune #EFEBD0)
    (168, 184, 152),  # MUTED
    (96, 114, 90),    # DISABLED
    (58, 78, 60),     # LINE
    (201, 164, 59),   # ACCENT (antique relic gold #C9A43B)
    (226, 188, 82),   # ACCENT_HOVER
    (18, 28, 20),     # INK
    (106, 115, 99),   # FLOOR (chiseled limestone slab #6A7363)
    (201, 164, 59),   # BLOCK (weathered antique gold relic #C9A43B)
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

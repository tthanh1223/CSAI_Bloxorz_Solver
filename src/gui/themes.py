"""Three art directions on the same cached Pygame renderer."""
from pathlib import Path
import pygame
from src.gui import theme as T

NAMES={'dream':'Dream City','blueprint':'Paper Blueprint','forest':'Forest Ruins'}
KEYS=('BG','PANEL','SURFACE','HOVER','PRESSED','TEXT','MUTED','DISABLED','LINE','ACCENT','ACCENT_HOVER','INK','FLOOR','BLOCK')
DREAM=tuple(getattr(T,key) for key in KEYS)
PALETTES={
 'dream':DREAM,
 'blueprint':((10,35,53),(13,38,55),(24,49,66),(35,65,81),(40,70,85),(248,237,216),(161,183,190),(107,133,148),(69,99,118),(246,175,54),(255,192,75),(15,36,48),(234,221,196),(205,181,137)),
 'forest':((34,47,39),(19,31,25),(40,54,44),(55,70,48),(63,79,52),(239,235,205),(181,191,160),(113,129,107),(75,91,72),(220,186,91),(240,208,111),(27,37,25),(164,170,146),(222,173,62))}


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

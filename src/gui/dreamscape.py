"""Cached environment backdrop; gameplay is always rendered separately."""
from functools import lru_cache
from pathlib import Path
import random
import pygame

ASSET=Path(__file__).resolve().parents[2]/'assets'/'dream_city_background.png'


@lru_cache(maxsize=3)
def background(size,style='dream',cells=(),stage_index=0):
    if style=='blueprint':return blueprint(size,cells,stage_index)
    asset=ASSET.with_name('forest_ruins_background.png') if style=='forest' else ASSET
    if asset.exists():
        image=pygame.image.load(str(asset))
        scale=max(size[0]/image.get_width(),size[1]/image.get_height())
        image=pygame.transform.smoothscale(image,(round(image.get_width()*scale),round(image.get_height()*scale)))
        result=pygame.Surface(size)
        result.blit(image,((size[0]-image.get_width())//2,(size[1]-image.get_height())//2))
        return result
    result=pygame.Surface(size)
    for y in range(size[1]):
        t=y/max(1,size[1]-1)
        pygame.draw.line(result,tuple(round(a+(b-a)*t) for a,b in zip((251,209,191),(214,155,172))),(0,y),(size[0],y))
    return result


def blueprint(size,cells,stage_index):
    """Paper grain, real isometric guide axes and a top-view of the current map."""
    w,h=size
    grain=pygame.Surface((256,256))
    rng=random.Random(72)
    for y in range(256):
        for x in range(256):
            delta=rng.randrange(-4,5)
            grain.set_at((x,y),(12+delta,38+delta,57+delta))
    result=pygame.Surface(size)
    for y in range(0,h,256):
        for x in range(0,w,256):result.blit(grain,(x,y))
    guides=pygame.Surface(size,pygame.SRCALPHA)
    boundary=w-320
    guides.set_clip((0,90,boundary,h-140))
    for origin in range(-h,w+h,144):
        for sign in (-1,1):
            start=(origin,112);end=(origin+sign*(h-200)*2,h-88)
            for segment in range(0,40,2):
                a=segment/40;b=(segment+1)/40
                pygame.draw.line(guides,(164,193,198,36),
                                 (start[0]+(end[0]-start[0])*a,start[1]+(end[1]-start[1])*a),
                                 (start[0]+(end[0]-start[0])*b,start[1]+(end[1]-start[1])*b))
    guides.set_clip(None)
    pygame.draw.line(guides,(215,225,214,95),(boundary,90),(boundary,h-64))
    for x,y in ((54,150),(54,h-152),(boundary,90),(boundary,h-64)):
        pygame.draw.line(guides,(215,225,214,130),(x-10,y),(x+10,y))
        pygame.draw.line(guides,(215,225,214,130),(x,y-10),(x,y+10))
    result.blit(guides,(0,0))
    font=pygame.font.Font(pygame.font.match_font('segoeui'),12)
    def label(value,x,y):result.blit(font.render(value,True,(134,164,177)),(x,y))
    label('P A P E R   M O D E L',72,155)
    label('S C A L E   1 : 1',72,178)
    if cells:
        rmin=min(r for r,c in cells);cmin=min(c for r,c in cells)
        span=max(max(r for r,c in cells)-rmin+1,max(c for r,c in cells)-cmin+1)
        unit=min(13,130/span)
        for r,c in cells:
            pygame.draw.rect(result,(95,131,150),(54+(c-cmin)*unit,h-270+(r-rmin)*unit,unit,unit),1)
        label(f'S T A G E   {stage_index+1:02}',54,h-166)
        label('T O P   V I E W',54,h-145)
    return result

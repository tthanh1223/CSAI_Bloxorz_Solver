"""Index actual GUI screenshots; source files stay at native resolution."""
from pathlib import Path
import pygame


def main():
    root=Path(__file__).resolve().parents[1]
    folder=root/'docs'/'screenshots'
    pygame.font.init()
    font=pygame.font.Font(None,24)
    sheet=pygame.Surface((1770,1296));sheet.fill((32,33,36))
    names=('01_play','02_searching','03_solution','04_replay','05_settings','06_compact','07_stage_picker','08_algorithm_menu','09_help')
    for i,name in enumerate(names):
        x,y=(i%3)*590,(i//3)*432
        source=pygame.image.load(str(folder/f'{name}.png'))
        ratio=min(590/source.get_width(),400/source.get_height())
        size=(round(source.get_width()*ratio),round(source.get_height()*ratio))
        sheet.blit(font.render(name.replace('_',' '),True,(242,236,220)),(x+12,y+6))
        sheet.blit(pygame.transform.smoothscale(source,size),(x+(590-size[0])//2,y+32+(400-size[1])//2))
    pygame.image.save(sheet,str(folder/'dream_interactions_charcoal.png'))


if __name__=='__main__':main()

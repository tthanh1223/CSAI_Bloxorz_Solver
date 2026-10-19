"""Five isolated, procedural art-direction studies. Main GUI is never modified.
python scripts/preview_concepts.py --all
python scripts/preview_concepts.py --concept 2 --show
"""
from pathlib import Path
import sys, argparse, random, math, json
import pygame
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.engine.loader import load_stage, TileType
from src.gui.renderer3d import cuboid, FACES

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'concepts'
SIZE = (1180, 800)
# Identical projection, map, tile thickness, block dimensions and placement.
ORIGIN = (352, 262)
TILE = 92
CONCEPTS = [
 dict(slug='01_quiet_courtyard', name='Quiet Courtyard', subtitle='A study in stillness', bg=(237,232,219),
      floor=(155,174,155), side=(81,111,103), block=(185,145,73), ink=(49,64,57), muted=(111,121,106),
      panel=(237,232,219), accent=(106,126,104), title='georgia.ttf', body='segoeui.ttf'),
 dict(slug='02_forest_ruins', name='Forest Ruins', subtitle='Follow the forgotten path', bg=(30,49,46),
      floor=(126,143,132), side=(59,85,72), block=(185,157,81), ink=(226,229,208), muted=(157,175,157),
      panel=(26,44,40), accent=(185,157,81), title='georgia.ttf', body='segoeui.ttf'),
 dict(slug='03_wooden_play', name='Wooden Play', subtitle='Made to be moved', bg=(220,194,153),
      floor=(194,155,102), side=(103,69,46), block=(174,78,55), ink=(75,50,37), muted=(126,98,71),
      panel=(245,232,207), accent=(174,78,55), title='trebuc.ttf', body='trebuc.ttf'),
 dict(slug='04_dream_city', name='Dream City', subtitle='Somewhere between here and a dream', bg=(228,198,202),
      floor=(175,210,196), side=(128,153,163), block=(237,176,132), ink=(78,70,101), muted=(130,106,132),
      panel=(241,221,222), accent=(134,110,154), title='GOTHIC.TTF', body='segoeui.ttf'),
 dict(slug='05_paper_blueprint', name='Paper Blueprint', subtitle='An exercise in balance', bg=(30,59,79),
      floor=(236,230,209), side=(160,176,178), block=(206,110,65), ink=(232,231,213), muted=(149,175,187),
      panel=(33,65,85), accent=(206,110,65), title='consola.ttf', body='consola.ttf')]


def font(file, size):
    path=Path('C:/Windows/Fonts') / file
    return pygame.font.Font(str(path) if path.exists() else pygame.font.match_font('dejavusans'), size)


def blend(a,b,t): return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))
def proj(p):
    r,c,z=p
    return (ORIGIN[0]+(c-r)*TILE/2, ORIGIN[1]+(r+c)*TILE/4-z*TILE*.6)


def polygon(s,color,pts):
    pygame.draw.polygon(s,color,pts)
    pygame.draw.aalines(s,color,True,pts)


def soft(s,layer,amount=10):
    small=pygame.transform.smoothscale(layer.premul_alpha(),(max(1,SIZE[0]//amount),max(1,SIZE[1]//amount)))
    s.blit(pygame.transform.smoothscale(small,SIZE),(0,0),special_flags=pygame.BLEND_PREMULTIPLIED)


def background(s,c,n,rng):
    s.fill(c['bg'])
    layer=pygame.Surface(SIZE,pygame.SRCALPHA)
    if n==0:
        polygon(layer,(255,249,224,90),[(0,110),(290,110),(880,680),(600,680)])
        polygon(layer,(255,249,224,60),[(330,110),(410,110),(980,680),(900,680)])
        soft(s,layer,24)
        pygame.draw.line(s,(217,214,199),(40,654),(824,654))
    elif n==1:
        # Receding trunks, ruin fragments and canopy; all outside the map silhouette.
        for depth in range(3):
            forest=pygame.Surface(SIZE,pygame.SRCALPHA)
            for i in range(9):
                x=rng.randrange(12,875)
                color=(*blend(c['bg'],(100,128,108),.16-depth*.035),150)
                lean=rng.randrange(-60,60)
                polygon(forest,color,[(x-12,680),(x+12,680),(x+lean+3,90),(x+lean-3,90)])
                for branch in range(3):
                    y=rng.randrange(160,450)
                    pygame.draw.line(forest,color,(x,y),(x+rng.choice((-90,90)),y-110),4)
                for j in range(3):
                    pygame.draw.ellipse(forest,(*color[:3],65),(x-100,70+j*32,200,85))
            soft(s,forest,12-depth*3)
        # Fog veils keep background low contrast.
        for y in range(100,700):
            alpha=int(25+38*math.sin((y-100)/600*math.pi))
            pygame.draw.line(layer,(97,132,116,alpha),(0,y),(867,y))
        soft(s,layer,20)
        for x,y in [(70,400),(778,290),(120,590)]:
            pygame.draw.rect(s,(48,73,62),(x,y,32,76))
            pygame.draw.rect(s,(68,90,75),(x-4,y,40,10))
        rays=pygame.Surface(SIZE,pygame.SRCALPHA)
        for x in (40,180,380): polygon(rays,(208,218,159,14),[(x,96),(x+28,96),(x+340,680),(x+230,680)])
        soft(s,rays,22)
    elif n==2:
        for y in range(84,704):
            tint=blend(c['bg'],(161,112,65),rng.random()*.08)
            pygame.draw.line(s,tint,(0,y),(875,y))
        for y in (190,382,574):
            pygame.draw.line(s,(191,159,118),(0,y),(874,y),2)
            pygame.draw.line(s,(232,210,177),(0,y+2),(874,y+2))
        for _ in range(100):
            y=rng.randint(85,700); x=rng.randint(0,800)
            pts=[(x+i*12,y+math.sin(i*.3)*rng.uniform(1,3)) for i in range(18)]
            pygame.draw.aalines(s,(207,178,134),False,pts)
    elif n==3:
        # Decorative architecture is deliberately outside the playable island.
        for x,y,scale in [(74,292,1),(742,162,.8)]:
            rect=pygame.Rect(x,y,64*scale,146*scale)
            pygame.draw.rect(s,(195,166,187),rect,border_top_left_radius=int(32*scale),border_top_right_radius=int(32*scale))
            inner=rect.inflate(-22*scale,-22*scale); inner.bottom=rect.bottom
            pygame.draw.rect(s,c['bg'],inner,border_top_left_radius=int(22*scale),border_top_right_radius=int(22*scale))
            pygame.draw.line(s,(243,216,219),rect.topleft,(rect.left,rect.bottom),2)
        for i in range(7):
            pygame.draw.rect(s,(194+i*3,169+i*2,191+i*2),(710+i*12,605-i*9,60,12+i*9))
        for x,y in [(50,548),(654,114)]:
            cloud=pygame.Surface(SIZE,pygame.SRCALPHA)
            for j in range(4): pygame.draw.ellipse(cloud,(250,230,227,100),(x+j*25,y-(j%2)*10,70,30))
            soft(s,cloud,8)
    else:
        for x in range(24,864,24): pygame.draw.line(s,(35,67,87),(x,88),(x,690))
        for y in range(88,700,24): pygame.draw.line(s,(35,67,87),(24,y),(864,y))
        for _ in range(14000):
            x,y=rng.randrange(1180),rng.randrange(800)
            s.set_at((x,y),blend(s.get_at((x,y))[:3],(180,197,196),.035))
        for x,y in [(62,160),(810,160),(62,660),(810,660)]:
            pygame.draw.line(s,(97,130,146),(x-8,y),(x+8,y))
            pygame.draw.line(s,(97,130,146),(x,y-8),(x,y+8))
        pygame.draw.line(s,(103,133,144),(170,658),(688,658))
        for x in (170,688): pygame.draw.line(s,(103,133,144),(x,650),(x,666))


def texture_face(s,points,color,n,rng,top,is_block=False):
    polygon(s,color,points)
    rect=pygame.Rect(min(p[0] for p in points),min(p[1] for p in points),
                     max(p[0] for p in points)-min(p[0] for p in points)+2,
                     max(p[1] for p in points)-min(p[1] for p in points)+2)
    if rect.w<2 or rect.h<2:return
    tex=pygame.Surface(rect.size,pygame.SRCALPHA)
    if n==2:
        for i in range(0,rect.h,5 if top else 8):
            pts=[(x,i+math.sin(x*.09+i)*1.3) for x in range(0,rect.w+4,4)]
            pygame.draw.lines(tex,(*blend(color,(72,42,26),.3),65),False,pts)
    elif n==3 and top and not is_block:
        for _ in range(10):
            x,y=rng.randrange(rect.w),rng.randrange(rect.h)
            col=rng.choice([(246,226,204,150),(139,158,162,130),(187,155,183,140)])
            pygame.draw.polygon(tex,col,[(x,y),(x+2,y+1),(x+1,y+3),(x-1,y+2)])
    else:
        for _ in range(max(6,rect.w*rect.h//35)):
            x,y=rng.randrange(rect.w),rng.randrange(rect.h)
            tex.set_at((x,y),(*blend(color,(240,236,210),.25),rng.randrange(15,65)))
    if n==1 and not is_block:
        for _ in range(12 if top else 25):
            x=rng.randrange(rect.w); y=rng.randrange(min(9,rect.h))
            pygame.draw.circle(tex,(85,113,69,160),(x,y),rng.randrange(1,4))
    mask=pygame.Surface(rect.size,pygame.SRCALPHA)
    pygame.draw.polygon(mask,(255,255,255,255),[(x-rect.x,y-rect.y) for x,y in points])
    tex.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(tex,rect)
    edge=blend(color,(255,249,222),.22) if n in (2,4) else blend(color,(40,65,60),.12)
    pygame.draw.aalines(s,edge,True,points)
    if n==4 and top:
        center=(sum(x for x,y in points)/4,sum(y for x,y in points)/4)
        inset=[(x*.95+center[0]*.05,y*.95+center[1]*.05) for x,y in points]
        pygame.draw.aalines(s,blend(color,(92,125,143),.30),True,inset)


def board(s,c,n,stage,rng):
    cells=[(r,col) for r,row in enumerate(stage.grid) for col,t in enumerate(row) if t!=TileType.VOID]
    shadow=pygame.Surface(SIZE,pygame.SRCALPHA)
    shift=(44,45) if n==0 else (18,24) if n!=2 else (5,9)
    shadow_color=(83,84,64,60) if n==0 else (4,20,14,110) if n==1 else (78,43,26,95) if n==2 else (133,97,143,70) if n==3 else (6,27,43,105)
    for r,col in cells:
        pts=[(x+shift[0],y+shift[1]) for x,y in map(proj,cuboid(r,col,-.24,1,1,0)[:4])]
        pygame.draw.polygon(shadow,shadow_color,pts)
    soft(s,shadow,14 if n==0 else 7 if n==2 else 10)
    # Physical face geometry shared by every concept.
    commands=[]
    for r,col in cells:
        top=c['floor']
        if n==3 and (r+col)%5==0:top=(193,186,211)
        top=blend(top,(240,240,228),rng.random()*.055)
        vertices=cuboid(r,col,-.24,1,1,.24)
        for face in (FACES[1],FACES[3],FACES[4]):
            pts=[vertices[i] for i in face]
            depth=sum(p[0]+p[1]+p[2]*.83 for p in pts)/4
            color=top if face==FACES[1] else c['side'] if face==FACES[3] else blend(c['side'],top,.20)
            commands.append((depth,'tile',list(map(proj,pts)),color,face==FACES[1],False))
    for _,_,pts,color,top,block in sorted(commands): texture_face(s,pts,color,n,rng,top)
    # Recessed goal rim and dark interior, identical footprint in all concepts.
    r,col=stage.goal
    rim=[proj(p) for p in cuboid(r+.12,col+.12,.005,.76,.76,0)[:4]]
    hole=[proj(p) for p in cuboid(r+.23,col+.23,.006,.54,.54,0)[:4]]
    polygon(s,blend(c['side'],c['floor'],.2),rim)
    polygon(s,(24,39,33) if n==1 else blend(c['side'],(8,17,22),.73),hole)
    pygame.draw.aalines(s,blend(c['floor'],(255,247,223),.28),False,rim[:3])
    # Block shadow cast onto the adjacent supported tiles.
    r,col=stage.start
    p0=proj((r,col,0));p1=proj((r,col+1,0));p2=proj((r+1,col+1,0));p3=proj((r+1,col,0))
    cast=pygame.Surface(SIZE,pygame.SRCALPHA)
    dx,dy=(48,20) if n==0 else (25,13)
    polygon(cast,(*shadow_color[:3],75),[p0,p1,(p2[0]+dx,p2[1]+dy),(p3[0]+dx,p3[1]+dy),p3])
    soft(s,cast,6)
    vertices=cuboid(r,col,0,1,1,2)
    for face,shade in [(FACES[3],.67),(FACES[4],.82),(FACES[1],1.08)]:
        color=tuple(min(255,int(v*shade)) for v in c['block'])
        texture_face(s,list(map(proj,[vertices[i] for i in face])),color,n,rng,face==FACES[1],True)


def ui(s,c,n):
    ink,muted=c['ink'],c['muted']
    title=font(c['title'],32); heading=font(c['title'],25); body=font(c['body'],18); small=font(c['body'],15)
    def label(t,x,y,f=body,color=ink):s.blit(f.render(t,True,color),(x,y))
    def button(t,rect,primary=False,selected=False,quiet=False):
        rect=pygame.Rect(rect)
        radius=0 if n==4 else 3 if n==0 else 6 if n==1 else 10 if n==2 else 20
        fill=c['accent'] if primary else blend(c['panel'],c['ink'],.07)
        if n==2:
            pygame.draw.rect(s,(177,140,96),rect.move(0,3),border_radius=radius)
        if not quiet or primary:pygame.draw.rect(s,fill,rect,border_radius=radius)
        if n==4:pygame.draw.rect(s,c['accent'] if primary else muted,rect,1)
        if selected:
            pygame.draw.line(s,c['accent'],(rect.x+12,rect.bottom-3),(rect.right-12,rect.bottom-3),2)
        fg=(244,237,221) if primary and n in (0,2,4) else (33,48,40) if primary and n==1 else (249,234,233) if primary else ink
        text=body.render(t,True,fg);s.blit(text,text.get_rect(center=rect.center))
    # Header identical function/placement, typography and ornament change by concept.
    label('Bloxorz' if n!=4 else 'BLOXORZ /',32,22,title)
    label('Stage 01',508,31); label('0 moves',650,32,small,muted)
    pygame.draw.lines(s,muted,False,[(606,38),(610,42),(614,38)])
    label('Settings',1060,31)
    pygame.draw.line(s,blend(c['bg'],ink,.16),(32,78),(1148,78))
    label(c['name'].upper(),40,112,small,muted)
    label(c['subtitle'],40,136,body,muted)
    if n==0:
        label('I',68,590,font(c['title'],56),blend(c['bg'],muted,.40))
    if n==4:label('PLAN 01     /     SCALE 1:1',280,672,small,muted)
    if n in (1,2,3,4):
        panel=pygame.Rect(884,128,272,424)
        if n==2:
            pygame.draw.rect(s,(194,163,120),panel.move(2,5),border_radius=12)
        pygame.draw.rect(s,c['panel'],panel,border_radius=0 if n==4 else 12 if n==2 else 20 if n==3 else 8)
        if n==4:
            pygame.draw.rect(s,muted,panel,1)
            for x,y in [panel.topleft,panel.topright,panel.bottomleft,panel.bottomright]:
                pygame.draw.line(s,ink,(x-4,y),(x+4,y))
    else:pygame.draw.line(s,blend(c['bg'],ink,.2),(884,144),(884,512))
    x=900
    label('Find a solution',x,152,heading)
    label('ALGORITHM',x,208,small,muted)
    button('A*',(x,240,240,44))
    pygame.draw.lines(s,muted,False,[(1116,259),(1121,264),(1126,259)])
    label('START FROM',x,316,small,muted)
    button('Beginning',(x,348,116,44))
    button('Current',(x+124,348,116,44),selected=True)
    button('Find a solution',(x,440,240,48),primary=True)
    for i,t in enumerate(('Undo','Restart','Hint')):
        button(t,(248+i*128,712,112,40),quiet=n in (0,1),selected=False)
    label('PREVIEW ONLY  /  controls are illustrative',32,774,small,muted)
    label(f'0{n+1} / 05',1070,774,small,muted)


def render(index):
    c=CONCEPTS[index];rng=random.Random(143)
    stage=load_stage(str(ROOT/'levels/stage_01.json'))
    surface=pygame.Surface(SIZE)
    background(surface,c,index,rng)
    board(surface,c,index,stage,rng)
    ui(surface,c,index)
    return surface


def contact_sheet(images):
    sheet=pygame.Surface((1800,1380));sheet.fill((231,228,219))
    f=font('segoeui.ttf',24);title=font('georgia.ttf',38)
    sheet.blit(title.render('Bloxorz / five directions',True,(40,49,47)),(40,24))
    for i,img in enumerate(images):
        x=40+(i%3)*584;y=100+(i//3)*624
        thumb=pygame.transform.smoothscale(img,(560,380))
        sheet.blit(thumb,(x,y))
        sheet.blit(f.render(f'{i+1:02}  {CONCEPTS[i]["name"]}',True,(40,49,47)),(x,y+400))
        desc=[['Warm stone / matte brass','Gallery light / editorial type'],['Moss / weathered stone','Forest haze / ancient gold'],
              ['Oak / walnut / painted wood','Tactile controls / cream paper'],['Terrazzo / pastel architecture','Colored shadows / soft controls'],
              ['Folded cardstock / burnt orange','Construction lines / mono type']][i]
        for j,line in enumerate(desc):sheet.blit(f.render(line,True,(91,101,96)),(x,y+448+j*36))
    x,y=1208,764
    for j,line in enumerate(['Same stage. Same camera.', 'Same block. Same controls.', '', 'Choose the atmosphere.', 'The game stays the same.']):
        sheet.blit(f.render(line,True,(65,79,75)),(x,y+j*40))
    return sheet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--concept',type=int,choices=range(1,6),default=1)
    parser.add_argument('--show',action='store_true')
    args=parser.parse_args();pygame.init();OUT.mkdir(parents=True,exist_ok=True)
    indices=range(5) if args.all else [args.concept-1]
    images=[]
    for i in indices:
        image=render(i);images.append(image)
        pygame.image.save(image,str(OUT/(CONCEPTS[i]['slug']+'.png')))
        print(CONCEPTS[i]['slug'])
    if args.all:pygame.image.save(contact_sheet(images),str(OUT/'00_contact_sheet.png'))
    (OUT/'comparison.json').write_text(json.dumps({'window':SIZE,'stage':'levels/stage_01.json',
        'block':{'position':[1,1],'dimensions':[1,1,2]},'projection':{'origin':ORIGIN,'tile_width':TILE,'tile_depth':TILE/2},
        'controls':'Illustrative only; no solver or gameplay wired in previews.'},indent=2))
    if args.show:
        window=pygame.display.set_mode(SIZE);pygame.display.set_caption('Bloxorz concepts - arrows to compare, Escape to close')
        i=args.concept-1;clock=pygame.time.Clock();running=True
        cached = [render(index) for index in range(5)]
        while running:
            window.blit(cached[i],(0,0));pygame.display.flip()
            for e in pygame.event.get():
                if e.type==pygame.QUIT:running=False
                elif e.type==pygame.KEYDOWN:
                    if e.key==pygame.K_ESCAPE:running=False
                    elif e.key==pygame.K_RIGHT:i=(i+1)%5
                    elif e.key==pygame.K_LEFT:i=(i-1)%5
            clock.tick(10)
    pygame.quit()

if __name__=='__main__':main()

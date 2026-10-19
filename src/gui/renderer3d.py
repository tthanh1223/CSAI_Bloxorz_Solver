"""Isometric board with physical edge-pivot animation, using Pygame polygons."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from math import cos, sin, pi, floor, ceil
import random
import pygame
import pygame.gfxdraw
from src.gui import theme
from src.engine.loader import StageData, TileType
from src.engine.problem import BloxorzProblem
from src.engine.state import Action, GameState, Orientation
from src.gui.contracts import MotionFrame

Point = tuple[float, float, float]
FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


@dataclass(frozen=True)
class Camera3D:
    origin: tuple[float, float] = (360, 120)
    tile_width: float = 54
    tile_depth: float = 27
    tile_height: float = 12

    def project(self, row: float, col: float, height: float = 0) -> tuple[float, float]:
        """Height is in screen pixels."""
        return (self.origin[0] + (col - row) * self.tile_width / 2,
                self.origin[1] + (col + row) * self.tile_depth / 2 - height)


def cuboid(r, c, z, rows, cols, height) -> list[Point]:
    return [(r, c, z), (r, c + cols, z), (r + rows, c + cols, z), (r + rows, c, z),
            (r, c, z + height), (r, c + cols, z + height),
            (r + rows, c + cols, z + height), (r + rows, c, z + height)]


@lru_cache(maxsize=32)
def _bevel_template(amount):
    """Cache topology and affine corner weights; rotation only transforms vertices."""
    vertices=cuboid(0,0,0,1,1,1)
    points,faces=_build_bevel(vertices,amount)
    return tuple(points),tuple(faces)


def bevel_mesh(vertices, amount=.025, uniform=False):
    # A constant fractional bevel keeps a shared template across every pose.
    template,faces=_bevel_template(amount)
    axes=[tuple(vertices[j][k]-vertices[0][k] for k in range(3)) for j in (3,1,4)]
    if uniform:
        lengths=[sum(v*v for v in axis)**.5 for axis in axes]
        template=[tuple(value/max(1,lengths[k]) if value<.5 else 1-(1-value)/max(1,lengths[k]) for k,value in enumerate(point)) for point in template]
    points=[tuple(vertices[0][k]+sum(p[axis]*axes[axis][k] for axis in range(3)) for k in range(3)) for p in template]
    return points,faces


def _build_bevel(vertices, amount):
    """26 low-poly faces; transform already-rolled corners without changing motion."""
    result, faces, corners, edges = [], [], {}, {}
    for face in FACES:
        indices=[]
        for j,index in enumerate(face):
            p=vertices[index]
            adjacent=(vertices[face[j-1]],vertices[face[(j+1)%4]])
            inset=list(p)
            for q in adjacent:
                length=sum((q[k]-p[k])**2 for k in range(3))**.5
                for k in range(3):inset[k]+=(q[k]-p[k])*min(amount/ max(length,1e-9),.12)
            new=len(result);result.append(tuple(inset));indices.append(new)
            corners.setdefault(index,[]).append(new)
        faces.append(tuple(indices))
        for j,index in enumerate(face):
            other=face[(j+1)%4]
            edges.setdefault(tuple(sorted((index,other))),[]).append({index:indices[j],other:indices[(j+1)%4]})
    for (a,b),pair in edges.items():
        faces.append((pair[0][a],pair[0][b],pair[1][b],pair[1][a]))
    faces.extend(tuple(indices) for indices in corners.values())
    # The existing projection expects inward winding. Edge/corner insertion order
    # is arbitrary, so normalize it once in the cached template to avoid gaps.
    fixed=[]
    for face in faces:
        a,b,c=(result[i] for i in face[:3])
        u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)]
        normal=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        center=[sum(result[i][k] for i in face)/len(face)-.5 for k in range(3)]
        fixed.append(tuple(reversed(face)) if sum(normal[k]*center[k] for k in range(3))>0 else face)
    faces=fixed
    return result,faces


def state_meshes(state: GameState) -> list[tuple[list[Point], bool]]:
    if state.orientation == Orientation.SPLIT:
        return [(cuboid(r, c, 0, 1, 1, 1), i == state.active_cube)
                for i, (r, c) in enumerate((state.pos1, state.pos2))]
    r = min(state.pos1[0], state.pos2[0])
    c = min(state.pos1[1], state.pos2[1])
    return [(cuboid(r, c, 0, abs(state.pos2[0] - state.pos1[0]) + 1,
                   abs(state.pos2[1] - state.pos1[1]) + 1,
                   2 if state.orientation == Orientation.STANDING else 1), False)]


def rotate_mesh(vertices: list[Point], action: Action, progress: float) -> list[Point]:
    """Rotate about the leading ground edge, without sliding."""
    axis = 0 if action in (Action.UP, Action.DOWN) else 1
    positive = action in (Action.DOWN, Action.RIGHT)
    pivot = (max if positive else min)(p[axis] for p in vertices)
    angle = progress * pi / 2 * (1 if positive else -1)
    result = []
    for point in vertices:
        v = list(point)
        offset, z = point[axis] - pivot, point[2]
        v[axis] = pivot + offset * cos(angle) + z * sin(angle)
        v[2] = -offset * sin(angle) + z * cos(angle)
        result.append(tuple(v))
    return result


def motion_meshes(motion: MotionFrame) -> list[tuple[list[Point], bool]]:
    before, after, action = motion.before, motion.after, motion.action
    if action == Action.SPACE:
        return state_meshes(after if motion.progress >= 0.5 else before)
    raw = BloxorzProblem.roll_block(before, action)
    teleport = raw is not None and (raw.pos1, raw.pos2, raw.orientation) != (
        after.pos1, after.pos2, after.orientation)
    roll_progress = min(1.0, motion.progress / 0.65) if teleport else motion.progress
    meshes = state_meshes(before)
    rotated = [(rotate_mesh(v, action, roll_progress)
                if before.orientation != Orientation.SPLIT or i == before.active_cube else v, active)
               for i, (v, active) in enumerate(meshes)]
    if teleport and motion.progress > 0.65:
        t = (motion.progress - 0.65) / 0.35
        assert raw is not None
        r, c = raw.pos1
        source = [cuboid(r, c, z, 1, 1, 1) for z in (0, 1)]
        return [([tuple(a + (b - a) * t for a, b in zip(p, q))
                  for p, q in zip(source[i], vertices)], active)
                for i, (vertices, active) in enumerate(state_meshes(after))]
    return rotated


class IsometricRenderer:
    BACKGROUND = theme.BG
    FLOOR = theme.FLOOR
    BLOCK = theme.BLOCK

    def __init__(self, camera: Camera3D | None = None):
        self.camera = camera or Camera3D()
        self.stage: StageData | None = None
        self.size = (760, 600)
        self.bridge_cells = {}
        self.zoom = 1.0
        self.pan = (0, 0)
        self.high_contrast = False
        rng=random.Random(103)
        self.flecks=[(rng.uniform(.04,.94),rng.uniform(.04,.94),rng.uniform(.012,.038),rng.randrange(5)) for _ in range(75)]
        self.material_cache={}
        self._static_key=None
        self._frame_key=None
        self._block_textures={}
        self.stats={'static_builds':0,'dynamic_frames':0,'frame_cache_hits':0}
        self.style='dream'
        self.stone_texture=self.gold_texture=None
        self._brushed_detail=None

    def set_stage(self, stage: StageData) -> None:
        self.stage = stage
        self.bridge_cells = {cell: i for i, cells in enumerate(stage.bridges.values()) for cell in cells}
        self.resize(self.size)
        self._static_key=None
        self._frame_key=None
        self.material_cache.clear()

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        if self.stage is None:
            return
        cells = [(r, c) for r, row in enumerate(self.stage.grid) for c, tile in enumerate(row)
                 if tile != TileType.VOID or (r, c) in self.bridge_cells]
        cells = cells or [(0, 0)]
        xs = [(c - r + delta) / 2 for r, c in cells for delta in (-1, 1)]
        ys = [(r + c) / 4 + delta for r, c in cells for delta in (-1.38, .68)]
        width = max(2, min(112, size[0] * .88 / (max(xs) - min(xs)),
                            size[1] * .88 / (max(ys) - min(ys))))
        origin = (size[0] / 2 - (min(xs) + max(xs)) * width / 2,
                  size[1] / 2 - (min(ys) + max(ys)) * width / 2)
        self.camera = Camera3D(origin, width, width / 2, width * .24)

    def project(self, point: Point) -> tuple[float, float]:
        x, y = self.camera.project(point[0], point[1], point[2] * self.camera.tile_width * 0.6)
        return ((x - self.size[0] / 2) * self.zoom + self.size[0] / 2 + self.pan[0],
                (y - self.size[1] / 2) * self.zoom + self.size[1] / 2 + self.pan[1])

    def _faces(self, vertices, color, outline=None, faces=FACES, player=False):
        result = []
        for face in faces:
            points = [vertices[i] for i in face]
            projected = [self.project(p) for p in points]
            area = sum(p[0] * q[1] - q[0] * p[1]
                       for p, q in zip(projected, projected[1:] + projected[:1]))
            if area <= 0.001:
                continue
            depth = sum(p[0] + p[1] + p[2] * (5 / 6) for p in points) / len(points)
            a, b, c = points[:3]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            length = max(1e-9, sum(n*n for n in normal) ** .5)
            top=abs(normal[2])/length
            shade = .73 + .27 * top + .09 * abs(normal[0])/length
            shaded=tuple(min(255,int(x*shade)) for x in color)
            if player:
                # Inward mesh winding -> outward normal. Fixed soft key light:
                # upper face brightest, front medium, opposite side darker.
                nx,ny,nz=(-value/length for value in normal)
                diffuse=max(0.,nx*.39-ny*.20+nz*.90)
                hemisphere=max(0.,nz)
                bevel_light=min(1.,4*abs(nz)*(abs(nx)+abs(ny)))
                strength=.66+.32*diffuse+.06*hemisphere+.045*bevel_light
                cream=(13,16,21)
                shaded=tuple(max(0,min(255,round(v*strength+cream[k]*hemisphere))) for k,v in enumerate(color))
            elif top<.4:
                if color[0]>color[1]*1.12:
                    shade=.67+.26*abs(normal[0])/length
                    shaded=tuple(min(255,int(x*shade)) for x in color)
                else:
                    tint=(154,143,126) if self.style=='blueprint' else (91,105,81) if self.style=='forest' else (161,132,163)
                    shaded=tuple(int(a*.82+b*.18) for a,b in zip(shaded,tint))
            result.append((depth, projected, shaded, outline))
        return result

    def _build_static(self, shown):
        """Bake only on stage / bridge / camera / contrast changes."""
        self.stats['static_builds']+=1
        self._base=pygame.Surface(self.size,pygame.SRCALPHA)
        self._top_mask=pygame.Surface(self.size,pygame.SRCALPHA)
        shadow=pygame.Surface(self.size,pygame.SRCALPHA)
        commands=[]
        holes=[]
        tile_outlines=[]
        for r,row in enumerate(self.stage.grid):
            for c,tile in enumerate(row):
                coord=(r,c);bridge=self.bridge_cells.get(coord)
                if bridge is not None:
                    if bridge>=len(shown.bridges_status) or not shown.bridges_status[bridge]:
                        pts=[self.project(p) for p in cuboid(r,c,-.12,1,1,0)[:4]]
                        commands.append((r+c+1,'outline',pts));continue
                elif tile==TileType.VOID:continue
                top=[self.project(p) for p in cuboid(r+.012,c+.012,0,.976,.976,0)[:4]]
                tile_outlines.append(top)
                pygame.draw.polygon(self._top_mask,(255,255,255,255),top)
                pygame.draw.polygon(shadow,(101,55,85,68),[(x-24*self.zoom,y+40*self.zoom) for x,y in top])
                color=(112,145,151) if bridge is not None else ((178,200,193) if self.high_contrast else self.FLOOR)
                if tile==TileType.FRAGILE:color=(202,167,145)
                vertices,indices=bevel_mesh(cuboid(r+.012,c+.012,-.24,.976,.976,.24),.018)
                for depth,pts,ink,edge in self._faces(vertices,color,faces=indices):
                    commands.append((depth,'face',(pts,ink)))
                label='goal' if coord==self.stage.goal else '!' if tile==TileType.FRAGILE else ''
                if coord in self.stage.switches:
                    label={'SOFT':'O','HEAVY':'X','SPLIT':'<>'}[self.stage.switches[coord].type.value]
                if label:commands.append((r+c+1.001,'marker',((r+.5,c+.5,.01),label)))
                if coord==self.stage.goal:
                    holes.append([self.project(p) for p in cuboid(r+.16,c+.16,0,.68,.68,0)[:4]])
        for hole in holes:pygame.draw.polygon(self._top_mask,(0,0,0,0),hole)
        small=pygame.transform.smoothscale(shadow,(max(1,self.size[0]//12),max(1,self.size[1]//12)))
        self._base.blit(pygame.transform.smoothscale(small,self.size),(0,0))
        for _,kind,payload in sorted(commands,key=lambda item:item[0]):
            if kind=='face':
                pts,ink=payload
                if len(pts)==4:self._material(self._base,pts,ink)
                else:pygame.draw.polygon(self._base,ink,pts)
                # Bevel polygons provide edge shading; avoid stacking outlines.
            elif kind=='marker':self._marker(self._base,*payload)
            else:pygame.draw.aalines(self._base,(139,105,123),True,payload)
        seam={'dream':(48,47,48),'blueprint':(48,47,48),'forest':(102,112,80)}.get(self.style,(168,174,163))
        seams=pygame.Surface(self.size,pygame.SRCALPHA)
        for outline in tile_outlines:pygame.draw.aalines(seams,(*seam,145),True,outline)
        self._base.blit(seams,(0,0))
        if self.style=='forest':self._moss_edges(shown)
        # Retain a bounded number of full-size buffers, never one per state.
        self._frame=pygame.Surface(self.size,pygame.SRCALPHA)
        self._frame_key=None
        self.stats['cached_layer_bytes']=self.size[0]*self.size[1]*4*3

    @staticmethod
    def _hull(points):
        points=sorted(set(points))
        def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        halves=[]
        for sequence in (points,list(reversed(points))):
            half=[]
            for point in sequence:
                while len(half)>1 and cross(half[-2],half[-1],point)<=0:half.pop()
                half.append(point)
            halves.extend(half[:-1])
        return halves

    def _block_face(self,surface,points,color):
        # Baked satin microtexture; all face tints reuse two signed detail maps.
        color=tuple(min(255,round(v/8)*8) for v in color)
        texture=self._block_textures.get(color)
        if texture is None:
            if self.style=='forest' and self.gold_texture is not None:
                texture=pygame.Surface((64,128),pygame.SRCALPHA)
                texture.blit(pygame.transform.smoothscale(self.gold_texture,(64,128)),(0,0))
                strength=min(1.,sum(color)/max(1,sum(self.BLOCK)))
                texture.fill((int(255*strength),)*3,special_flags=pygame.BLEND_RGB_MULT)
                self._block_textures[color]=texture
                pts=[(round(x),round(y)) for x,y in points]
                pygame.gfxdraw.textured_polygon(surface,pts,texture,pts[0][0],pts[0][1])
                pygame.draw.aalines(surface,color,True,pts)
                return
            if self._brushed_detail is None:
                light=pygame.Surface((64,128),pygame.SRCALPHA);light.fill((0,0,0,255))
                dark=light.copy()
                rng=random.Random(71)
                for y in range(128):
                    fiber=rng.choice((-3,-2,-1,0,0,1,2,3))
                    for x in range(64):
                        delta=round(fiber+2*sin(x*pi/32)+rng.choice((-1,0,0,1)))
                        target=light if delta>=0 else dark
                        target.set_at((x,y),(abs(delta),)*3+(255,))
                self._brushed_detail=(light,dark)
            texture=pygame.Surface((64,128),pygame.SRCALPHA);texture.fill(color)
            texture.blit(self._brushed_detail[0],(0,0),special_flags=pygame.BLEND_RGB_ADD)
            texture.blit(self._brushed_detail[1],(0,0),special_flags=pygame.BLEND_RGB_SUB)
            self._block_textures[color]=texture
        pts=[(round(x),round(y)) for x,y in points]
        pygame.gfxdraw.textured_polygon(surface,pts,texture,pts[0][0],pts[0][1])
        # User-selected charcoal contour for the two architectural themes.
        edge=(48,47,48) if self.style in ('dream','blueprint') else color
        pygame.draw.aalines(surface,edge,True,pts)

    def draw(self,surface,state,motion=None):
        if surface.get_size()!=self.size:self.resize(surface.get_size())
        if self.stage is None:
            surface.fill((0,0,0,0) if surface.get_flags()&pygame.SRCALPHA else self.BACKGROUND);return
        shown=motion.before if motion and motion.progress<.65 else state
        static_key=(self.size,self.camera,self.zoom,tuple(self.pan),self.high_contrast,shown.bridges_status)
        if static_key!=self._static_key:
            self.material_cache.clear()
            self._build_static(shown);self._static_key=static_key
        key=(state,motion,static_key)
        if key!=self._frame_key:
            self.stats['dynamic_frames']+=1
            self._frame.fill((0,0,0,0));self._frame.blit(self._base,(0,0))
            meshes=motion_meshes(motion) if motion else state_meshes(state)
            # Work only on the small projected shadow footprint, not the full viewport.
            hulls=[self._hull([self.project((r+z*.65,c-z*.16,.01)) for r,c,z in vertices]) for vertices,_ in meshes]
            all_points=[p for hull in hulls for p in hull]
            x,y=floor(min(p[0] for p in all_points))-4,floor(min(p[1] for p in all_points))-4
            bounds=pygame.Rect(x,y,ceil(max(p[0] for p in all_points))-x+5,ceil(max(p[1] for p in all_points))-y+5).clip(self._frame.get_rect())
            if bounds.width and bounds.height:
                contact=pygame.Surface(bounds.size,pygame.SRCALPHA)
                for hull in hulls:
                    if len(hull)>=3:pygame.draw.polygon(contact,(98,72,107,85),[(a-bounds.x,b-bounds.y) for a,b in hull])
                tiny=pygame.transform.smoothscale(contact,(max(1,bounds.w//4),max(1,bounds.h//4)))
                pygame.transform.smoothscale(tiny,bounds.size,contact)
                contact.blit(self._top_mask,(0,0),bounds,special_flags=pygame.BLEND_RGBA_MULT)
                self._frame.blit(contact,bounds)
            faces=[]
            for vertices,active in meshes:
                vertices,indices=bevel_mesh(vertices,.04,uniform=True)
                color=tuple(min(255,c+18) for c in self.BLOCK) if active else self.BLOCK
                faces.extend(self._faces(vertices,color,faces=indices,player=True))
            for _,pts,color,_ in sorted(faces,key=lambda item:item[0]):self._block_face(self._frame,pts,color)
            self._frame_key=key
        else:self.stats['frame_cache_hits']+=1
        surface.fill((0,0,0,0) if surface.get_flags()&pygame.SRCALPHA else self.BACKGROUND)
        surface.blit(self._frame,(0,0))
        self.stats['material_cache_bytes']=sum(s.get_pitch()*s.get_height() for s in self.material_cache.values())
        self.stats['block_texture_bytes']=sum(s.get_pitch()*s.get_height() for s in self._block_textures.values())

    def _material(self,surface,points,color):
        x,y=floor(min(p[0] for p in points)),floor(min(p[1] for p in points))
        local=[(p[0]-x,p[1]-y) for p in points]
        key=(tuple((round(a,2),round(b,2)) for a,b in local),color)
        stamp=self.material_cache.get(key)
        if stamp is None:
            stamp=pygame.Surface((max(1,ceil(max(p[0] for p in local))+1),max(1,ceil(max(p[1] for p in local))+1)),pygame.SRCALPHA)
            self._paint_material(stamp,local,color)
            if len(self.material_cache)>768:self.material_cache.clear()
            self.material_cache[key]=stamp
        surface.blit(stamp,(x,y))

    def _paint_material(self,surface,points,color):
        pygame.draw.polygon(surface,color,points)
        if self.style=='forest' and self.stone_texture is not None:
            self._stone_material(surface,points,color)
            return
        a,b,_,d=points
        warm=color[0]>color[1]*1.12
        palette=((248,242,218),(170,152,177),(186,198,183),(240,211,183),(251,247,229))
        if self.style=='blueprint':
            rng=random.Random(92)
            # Fine fibers and paper grain, without terrazzo inclusions.
            for _ in range(140):
                u,v=rng.uniform(.02,.98),rng.uniform(.02,.98)
                p=(a[0]+(b[0]-a[0])*u+(d[0]-a[0])*v,a[1]+(b[1]-a[1])*u+(d[1]-a[1])*v)
                delta=rng.choice((-9,-5,4,8))
                pygame.draw.line(surface,tuple(max(0,min(255,c+delta)) for c in color),p,(p[0]+rng.uniform(.5,1.5),p[1]))
            return
        for u,v,s,index in self.flecks:
            def at(x,y):return (a[0]+(b[0]-a[0])*x+(d[0]-a[0])*y,a[1]+(b[1]-a[1])*x+(d[1]-a[1])*y)
            ink=tuple(min(255,max(0,c+(7 if index%2 else -8))) for c in color) if warm else tuple(int(c*.25+p*.75) for c,p in zip(color,palette[index]))
            pygame.draw.polygon(surface,ink,[at(u,v),at(u+s,v+s*.2),at(u+s*.4,v+s),at(u-s*.3,v+s*.5)])

    def _stone_material(self,surface,points,color):
        width,height=surface.get_size()
        a,b,_,d=points
        top=abs((b[1]-a[1])+(d[1]-a[1]))>1 and abs(b[1]-d[1])<2
        source=pygame.transform.rotate(self.stone_texture,45) if top else self.stone_texture
        texture=pygame.transform.smoothscale(source,(width,height))
        brightness=min(1.,sum(color)/max(1,sum(self.FLOOR)))
        texture.fill((int(brightness*255),)*3,special_flags=pygame.BLEND_RGB_MULT)
        mask=pygame.Surface(surface.get_size(),pygame.SRCALPHA)
        pygame.draw.polygon(mask,(255,255,255,255),points)
        rgba=pygame.Surface(surface.get_size(),pygame.SRCALPHA)
        rgba.blit(texture,(0,0))
        rgba.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(rgba,(0,0))

    def _moss_edges(self,shown):
        """Baked hanging moss only along exposed front-facing edges."""
        rng=random.Random(842)
        cells=set()
        for r,row in enumerate(self.stage.grid):
            for c,tile in enumerate(row):
                bridge=self.bridge_cells.get((r,c))
                if bridge is not None:
                    if bridge<len(shown.bridges_status) and shown.bridges_status[bridge]:cells.add((r,c))
                elif tile!=TileType.VOID:cells.add((r,c))
        for r,c in cells:
            for neighbor,start,end in (((r+1,c),(r+1,c),(r+1,c+1)),((r,c+1),(r,c+1),(r+1,c+1))):
                if neighbor in cells:continue
                for _ in range(7):
                    t=rng.random()
                    rr=start[0]+(end[0]-start[0])*t
                    cc=start[1]+(end[1]-start[1])*t
                    x,y=self.project((rr,cc,-.05))
                    length=rng.uniform(.05,.28)*self.camera.tile_width*self.zoom
                    for i in range(max(2,int(length/3))):
                        pygame.draw.circle(self._base,rng.choice(((64,80,30),(90,109,39),(120,131,54))),
                                           (round(x+rng.uniform(-2,2)),round(y+i*3)),max(1,round(self.zoom*1.4)))

    def _marker(self, surface, point, kind):
        r, c, z = point
        ink = (121, 104, 137)
        def project(dr, dc):
            return self.project((r + dr, c + dc, z))
        def line(points, color=ink):
            pygame.draw.aalines(surface, color, False, [project(*p) for p in points])
        if kind == 'goal':
            # Recessed opening with a light far rim, no text label.
            hole = [project(-.34,-.34), project(-.34,.34), project(.34,.34), project(.34,-.34)]
            pygame.draw.polygon(surface, (13, 24, 32), hole)
            inner=[(x,y+self.camera.tile_width*.12*self.zoom) for x,y in hole]
            pygame.draw.polygon(surface,(89,83,111),[hole[0],hole[1],inner[1],inner[0]])
            pygame.draw.polygon(surface,(63,64,87),[hole[0],inner[0],inner[3],hole[3]])
            pygame.draw.aalines(surface, (250,231,212), True, hole)
            if self.style=='forest':
                rim=[project(-.4,-.4),project(-.4,.4),project(.4,.4),project(.4,-.4)]
                pygame.draw.aalines(surface,(180,156,91),True,rim)
                for i in range(4):
                    a,b=rim[i],rim[(i+1)%4]
                    for t in (.16,.34,.52,.7,.88):
                        x,y=a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t
                        pygame.draw.circle(surface,(94,103,76),(round(x),round(y)),1)
        elif kind == 'O':
            points = [project(.23*cos(i*pi/16), .23*sin(i*pi/16)) for i in range(33)]
            pygame.draw.aalines(surface, ink, False, points)
        elif kind == 'X':
            line([(-.24,-.24),(.24,.24)])
            line([(-.24,.24),(.24,-.24)])
        elif kind == '<>':
            line([(-.24,-.12),(-.24,-.27),(.24,-.27),(.24,-.12)])
            line([(-.24,.12),(-.24,.27),(.24,.27),(.24,.12)])
        elif kind == '!':
            line([(-.4,-.12),(-.1,.06),(.02,-.14),(.22,.12),(.4,.02)], (87, 78, 71))

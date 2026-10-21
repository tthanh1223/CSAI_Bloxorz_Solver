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


# ---------------------------------------------------------------------------
# Camera views
#   'iso'  : classic isometric view of the original game. Every arrow key moves
#            the block diagonally on screen.
#   'original': default. The original Flash game's camera: front-left and
#            high, with real perspective (far tiles get smaller), so boards
#            split into islands clearly lie on one ground plane. Rows run
#            almost level and the board's left and front sides show.
#            UP = away from you, LEFT/RIGHT = left/right on screen.
# ---------------------------------------------------------------------------
VIEWS = ('original', 'iso')
DEFAULT_VIEW = 'original'
HEIGHT_SCALE = 0.6  # 'iso': one unit of block height = 0.6 * tile width (see project())

# 'original' perspective camera, aimed at the board centre.
# Tuned against a screenshot of the Flash game's stage 1.
ORIGINAL_YAW = 0.2        # radians the camera stands to the left of straight-in-front
ORIGINAL_PITCH = 0.58     # radians the camera looks down (~33 degrees)
ORIGINAL_DISTANCE = 2.5   # distance from the board centre, in board sizes (smaller = stronger perspective)
ORIGINAL_HEIGHT = 1.0     # one block unit of height, in tile widths


def height_scale(view: str) -> float:
    return ORIGINAL_HEIGHT if view == 'original' else HEIGHT_SCALE


def perspective_eye(row: float, col: float, distance: float) -> tuple:
    """Camera pose looking at (row, col, 0): position, right, up, forward.

    World axes: x = col (right), y = row (toward the viewer), z = up.
    """
    ch, sh = cos(ORIGINAL_PITCH), sin(ORIGINAL_PITCH)
    position = (col - distance * ch * sin(ORIGINAL_YAW), row + distance * ch * cos(ORIGINAL_YAW), distance * sh)
    forward = tuple((t - p) / distance for t, p in zip((col, row, 0), position))
    right = (-forward[1], forward[0], 0)  # world up x forward
    length = (right[0] ** 2 + right[1] ** 2) ** .5
    right = (right[0] / length, right[1] / length, 0)
    up = (forward[1] * right[2] - forward[2] * right[1],  # forward x right
          forward[2] * right[0] - forward[0] * right[2],
          forward[0] * right[1] - forward[1] * right[0])
    return position + right + up + forward


def perspective_raw(eye, row: float, col: float, z: float) -> tuple[float, float, float]:
    """Pinhole projection with focal length 1: (x, y, distance along the view).

    eye comes from perspective_eye(); screen y grows downward; z is in block units.
    """
    # Dot products written out by hand: this runs ~100k times per board rebuild.
    vx, vy, vz = col - eye[0], row - eye[1], z * ORIGINAL_HEIGHT - eye[2]
    x = vx * eye[3] + vy * eye[4] + vz * eye[5]
    y = vx * eye[6] + vy * eye[7] + vz * eye[8]
    forward = vx * eye[9] + vy * eye[10] + vz * eye[11]
    if forward < 1e-3:
        forward = 1e-3
    return x / forward, -y / forward, forward


@dataclass(frozen=True)
class Camera3D:
    origin: tuple[float, float] = (360, 120)
    tile_width: float = 54
    tile_depth: float = 27
    tile_height: float = 12
    # The perspective camera needs a board to aim at, so the stage-less default
    # is 'iso'; IsometricRenderer.resize() builds the real camera per stage.
    view: str = 'iso'
    eye: tuple = ()  # 'original' only: perspective_eye() + focal length

    def project(self, row: float, col: float, height: float = 0) -> tuple[float, float]:
        """Height is in screen pixels (block units * tile_width * height_scale)."""
        if self.view == 'original':
            x, y, _ = perspective_raw(self.eye, row, col, height / (self.tile_width * ORIGINAL_HEIGHT))
            return self.origin[0] + x * self.eye[12], self.origin[1] + y * self.eye[12]
        return (self.origin[0] + (col - row) * self.tile_width / 2,
                self.origin[1] + (col + row) * self.tile_depth / 2 - height)

    def depth(self, row: float, col: float, z: float) -> float:
        """Painter's-algorithm key: larger = closer to the viewer, drawn later.

        It is the dot product with the projection direction, i.e. the 3D
        direction that projects onto a single screen point. For 'iso' this is
        exactly the old key row + col + z * 5/6. For 'original' it is minus the distance in front of the camera.
        """
        if self.view == 'original':
            return -perspective_raw(self.eye, row, col, z)[2]
        return row + col + z * (5 / 6)


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


FALL_ROLL_END = 0.3   # first 30% of a fall: the normal roll into the illegal pose
FALL_DISTANCE = 9.0   # how far (in block units) the block drops before restart

# How the block tips over an edge: (axis, direction, pivot)
#   axis 0 = rows, 1 = cols; direction = +1/-1 toward the empty side;
#   pivot = grid line of the board edge the block tips over.
Tip = tuple[int, int, float]


def tip_mesh(vertices: list[Point], tip: Tip, fraction: float) -> list[Point]:
    """Rotate about the board edge so the part beyond it goes DOWN.

    u = signed distance past the edge (toward the empty side). A point at
    (u=1, z=0) moves to (cos a, -sin a): it drops. A point above the edge
    (u=0, z=1) moves to (sin a, cos a): the block topples over the edge.
    """
    axis, direction, pivot = tip
    angle = fraction * pi / 2
    result = []
    for point in vertices:
        v = list(point)
        u, z = (point[axis] - pivot) * direction, point[2]
        v[axis] = pivot + (u * cos(angle) + z * sin(angle)) * direction
        v[2] = -u * sin(angle) + z * cos(angle)
        result.append(tuple(v))
    return result


def fall_meshes(motion: MotionFrame, tip: Tip | None) -> list[tuple[list[Point], bool, bool]]:
    """Geometry of a falling block. Returns (vertices, active, moving) per mesh.

    Phase 1 (progress < FALL_ROLL_END): the usual roll into the illegal pose.
    Phase 2: the block drops with gravity (distance ~ t^2) and, if part of it
    hangs over empty space, topples over the board edge (tip). tip=None means
    every cell has a tile under it (a fragile tile broke): drop straight down.
    In split mode only the active cube moves; the other cube stays put.
    """
    split = motion.before.orientation == Orientation.SPLIT
    if motion.progress < FALL_ROLL_END:
        roll = MotionFrame(motion.before, motion.after, motion.action,
                           motion.progress / FALL_ROLL_END)
        return [(v, active, not split or i == motion.before.active_cube)
                for i, (v, active) in enumerate(motion_meshes(roll))]
    t = (motion.progress - FALL_ROLL_END) / (1 - FALL_ROLL_END)
    # Tipping over an edge starts slowly (t^2). A broken fragile tile (tip=None)
    # gives way at once, so the block drops with some speed from the start.
    drop = FALL_DISTANCE * (t * t if tip is not None else t * (0.4 + 0.6 * t))
    result = []
    # Two split cubes can merge in the illegal pose, so look at `after` here.
    split_after = motion.after.orientation == Orientation.SPLIT
    for i, (vertices, active) in enumerate(state_meshes(motion.after)):
        moving = not split_after or i == motion.after.active_cube
        if moving:
            if tip is not None:
                vertices = tip_mesh(vertices, tip, min(1.0, t * 1.8))
            vertices = [(r, c, z - drop) for r, c, z in vertices]
        result.append((vertices, active, moving))
    return result


SINK_DEPTH = 2.05  # a standing block is 2 units tall: sink until fully inside


def sink_meshes(motion: MotionFrame) -> list[tuple[list[Point], bool]]:
    """Win animation: the block slides straight down into the goal hole.

    Starts slowly and speeds up (t^2). Everything below the board top (z < 0)
    is cut away by clip_below_floor(), so the block looks swallowed by the hole.
    """
    t = motion.progress
    drop = SINK_DEPTH * t * t
    return [([(r, c, z - drop) for r, c, z in vertices], active)
            for vertices, active in state_meshes(motion.after)]


def clip_below_floor(vertices: list[Point], faces, above: bool = True) -> tuple[list[Point], list[tuple[int, ...]]]:
    """Cut every face at the board-top plane z = 0 and keep the part above it
    (or, with above=False, the part below it).

    Sutherland-Hodgman clipping against one plane: walk around each polygon,
    keep vertices on the wanted side and add the crossing point on edges that
    cross the plane. Faces entirely on the other side disappear.
    """
    def keep(point):
        return (point[2] >= 0) == above

    points, result = [], []
    for face in faces:
        polygon = [vertices[i] for i in face]
        kept = []
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            if keep(a):
                kept.append(a)
            if keep(a) != keep(b):
                k = a[2] / (a[2] - b[2])
                kept.append(tuple(a[i] + (b[i] - a[i]) * k for i in range(3)))
        if len(kept) >= 3:
            start = len(points)
            points.extend(kept)
            result.append(tuple(range(start, start + len(kept))))
    return points, result


class IsometricRenderer:
    BACKGROUND = theme.BG
    FLOOR = theme.FLOOR
    BLOCK = theme.BLOCK
    FRAGILE = (202, 167, 145)

    def __init__(self, camera: Camera3D | None = None):
        self.camera = camera or Camera3D()
        self.stage: StageData | None = None
        self.size = (760, 600)
        self.bridge_cells = {}
        self.zoom = 1.0
        self.pan = (0, 0)
        self.view = DEFAULT_VIEW
        self.high_contrast = False
        rng=random.Random(103)
        self.flecks=[(rng.uniform(.04,.94),rng.uniform(.04,.94),rng.uniform(.012,.038),rng.randrange(5)) for _ in range(75)]
        self.material_cache={}
        self._material_key=None
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

    def set_view(self, view: str) -> None:
        """Switch camera view (one of VIEWS) and refit the board."""
        if view not in VIEWS:
            raise ValueError(f'Unknown view: {view!r}')
        self.view = view
        self.resize(self.size)  # new camera -> static cache key changes -> rebuild

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        if self.stage is None:
            return
        cells = [(r, c) for r, row in enumerate(self.stage.grid) for c, tile in enumerate(row)
                 if tile != TileType.VOID or (r, c) in self.bridge_cells]
        cells = cells or [(0, 0)]
        if self.view == 'original':
            corners = [(r + dr, c + dc) for r, c in cells for dr in (0, 1) for dc in (0, 1)]
            rows = [r for r, _ in corners];cols = [c for _, c in corners]
            distance = ORIGINAL_DISTANCE * max(max(rows) - min(rows), max(cols) - min(cols), 4)
            eye = perspective_eye((min(rows) + max(rows)) / 2, (min(cols) + max(cols)) / 2, distance)
            points = [perspective_raw(eye, r, c, z) for r, c in corners
                      for z in (-.45, 2.2)]  # tile side .. standing block
            xs = [p[0] for p in points];ys = [p[1] for p in points]
            focal = min(size[0] * .88 / (max(xs) - min(xs)), size[1] * .88 / (max(ys) - min(ys)))
            focal = max(2 * distance, min(112 * distance, focal))  # tile width 2..112 px at the centre
            origin = (size[0] / 2 - (min(xs) + max(xs)) * focal / 2,
                      size[1] / 2 - (min(ys) + max(ys)) * focal / 2)
            width = focal / distance  # tile width at the board centre, for markers and moss
            self.camera = Camera3D(origin, width, width / 2, width * .24, 'original', eye + (focal,))
            return
        xs = [(c - r + delta) / 2 for r, c in cells for delta in (-1, 1)]
        ys = [(r + c) / 4 + delta for r, c in cells for delta in (-1.38, .68)]
        width = max(2, min(112, size[0] * .88 / (max(xs) - min(xs)),
                            size[1] * .88 / (max(ys) - min(ys))))
        origin = (size[0] / 2 - (min(xs) + max(xs)) * width / 2,
                  size[1] / 2 - (min(ys) + max(ys)) * width / 2)
        self.camera = Camera3D(origin, width, width / 2, width * .24, 'iso')

    def project(self, point: Point) -> tuple[float, float]:
        x, y = self.camera.project(point[0], point[1],
                                   point[2] * self.camera.tile_width * height_scale(self.camera.view))
        return ((x - self.size[0] / 2) * self.zoom + self.size[0] / 2 + self.pan[0],
                (y - self.size[1] / 2) * self.zoom + self.size[1] / 2 + self.pan[1])

    def _faces(self, vertices, color, outline=None, faces=FACES, player=False, cut=False):
        """cut=True: the faces were split at the board top by clip_below_floor().
        The 4th item of each result is then a per-edge flag marking the cut
        edges (z = 0), so _block_face() can leave them without a seam line."""
        result = []
        for face in faces:
            points = [vertices[i] for i in face]
            projected = [self.project(p) for p in points]
            area = sum(p[0] * q[1] - q[0] * p[1]
                       for p, q in zip(projected, projected[1:] + projected[:1]))
            if area <= 0.001:
                continue
            if cut:
                outline = tuple(abs(p[2]) < 1e-9 and abs(q[2]) < 1e-9
                                for p, q in zip(points, points[1:] + points[:1]))
            depth = sum(self.camera.depth(*p) for p in points) / len(points)
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

    def _build_static(self, shown, broken=None):
        """Bake only on stage / bridge / camera / contrast changes.

        broken: a fragile tile that has just broken; it is left out of the board,
        so it vanishes and the block drops through the hole."""
        self.stats['static_builds']+=1
        self._base=pygame.Surface(self.size,pygame.SRCALPHA)
        self._top_mask=pygame.Surface(self.size,pygame.SRCALPHA)
        commands=[]
        holes=[]
        tile_outlines=[]
        for r,row in enumerate(self.stage.grid):
            for c,tile in enumerate(row):
                coord=(r,c);bridge=self.bridge_cells.get(coord)
                if bridge is not None:
                    if bridge>=len(shown.bridges_status) or not shown.bridges_status[bridge]:
                        pts=[self.project(p) for p in cuboid(r,c,-.12,1,1,0)[:4]]
                        commands.append((self.camera.depth(r+.5,c+.5,0),'outline',pts));continue
                elif tile==TileType.VOID or coord==broken:continue
                top=[self.project(p) for p in cuboid(r+.012,c+.012,0,.976,.976,0)[:4]]
                tile_outlines.append(top)
                pygame.draw.polygon(self._top_mask,(255,255,255,255),top)
                color=(112,145,151) if bridge is not None else ((178,200,193) if self.high_contrast else self.FLOOR)
                if tile==TileType.FRAGILE:color=self.FRAGILE
                vertices,indices=bevel_mesh(cuboid(r+.012,c+.012,-.24,.976,.976,.24),.018)
                for depth,pts,ink,edge in self._faces(vertices,color,faces=indices):
                    commands.append((depth,'face',(pts,ink)))
                label='goal' if coord==self.stage.goal else '!' if tile==TileType.FRAGILE else ''
                if coord in self.stage.switches:
                    label={'SOFT':'O','HEAVY':'X','SPLIT':'<>'}[self.stage.switches[coord].type.value]
                if label:commands.append((self.camera.depth(r+.5,c+.5,0)+.001,'marker',((r+.5,c+.5,.01),label)))
                if coord==self.stage.goal:
                    holes.append([self.project(p) for p in cuboid(r+.16,c+.16,0,.68,.68,0)[:4]])
        for hole in holes:pygame.draw.polygon(self._top_mask,(0,0,0,0),hole)
        for _,kind,payload in sorted(commands,key=lambda item:item[0]):
            if kind=='face':
                pts,ink=payload
                if len(pts)==4:self._material(self._base,pts,ink)
                else:pygame.draw.polygon(self._base,ink,pts)
                # Bevel polygons provide edge shading; avoid stacking outlines.
            elif kind=='marker':self._marker(self._base,*payload)
            else:pygame.draw.aalines(self._base,(139,105,123),True,payload)
        soft_edges=self.style in ('dream','blueprint')
        seam={'dream':(244,242,229),'blueprint':(255,246,225),'forest':(102,112,80)}.get(self.style,(168,174,163))
        seams=pygame.Surface(self.size,pygame.SRCALPHA)
        for outline in tile_outlines:pygame.draw.aalines(seams,(*seam,38 if soft_edges else 145),True,outline)
        self._base.blit(seams,(0,0))
        if self.style=='forest':self._moss_edges(shown)
        # Retain a bounded number of full-size buffers, never one per state.
        self._frame=pygame.Surface(self.size,pygame.SRCALPHA)
        self._frame_key=None
        self.stats['cached_layer_bytes']=self.size[0]*self.size[1]*4*3

    def _supported(self, cell, bridges_status) -> bool:
        """A tile (not void / outside / closed bridge) is under this cell."""
        r, c = cell
        grid = self.stage.grid
        if not (0 <= r < len(grid) and 0 <= c < len(grid[r])):
            return False
        bridge = self.bridge_cells.get(cell)
        if bridge is not None:
            return bridge < len(bridges_status) and bridges_status[bridge]
        return grid[r][c] != TileType.VOID

    def _broken_tile(self, pose: GameState) -> tuple[int, int] | None:
        """The fragile tile under a block standing upright on it (it breaks), else None."""
        if self.stage is None or pose.orientation != Orientation.STANDING:
            return None
        r, c = pose.pos1
        grid = self.stage.grid
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]) and grid[r][c] == TileType.FRAGILE:
            return (r, c)
        return None

    def _tip(self, pose: GameState, action: Action) -> Tip | None:
        """Which edge the falling block topples over (see tip_mesh).

        - All cells supported (fragile tile broke) -> None: straight drop.
        - Lying block, one half supported -> tip along the block toward the
          empty half, around the edge between the two halves.
        - Nothing supported -> nose-dive forward in the rolling direction,
          around the block's trailing bottom edge.
        """
        if self.stage is None:
            return None
        if pose.orientation == Orientation.SPLIT:
            cells = [pose.pos1 if pose.active_cube == 0 else pose.pos2]
        elif pose.orientation == Orientation.STANDING:
            cells = [pose.pos1]
        else:
            cells = [pose.pos1, pose.pos2]
        supported = [cell for cell in cells if self._supported(cell, pose.bridges_status)]
        if len(supported) == len(cells):
            return None
        if supported:
            held, empty = supported[0], next(cell for cell in cells if cell not in supported)
            axis = 0 if held[0] != empty[0] else 1
            direction = 1 if empty[axis] > held[axis] else -1
            pivot = held[axis] + (1 if direction > 0 else 0)
            return axis, direction, pivot
        axis = 0 if action in (Action.UP, Action.DOWN) else 1
        direction = 1 if action in (Action.DOWN, Action.RIGHT) else -1
        low = min(cell[axis] for cell in cells)
        high = max(cell[axis] for cell in cells) + 1
        return axis, direction, (low if direction > 0 else high)

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

    def _block_face(self,surface,points,color,cut=None):
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
                if self._can_texture(surface,pts):
                    pygame.gfxdraw.textured_polygon(surface,pts,texture,pts[0][0],pts[0][1])
                self._outline(surface,color,pts,cut)
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
        if self._can_texture(surface,pts):
            pygame.gfxdraw.textured_polygon(surface,pts,texture,pts[0][0],pts[0][1])
        # A faint, antialiased one-pixel contour follows each face's shading.
        edge=tuple(round(c*.92+255*.08) for c in color) if self.style in ('dream','blueprint') else color
        self._outline(surface,edge,pts,cut)

    @staticmethod
    def _outline(surface,color,pts,cut=None):
        if not cut or not any(cut):
            pygame.draw.aalines(surface,color,True,pts);return
        for (a,b),skip in zip(zip(pts,pts[1:]+pts[:1]),cut):
            if not skip:pygame.draw.aaline(surface,color,a,b)

    @staticmethod
    def _can_texture(surface,pts):
        # SDL_gfx raises on zero-height or fully clipped polygons, e.g. a block falling off-screen.
        xs=[x for x,_ in pts];ys=[y for _,y in pts]
        box=pygame.Rect(min(xs),min(ys),max(xs)-min(xs)+1,max(ys)-min(ys)+1)
        return max(ys)>min(ys) and box.colliderect(surface.get_clip())

    def draw(self,surface,state,motion=None):
        if surface.get_size()!=self.size:self.resize(surface.get_size())
        if self.stage is None:
            surface.fill((0,0,0,0) if surface.get_flags()&pygame.SRCALPHA else self.BACKGROUND);return
        shown=motion.before if motion and motion.progress<.65 else state
        # Once the block stops rolling onto a fragile tile, that tile breaks.
        broken=(self._broken_tile(motion.after)
                if motion and motion.falling and motion.progress>=FALL_ROLL_END else None)
        static_key=(self.size,self.camera,self.zoom,tuple(self.pan),self.high_contrast,shown.bridges_status,broken)
        # Tile texture stamps only depend on each tile's on-screen shape, so they
        # survive bridge toggles, broken tiles and panning (pan moves whole pixels).
        # Only a new camera / zoom / size / look makes them stale.
        material_key=(self.size,self.camera,self.zoom,self.high_contrast,self.style)
        if material_key!=self._material_key:
            self.material_cache.clear();self._material_key=material_key
        if static_key!=self._static_key:
            self._build_static(shown,broken);self._static_key=static_key
        key=(state,motion,static_key)
        if key!=self._frame_key:
            self.stats['dynamic_frames']+=1
            self._frame.fill((0,0,0,0))
            falling=bool(motion and motion.falling)
            if falling:
                tip=self._tip(motion.after,motion.action)
                tagged=fall_meshes(motion,tip)
                dropping=motion.progress>=FALL_ROLL_END
                meshes=[(v,a) for v,a,_ in tagged]
                # What is below the board top is drawn first and the board is
                # blitted over it, so the board hides the block wherever it is in
                # front of it (parallel projection makes this exact).
                # Tipping away from the viewer (depth shrinks along the tip), each
                # face is cut at the board top: drawing a face that straddles it
                # on top would show the block through the board. Tipping toward
                # the viewer, the board is behind the block, so only faces fully
                # below the top go underneath (cutting there would let the
                # board's thick front side cover the block).
                # A straight drop through a broken tile is cut like the goal sink:
                # the tiles around the hole hide what has gone below the top.
                away=tip is None
                if tip is not None:
                    step=[0,0];step[tip[0]]=tip[1]
                    away=self.camera.depth(step[0],step[1],0)<self.camera.depth(0,0,0)
                under=[]
                for vertices,active,moving in tagged:
                    if not moving:continue
                    vertices,indices=bevel_mesh(vertices,.04,uniform=True)
                    color=tuple(min(255,c+18) for c in self.BLOCK) if active else self.BLOCK
                    if away:
                        vertices,indices=clip_below_floor(vertices,indices,above=False)
                    else:
                        indices=[f for f in indices if max(vertices[i][2] for i in f)<0]
                    under.extend(self._faces(vertices,color,faces=indices,player=True,cut=away and dropping))
                for _,pts,color,cut in sorted(under,key=lambda item:item[0]):self._block_face(self._frame,pts,color,cut)
            else:
                sinking=bool(motion and motion.sinking)
                meshes=sink_meshes(motion) if sinking else motion_meshes(motion) if motion else state_meshes(state)
            self._frame.blit(self._base,(0,0))
            # Work only on the small projected shadow footprint, not the full viewport.
            shadow_meshes=([(v,a) for v,a,moving in tagged if not moving] if falling and dropping
                           else [] if motion and motion.sinking else meshes)
            hulls=[self._hull([self.project((r+z*.65,c-z*.16,.01)) for r,c,z in vertices]) for vertices,_ in shadow_meshes]
            all_points=[p for hull in hulls for p in hull]
            bounds=pygame.Rect(0,0,0,0)
            if all_points:
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
            moving=[m for _,_,m in tagged] if falling else [False]*len(meshes)
            for (vertices,active),mesh_moving in zip(meshes,moving):
                vertices,indices=bevel_mesh(vertices,.04,uniform=True)
                color=tuple(min(255,c+18) for c in self.BLOCK) if active else self.BLOCK
                if falling and away:  # the part below the board was already drawn under it
                    vertices,indices=clip_below_floor(vertices,indices)
                elif falling:
                    indices=[f for f in indices if max(vertices[i][2] for i in f)>=0]
                elif motion and motion.sinking:  # the hole swallows what is below the floor
                    vertices,indices=clip_below_floor(vertices,indices)
                faces.extend(self._faces(vertices,color,faces=indices,player=True,
                                         cut=falling and away and dropping and mesh_moving))
            for _,pts,color,cut in sorted(faces,key=lambda item:item[0]):self._block_face(self._frame,pts,color,cut)
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
            if len(self.material_cache)>3000:self.material_cache.clear()  # ~1 large board + its bridges
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
        if self.style=='dream':
            # Fine ceramic grain beneath the existing pastel terrazzo chips.
            rng=random.Random(103)
            for _ in range(180):
                u,v=rng.uniform(.02,.98),rng.uniform(.02,.98)
                p=(a[0]+(b[0]-a[0])*u+(d[0]-a[0])*v,a[1]+(b[1]-a[1])*u+(d[1]-a[1])*v)
                delta=rng.choice((-6,-3,3,6))
                pygame.draw.line(surface,tuple(max(0,min(255,c+delta)) for c in color),p,p)
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

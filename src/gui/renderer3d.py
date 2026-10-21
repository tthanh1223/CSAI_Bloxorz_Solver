"""Isometric board with physical edge-pivot animation, using Pygame polygons."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
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
VIEWS = ('iso', 'original')
DEFAULT_VIEW = 'iso'
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
    """Rotate about the leading ground edge with inertia cresting and impact cushion."""
    axis = 0 if action in (Action.UP, Action.DOWN) else 1
    positive = action in (Action.DOWN, Action.RIGHT)
    pivot = (max if positive else min)(p[axis] for p in vertices)

    # Physical inertia cresting curve: initial push resistance -> acceleration over crest
    p = max(0.0, min(1.0, progress))
    eased_p = p * (1.0 - sin(pi * p) * 0.16)
    angle = eased_p * pi / 2 * (1 if positive else -1)

    # Impact landing cushion / squash damping on contact
    squash = (sin(pi * (p - 0.84) / 0.16) * 0.038) if p > 0.84 else 0.0

    result = []
    for point in vertices:
        v = list(point)
        offset, z = point[axis] - pivot, point[2]
        v[axis] = pivot + offset * cos(angle) + z * sin(angle)
        v[2] = -offset * sin(angle) + z * cos(angle)
        if squash > 0.001 and v[2] > 0.01:
            v[2] = v[2] * (1.0 - squash)
            v[axis] += (v[axis] - pivot) * squash * 0.35
        result.append(tuple(v))
    return result


def motion_meshes(motion: MotionFrame) -> list[tuple[list[Point], bool]]:
    before, after, action = motion.before, motion.after, motion.action
    if action == Action.SPACE:
        t = motion.progress
        # Micro-bob jump on the selected active cube
        hop = sin(pi * t) * 0.18
        meshes = state_meshes(after if t >= 0.5 else before)
        return [([(r, c, z + (hop if i == after.active_cube else 0.0)) for r, c, z in v], active)
                for i, (v, active) in enumerate(meshes)]
    raw = BloxorzProblem.roll_block(before, action)
    teleport = raw is not None and (raw.pos1, raw.pos2, raw.orientation) != (
        after.pos1, after.pos2, after.orientation)
    roll_progress = min(1.0, motion.progress / 0.65) if teleport else motion.progress
    meshes = state_meshes(before)
    rotated = [(rotate_mesh(v, action, roll_progress)
                if before.orientation != Orientation.SPLIT or i == before.active_cube else v, active)
               for i, (v, active) in enumerate(meshes)]
    if teleport and motion.progress > 0.65:
        # Magnetic snap curve on merge/teleport
        t = (motion.progress - 0.65) / 0.35
        snap_t = t * t * (3.0 - 2.0 * t)  # Smoothstep magnetic convergence
        assert raw is not None
        r, c = raw.pos1
        source = [cuboid(r, c, z, 1, 1, 1) for z in (0, 1)]
        return [([tuple(a + (b - a) * snap_t for a, b in zip(p, q))
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
        self._frame = pygame.Surface(self.size, pygame.SRCALPHA)
        self._base = pygame.Surface(self.size, pygame.SRCALPHA)
        self._top_mask = pygame.Surface(self.size, pygame.SRCALPHA)
        self._shadow_surf = None
        self._tile_sprites = []

    def set_stage(self, stage: StageData) -> None:
        self.stage = stage
        self.bridge_cells = {cell: i for i, cells in enumerate(stage.bridges.values()) for cell in cells}
        self.resize(self.size)
        self._static_key=None
        self._frame_key=None
        self.material_cache.clear()
        self._tile_sprites = []

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
        # Collect active cells to ground the 3D board to the background environment
        active_cells = []
        for r, row in enumerate(self.stage.grid):
            for c, tile in enumerate(row):
                coord = (r, c)
                bridge = self.bridge_cells.get(coord)
                if bridge is not None:
                    if bridge < len(shown.bridges_status) and shown.bridges_status[bridge]:
                        active_cells.append(coord)
                elif tile != TileType.VOID and coord != broken:
                    active_cells.append(coord)

        # Volumetric under-island ambient drop shadow for all 3 themes
        # Grounds the floating stage, giving realistic depth and weight in mid-air
        shadow_colors = {
            'dream': (120, 70, 98, 100),       # Soft dreamy lavender-mauve shadow onto clouds
            'forest': (14, 26, 18, 140),       # Deep misty canopy shadow
            'blueprint': (8, 22, 38, 120),     # Blueprint drafting depth shadow
        }
        shadow_color = shadow_colors.get(self.style, (25, 25, 35, 100))
        shadow_surf = pygame.Surface(self.size, pygame.SRCALPHA)
        for r, c in active_cells:
            fp = [self.project((r + dr, c + dc, -0.58)) for dr, dc in ((0, 0), (0, 1), (1, 1), (1, 0))]
            pygame.draw.polygon(shadow_surf, shadow_color, fp)

        sw, sh = self.size
        # Pass 1: Broad diffused ambient drop shadow (offset +14px down)
        tiny1 = pygame.transform.smoothscale(shadow_surf, (max(1, sw // 6), max(1, sh // 6)))
        soft1 = pygame.transform.smoothscale(tiny1, (sw, sh))

        # Pass 2: Closer contact drop shadow (offset +6px down)
        tiny2 = pygame.transform.smoothscale(shadow_surf, (max(1, sw // 3), max(1, sh // 3)))
        soft2 = pygame.transform.smoothscale(tiny2, (sw, sh))

        self._shadow_surf = pygame.Surface(self.size, pygame.SRCALPHA)
        self._shadow_surf.blit(soft1, (0, 14))
        self._shadow_surf.blit(soft2, (0, 6))
        self._base.blit(self._shadow_surf, (0, 0))

        if self.style == 'blueprint':
            # Blueprint datum floor footprint & architectural projection lines
            for r, c in active_cells:
                fp = [self.project((r + dr, c + dc, -0.62)) for dr, dc in ((0, 0), (0, 1), (1, 1), (1, 0))]
                pygame.draw.polygon(self._base, (20, 52, 78, 55), fp)
                pygame.draw.aalines(self._base, (48, 130, 160, 60), True, fp)
            corners = set()
            for r, c in active_cells:
                for dr, dc in ((0, 0), (0, 1), (1, 1), (1, 0)):
                    corners.add((r + dr, c + dc))
            for cr, cc in corners:
                adjacent = sum((cr - dr, cc - dc) in active_cells for dr in (0, 1) for dc in (0, 1))
                if adjacent < 4:
                    top_p = self.project((cr, cc, -0.32))
                    bot_p = self.project((cr, cc, -0.62))
                    for st in range(0, 8, 2):
                        t1, t2 = st / 8, (st + 1) / 8
                        pa = (top_p[0] + (bot_p[0] - top_p[0]) * t1, top_p[1] + (bot_p[1] - top_p[1]) * t1)
                        pb = (top_p[0] + (bot_p[0] - top_p[0]) * t2, top_p[1] + (bot_p[1] - top_p[1]) * t2)
                        pygame.draw.line(self._base, (64, 168, 196, 75), pa, pb, 1)
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
                vertices,indices=bevel_mesh(cuboid(r+.012,c+.012,-.32,.976,.976,.32),.02)
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
            elif kind=='marker':self._marker(self._base,*payload)
            else:pygame.draw.aalines(self._base,(139,105,123),True,payload)
        seam = {'dream': (202, 178, 184), 'blueprint': (48, 112, 140), 'forest': (102, 112, 80)}.get(self.style, (168, 174, 163))
        seams = pygame.Surface(self.size, pygame.SRCALPHA)
        for outline in tile_outlines:
            pygame.draw.aalines(seams, (*seam, 165), True, outline)
        self._base.blit(seams, (0, 0))
        if self.style == 'forest':
            self._moss_edges(shown)

        # Pre-render individual tile sprites for 60 FPS lag-free assembly and disassembly
        self._tile_sprites = []
        grid = self.stage.grid
        r_mid = len(grid) / 2.0
        c_mid = len(grid[0]) / 2.0
        max_d = max(1.0, (r_mid ** 2 + c_mid ** 2) ** 0.5)
        for r, row in enumerate(self.stage.grid):
            for c, tile in enumerate(row):
                coord = (r, c)
                bridge = self.bridge_cells.get(coord)
                if bridge is not None:
                    if bridge >= len(shown.bridges_status) or not shown.bridges_status[bridge]:
                        continue
                elif tile == TileType.VOID or coord == broken:
                    continue
                color = (112, 145, 151) if bridge is not None else ((178, 200, 193) if self.high_contrast else self.FLOOR)
                if tile == TileType.FRAGILE:
                    color = self.FRAGILE
                vertices, indices = bevel_mesh(cuboid(r + .012, c + .012, -.32, .976, .976, .32), .02)
                t_faces = self._faces(vertices, color, faces=indices)
                top = [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]
                all_pts = [p for _, pts, _, _ in t_faces for p in pts] + top
                min_x = floor(min(p[0] for p in all_pts)) - 2
                max_x = ceil(max(p[0] for p in all_pts)) + 2
                min_y = floor(min(p[1] for p in all_pts)) - 2
                max_y = ceil(max(p[1] for p in all_pts)) + 2
                spr_w = max(4, max_x - min_x + 1)
                spr_h = max(4, max_y - min_y + 1)
                tile_surf = pygame.Surface((spr_w, spr_h), pygame.SRCALPHA)
                for depth, pts, ink, edge in sorted(t_faces, key=lambda it: it[0]):
                    local_pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
                    if len(local_pts) == 4:
                        self._material(tile_surf, local_pts, ink)
                    else:
                        pygame.draw.polygon(tile_surf, ink, local_pts)
                local_top = [(p[0] - min_x, p[1] - min_y) for p in top]
                pygame.draw.aalines(tile_surf, (*seam, 165), True, local_top)
                label = 'goal' if coord == self.stage.goal else '!' if tile == TileType.FRAGILE else ''
                if coord in self.stage.switches:
                    label = {'SOFT': 'O', 'HEAVY': 'X', 'SPLIT': '<>'}[self.stage.switches[coord].type.value]
                if label:
                    self._marker(tile_surf, (r + .5, c + .5, .01), label, offset=(min_x, min_y))
                tile_depth = self.camera.depth(r + .5, c + .5, 0)
                d = ((r - r_mid) ** 2 + (c - c_mid) ** 2) ** 0.5
                delay = (d / max_d) * 0.22
                seed = r * 137 + c * 89
                theta_base = (seed % 360) * pi / 180.0 + (seed % 5) * 0.3
                radius_base = 160.0 + (seed % 8) * 20.0
                self._tile_sprites.append((tile_depth, tile_surf, (min_x, min_y), (r, c), delay, theta_base, radius_base))

        self._tile_sprites.sort(key=lambda it: it[0])

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

    def _block_face(self, surface, points, color, cut=None):
        pts = [(round(x), round(y)) for x, y in points]
        if not self._can_texture(surface, pts):
            return

        min_x = min(p[0] for p in pts); max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts); max_y = max(p[1] for p in pts)
        bw = max(2, max_x - min_x + 1)
        bh = max(2, max_y - min_y + 1)
        strength = min(1.3, max(0.5, sum(color) / 540.0))

        if self.style == 'forest':
            # Warm ancient sunlit gold & rich bronze-amber gradient (streamlined, no yellow clutter)
            c_top = tuple(min(255, int(c * strength)) for c in (255, 240, 172))  # Sunlit luminous gold crown
            c_mid = tuple(min(255, int(c * strength)) for c in (226, 174, 62))   # Warm radiant amber gold
            c_bot = tuple(min(255, int(c * strength)) for c in (148, 102, 28))   # Deep burnished bronze
            edge_color = tuple(min(255, int(c * 1.12)) for c in c_top)
            sheen_color = (255, 255, 235, 75)
            sparkle_colors = ((255, 255, 220, 240), (255, 240, 160, 200), (245, 205, 90, 180), (255, 248, 225, 220))
            seam_dark = (88, 58, 16)
            seam_light = (255, 238, 145)

        elif self.style == 'blueprint':
            # Architectural terracotta laser orange gradient matching blueprint technical drafting
            c_top = tuple(min(255, int(c * strength)) for c in (255, 172, 115))  # Luminous coral terracotta crown
            c_mid = tuple(min(255, int(c * strength)) for c in (228, 92, 38))    # Vibrant drafting terracotta
            c_bot = tuple(min(255, int(c * strength)) for c in (148, 48, 20))    # Deep burnt sienna
            edge_color = (255, 185, 140) if sum(color) > 300 else (210, 110, 60)
            sheen_color = (255, 225, 205, 80)
            sparkle_colors = ((255, 240, 230, 230), (255, 200, 165, 200), (255, 160, 110, 180), (255, 250, 245, 210))
            seam_dark = (68, 20, 10)
            seam_light = (255, 160, 120)

        else:  # 'dream' and default
            # Multi-shade pink gradient with crystalline sparkles matching pastel dream sky
            c_top = tuple(min(255, int(c * strength)) for c in (255, 226, 236))  # Luminous peach-pink crown
            c_mid = tuple(min(255, int(c * strength)) for c in (246, 148, 178))  # Radiant rose blossom
            c_bot = tuple(min(255, int(c * strength)) for c in (210, 98, 140))   # Deep dusk twilight rose
            edge_color = tuple(min(255, int(c * 1.15)) for c in c_top)
            sheen_color = (255, 255, 255, 80)
            sparkle_colors = ((255, 255, 255, 230), (255, 235, 245, 200), (255, 218, 235, 190), (255, 248, 220, 210))
            seam_dark = (198, 92, 132)
            seam_light = (255, 230, 242)

        # Render 3-stop vertical gradient
        grad = pygame.Surface((bw, bh), pygame.SRCALPHA)
        for y in range(bh):
            t = y / max(1, bh - 1)
            if t < 0.5:
                t2 = t * 2.0
                c = tuple(int(a + (b - a) * t2) for a, b in zip(c_top, c_mid))
            else:
                t2 = (t - 0.5) * 2.0
                c = tuple(int(a + (b - a) * t2) for a, b in zip(c_mid, c_bot))
            pygame.draw.line(grad, (*c, 255), (0, y), (bw, y))

        # Diagonal luster / sheen band
        sheen_y = int(bh * 0.25)
        pygame.draw.line(grad, sheen_color, (0, sheen_y), (bw, sheen_y + int(bh * 0.18)), 2)

        # Embedded theme-coherent sparkles & glints
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        seed = int(abs(cx * 73 + cy * 127)) % 10000
        rng = random.Random(seed)

        # Micro-sparkle flecks
        for _ in range(max(4, min(14, (bw * bh) // 120))):
            gx = rng.randint(1, max(1, bw - 2))
            gy = rng.randint(1, max(1, bh - 2))
            grad.set_at((gx, gy), rng.choice(sparkle_colors))

        # Diamond accent glints
        for _ in range(max(1, min(4, (bw * bh) // 320))):
            sx = rng.randint(3, max(3, bw - 4))
            sy = rng.randint(3, max(3, bh - 4))
            grad.set_at((sx, sy), (255, 255, 255, 255))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if 0 <= sx + dx < bw and 0 <= sy + dy < bh:
                    grad.set_at((sx + dx, sy + dy), sparkle_colors[0])

        # Mask exactly to polygon
        local_pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
        mask = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), local_pts)
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, (min_x, min_y))

        # Smooth contour outline
        self._outline(surface, edge_color, pts, cut)

        # Tactile center dividing seam across elongated faces (1x1x2 block division)
        if len(pts) == 4:
            d01 = (pts[1][0] - pts[0][0]) ** 2 + (pts[1][1] - pts[0][1]) ** 2
            d12 = (pts[2][0] - pts[1][0]) ** 2 + (pts[2][1] - pts[1][1]) ** 2
            if d01 > d12 * 2.2:
                m0 = ((pts[0][0] + pts[1][0]) // 2, (pts[0][1] + pts[1][1]) // 2)
                m1 = ((pts[3][0] + pts[2][0]) // 2, (pts[3][1] + pts[2][1]) // 2)
                pygame.draw.aaline(surface, seam_dark, m0, m1)
                pygame.draw.aaline(surface, seam_light, (m0[0] + 1, m0[1]), (m1[0] + 1, m1[1]))
            elif d12 > d01 * 2.2:
                m0 = ((pts[1][0] + pts[2][0]) // 2, (pts[1][1] + pts[2][1]) // 2)
                m1 = ((pts[0][0] + pts[3][0]) // 2, (pts[0][1] + pts[3][1]) // 2)
                pygame.draw.aaline(surface, seam_dark, m0, m1)
                pygame.draw.aaline(surface, seam_light, (m0[0], m0[1] + 1), (m1[0], m1[1] + 1))

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

    def draw(self, surface, state, motion=None, intro_t=None, outro_t=None, shockwave=None):
        if surface.get_size() != self.size:
            self.resize(surface.get_size())
        if self._frame.get_size() != self.size:
            self._frame = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.stage is None:
            surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            return

        shown = motion.before if motion and motion.progress < .65 else state
        broken = (self._broken_tile(motion.after)
                  if motion and motion.falling and motion.progress >= FALL_ROLL_END else None)
        static_key = (self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast, shown.bridges_status, broken)
        material_key = (self.size, self.camera, self.zoom, self.high_contrast, self.style)
        if material_key != self._material_key:
            self.material_cache.clear()
            self._material_key = material_key
        if static_key != self._static_key:
            self._build_static(shown, broken)
            self._static_key = static_key

        if intro_t is not None:
            # Map Assembly Intro: Chaotic multi-directional arrival, with shadow ONLY appearing after map is formed
            self._frame.fill((0, 0, 0, 0))
            if getattr(self, '_shadow_surf', None) is not None and intro_t >= 0.58:
                shadow_p = max(0.0, min(1.0, (intro_t - 0.58) / 0.38))
                shadow_alpha = int(255 * (shadow_p ** 1.8))
                if shadow_alpha > 0:
                    self._shadow_surf.set_alpha(shadow_alpha)
                    self._frame.blit(self._shadow_surf, (0, 0))
                    self._shadow_surf.set_alpha(255)

            for depth, spr, (x0, y0), (r, c), delay, theta_base, radius_base in self._tile_sprites:
                p = max(0.0, min(1.0, (intro_t - delay) / 0.55))
                ease = 1.0 - (1.0 - p) ** 3
                scatter_dist = radius_base * 0.70
                dx = int(cos(theta_base) * scatter_dist * (1.0 - ease))
                dy = int((140.0 + sin(theta_base) * scatter_dist * 0.40) * (1.0 - ease))
                spr_alpha = min(255, int(p * 320))
                if spr_alpha > 0:
                    if spr_alpha < 255:
                        spr.set_alpha(spr_alpha)
                        self._frame.blit(spr, (x0 + dx, y0 + dy))
                        spr.set_alpha(255)
                    else:
                        self._frame.blit(spr, (x0 + dx, y0 + dy))

            # Block falling down from above after tiles begin assembling
            block_p = max(0.0, min(1.0, (intro_t - 0.35) / 0.65))
            if block_p > 0.0:
                block_ease = 1.0 - (1.0 - block_p) ** 3
                block_dz = 7.0 * (1.0 - block_ease)
                meshes = state_meshes(state)
                block_faces = []
                for vertices, active in meshes:
                    v_elevated = [(r, c, z + block_dz) for r, c, z in vertices]
                    v_elevated, indices = bevel_mesh(v_elevated, 0.04, uniform=True)
                    color = tuple(min(255, c + 18) for c in self.BLOCK) if active else self.BLOCK
                    block_faces.extend(self._faces(v_elevated, color, faces=indices, player=True))
                for _, pts, color, cut in sorted(block_faces, key=lambda it: it[0]):
                    self._block_face(self._frame, pts, color, cut)

            surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            surface.blit(self._frame, (0, 0))
            self._frame_key = None
            return

        if outro_t is not None:
            # Map Disassembly Outro (silky smooth chaotic swirling orbit at 60 FPS)
            self._frame.fill((0, 0, 0, 0))
            if getattr(self, '_shadow_surf', None) is not None:
                p = min(1.0, max(0.0, outro_t))
                shadow_alpha = int(255 * max(0.0, 1.0 - p * 1.5))
                if shadow_alpha > 0:
                    self._shadow_surf.set_alpha(shadow_alpha)
                    self._frame.blit(self._shadow_surf, (0, 0))
                    self._shadow_surf.set_alpha(255)

            for depth, spr, (x0, y0), (r, c), delay, theta_base, radius_base in self._tile_sprites:
                theta = theta_base + p * 3.8
                radius = p * radius_base
                dx = int(cos(theta) * radius)
                dy = int(sin(theta) * radius * 0.65 + p * p * 90.0)
                alpha = int(255 * max(0.0, 1.0 - p * 1.4))
                if alpha > 0:
                    spr.set_alpha(alpha)
                    self._frame.blit(spr, (x0 + dx, y0 + dy))
                    spr.set_alpha(255)

            surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            surface.blit(self._frame, (0, 0))
            self._frame_key = None
            return
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
            # Physical switch depression when stepped on
            for coord in (shown.pos1, shown.pos2):
                if coord in self.stage.switches:
                    sw_type = self.stage.switches[coord].type.value
                    sw_label = {'SOFT': 'O', 'HEAVY': 'X', 'SPLIT': '<>'}[sw_type]
                    r, c = coord
                    tile_top = [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]
                    bridge = self.bridge_cells.get(coord)
                    color = (112, 145, 151) if bridge is not None else ((178, 200, 193) if self.high_contrast else self.FLOOR)
                    self._material(self._frame, tile_top, color)
                    self._marker(self._frame, (r + 0.5, c + 0.5, -0.05), sw_label)

            # Dynamic mechanical bridge ascension / descent
            if motion and motion.before.bridges_status != motion.after.bridges_status:
                b_p = max(0.0, min(1.0, (motion.progress - 0.25) / 0.75))
                b_ease = 1.0 - (1.0 - b_p) ** 3
                for coord, b_idx in self.bridge_cells.items():
                    if b_idx < len(motion.before.bridges_status) and b_idx < len(motion.after.bridges_status):
                        old_s = motion.before.bridges_status[b_idx]
                        new_s = motion.after.bridges_status[b_idx]
                        if old_s != new_s:
                            br_r, br_c = coord
                            if not old_s and new_s:
                                # Bridge Opening: Smooth hydraulic ascension from the abyss
                                b_z = -2.8 * (1.0 - b_ease)
                                b_col = (135, 175, 185) if not self.high_contrast else (195, 220, 230)
                                b_verts, b_idx_list = bevel_mesh(cuboid(br_r + .012, br_c + .012, b_z - .32, .976, .976, .32), .02)
                                for _, b_pts, b_ink, _ in sorted(self._faces(b_verts, b_col, faces=b_idx_list), key=lambda it: it[0]):
                                    pygame.draw.polygon(self._frame, b_ink, b_pts)
                                pygame.draw.aalines(self._frame, (120, 240, 255), True, [self.project(p) for p in cuboid(br_r, br_c, b_z, 1, 1, 0)[:4]])
                            elif old_s and not new_s:
                                # Bridge Closing: Sinking down into the abyss with fading alpha
                                b_z = -4.5 * (b_p ** 1.8)
                                b_alpha = max(0, int(230 * (1.0 - b_p)))
                                if b_alpha > 0:
                                    b_surf = pygame.Surface(self.size, pygame.SRCALPHA)
                                    top_p = [self.project(p) for p in cuboid(br_r + .012, br_c + .012, b_z, .976, .976, 0)[:4]]
                                    pygame.draw.polygon(b_surf, (80, 110, 120, b_alpha), top_p)
                                    pygame.draw.aalines(b_surf, (160, 200, 215, b_alpha), True, top_p)
                                    self._frame.blit(b_surf, (0, 0))

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
                min_z = max(0.0, min((p[2] for vertices, _ in shadow_meshes for p in vertices), default=0.0))
                shadow_alpha = max(24, int(82 - min(min_z, 1.2) * 48))
                shadow_tint = {'dream': (92, 58, 88), 'forest': (18, 30, 22), 'blueprint': (14, 38, 54)}.get(self.style, (72, 52, 78))
                contact=pygame.Surface(bounds.size,pygame.SRCALPHA)
                for hull in hulls:
                    if len(hull)>=3:
                        pygame.draw.polygon(contact,(*shadow_tint, shadow_alpha),[(a-bounds.x,b-bounds.y) for a,b in hull])
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

            # Active Cube Holographic 3D Faceted Beacon in SPLIT mode
            if state.orientation == Orientation.SPLIT and not falling:
                act_coord = state.pos1 if state.active_cube == 0 else state.pos2
                ar, ac = act_coord
                ticks = pygame.time.get_ticks()
                z_mid = 1.62 + sin(ticks * 0.0055) * 0.13
                z_top = z_mid + 0.38
                z_bot = z_mid - 0.38
                rot_ang = ticks * 0.0035
                r_rad = 0.28

                eq = [self.project((ar + 0.5 + r_rad * cos(rot_ang + k * pi / 2),
                                    ac + 0.5 + r_rad * sin(rot_ang + k * pi / 2), z_mid)) for k in range(4)]
                top_p = self.project((ar + 0.5, ac + 0.5, z_top))
                bot_p = self.project((ar + 0.5, ac + 0.5, z_bot))

                c_light = (255, 245, 170, 235) if self.style == 'dream' else ((120, 255, 255, 235) if self.style == 'blueprint' else (180, 255, 190, 235))
                c_mid = (255, 150, 190, 215) if self.style == 'dream' else ((35, 190, 240, 215) if self.style == 'blueprint' else (65, 215, 125, 215))
                c_dark = (210, 95, 145, 195) if self.style == 'dream' else ((18, 125, 185, 195) if self.style == 'blueprint' else (35, 155, 80, 195))

                gem_surf = pygame.Surface(self.size, pygame.SRCALPHA)
                pygame.draw.polygon(gem_surf, c_light, [top_p, eq[0], eq[1]])
                pygame.draw.polygon(gem_surf, c_mid, [top_p, eq[1], eq[2]])
                pygame.draw.polygon(gem_surf, c_dark, [top_p, eq[2], eq[3]])
                pygame.draw.polygon(gem_surf, c_mid, [top_p, eq[3], eq[0]])

                pygame.draw.polygon(gem_surf, c_mid, [bot_p, eq[1], eq[0]])
                pygame.draw.polygon(gem_surf, c_dark, [bot_p, eq[2], eq[1]])
                pygame.draw.polygon(gem_surf, c_dark, [bot_p, eq[3], eq[2]])
                pygame.draw.polygon(gem_surf, c_mid, [bot_p, eq[0], eq[3]])

                for k in range(4):
                    pygame.draw.aaline(gem_surf, (255, 255, 255), top_p, eq[k])
                    pygame.draw.aaline(gem_surf, (255, 255, 255), bot_p, eq[k])
                    pygame.draw.aaline(gem_surf, (255, 255, 255), eq[k], eq[(k + 1) % 4])

                ring_pts = [self.project((ar + 0.5 + 0.36 * cos(rot_ang * 1.6 + i * pi / 8),
                                          ac + 0.5 + 0.36 * sin(rot_ang * 1.6 + i * pi / 8),
                                          z_mid + 0.05 * sin(i * pi / 4))) for i in range(16)]
                pygame.draw.aalines(gem_surf, (255, 255, 255), True, ring_pts)

                floor_ring = [self.project((ar + 0.5 + 0.44 * cos(i * pi / 8),
                                            ac + 0.5 + 0.44 * sin(i * pi / 8), 0.02)) for i in range(16)]
                pygame.draw.aalines(gem_surf, c_light[:3], True, floor_ring)

                self._frame.blit(gem_surf, (0, 0))

            # Fragile tile shatter, chunky stone shards & fine mineral dust particles
            if broken is not None and motion and motion.falling and motion.progress >= FALL_ROLL_END:
                br, bc = broken
                t = max(0.0, min(1.0, (motion.progress - FALL_ROLL_END) / (1.0 - FALL_ROLL_END)))

                sh_surf = pygame.Surface(self.size, pygame.SRCALPHA)
                shard_alpha = max(0, int(245 * (1.0 - t)))
                dz = -3.8 * (t ** 1.8)

                pts_ring = [
                    (br + 0.02, bc + 0.02), (br + 0.02, bc + 0.52), (br + 0.02, bc + 0.98),
                    (br + 0.98, bc + 0.98), (br + 0.98, bc + 0.48), (br + 0.98, bc + 0.02)
                ]
                center = (br + 0.48, bc + 0.52)
                for k in range(6):
                    p_a = pts_ring[k]
                    p_b = pts_ring[(k + 1) % 6]
                    dr = cos(k * pi / 3.0) * 0.48 * t
                    dc = sin(k * pi / 3.0) * 0.48 * t
                    top_shard = [self.project((p[0] + dr, p[1] + dc, dz)) for p in (center, p_a, p_b)]
                    sub_shard = [self.project((p[0] + dr, p[1] + dc, dz - 0.12)) for p in (p_a, p_b)]
                    pygame.draw.polygon(sh_surf, (35, 20, 15, shard_alpha), [top_shard[1], top_shard[2], sub_shard[1], sub_shard[0]])
                    sh_col = (*self.FRAGILE, shard_alpha)
                    pygame.draw.polygon(sh_surf, sh_col, top_shard)
                    pygame.draw.aalines(sh_surf, (255, 185, 110, shard_alpha), True, top_shard)

                for i in range(24):
                    seed = (br * 37 + bc * 79 + i * 19)
                    ang = (seed % 360) * pi / 180.0
                    spd = 0.18 + (seed % 10) * 0.04
                    d_r = br + 0.5 + cos(ang) * spd * (t ** 0.65)
                    d_c = bc + 0.5 + sin(ang) * spd * (t ** 0.65)
                    d_z = -1.4 * (t ** 1.3) - (seed % 6) * 0.06 * t
                    p_pt = self.project((d_r, d_c, d_z))
                    dust_a = max(0, int(210 * (1.0 - t) * (1.0 - t * 0.8)))
                    if dust_a > 0:
                        d_col = (250, 200, 130, dust_a) if i % 2 == 0 else (185, 165, 150, dust_a)
                        pygame.draw.circle(sh_surf, d_col, (round(p_pt[0]), round(p_pt[1])), 1 if i % 3 != 0 else 2)

                self._frame.blit(sh_surf, (0, 0))

            self._frame_key=key
        else:self.stats['frame_cache_hits']+=1
        surface.fill((0,0,0,0) if surface.get_flags()&pygame.SRCALPHA else self.BACKGROUND)
        surface.blit(self._frame,(0,0))

        # Expanding magnetic merge shockwave ring
        if shockwave is not None:
            sr, sc, st = shockwave
            p = max(0.0, min(1.0, st / 0.35))
            center = self.project((sr + 0.5, sc + 0.5, 0.02))
            rx = int((20.0 + p * 65.0) * self.zoom)
            ry = int(rx * 0.48)
            alpha = int(180 * (1.0 - p))
            if rx > 2 and ry > 2 and alpha > 0:
                wave_surf = pygame.Surface((rx * 2 + 4, ry * 2 + 4), pygame.SRCALPHA)
                wave_rect = pygame.Rect(2, 2, rx * 2, ry * 2)
                wave_color = (255, 235, 170, alpha) if self.style == 'dream' else ((60, 240, 255, alpha) if self.style == 'blueprint' else (160, 255, 140, alpha))
                pygame.draw.ellipse(wave_surf, wave_color, wave_rect, max(1, int(3 * (1.0 - p) * self.zoom)))
                surface.blit(wave_surf, (center[0] - rx - 2, center[1] - ry - 2))
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

    def _paint_material(self, surface, points, color):
        pygame.draw.polygon(surface, color, points)
        if self.style == 'forest' and getattr(self, 'stone_texture', None) is not None:
            self._stone_material(surface, points, color)
            return

        if self.style == 'dream':
            a, b, _, d = points
            warm = color[0] > color[1] * 1.12
            palette = ((248, 242, 218), (170, 152, 177), (186, 198, 183), (240, 211, 183), (251, 247, 229))
            for u, v, s, index in self.flecks:
                def at(x, y):
                    return (a[0] + (b[0] - a[0]) * x + (d[0] - a[0]) * y, a[1] + (b[1] - a[1]) * x + (d[1] - a[1]) * y)
                ink = tuple(min(255, max(0, c + (7 if index % 2 else -8))) for c in color) if warm else tuple(int(c * .25 + p * .75) for c, p in zip(color, palette[index]))
                pygame.draw.polygon(surface, ink, [at(u, v), at(u + s, v + s * .2), at(u + s * .4, v + s), at(u - s * .3, v + s * .5)])
            return

        if len(points) >= 4:
            highlight = tuple(min(255, c + 24) for c in color)
            shadow = tuple(max(0, c - 20) for c in color)
            pygame.draw.aaline(surface, highlight, points[0], points[1])
            pygame.draw.aaline(surface, highlight, points[1], points[2])
            pygame.draw.aaline(surface, shadow, points[2], points[3])
            pygame.draw.aaline(surface, shadow, points[3], points[0])
            if self.style == 'blueprint':
                tick_color = (min(255, color[0] + 32), min(255, color[1] + 38), min(255, color[2] + 42))
                for p in points:
                    pygame.draw.circle(surface, tick_color, (round(p[0]), round(p[1])), 1)

    def _stone_material(self, surface, points, color):
        width, height = surface.get_size()
        a, b, _, d = points
        top = abs((b[1] - a[1]) + (d[1] - a[1])) > 1 and abs(b[1] - d[1]) < 2
        source = pygame.transform.rotate(self.stone_texture, 45) if top else self.stone_texture
        texture = pygame.transform.smoothscale(source, (width, height))
        brightness = min(1.0, sum(color) / max(1, sum(self.FLOOR)))
        texture.fill((int(brightness * 255),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), points)
        rgba = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        rgba.blit(texture, (0, 0))
        rgba.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(rgba, (0, 0))

    def _moss_edges(self, shown):
        """Baked hanging moss only along exposed front-facing edges."""
        rng = random.Random(842)
        cells = set()
        for r, row in enumerate(self.stage.grid):
            for c, tile in enumerate(row):
                bridge = self.bridge_cells.get((r, c))
                if bridge is not None:
                    if bridge < len(shown.bridges_status) and shown.bridges_status[bridge]:
                        cells.add((r, c))
                elif tile != TileType.VOID:
                    cells.add((r, c))
        for r, c in cells:
            for neighbor, start, end in (((r + 1, c), (r + 1, c), (r + 1, c + 1)), ((r, c + 1), (r, c + 1), (r + 1, c + 1))):
                if neighbor in cells:
                    continue
                for _ in range(7):
                    t = rng.random()
                    rr = start[0] + (end[0] - start[0]) * t
                    cc = start[1] + (end[1] - start[1]) * t
                    x, y = self.project((rr, cc, -.05))
                    length = rng.uniform(.05, .28) * self.camera.tile_width * self.zoom
                    for i in range(max(2, int(length / 3))):
                        pygame.draw.circle(self._base, rng.choice(((64, 80, 30), (90, 109, 39), (120, 131, 54))),
                                           (round(x + rng.uniform(-2, 2)), round(y + i * 3)), max(1, round(self.zoom * 1.4)))

    def _marker(self, surface, point, kind, offset=(0, 0)):
        r, c, z = point
        ox, oy = offset
        def project(dr, dc, dz=0):
            p = self.project((r + dr, c + dc, z + dz))
            return (p[0] - ox, p[1] - oy)

        pressed = z < 0.0

        if kind == 'goal':
            # 3D Royal/Cosmic Vortex Sinkhole: Multi-layer concentric rim, 3D interior walls, and portal core
            outer_rim = [project(-.48, -.48), project(-.48, .48), project(.48, .48), project(.48, -.48)]
            mid_rim = [project(-.42, -.42), project(-.42, .42), project(.42, .42), project(.42, -.42)]
            hole = [project(-.36, -.36), project(-.36, .36), project(.36, .36), project(.36, -.36)]
            pit_deep = [project(dr * 0.72, dc * 0.72, -0.65) for dr, dc in ((-.36, -.36), (-.36, .36), (.36, .36), (.36, -.36))]
            pit_core = [project(dr * 0.35, dc * 0.35, -1.15) for dr, dc in ((-.36, -.36), (-.36, .36), (.36, .36), (.36, -.36))]

            collar_col = (215, 160, 52) if self.style == 'forest' else ((245, 165, 192) if self.style == 'dream' else (58, 172, 225))
            dark_collar = (90, 65, 20) if self.style == 'forest' else ((160, 88, 115) if self.style == 'dream' else (28, 78, 105))
            pygame.draw.polygon(surface, dark_collar, outer_rim)
            pygame.draw.polygon(surface, collar_col, mid_rim)

            pygame.draw.polygon(surface, (18, 22, 30), hole)
            pygame.draw.polygon(surface, (36, 44, 58), [hole[0], hole[1], pit_deep[1], pit_deep[0]])
            pygame.draw.polygon(surface, (24, 30, 42), [hole[0], pit_deep[0], pit_deep[3], hole[3]])
            pygame.draw.polygon(surface, (10, 14, 20), [pit_deep[0], pit_deep[1], pit_core[1], pit_core[0]])
            pygame.draw.polygon(surface, (4, 6, 10), pit_core)

            rivet_col = (255, 240, 180) if self.style != 'blueprint' else (180, 245, 255)
            for dr, dc in ((-.45, -.45), (-.45, .45), (.45, .45), (.45, -.45), (0, -.45), (0, .45), (-.45, 0), (.45, 0)):
                pt = project(dr, dc)
                pygame.draw.circle(surface, rivet_col, (round(pt[0]), round(pt[1])), 2)

            pygame.draw.aalines(surface, (255, 255, 255), True, hole)
            pygame.draw.aalines(surface, collar_col, True, outer_rim)

        elif kind == 'O':
            # SOFT SWITCH: Futuristic 3D Mechanical Dome Button with glowing amber ring & tech notches
            oct_pts = [project(0.35 * cos(i * pi / 8 + pi / 16), 0.35 * sin(i * pi / 8 + pi / 16)) for i in range(16)]
            collar_pts = [project(0.30 * cos(i * pi / 8 + pi / 16), 0.30 * sin(i * pi / 8 + pi / 16)) for i in range(16)]
            pygame.draw.polygon(surface, (20, 24, 32), oct_pts)
            pygame.draw.polygon(surface, (42, 48, 62) if not pressed else (28, 34, 44), collar_pts)

            ring_col = (255, 245, 140) if pressed else ((255, 192, 45) if not self.high_contrast else (255, 230, 70))
            led_pts = [project(0.24 * cos(i * pi / 12), 0.24 * sin(i * pi / 12)) for i in range(24)]
            pygame.draw.polygon(surface, ring_col, led_pts)

            btn_pts = [project(0.18 * cos(i * pi / 12), 0.18 * sin(i * pi / 12), 0.02 if not pressed else -0.02) for i in range(24)]
            btn_col = (255, 225, 95) if pressed else (235, 145, 28)
            pygame.draw.polygon(surface, btn_col, btn_pts)

            core_pts = [project(0.10 * cos(i * pi / 8), 0.10 * sin(i * pi / 8), 0.03 if not pressed else -0.01) for i in range(16)]
            pygame.draw.polygon(surface, (255, 255, 235), core_pts)

            for angle in (0, pi / 2, pi, 3 * pi / 2):
                p_in = project(0.18 * cos(angle), 0.18 * sin(angle))
                p_out = project(0.33 * cos(angle), 0.33 * sin(angle))
                pygame.draw.line(surface, (16, 20, 26), p_in, p_out, 2)

            pygame.draw.aalines(surface, (255, 255, 255), True, core_pts)
            pygame.draw.aalines(surface, (255, 240, 180), True, btn_pts)
            pygame.draw.aalines(surface, (16, 20, 26), True, oct_pts)

        elif kind == 'X':
            # HEAVY SWITCH: Heavy-Duty Industrial Hydraulic Stamped Plate with 4 Corner Hex Bolts & Ruby Core
            plate = [project(-.38, -.38), project(-.38, .38), project(.38, .38), project(.38, -.38)]
            inner_plate = [project(-.32, -.32), project(-.32, .32), project(.32, .32), project(.32, -.32)]
            pygame.draw.polygon(surface, (22, 26, 34), plate)
            pygame.draw.polygon(surface, (36, 42, 54) if not pressed else (24, 28, 38), inner_plate)

            for br_c, bc_c in ((-.30, -.30), (-.30, .30), (.30, .30), (.30, -.30)):
                bolt = [project(br_c + 0.038 * cos(i * pi / 3), bc_c + 0.038 * sin(i * pi / 3)) for i in range(6)]
                pygame.draw.polygon(surface, (180, 190, 205), bolt)
                c_pt = project(br_c, bc_c)
                pygame.draw.circle(surface, (30, 35, 45), (round(c_pt[0]), round(c_pt[1])), 1)

            arm_w = 0.088
            arm_l = 0.27
            dz_arm = 0.025 if not pressed else -0.02
            p1 = [
                project(-arm_l, -arm_l + arm_w, dz_arm),
                project(-arm_l + arm_w, -arm_l, dz_arm),
                project(arm_l, arm_l - arm_w, dz_arm),
                project(arm_l - arm_w, arm_l, dz_arm)
            ]
            p2 = [
                project(-arm_l, arm_l - arm_w, dz_arm),
                project(-arm_l + arm_w, arm_l, dz_arm),
                project(arm_l, -arm_l + arm_w, dz_arm),
                project(arm_l - arm_w, -arm_l, dz_arm)
            ]
            x_col = (255, 95, 80) if pressed else ((235, 52, 42) if not self.high_contrast else (255, 40, 40))
            x_shadow = (140, 24, 18)
            pygame.draw.polygon(surface, x_shadow, p1)
            pygame.draw.polygon(surface, x_col, p1)
            pygame.draw.polygon(surface, x_col, p2)

            pygame.draw.aalines(surface, (255, 220, 215) if pressed else (255, 195, 185), True, p1)
            pygame.draw.aalines(surface, (255, 220, 215) if pressed else (255, 195, 185), True, p2)

            ruby_core = [project(0.08 * cos(i * pi / 4), 0.08 * sin(i * pi / 4), dz_arm + 0.01) for i in range(8)]
            pygame.draw.polygon(surface, (255, 255, 255) if pressed else (255, 230, 230), ruby_core)
            pygame.draw.aalines(surface, (255, 255, 255), True, ruby_core)
            pygame.draw.aalines(surface, (60, 72, 90), True, inner_plate)
            pygame.draw.aalines(surface, (14, 18, 24), True, plate)

        elif kind == '<>':
            # SPLIT SWITCH: Sci-Fi Quantum Teleport Conduit with Dual Prism Pylons & Energy Rift
            base_pts = [project(-.38, 0), project(0, .38), project(.38, 0), project(0, -.38)]
            inner_base = [project(-.32, 0), project(0, .32), project(.32, 0), project(0, -.32)]
            pygame.draw.polygon(surface, (14, 26, 38), base_pts)
            pygame.draw.polygon(surface, (24, 46, 64) if not pressed else (18, 34, 48), inner_base)

            cyan_glow = (160, 255, 255) if pressed else (44, 225, 245)
            cyan_face = (90, 210, 235) if pressed else (28, 160, 185)

            c_left_top = [project(-.22, -.06, .03), project(0, -.26, .03), project(.22, -.06, .03),
                          project(.15, -.02, .03), project(0, -.18, .03), project(-.15, -.02, .03)]
            c_right_top = [project(-.22, .06, .03), project(0, .26, .03), project(.22, .06, .03),
                           project(.15, .02, .03), project(0, .18, .03), project(-.15, .02, .03)]

            pygame.draw.polygon(surface, cyan_face, c_left_top)
            pygame.draw.polygon(surface, cyan_face, c_right_top)
            pygame.draw.aalines(surface, cyan_glow, True, c_left_top)
            pygame.draw.aalines(surface, cyan_glow, True, c_right_top)

            pygame.draw.aaline(surface, (255, 255, 255), project(-.18, -.05, .04), project(0, -.22, .04))
            pygame.draw.aaline(surface, (255, 255, 255), project(0, -.22, .04), project(.18, -.05, .04))
            pygame.draw.aaline(surface, (255, 255, 255), project(-.18, .05, .04), project(0, .22, .04))
            pygame.draw.aaline(surface, (255, 255, 255), project(0, .22, .04), project(.18, .05, .04))

            pygame.draw.aaline(surface, (255, 255, 255), project(-.24, 0), project(.24, 0))
            for offset_r in (-.14, 0, .14):
                n_pt = project(offset_r, 0)
                pygame.draw.circle(surface, (255, 255, 255), (round(n_pt[0]), round(n_pt[1])), 2)

            pygame.draw.aalines(surface, (60, 140, 180), True, inner_base)
            pygame.draw.aalines(surface, (12, 22, 32), True, base_pts)

        elif kind == '!':
            # FRAGILE TILE: High-detail Shattered Glass / Crystalline Fault Network with warning glow
            dark_crack = (38, 22, 16)
            crack_accent = (255, 145, 45)
            cracks = [
                [project(-.45, -.35), project(-.26, -.16), project(-.08, -.04), project(0, 0)],
                [project(-.42, .38), project(-.22, .18), project(-.06, .06), project(0, 0)],
                [project(.44, .36), project(.24, .18), project(.08, .06), project(0, 0)],
                [project(.42, -.38), project(.22, -.20), project(.06, -.06), project(0, 0)],
                [project(-.02, -.44), project(-.02, -.22), project(0, 0)],
                [project(.02, .44), project(.02, .22), project(0, 0)],
                [project(-.26, -.16), project(-.35, .06), project(-.22, .18)],
                [project(.22, -.20), project(.35, -.06), project(.24, .18)]
            ]
            for crack in cracks:
                pygame.draw.lines(surface, dark_crack, False, crack, 2)
                pygame.draw.aalines(surface, crack_accent, False, crack)

            f_pad = [project(0, -.18), project(-.18, 0), project(0, .18), project(.18, 0)]
            pygame.draw.polygon(surface, (68, 38, 24), f_pad)
            pygame.draw.aalines(surface, (255, 175, 60), True, f_pad)
            c_pt = project(0, 0)
            pygame.draw.circle(surface, (255, 205, 100), (round(c_pt[0]), round(c_pt[1])), 2)

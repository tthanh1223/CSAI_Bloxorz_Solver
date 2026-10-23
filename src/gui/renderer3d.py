"""Isometric board with physical edge-pivot animation, using Pygame polygons."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
from math import cos, sin, pi, floor, ceil
import random
import time
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


# Floor tiles are separate chunky slabs (see _build_static).
TILE_GAP = .03            # inset on each side, so neighbouring slabs show a seam
TILE_BEVEL = .035         # rounded top edge
TILE_THICKNESS = {'iso': .5, 'original': .55}  # in block units

# One key light for floor and block, from the front-left and above, as a unit
# vector in (row, col, z): top faces brightest, the front-left side medium,
# the right side in shade, so every slab and the block read as solid 3D.
_LIGHT = (.35, -.55, 1.0)
LIGHT = tuple(v / sum(w * w for w in _LIGHT) ** .5 for v in _LIGHT)


# Switches are raised push buttons: (base colour, height in block units).
SWITCH_BUTTONS = {
    'O':  ((158, 170, 194), .11),  # soft switch: round pale slate button
    'X':  ((222, 140, 122), .12),  # heavy switch: soft coral cross
    '<>': ((136, 174, 218), .11),  # split switch: round pale blue button
}


def tile_thickness(view: str) -> float:
    return TILE_THICKNESS.get(view, .3)


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


class _Bridges:
    """Stand-in for a GameState where only bridges_status is read (board composition)."""
    __slots__ = ('bridges_status',)

    def __init__(self, bridges_status):
        self.bridges_status = bridges_status


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


def rotate_mesh(vertices: list[Point], action: Action, progress: float,
                before_orient: Orientation | None = None,
                after_orient: Orientation | None = None) -> list[Point]:
    """Rotate about the leading ground edge with center-of-mass inertia and impact cushion."""
    axis = 0 if action in (Action.UP, Action.DOWN) else 1
    positive = action in (Action.DOWN, Action.RIGHT)
    pivot = (max if positive else min)(p[axis] for p in vertices)

    p = max(0.0, min(1.0, progress))

    # Center-of-mass differentiation:
    if before_orient == Orientation.STANDING and after_orient in (Orientation.LYING_H, Orientation.LYING_V):
        # STANDING -> LYING: Falling from z=1.0 to z=0.5 -> Gravity accelerates over crest
        eased_p = p * (1.0 + (1.0 - p) * 0.14)
        angle = eased_p * pi / 2 * (1 if positive else -1)
        # Heavy solid thud landing cushion
        squash = (sin(pi * (p - 0.78) / 0.22) * 0.052) if p > 0.78 else 0.0
    elif before_orient in (Orientation.LYING_H, Orientation.LYING_V) and after_orient == Orientation.STANDING:
        # LYING -> STANDING: Lifting from z=0.5 to z=1.0 -> Effort to crest, then snapping into upright lock
        eased_p = p * (1.0 - sin(pi * p) * 0.22)
        angle = eased_p * pi / 2 * (1 if positive else -1)
        # Upright rebound damping
        squash = (sin(pi * (p - 0.85) / 0.15) * 0.024) if p > 0.85 else 0.0
    else:
        # LYING -> LYING or SPLIT: Smooth balanced roll
        eased_p = p * (1.0 - sin(pi * p) * 0.16)
        angle = eased_p * pi / 2 * (1 if positive else -1)
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
    rotated = [(rotate_mesh(v, action, roll_progress, before.orientation, after.orientation)
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
                if t > 0.35:
                    tumble = (t - 0.35) * 1.4
                    axis_tumble = 1 if tip[0] == 0 else 0
                    c_mid = sum(p[axis_tumble] for p in vertices) / len(vertices)
                    ang_tumble = sin(tumble * pi * 0.8) * 0.45 * tip[1]
                    tumbled = []
                    for r, c, z in vertices:
                        coord = list((r, c, z))
                        off = coord[axis_tumble] - c_mid
                        coord[axis_tumble] = c_mid + off * cos(ang_tumble) - z * sin(ang_tumble) * 0.2
                        tumbled.append(tuple(coord))
                    vertices = tumbled
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
    @property
    def FRAGILE(self):
        if getattr(self, 'style', None) == 'dream':
            return (226, 212, 218)
        elif getattr(self, 'style', None) == 'forest':
            return (168, 166, 144)
        else:
            return (235, 226, 212)

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
        self._bridge_tile_sprites = {}
        self._landing_bursts = []
        self._last_landing_id = None
        self.pixel_scale = 1

    def set_stage(self, stage: StageData) -> None:
        self.stage = stage
        self.bridge_cells = {cell: i for i, cells in enumerate(stage.bridges.values()) for cell in cells}
        self.resize(self.size)
        self._static_key=None
        self._frame_key=None
        self.material_cache.clear()
        self._tile_sprites = []
        if hasattr(self, '_bridge_tile_sprites'):
            self._bridge_tile_sprites.clear()
        self._landing_bursts = []
        self._last_landing_id = None

    def set_view(self, view: str) -> None:
        """Switch camera view (one of VIEWS) and refit the board."""
        if view not in VIEWS:
            raise ValueError(f'Unknown view: {view!r}')
        self.view = view
        self.resize(self.size)  # new camera -> static cache key changes -> rebuild

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        if hasattr(self, '_bridge_tile_sprites'):
            self._bridge_tile_sprites.clear()
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
                      for z in (-.32, 0.65)]
            xs = [p[0] for p in points];ys = [p[1] for p in points]
            focal = min(size[0] * .86 / (max(xs) - min(xs)), size[1] * .86 / (max(ys) - min(ys)))
            cap = 112 * self.pixel_scale  # tile width 2..112 logical px at the centre
            focal = max(2 * distance, min(cap * distance, focal))
            origin = (size[0] / 2 - (min(xs) + max(xs)) * focal / 2,
                      size[1] / 2 - (min(ys) + max(ys)) * focal / 2)
            width = focal / distance  # tile width at the board centre, for markers and moss
            self.camera = Camera3D(origin, width, width / 2, width * .24, 'original', eye + (focal,))
            return
        xs = [(c - r + delta) / 2 for r, c in cells for delta in (-1, 1)]
        ys = [(r + c) / 4 + delta for r, c in cells for delta in (-1.38, .68)]
        width = max(2, min(112 * self.pixel_scale, size[0] * .88 / (max(xs) - min(xs)),
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
            # Inward mesh winding -> outward normal, lit by LIGHT.
            nx,ny,nz=(-value/length for value in normal)
            diffuse=max(0.,nx*LIGHT[0]+ny*LIGHT[1]+nz*LIGHT[2])
            if player:
                # Upper face brightest, front-left side medium, right side in shade.
                hemisphere=max(0.,nz)
                bevel_light=min(1.,4*abs(nz)*(abs(nx)+abs(ny)))
                strength=.4+.62*diffuse+.05*hemisphere+.06*bevel_light
                cream=(13,16,21)
                shaded=tuple(max(0,min(255,round(v*strength+cream[k]*hemisphere))) for k,v in enumerate(color))
            else:
                # Same three clear tones on every floor slab.
                strength=.42+.6*diffuse
                shaded=tuple(min(255,int(x*strength)) for x in color)
                if top<.4 and color[0]<=color[1]*1.12:
                    tint=(154,143,126) if self.style=='blueprint' else (91,105,81) if self.style=='forest' else (161,132,163)
                    shaded=tuple(int(a*.88+b*.12) for a,b in zip(shaded,tint))
            result.append((depth, projected, shaded, outline))
        return result

    def _active_cells(self, shown, broken=None, changing_bridges=()):
        """Cells that currently have a tile: floor (minus a broken one) and open bridges."""
        active_cells = []
        for r, row in enumerate(self.stage.grid):
            for c, tile in enumerate(row):
                coord = (r, c)
                bridge = self.bridge_cells.get(coord)
                if bridge is not None:
                    if bridge not in changing_bridges and bridge < len(shown.bridges_status) and shown.bridges_status[bridge]:
                        active_cells.append(coord)
                elif tile != TileType.VOID and coord != broken:
                    active_cells.append(coord)
        return active_cells

    def _base_key(self, active_cells):
        return (id(self.stage), self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast,
                self.style, tuple(active_cells))

    def _build_static(self, shown, broken=None, changing_bridges=()):
        """Bake only on stage / bridge / camera / contrast changes.

        broken: a fragile tile that has just broken; it is left out of the board,
        so it vanishes and the block drops through the hole.

        A few recent boards are kept (see _compose_board): when a switch is
        pressed, the board while the bridge flies in is the board from just
        before, and the board it lands on was composed during the flight."""
        self.stats['static_builds']+=1
        if not hasattr(self, '_base_cache'):
            self._base_cache = {}
        active_cells = self._active_cells(shown, broken, changing_bridges)
        base_key = self._base_key(active_cells)
        if base_key not in self._base_cache:
            for _ in self._compose_board(shown, active_cells, base_key):
                pass
        self._base, self._top_mask, self._shadow_surf, self._tile_sprites = self._base_cache[base_key]
        if self._frame.get_size() != self.size:
            self._frame=pygame.Surface(self.size,pygame.SRCALPHA)
        self._frame_key=None
        self.stats['cached_layer_bytes']=self.size[0]*self.size[1]*4*3

    def _compose_board(self, shown, active_cells, base_key):
        """Compose one board (blueprint guides, tiles) into the cache.

        A generator that yields between steps, so draw() can spread the work for
        the board a bridge is about to land on over the frames of its flight."""
        base = pygame.Surface(self.size, pygame.SRCALPHA)
        yield
        top_mask = pygame.Surface(self.size, pygame.SRCALPHA)
        # Volumetric under-island ambient drop shadow for all 3 themes
        shadow_colors = {
            'dream': (120, 70, 98, 95),       # Soft dreamy lavender-mauve shadow onto clouds
            'forest': (14, 26, 18, 130),      # Deep misty canopy shadow
            'blueprint': (8, 22, 38, 115),    # Blueprint drafting depth shadow
        }
        shadow_color = shadow_colors.get(self.style, (25, 25, 35, 100))
        raw_shadow = pygame.Surface(self.size, pygame.SRCALPHA)
        for r, c in active_cells:
            fp = [self.project((r + dr, c + dc, -0.58)) for dr, dc in ((0, 0), (0, 1), (1, 1), (1, 0))]
            pygame.draw.polygon(raw_shadow, shadow_color, fp)

        sw, sh = self.size
        # Pass 1: Broad diffused ambient drop shadow (offset +14px down)
        tiny1 = pygame.transform.smoothscale(raw_shadow, (max(1, sw // 6), max(1, sh // 6)))
        soft1 = pygame.transform.smoothscale(tiny1, (sw, sh))

        # Pass 2: Closer contact drop shadow (offset +6px down)
        tiny2 = pygame.transform.smoothscale(raw_shadow, (max(1, sw // 3), max(1, sh // 3)))
        soft2 = pygame.transform.smoothscale(tiny2, (sw, sh))

        shadow_surf = pygame.Surface(self.size, pygame.SRCALPHA)
        shadow_surf.blit(soft1, (0, 14))
        shadow_surf.blit(soft2, (0, 6))
        base.blit(shadow_surf, (0, 0))
        yield
        if self.style == 'blueprint':
            # Blueprint datum floor footprint & architectural projection lines
            for r, c in active_cells:
                fp = [self.project((r + dr, c + dc, -0.62)) for dr, dc in ((0, 0), (0, 1), (1, 1), (1, 0))]
                pygame.draw.polygon(base, (20, 52, 78, 55), fp)
                pygame.draw.aalines(base, (48, 130, 160, 60), True, fp)
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
                        pygame.draw.line(base, (64, 168, 196, 75), pa, pb, 1)

        yield
        # The board is composed from per-tile sprites (see _tile_sprite). They are
        # cached per camera, so toggling a bridge or breaking a tile only re-blits
        # sprites instead of re-projecting and re-texturing every tile, which made
        # the bridge animation stutter. The same sprites drive the assembly intro.
        grid = self.stage.grid
        r_mid = len(grid) / 2.0
        c_mid = len(grid[0]) / 2.0
        max_d = max(1.0, (r_mid ** 2 + c_mid ** 2) ** 0.5)
        tile_sprites = []
        for r, c in active_cells:
            tile_surf, (min_x, min_y), tile_depth = self._tile_sprite(r, c)
            d = ((r - r_mid) ** 2 + (c - c_mid) ** 2) ** 0.5
            delay = (d / max_d) * 0.22
            seed = r * 137 + c * 89
            theta_base = (seed % 360) * pi / 180.0 + (seed % 5) * 0.3
            radius_base = 160.0 + (seed % 8) * 20.0
            tile_sprites.append((tile_depth, tile_surf, (min_x, min_y), (r, c), delay, theta_base, radius_base))
        tile_sprites.sort(key=lambda it: it[0])
        for i, (_, tile_surf, position, _, _, _, _) in enumerate(tile_sprites):
            base.blit(tile_surf, position)
            if i % 8 == 7:
                yield
        for r, c in active_cells:
            top = [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]
            pygame.draw.polygon(top_mask, (255, 255, 255, 255), top)
        if self.stage.goal in active_cells:
            r, c = self.stage.goal
            pygame.draw.polygon(top_mask, (0, 0, 0, 0), [self.project(p) for p in cuboid(r + .16, c + .16, 0, .68, .68, 0)[:4]])
        if self.style == 'forest':
            self._moss_edges(shown, base)
        # Bridge tiles are drawn ahead of time, so the frame a bridge settles on
        # only re-blits sprites.
        for r, c in self.bridge_cells:
            self._tile_sprite(r, c)
        if len(self._base_cache) >= 4:  # bounded: a handful of full-size layers
            self._base_cache.pop(next(iter(self._base_cache)))
        self._base_cache[base_key] = (base, top_mask, shadow_surf, tile_sprites)

    def _tile_sprite(self, r, c):
        """One floor or open-bridge tile, drawn once per camera and then reused.

        Returns (surface, top-left screen position, painter depth)."""
        key = (id(self.stage), self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast, self.style)
        if getattr(self, '_tile_sprite_key', None) != key:
            self._tile_sprite_cache = {}
            self._tile_sprite_key = key
        cached = self._tile_sprite_cache.get((r, c))
        if cached is not None:
            return cached
        coord = (r, c)
        tile = self.stage.grid[r][c]
        bridge = self.bridge_cells.get(coord)
        vertices, indices = bevel_mesh(cuboid(r + .012, c + .012, -.32, .976, .976, .32), .02)
        if bridge is not None:  # open bridge tile: styled like the player block
            t_faces = self._faces(vertices, self.BLOCK, faces=indices, player=True)
        else:
            color = (178, 200, 193) if self.high_contrast else self.FLOOR
            if tile == TileType.FRAGILE:
                color = self.FRAGILE
            t_faces = self._faces(vertices, color, faces=indices)
        top = [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]
        all_pts = [p for _, pts, _, _ in t_faces for p in pts] + top
        min_x = floor(min(p[0] for p in all_pts)) - 2
        max_x = ceil(max(p[0] for p in all_pts)) + 2
        min_y = floor(min(p[1] for p in all_pts)) - 2
        max_y = ceil(max(p[1] for p in all_pts)) + 2
        tile_surf = pygame.Surface((max(4, max_x - min_x + 1), max(4, max_y - min_y + 1)), pygame.SRCALPHA)
        for _, pts, ink, edge in sorted(t_faces, key=lambda it: it[0]):
            local_pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
            if bridge is not None:
                self._block_face(tile_surf, local_pts, ink, edge)
            elif len(local_pts) == 4:
                self._material(tile_surf, local_pts, ink)
            else:
                pygame.draw.polygon(tile_surf, ink, local_pts)
        seam = {'dream': (202, 178, 184), 'blueprint': (48, 112, 140), 'forest': (102, 112, 80)}.get(self.style, (168, 174, 163))
        pygame.draw.aalines(tile_surf, (*seam, 165), True, [(p[0] - min_x, p[1] - min_y) for p in top])
        label = 'goal' if coord == self.stage.goal else '!' if tile == TileType.FRAGILE and bridge is None else ''
        if coord in self.stage.switches:
            label = {'SOFT': 'O', 'HEAVY': 'X', 'SPLIT': '<>'}[self.stage.switches[coord].type.value]
        if label:
            self._marker(tile_surf, (r + .5, c + .5, .01), label, offset=(min_x, min_y))
        result = (tile_surf, (min_x, min_y), self.camera.depth(r + .5, c + .5, 0))
        self._tile_sprite_cache[coord] = result
        return result

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

    def _get_bridge_sprite(self, coord):
        if not hasattr(self, '_bridge_tile_sprites'):
            self._bridge_tile_sprites = {}
        if coord in self._bridge_tile_sprites:
            return self._bridge_tile_sprites[coord]
        r, c = coord
        vertices, indices = bevel_mesh(cuboid(r + .012, c + .012, -.32, .976, .976, .32), .02)
        faces = self._faces(vertices, self.BLOCK, faces=indices, player=True)
        all_pts = [p for _, pts, _, _ in faces for p in pts]
        min_x = floor(min(p[0] for p in all_pts)) - 4
        max_x = ceil(max(p[0] for p in all_pts)) + 4
        min_y = floor(min(p[1] for p in all_pts)) - 4
        max_y = ceil(max(p[1] for p in all_pts)) + 4
        bw = max(4, max_x - min_x + 1)
        bh = max(4, max_y - min_y + 1)
        spr = pygame.Surface((bw, bh), pygame.SRCALPHA)
        for _, pts, color, cut in sorted(faces, key=lambda it: it[0]):
            local_pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
            self._block_face(spr, local_pts, color, cut)
        self._bridge_tile_sprites[coord] = (spr, (min_x, min_y))
        return self._bridge_tile_sprites[coord]

    def _render_bridge_shatter(self, surface, coord, p):
        """Render 12 3D tumbling debris shards falling past bottom frame, dense dust cloud, and collapse wave."""
        br, bc = coord
        p = max(0.0, min(1.0, p))

        # 1. Collapse shockwave at floor plane z = 0.01
        if p <= 0.45:
            p_w = p / 0.45
            c_pt = self.project((br + 0.5, bc + 0.5, 0.01))
            rx = int((14.0 + p_w * 54.0) * self.zoom)
            ry = int(rx * 0.48)
            alpha = int(210 * (1.0 - p_w))
            if rx > 2 and ry > 2 and alpha > 0:
                w_col = {'dream': (255, 185, 215, alpha), 'forest': (255, 215, 60, alpha), 'blueprint': (80, 225, 255, alpha)}.get(self.style, (255, 255, 255, alpha))
                pygame.draw.ellipse(surface, w_col, (c_pt[0] - rx, c_pt[1] - ry, rx * 2, ry * 2), max(1, int(2.5 * (1.0 - p_w) * self.zoom)))

        # 2. 12 3D Tumbling Debris Shards falling all the way down past the bottom screen
        shard_alpha = 255 if p < 0.65 else max(0, int(255 * (1.0 - (p - 0.65) / 0.35)))

        # Theme colors for shards matching the player block cuboid
        if self.style == 'forest':
            c_top = (255, 240, 172, shard_alpha)
            c_side = (148, 102, 28, shard_alpha)
            edge_col = (255, 250, 200, shard_alpha)
            dust_main = (235, 205, 140)
            dust_sparkle = (255, 245, 190)
        elif self.style == 'blueprint':
            c_top = (255, 172, 115, shard_alpha)
            c_side = (148, 48, 20, shard_alpha)
            edge_col = (255, 210, 175, shard_alpha)
            dust_main = (160, 220, 245)
            dust_sparkle = (220, 245, 255)
        else:  # dream
            c_top = (255, 226, 236, shard_alpha)
            c_side = (210, 98, 140, shard_alpha)
            edge_col = (255, 255, 255, shard_alpha)
            dust_main = (255, 210, 230)
            dust_sparkle = (255, 245, 250)

        perim = [
            (br + 0.05, bc + 0.05), (br + 0.05, bc + 0.50), (br + 0.05, bc + 0.95),
            (br + 0.50, bc + 0.95), (br + 0.95, bc + 0.95), (br + 0.95, bc + 0.50),
            (br + 0.95, bc + 0.05), (br + 0.50, bc + 0.05)
        ]
        center = (br + 0.50, bc + 0.50)
        dz = -0.6 * p - 13.5 * (p ** 1.85)  # Plummets all the way past the bottom frame!

        shard_commands = []
        for k in range(8):
            pa = perim[k]
            pb = perim[(k + 1) % 8]
            ang = k * pi / 4.0 + pi / 8.0
            dr = cos(ang) * 0.62 * p
            dc = sin(ang) * 0.62 * p
            rot_tumble = p * 4.2 * (1.0 if k % 2 == 0 else -1.0)

            s_mid_r = (center[0] + pa[0] + pb[0]) / 3.0 + dr
            s_mid_c = (center[1] + pa[1] + pb[1]) / 3.0 + dc

            pts_local = []
            for pr, pc in (center, pa, pb):
                dpr = (pr - center[0]) * 0.88
                dpc = (pc - center[1]) * 0.88
                r_rot = dpr * cos(rot_tumble) - dpc * sin(rot_tumble)
                c_rot = dpr * sin(rot_tumble) + dpc * cos(rot_tumble)
                pts_local.append((s_mid_r + r_rot, s_mid_c + c_rot))

            top_shard = [self.project((pr, pc, dz)) for pr, pc in pts_local]
            bot_shard = [self.project((pr, pc, dz - 0.16)) for pr, pc in pts_local]
            depth = self.camera.depth(s_mid_r, s_mid_c, dz)
            shard_commands.append((depth, top_shard, bot_shard))

        # 4 center core diamond shards
        for k in range(4):
            ang = k * pi / 2.0
            dr = cos(ang) * 0.35 * p
            dc = sin(ang) * 0.35 * p
            rot_tumble = p * 5.0 * (-1.0 if k % 2 == 0 else 1.0)
            c_mid_r = center[0] + dr
            c_mid_c = center[1] + dc
            diamond_pts = [
                (0.0, 0.14), (0.14, 0.0), (0.0, -0.14), (-0.14, 0.0)
            ]
            pts_local = []
            for dpr, dpc in diamond_pts:
                r_rot = dpr * cos(rot_tumble) - dpc * sin(rot_tumble)
                c_rot = dpr * sin(rot_tumble) + dpc * cos(rot_tumble)
                pts_local.append((c_mid_r + r_rot, c_mid_c + c_rot))
            top_shard = [self.project((pr, pc, dz)) for pr, pc in pts_local]
            bot_shard = [self.project((pr, pc, dz - 0.16)) for pr, pc in pts_local]
            depth = self.camera.depth(c_mid_r, c_mid_c, dz)
            shard_commands.append((depth, top_shard, bot_shard))

        for _, top_shard, bot_shard in sorted(shard_commands, key=lambda it: it[0]):
            pygame.draw.polygon(surface, c_side, [top_shard[1], top_shard[2], bot_shard[2], bot_shard[1]])
            pygame.draw.polygon(surface, c_top, top_shard)
            pygame.draw.aalines(surface, edge_col, True, top_shard)

        # 3. Dense Billowing Dust Storm (36 volumetric particles rendered directly on surface)
        for i in range(36):
            seed = int(br * 43 + bc * 89 + i * 23)
            ang = ((seed % 360) * pi / 180.0)
            spd = 0.25 + (seed % 10) * 0.055
            dust_r = br + 0.5 + cos(ang) * spd * (p ** 0.60)
            dust_c = bc + 0.5 + sin(ang) * spd * (p ** 0.60)
            dust_z = 0.25 * sin(pi * p) - 0.75 * p - (seed % 5) * 0.04
            pt = self.project((dust_r, dust_c, dust_z))
            dust_a = max(0, int(220 * sin(pi * max(0.01, min(0.99, p))) * (1.0 - p * 0.45)))
            if dust_a > 0:
                rad = max(2, int((3 + (seed % 6) + p * 8) * self.zoom))
                col = (*dust_main, dust_a) if i % 3 != 0 else (*dust_sparkle, dust_a)
                pygame.draw.circle(surface, col, (round(pt[0]), round(pt[1])), rad)

    def draw(self, surface, state, motion=None, intro_t=None, outro_t=None, shockwave=None,
             bridges=None, clear=True):
        """Draw the board for `state` (with `motion`, if a roll is running) onto `surface`.

        bridges: (old_status, new_status, progress) while a switch's bridges fly
        in or shatter. It runs on its own timeline (see BloxorzApp.bridge_fx),
        so the block keeps its normal rolling speed.
        clear=False: draw over what `surface` already holds instead of clearing
        it; moving frames are then composed straight onto it, saving a
        full-size copy per frame. `surface` should have per-pixel alpha (the
        glow and particle effects use translucent colours).
        """
        if surface.get_size() != self.size:
            self.resize(surface.get_size())
        if self._frame.get_size() != self.size:
            self._frame = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.stage is None:
            if clear:
                surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            return

        changing_bridges = ()
        b_p = 0.0
        if bridges is not None:
            old_bridges, new_bridges, b_p = bridges
            b_p = max(0.0, min(1.0, b_p))
            changing_bridges = tuple(i for i, (b_old, b_new) in enumerate(zip(old_bridges, new_bridges)) if b_old != b_new)
        shown = motion.before if motion and motion.progress < .65 else state
        broken = (self._broken_tile(motion.after)
                  if motion and motion.falling and motion.progress >= FALL_ROLL_END else None)
        static_key = (self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast, shown.bridges_status, changing_bridges, broken)
        material_key = (self.size, self.camera, self.zoom, self.high_contrast, self.style)
        if material_key != self._material_key:
            self.material_cache.clear()
            if hasattr(self, '_bridge_tile_sprites'):
                self._bridge_tile_sprites.clear()
            self._material_key = material_key
        if static_key != self._static_key:
            self._build_static(shown, broken, changing_bridges=changing_bridges)
            self._static_key = static_key

        # While a bridge flies in (or shatters), compose the board it will settle
        # on a few milliseconds per frame, so the landing frame has no hitch.
        target = None
        if changing_bridges:
            landed = _Bridges(tuple(new_bridges))
            target_cells = self._active_cells(landed)
            target_key = self._base_key(target_cells)
            target = self._base_cache.get(target_key)
            if target is None:
                if getattr(self, '_prebuild_key', None) != target_key:
                    self._prebuild = self._compose_board(landed, target_cells, target_key)
                    self._prebuild_key = target_key
                deadline = time.perf_counter() + .002
                for _ in self._prebuild:  # breaking out keeps the generator resumable
                    if time.perf_counter() > deadline:
                        break
                target = self._base_cache.get(target_key)

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

            if clear:
                surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            surface.blit(self._frame, (0, 0))
            self._frame_key = None
            return

        if outro_t is not None:
            # Win outro: after the block has sunk into the goal, the tiles fall
            # away in a ripple spreading out from the goal hole. Each tile eases
            # in (starts gently, then drops faster) and fades, so the board
            # empties smoothly; at outro_t = 1 nothing is left (the board stays
            # empty behind the "Stage complete" dialog).
            p = min(1.0, max(0.0, outro_t))
            self._frame.fill((0, 0, 0, 0))
            if p < 1.0 and self._tile_sprites:
                gr, gc = self.stage.goal
                reach = max(1.0, max(((r - gr) ** 2 + (c - gc) ** 2) ** .5
                                     for _, _, _, (r, c), *_ in self._tile_sprites))
                fall = self.camera.tile_width * 3.2   # device pixels, so Retina and 1x match
                drift = self.camera.tile_width * .45
                for depth, spr, (x0, y0), (r, c), delay, theta_base, radius_base in self._tile_sprites:
                    start = .42 * (((r - gr) ** 2 + (c - gc) ** 2) ** .5) / reach
                    local = min(1.0, max(0.0, (p - start) / .58))
                    if local <= 0.0:
                        self._frame.blit(spr, (x0, y0))
                        continue
                    ease = local * local
                    alpha = int(255 * (1.0 - local) ** 1.3)
                    if alpha <= 0:
                        continue
                    spr.set_alpha(alpha)
                    self._frame.blit(spr, (round(x0 + cos(theta_base) * drift * ease), round(y0 + fall * ease)))
                    spr.set_alpha(255)

            if clear:
                surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)
            surface.blit(self._frame, (0, 0))
            self._frame_key = None
            return
        key=(state,motion,static_key,bridges)
        # A moving frame (roll, fall, bridge flight) changes every frame anyway:
        # with clear=False it is composed straight onto `surface`. A still frame
        # is composed once into self._frame and reused.
        direct = not clear and (motion is not None or bridges is not None)
        canvas = surface if direct else self._frame
        if direct or key!=self._frame_key:
            self.stats['dynamic_frames']+=1
            if not direct:
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
                for _,pts,color,cut in sorted(under,key=lambda item:item[0]):self._block_face(canvas,pts,color,cut)
            else:
                sinking=bool(motion and motion.sinking)
                meshes=sink_meshes(motion) if sinking else motion_meshes(motion) if motion else state_meshes(state)
            canvas.blit(self._base,(0,0))
            if target is not None and b_p > .7:
                # Fade in the landed board over the end of the flight, so the
                # bridge settles into it instead of popping in afterwards.
                target[0].set_alpha(min(255, int(255 * (b_p - .7) / .3)))
                canvas.blit(target[0], (0, 0))
                target[0].set_alpha(255)
            # Physical switch depression when stepped on
            for coord in (shown.pos1, shown.pos2):
                if coord in self.stage.switches:
                    sw_type = self.stage.switches[coord].type.value
                    sw_label = {'SOFT': 'O', 'HEAVY': 'X', 'SPLIT': '<>'}[sw_type]
                    r, c = coord
                    tile_top = [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]
                    bridge = self.bridge_cells.get(coord)
                    color = self.BLOCK if bridge is not None else ((178, 200, 193) if self.high_contrast else self.FLOOR)
                    self._material(canvas, tile_top, color)
                    self._marker(canvas, (r + 0.5, c + 0.5, -0.05), sw_label)

            # Dynamic bridge ascension & shattering collapse
            if changing_bridges:
                for coord, b_idx in self.bridge_cells.items():
                    if b_idx < len(old_bridges) and b_idx < len(new_bridges):
                        old_s = old_bridges[b_idx]
                        new_s = new_bridges[b_idx]
                        if old_s != new_s:
                            br_r, br_c = coord
                            if not old_s and new_s:
                                # 1. Bridge Opening: Launching from below the game window frame straight into place
                                spr, (bx, by) = self._get_bridge_sprite(coord)
                                y_start = self.size[1] + 60
                                b_ease = 1.0 - (1.0 - b_p) ** 3.0
                                cur_y = int(by + (y_start - by) * (1.0 - b_ease))

                                # High-energy ascension thrust streak
                                streak_h = max(4, int(52 * (1.0 - b_ease)))
                                trail_col = {'dream': (255, 180, 220, 160), 'forest': (255, 215, 60, 160), 'blueprint': (80, 220, 255, 160)}.get(self.style, (255, 255, 255, 160))
                                trail_y = cur_y + spr.get_height() - 4
                                for sx in (bx + 8, bx + spr.get_width() - 8, bx + spr.get_width() // 2):
                                    pygame.draw.line(canvas, trail_col, (sx, trail_y), (sx, trail_y + streak_h), 2)

                                # Pre-baked bridge tile sprite blit (0.005 ms)
                                canvas.blit(spr, (bx, cur_y))

                                # Arrival energy snap ring
                                if b_p >= 0.84:
                                    snap_a = int(240 * (b_p - 0.84) / 0.16)
                                    top_p = [self.project(p) for p in cuboid(br_r, br_c, 0.01, 1, 1, 0)[:4]]
                                    snap_col = {'dream': (255, 220, 240, snap_a), 'forest': (255, 245, 160, snap_a), 'blueprint': (140, 240, 255, snap_a)}.get(self.style, (255, 255, 255, snap_a))
                                    pygame.draw.aalines(canvas, snap_col, True, top_p)
                            elif old_s and not new_s:
                                # 2. Bridge Closing: Shatter into 12 3D tumbling debris shards falling past bottom frame + billowing dust
                                self._render_bridge_shatter(canvas, coord, b_p)

            # Work only on the small projected shadow footprint, not the full viewport.
            shadow_meshes=([(v,a) for v,a,moving in tagged if not moving] if falling and dropping
                           else [] if motion and motion.sinking else meshes)
            hulls=[self._hull([self.project((r+z*.65,c-z*.16,.01)) for r,c,z in vertices]) for vertices,_ in shadow_meshes]
            all_points=[p for hull in hulls for p in hull]
            bounds=pygame.Rect(0,0,0,0)
            if all_points:
                x,y=floor(min(p[0] for p in all_points))-4,floor(min(p[1] for p in all_points))-4
                bounds=pygame.Rect(x,y,ceil(max(p[0] for p in all_points))-x+5,ceil(max(p[1] for p in all_points))-y+5).clip(canvas.get_rect())
            if bounds.width and bounds.height:
                min_z = max(0.0, min((p[2] for vertices, _ in shadow_meshes for p in vertices), default=0.0))
                shadow_alpha = max(24, int(82 - min(min_z, 1.2) * 48))
                shadow_tint = {'dream': (92, 58, 88), 'forest': (18, 30, 22), 'blueprint': (14, 38, 54)}.get(self.style, (72, 52, 78))
                contact=pygame.Surface(bounds.size,pygame.SRCALPHA)
                for hull in hulls:
                    if len(hull)>=3:
                        pygame.draw.polygon(contact,(*shadow_tint, shadow_alpha),[(a-bounds.x,b-bounds.y) for a,b in hull])
                contact.blit(self._top_mask,(0,0),bounds,special_flags=pygame.BLEND_RGBA_MULT)
                canvas.blit(contact,bounds)
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
            for _,pts,color,cut in sorted(faces,key=lambda item:item[0]):self._block_face(canvas,pts,color,cut)

            # Fragile tile shatter, chunky stone shards & fine mineral dust particles
            if broken is not None and motion and motion.falling and motion.progress >= FALL_ROLL_END:
                br, bc = broken
                t = max(0.0, min(1.0, (motion.progress - FALL_ROLL_END) / (1.0 - FALL_ROLL_END)))

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
                    pygame.draw.polygon(canvas, (35, 20, 15, shard_alpha), [top_shard[1], top_shard[2], sub_shard[1], sub_shard[0]])
                    sh_col = (*self.FRAGILE, shard_alpha)
                    pygame.draw.polygon(canvas, sh_col, top_shard)
                    pygame.draw.aalines(canvas, (255, 185, 110, shard_alpha), True, top_shard)

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
                        pygame.draw.circle(canvas, d_col, (round(p_pt[0]), round(p_pt[1])), 1 if i % 3 != 0 else 2)

            self._frame_key=None if direct else key
        else:self.stats['frame_cache_hits']+=1
        if not direct:
            if clear:
                surface.fill((0,0,0,0) if surface.get_flags()&pygame.SRCALPHA else self.BACKGROUND)
            surface.blit(self._frame,(0,0))

        # Companion Holographic 3D Faceted Diamond Beacon (active throughout entire game)
        # Hovers above 1x1 standing block, centered over 1x2 lying block, or over active cube in SPLIT mode
        show_beacon = not bool(motion and (motion.falling or motion.sinking)) and intro_t is None and outro_t is None
        if show_beacon:
            ticks = int(motion.progress * 1000) if motion else pygame.time.get_ticks()
            # Calculate beacon center and base block height
            if motion and not motion.falling and not motion.sinking:
                m_list = motion_meshes(motion)
                if motion.before.orientation == Orientation.SPLIT:
                    act_idx = min(len(m_list) - 1, max(0, motion.before.active_cube))
                    b_verts = m_list[act_idx][0]
                else:
                    b_verts = [pt for m_verts, _ in m_list for pt in m_verts]
                ar = sum(pt[0] for pt in b_verts) / len(b_verts)
                ac = sum(pt[1] for pt in b_verts) / len(b_verts)
                block_top_z = max(pt[2] for pt in b_verts)
            else:
                if state.orientation == Orientation.SPLIT:
                    act_coord = state.pos1 if state.active_cube == 0 else state.pos2
                    ar = act_coord[0] + 0.5
                    ac = act_coord[1] + 0.5
                    block_top_z = 1.0
                elif state.orientation == Orientation.STANDING:
                    ar = state.pos1[0] + 0.5
                    ac = state.pos1[1] + 0.5
                    block_top_z = 2.0
                else:  # HORIZONTAL_R or HORIZONTAL_C: centered between the two tiles
                    ar = (state.pos1[0] + state.pos2[0]) * 0.5 + 0.5
                    ac = (state.pos1[1] + state.pos2[1]) * 0.5 + 0.5
                    block_top_z = 1.0

            # Lively vertical bobbing (+- 0.22 tile height, smooth 60 FPS motion)
            z_mid = block_top_z + 0.68 + sin(ticks * 0.0055) * 0.22
            z_top = z_mid + 0.38
            z_bot = z_mid - 0.38
            rot_ang = ticks * 0.0035
            r_rad = 0.26

            eq = [self.project((ar + r_rad * cos(rot_ang + k * pi / 2),
                                ac + r_rad * sin(rot_ang + k * pi / 2), z_mid)) for k in range(4)]
            top_p = self.project((ar, ac, z_top))
            bot_p = self.project((ar, ac, z_bot))

            # Theme palettes:
            # Dream City: Pink (Hồng)
            # Forest Ruins: Yellow (Vàng hổ phách)
            # Blueprint Studio: Red (Đỏ)
            if self.style == 'dream':
                c_light = (255, 225, 242, 245)
                c_mid = (255, 125, 185, 230)
                c_dark = (215, 60, 135, 210)
                ring_col = (255, 180, 220)
            elif self.style == 'forest':
                c_light = (255, 252, 185, 245)
                c_mid = (255, 215, 30, 230)
                c_dark = (205, 150, 10, 210)
                ring_col = (255, 235, 90)
            else:  # 'blueprint' / paper
                c_light = (255, 180, 180, 245)
                c_mid = (245, 55, 55, 230)
                c_dark = (185, 20, 20, 210)
                ring_col = (255, 105, 105)

            # Upper 4 facets (rendered directly to surface)
            pygame.draw.polygon(surface, c_light, [top_p, eq[0], eq[1]])
            pygame.draw.polygon(surface, c_mid, [top_p, eq[1], eq[2]])
            pygame.draw.polygon(surface, c_dark, [top_p, eq[2], eq[3]])
            pygame.draw.polygon(surface, c_mid, [top_p, eq[3], eq[0]])

            # Lower 4 facets
            pygame.draw.polygon(surface, c_mid, [bot_p, eq[1], eq[0]])
            pygame.draw.polygon(surface, c_dark, [bot_p, eq[2], eq[1]])
            pygame.draw.polygon(surface, c_dark, [bot_p, eq[3], eq[2]])
            pygame.draw.polygon(surface, c_mid, [bot_p, eq[0], eq[3]])

            # White crystalline facets edges
            for k in range(4):
                pygame.draw.aaline(surface, (255, 255, 255), top_p, eq[k])
                pygame.draw.aaline(surface, (255, 255, 255), bot_p, eq[k])
                pygame.draw.aaline(surface, (255, 255, 255), eq[k], eq[(k + 1) % 4])

            # Tilted holographic orbital halo ring around diamond waist (bobs with z_mid)
            ring_pts = [self.project((ar + 0.38 * cos(rot_ang * 1.6 + i * pi / 8),
                                      ac + 0.38 * sin(rot_ang * 1.6 + i * pi / 8),
                                      z_mid + 0.08 * sin(i * pi / 4))) for i in range(16)]
            pygame.draw.aalines(surface, (*ring_col, 200), True, ring_pts)
            for k in (0, 4, 8, 12):
                node_pt = ring_pts[k]
                pygame.draw.circle(surface, (255, 255, 255, 220), (round(node_pt[0]), round(node_pt[1])), 1)

        # Expanding magnetic merge shockwave ring (rendered directly to surface)
        if shockwave is not None:
            sr, sc, st = shockwave
            p = max(0.0, min(1.0, st / 0.35))
            center = self.project((sr + 0.5, sc + 0.5, 0.02))
            rx = int((20.0 + p * 65.0) * self.zoom)
            ry = int(rx * 0.48)
            alpha = int(180 * (1.0 - p))
            if rx > 2 and ry > 2 and alpha > 0:
                wave_color = (255, 235, 170, alpha) if self.style == 'dream' else ((60, 240, 255, alpha) if self.style == 'blueprint' else (160, 255, 140, alpha))
                pygame.draw.ellipse(surface, wave_color, (center[0] - rx, center[1] - ry, rx * 2, ry * 2), max(1, int(3 * (1.0 - p) * self.zoom)))

        # Quantum teleport tracer stream when splitting
        if motion and not motion.falling and not motion.sinking:
            raw = BloxorzProblem.roll_block(motion.before, motion.action)
            is_split_tel = (raw is not None and motion.after.orientation == Orientation.SPLIT
                            and motion.before.orientation != Orientation.SPLIT)
            if is_split_tel and motion.progress > 0.35:
                tp = (motion.progress - 0.35) / 0.65
                s_alpha = max(0, int(220 * sin(pi * tp)))
                src_pt = self.project((raw.pos1[0] + 0.5, raw.pos1[1] + 0.5, 0.15 + (1.0 - tp) * 0.6))
                for target_pos in (motion.after.pos1, motion.after.pos2):
                    dst_pt = self.project((target_pos[0] + 0.5, target_pos[1] + 0.5, 0.20 + (1.0 - tp) * 0.5))
                    ctrl_r = (raw.pos1[0] + target_pos[0]) * 0.5
                    ctrl_c = (raw.pos1[1] + target_pos[1]) * 0.5
                    ctrl_pt = self.project((ctrl_r, ctrl_c, 1.25))
                    beam_pts = []
                    for s_step in range(11):
                        st = s_step / 10.0
                        bx = (1 - st) ** 2 * src_pt[0] + 2 * (1 - st) * st * ctrl_pt[0] + st ** 2 * dst_pt[0]
                        by = (1 - st) ** 2 * src_pt[1] + 2 * (1 - st) * st * ctrl_pt[1] + st ** 2 * dst_pt[1]
                        beam_pts.append((bx, by))
                    beam_col = (180, 255, 255, s_alpha)
                    pygame.draw.lines(surface, (30, 210, 245, s_alpha // 2), False, beam_pts, 4)
                    pygame.draw.aalines(surface, beam_col, False, beam_pts)

        # Magnetic merge electric arcs between converging cubes
        if motion and not motion.falling and not motion.sinking:
            is_merge = (motion.before.orientation == Orientation.SPLIT
                        and motion.after.orientation != Orientation.SPLIT)
            if is_merge and motion.progress > 0.60:
                mp = (motion.progress - 0.60) / 0.40
                arc_alpha = max(0, int(230 * sin(pi * mp)))
                c1_pt = self.project((motion.after.pos1[0] + 0.5, motion.after.pos1[1] + 0.5, 0.5))
                c2_pt = self.project((motion.after.pos2[0] + 0.5, motion.after.pos2[1] + 0.5, 0.5))
                ticks = int(motion.progress * 1000) if motion else pygame.time.get_ticks()
                for arc_i in range(2):
                    arc_pts = [c1_pt]
                    for seg in range(1, 4):
                        st = seg / 4.0
                        mx = c1_pt[0] + (c2_pt[0] - c1_pt[0]) * st + sin(ticks * 0.05 + seg * 2.3 + arc_i) * 9.0
                        my = c1_pt[1] + (c2_pt[1] - c1_pt[1]) * st + cos(ticks * 0.06 + seg * 2.7 + arc_i) * 7.0
                        arc_pts.append((mx, my))
                    arc_pts.append(c2_pt)
                    arc_col = (255, 255, 255, arc_alpha) if arc_i == 0 else (120, 245, 255, arc_alpha)
                    pygame.draw.lines(surface, arc_col, False, arc_pts, 2)

        # Natural Celestial Goal Portal & Constellation Ascension (organic volumetric radiance & sacred particles)
        if motion and motion.sinking:
            gr, gc = self.stage.goal
            sp = max(0.0, min(1.0, motion.progress))
            beam_alpha = min(255, int(255 * sin(pi * sp * 0.90)))
            if beam_alpha > 0:
                ticks = int(motion.progress * 1000) if motion else pygame.time.get_ticks()

                # Theme color palettes
                if self.style == 'dream':
                    c_core = (255, 245, 252)
                    c_inner = (255, 175, 220)
                    c_outer = (240, 110, 190)
                    c_ground = (255, 160, 215)
                elif self.style == 'forest':
                    c_core = (255, 255, 230)
                    c_inner = (255, 220, 80)
                    c_outer = (180, 200, 40)
                    c_ground = (245, 210, 50)
                else:  # blueprint / paper (Crimson Red Theme)
                    c_core = (255, 245, 245)
                    c_inner = (255, 60, 60)
                    c_outer = (205, 20, 20)
                    c_ground = (255, 55, 55)

                # 1. Soft ground pool bloom & illuminated goal perimeter
                rx = int((18.0 + sp * 35.0) * self.zoom)
                ry = int(rx * 0.48)
                if rx > 2 and ry > 2:
                    g_center = self.project((gr + 0.5, gc + 0.5, 0.01))
                    for r_layer, a_mult in ((1.3, 0.25), (1.0, 0.45), (0.6, 0.75)):
                        lrx = int(rx * r_layer)
                        lry = int(ry * r_layer)
                        pygame.draw.ellipse(surface, (*c_ground, int(beam_alpha * a_mult * 0.5)), (g_center[0] - lrx, g_center[1] - lry, lrx * 2, lry * 2))

                hole_pts = [self.project((gr + dr, gc + dc, 0.01))
                            for dr, dc in ((0.02, 0.02), (0.02, 0.98), (0.98, 0.98), (0.98, 0.02))]
                pygame.draw.aalines(surface, (*c_core, min(255, int(beam_alpha * 1.1))), True, hole_pts)

                # 2. Volumetric Column of Light (Ascending & smoothly fading into the open sky)
                layers = [
                    (0.72, 1.10, c_outer, 0.18),  # Ethereal outer mist
                    (0.48, 0.75, c_inner, 0.38),  # Ambient glow
                    (0.26, 0.42, c_inner, 0.65),  # Inner radiant column
                    (0.12, 0.18, c_core,  0.88),  # Brilliant core
                ]
                z_heights = [0.0, 0.8, 1.6, 2.5, 3.4, 4.3]
                for rad_bot, rad_top, col, a_mult in layers:
                    for zi in range(len(z_heights) - 1):
                        z0 = z_heights[zi]
                        z1 = z_heights[zi + 1]
                        breath0 = 1.0 + sin(ticks * 0.003 + z0 * 1.5) * 0.06
                        breath1 = 1.0 + sin(ticks * 0.003 + z1 * 1.5) * 0.06
                        r0 = (rad_bot + (rad_top - rad_bot) * (z0 / 4.3)) * breath0
                        r1 = (rad_bot + (rad_top - rad_bot) * (z1 / 4.3)) * breath1
                        fade0 = max(0.0, 1.0 - (z0 / 4.6) ** 1.3)
                        fade1 = max(0.0, 1.0 - (z1 / 4.6) ** 1.3)
                        seg_alpha = int(beam_alpha * a_mult * (fade0 + fade1) * 0.5)
                        if seg_alpha <= 0:
                            continue
                        p0_l = self.project((gr + 0.5 - r0 * 0.707, gc + 0.5 + r0 * 0.707, z0))
                        p0_r = self.project((gr + 0.5 + r0 * 0.707, gc + 0.5 - r0 * 0.707, z0))
                        p1_r = self.project((gr + 0.5 + r1 * 0.707, gc + 0.5 - r1 * 0.707, z1))
                        p1_l = self.project((gr + 0.5 - r1 * 0.707, gc + 0.5 + r1 * 0.707, z1))
                        pygame.draw.polygon(surface, (*col, seg_alpha), [p0_l, p0_r, p1_r, p1_l])

                c0 = self.project((gr + 0.5, gc + 0.5, 0.0))
                c1 = self.project((gr + 0.5, gc + 0.5, 4.5))
                pygame.draw.line(surface, (*c_core, int(beam_alpha * 0.95)), c0, c1, max(1, int(2 * self.zoom)))

                # 3. Floating Ethereal Serpentine Wave Ribbons
                for ribbon_i in range(2):
                    ribbon_offset = ribbon_i * pi
                    ribbon_pts = []
                    for step in range(24):
                        rz = (step / 23.0) * 4.2
                        r_ang = rz * 2.2 - ticks * 0.005 + ribbon_offset
                        r_rad = 0.32 + 0.12 * sin(ticks * 0.004 + rz * 2.0)
                        rp_r = gr + 0.5 + cos(r_ang) * r_rad
                        rp_c = gc + 0.5 + sin(r_ang) * r_rad
                        ribbon_pts.append(self.project((rp_r, rp_c, rz)))
                    r_alpha = int(beam_alpha * 0.55)
                    if r_alpha > 0 and len(ribbon_pts) > 1:
                        pygame.draw.lines(surface, (*c_inner, r_alpha // 2), False, ribbon_pts, max(2, int(3 * self.zoom)))
                        pygame.draw.aalines(surface, (*c_core, r_alpha), False, ribbon_pts)

                # 4. Theme-Specific Living Special Effects
                if self.style == 'dream':
                    # Glowing Sakura Petals fluttering up with aerodynamic tilt & stardust
                    for i in range(18):
                        p_t = ((ticks * 0.0016 + i * 0.055) % 1.0)
                        pz = p_t * 4.2
                        sway_ang = ticks * 0.003 + i * 1.7
                        sway_r = cos(sway_ang) * (0.28 + (i % 4) * 0.08)
                        sway_c = sin(sway_ang * 1.2) * (0.28 + (i % 4) * 0.08)
                        p_pos = self.project((gr + 0.5 + sway_r, gc + 0.5 + sway_c, pz))
                        p_a = max(0, int(beam_alpha * sin(pi * p_t)))
                        if p_a <= 0:
                            continue
                        if i % 3 == 0:
                            # 4-point diamond starlight sparkle
                            glint_col = (255, 255, 255, p_a)
                            g_rad = 3 if p_a > 140 else 2
                            pygame.draw.line(surface, glint_col, (p_pos[0] - g_rad, p_pos[1]), (p_pos[0] + g_rad, p_pos[1]), 1)
                            pygame.draw.line(surface, glint_col, (p_pos[0], p_pos[1] - g_rad), (p_pos[0], p_pos[1] + g_rad), 1)
                            pygame.draw.circle(surface, (255, 240, 250, p_a), (round(p_pos[0]), round(p_pos[1])), 1)
                        else:
                            # Translucent pink cherry blossom petal with 3D aerodynamic tilt
                            tilt = sin(ticks * 0.006 + i * 2.0)
                            pw = max(3, int(7 * (0.6 + 0.4 * abs(tilt))))
                            ph = max(2, int(5 * (0.6 + 0.4 * (1.0 - abs(tilt)))))
                            pet_col = (255, 180 + (i % 3) * 25, 220 + (i % 2) * 20, p_a)
                            pygame.draw.ellipse(surface, pet_col, (p_pos[0] - pw // 2, p_pos[1] - ph // 2, pw, ph))

                elif self.style == 'forest':
                    # Sacred Forest Fireflies (Bầy đom đóm thần thoại phát quang)
                    for i in range(18):
                        p_t = ((ticks * 0.0013 + i * 0.055) % 1.0)
                        pz = p_t * 4.0
                        wander_ang = ticks * 0.0035 + i * 2.2
                        orbit_rad = 0.25 + 0.22 * sin(ticks * 0.002 + i * 1.5)
                        wander_r = cos(wander_ang) * orbit_rad
                        wander_c = sin(wander_ang * 0.9 + i) * orbit_rad
                        f_pos = self.project((gr + 0.5 + wander_r, gc + 0.5 + wander_c, pz))
                        glow = 0.65 + 0.35 * sin(ticks * 0.008 + i * 2.8)
                        f_a = max(0, int(beam_alpha * sin(pi * p_t) * glow))
                        if f_a <= 0:
                            continue
                        pygame.draw.circle(surface, (255, 215, 60, int(f_a * 0.40)), (round(f_pos[0]), round(f_pos[1])), 5)
                        pygame.draw.circle(surface, (255, 255, 200, f_a), (round(f_pos[0]), round(f_pos[1])), 2)

                else:  # blueprint / paper (Crimson Red Uplink)
                    # Quantum Data Stream: Crimson Ascension pulse rings & coordinate markers
                    for ring_i in range(3):
                        ring_t = ((ticks * 0.002 + ring_i * 0.33) % 1.0)
                        ring_z = ring_t * 4.2
                        ring_rx = int((12.0 + ring_z * 8.0) * self.zoom)
                        ring_ry = int(ring_rx * 0.48)
                        ring_a = max(0, int(beam_alpha * sin(pi * ring_t) * 0.70))
                        if ring_a > 0 and ring_rx > 2:
                            r_center = self.project((gr + 0.5, gc + 0.5, ring_z))
                            pygame.draw.ellipse(surface, (255, 65, 65, ring_a), (r_center[0] - ring_rx, r_center[1] - ring_ry, ring_rx * 2, ring_ry * 2), 1)

                    for i in range(16):
                        p_t = ((ticks * 0.0022 + i * 0.0625) % 1.0)
                        pz = p_t * 4.2
                        track_r = ((i % 4) - 1.5) * 0.22
                        track_c = (((i // 4) % 4) - 1.5) * 0.22
                        d_pos = self.project((gr + 0.5 + track_r, gc + 0.5 + track_c, pz))
                        d_a = max(0, int(beam_alpha * sin(pi * p_t)))
                        if d_a <= 0:
                            continue
                        if i % 2 == 0:
                            pygame.draw.line(surface, (255, 80, 80, d_a), (d_pos[0] - 3, d_pos[1]), (d_pos[0] + 3, d_pos[1]), 1)
                            pygame.draw.line(surface, (255, 80, 80, d_a), (d_pos[0], d_pos[1] - 3), (d_pos[0], d_pos[1] + 3), 1)
                        else:
                            pygame.draw.circle(surface, (255, 230, 230, d_a), (round(d_pos[0]), round(d_pos[1])), 1)
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

    def _moss_edges(self, shown, surface=None):
        """Baked hanging moss only along exposed front-facing edges."""
        surface = self._base if surface is None else surface
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
                        pygame.draw.circle(surface, rng.choice(((64, 80, 30), (90, 109, 39), (120, 131, 54))),
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

            collar_col = (215, 160, 52) if self.style == 'forest' else ((245, 165, 192) if self.style == 'dream' else (235, 52, 65))
            dark_collar = (90, 65, 20) if self.style == 'forest' else ((160, 88, 115) if self.style == 'dream' else (120, 24, 32))
            pygame.draw.polygon(surface, dark_collar, outer_rim)
            pygame.draw.polygon(surface, collar_col, mid_rim)

            pygame.draw.polygon(surface, (18, 22, 30), hole)
            pygame.draw.polygon(surface, (36, 44, 58), [hole[0], hole[1], pit_deep[1], pit_deep[0]])
            pygame.draw.polygon(surface, (24, 30, 42), [hole[0], pit_deep[0], pit_deep[3], hole[3]])
            pygame.draw.polygon(surface, (10, 14, 20), [pit_deep[0], pit_deep[1], pit_core[1], pit_core[0]])
            pygame.draw.polygon(surface, (4, 6, 10), pit_core)

            rivet_col = (255, 240, 180) if self.style == 'forest' else ((255, 230, 240) if self.style == 'dream' else (255, 190, 190))
            for dr, dc in ((-.45, -.45), (-.45, .45), (.45, .45), (.45, -.45), (0, -.45), (0, .45), (-.45, 0), (.45, 0)):
                pt = project(dr, dc)
                pygame.draw.circle(surface, rivet_col, (round(pt[0]), round(pt[1])), 2)

            pygame.draw.aalines(surface, (255, 255, 255), True, hole)
            pygame.draw.aalines(surface, collar_col, True, outer_rim)

        elif kind == 'O':
            # SOFT SWITCH: Faceted Holographic Citrine Solenoid Gem with Orbital Ring & Specular Apex
            base_pts = [project(0.34 * cos(i * pi / 6), 0.34 * sin(i * pi / 6)) for i in range(12)]
            bezel_pts = [project(0.28 * cos(i * pi / 6), 0.28 * sin(i * pi / 6)) for i in range(12)]
            pygame.draw.polygon(surface, (18, 22, 30), base_pts)
            pygame.draw.polygon(surface, (40, 48, 62) if not pressed else (26, 32, 42), bezel_pts)
            pygame.draw.aalines(surface, (68, 80, 100), True, base_pts)

            orb_pts = [project(0.36 * cos(i * pi / 8), 0.36 * sin(i * pi / 8), 0.01) for i in range(16)]
            ring_glow = (255, 235, 140) if not pressed else (255, 255, 200)
            pygame.draw.aalines(surface, ring_glow, True, orb_pts)
            for k in (0, 4, 8, 12):
                node_pt = orb_pts[k]
                pygame.draw.circle(surface, (255, 255, 255), (round(node_pt[0]), round(node_pt[1])), 2)

            dz_gem = 0.035 if not pressed else -0.015
            dz_apex = dz_gem + (0.045 if not pressed else 0.015)
            apex = project(0, 0, dz_apex)
            eq_pts = [project(0.22 * cos(i * pi / 4), 0.22 * sin(i * pi / 4), dz_gem) for i in range(8)]

            if self.style == 'dream':
                c_light = (255, 245, 175)
                c_mid = (255, 195, 65)
                c_dark = (215, 130, 25)
            elif self.style == 'forest':
                c_light = (255, 250, 160)
                c_mid = (245, 185, 35)
                c_dark = (195, 125, 15)
            else:  # blueprint
                c_light = (255, 240, 170)
                c_mid = (235, 165, 40)
                c_dark = (180, 110, 20)

            facet_colors = [c_light, c_light, c_mid, c_dark, c_dark, c_dark, c_mid, c_light]
            for i in range(8):
                tri = [apex, eq_pts[i], eq_pts[(i + 1) % 8]]
                col = facet_colors[i] if not pressed else tuple(max(0, c - 30) for c in facet_colors[i])
                pygame.draw.polygon(surface, col, tri)
                pygame.draw.aaline(surface, (255, 255, 255), apex, eq_pts[i])
                pygame.draw.aaline(surface, (255, 255, 255), eq_pts[i], eq_pts[(i + 1) % 8])

            pygame.draw.circle(surface, (255, 255, 255), (round(apex[0]), round(apex[1])), 2)

        elif kind == 'X':
            # HEAVY SWITCH: Faceted Crystalline Ruby Cross aligned with tile diagonals (true 'X')
            pad = [project(-.35, -.35), project(-.35, .35), project(.35, .35), project(.35, -.35)]
            inner_pad = [project(-.30, -.30), project(-.30, .30), project(.30, .30), project(.30, -.30)]
            pygame.draw.polygon(surface, (18, 22, 30), pad)
            pygame.draw.polygon(surface, (28, 34, 46) if not pressed else (20, 24, 32), inner_pad)
            pygame.draw.aalines(surface, (56, 68, 88), True, pad)

            dia_ring = [project(-.33, 0, .01), project(0, .33, .01), project(.33, 0, .01), project(0, -.33, .01)]
            pygame.draw.aalines(surface, (255, 110, 120), True, dia_ring)
            for r_pt in dia_ring:
                pygame.draw.circle(surface, (255, 180, 185), (round(r_pt[0]), round(r_pt[1])), 2)

            dz_arm = 0.03 if not pressed else -0.015
            dz_ridge = dz_arm + (0.035 if not pressed else 0.015)
            arm_l = 0.30
            arm_w = 0.076

            r_light = (255, 140, 130) if not pressed else (240, 100, 95)
            r_mid = (235, 48, 58) if not pressed else (195, 32, 42)
            r_dark = (160, 20, 30) if not pressed else (125, 15, 22)

            # 4 diagonal corner arms forming a clear, bold 'X' across the two diagonals of the tile
            u = 0.7071
            for dr, dc in ((-u, -u), (u, u), (-u, u), (u, -u)):
                tip_apex = project(dr * arm_l, dc * arm_l, dz_ridge)
                tip_left = project(dr * arm_l - dc * arm_w, dc * arm_l + dr * arm_w, dz_arm)
                tip_right = project(dr * arm_l + dc * arm_w, dc * arm_l - dr * arm_w, dz_arm)
                base_left = project(-dc * arm_w, dr * arm_w, dz_arm)
                base_right = project(dc * arm_w, -dr * arm_w, dz_arm)
                c_apex = project(0, 0, dz_ridge + 0.01)

                f1 = [c_apex, base_left, tip_left, tip_apex]
                f2 = [c_apex, tip_apex, tip_right, base_right]

                col1 = r_light if dr < 0 or dc < 0 else r_mid
                col2 = r_mid if dr < 0 or dc < 0 else r_dark
                pygame.draw.polygon(surface, col1, f1)
                pygame.draw.polygon(surface, col2, f2)
                pygame.draw.aalines(surface, (255, 215, 215), True, f1)
                pygame.draw.aalines(surface, (255, 215, 215), True, f2)

            c_dia = [project(0.065 * cos(i * pi / 2), 0.065 * sin(i * pi / 2), dz_ridge + 0.02) for i in range(4)]
            pygame.draw.polygon(surface, (255, 255, 255), c_dia)
            pygame.draw.circle(surface, (255, 255, 255), (round(project(0, 0, dz_ridge + 0.02)[0]), round(project(0, 0, dz_ridge + 0.02)[1])), 2)

        elif kind == '<>':
            # SPLIT SWITCH: Dual Faceted Quantum Chevrons & Central Faceted Diamond Core
            base_pts = [project(-.36, -.36), project(-.36, .36), project(.36, .36), project(.36, -.36)]
            pygame.draw.polygon(surface, (12, 22, 32), base_pts)
            pygame.draw.aalines(surface, (36, 75, 105), True, base_pts)

            dz_q = 0.03 if not pressed else -0.015
            cyan_light = (180, 255, 255) if not pressed else (120, 240, 255)
            cyan_mid = (40, 225, 245) if not pressed else (25, 175, 205)
            cyan_dark = (18, 140, 175) if not pressed else (12, 105, 135)

            # Central Faceted Quantum Micro-Diamond
            d_top = project(0, 0, dz_q + 0.06)
            d_bot = project(0, 0, dz_q - 0.03)
            d_eq = [project(0.08 * cos(k * pi / 2), 0.08 * sin(k * pi / 2), dz_q + 0.015) for k in range(4)]
            pygame.draw.polygon(surface, cyan_light, [d_top, d_eq[0], d_eq[1]])
            pygame.draw.polygon(surface, cyan_mid, [d_top, d_eq[1], d_eq[2]])
            pygame.draw.polygon(surface, cyan_dark, [d_top, d_eq[2], d_eq[3]])
            pygame.draw.polygon(surface, cyan_mid, [d_top, d_eq[3], d_eq[0]])
            for k in range(4):
                pygame.draw.aaline(surface, (255, 255, 255), d_top, d_eq[k])
                pygame.draw.aaline(surface, (255, 255, 255), d_eq[k], d_eq[(k + 1) % 4])

            # Left Faceted Quantum Chevron Prism `<`
            c_tip_l = project(0, -.26, dz_q)
            c_top_l = project(-.22, -.06, dz_q)
            c_bot_l = project(.22, -.06, dz_q)
            c_in_l = project(0, -.14, dz_q + 0.02)

            f_left_top = [c_top_l, c_tip_l, c_in_l]
            f_left_bot = [c_tip_l, c_bot_l, c_in_l]
            pygame.draw.polygon(surface, cyan_light, f_left_top)
            pygame.draw.polygon(surface, cyan_mid, f_left_bot)
            pygame.draw.aalines(surface, (255, 255, 255), True, f_left_top)
            pygame.draw.aalines(surface, (255, 255, 255), True, f_left_bot)

            # Right Faceted Quantum Chevron Prism `>`
            c_tip_r = project(0, .26, dz_q)
            c_top_r = project(-.22, .06, dz_q)
            c_bot_r = project(.22, .06, dz_q)
            c_in_r = project(0, .14, dz_q + 0.02)

            f_right_top = [c_top_r, c_tip_r, c_in_r]
            f_right_bot = [c_tip_r, c_bot_r, c_in_r]
            pygame.draw.polygon(surface, cyan_light, f_right_top)
            pygame.draw.polygon(surface, cyan_mid, f_right_bot)
            pygame.draw.aalines(surface, (255, 255, 255), True, f_right_top)
            pygame.draw.aalines(surface, (255, 255, 255), True, f_right_bot)

            pygame.draw.aaline(surface, (200, 255, 255), project(0, -.32, dz_q), project(0, .32, dz_q))
            for offset_c in (-.32, -.26, 0, .26, .32):
                p_node = project(0, offset_c, dz_q)
                pygame.draw.circle(surface, (255, 255, 255), (round(p_node[0]), round(p_node[1])), 1)

        elif kind == '!':
            # FRAGILE TILE: Procedural Unique Multi-Branch Fracture Network with 3D Light-and-Shadow Relief
            seed = int(((r * 37 + c * 179 + 53) * 9301 + 49297) % 233280)

            er = -0.06 + ((seed % 13) - 6) * 0.015
            ec = -0.06 + (((seed // 13) % 13) - 6) * 0.015

            if self.style == 'dream':
                fissure_shadow = (75, 45, 58)
                fissure_lit = (255, 245, 250)
                dust_col = (245, 210, 225)
            elif self.style == 'forest':
                fissure_shadow = (34, 25, 18)
                fissure_lit = (235, 225, 195)
                dust_col = (195, 185, 155)
            else:  # blueprint
                fissure_shadow = (18, 52, 78)
                fissure_lit = (130, 225, 255)
                dust_col = (160, 215, 240)

            corner_targets = [(-.44, -.42), (-.42, .44), (.44, .42), (.42, -.44)]
            shift_idx = seed % 4

            for i in range(4):
                tgt_r, tgt_c = corner_targets[(i + shift_idx) % 4]
                mid1_r = er + (tgt_r - er) * 0.38 + ((seed + i * 29) % 7 - 3) * 0.022
                mid1_c = ec + (tgt_c - ec) * 0.38 + ((seed + i * 43) % 7 - 3) * 0.022
                mid2_r = er + (tgt_r - er) * 0.72 + ((seed + i * 61) % 7 - 3) * 0.025
                mid2_c = ec + (tgt_c - ec) * 0.72 + ((seed + i * 79) % 7 - 3) * 0.025

                pts = [project(er, ec), project(mid1_r, mid1_c), project(mid2_r, mid2_c), project(tgt_r, tgt_c)]
                lit_pts = [project(er - 0.008, ec - 0.008),
                           project(mid1_r - 0.008, mid1_c - 0.008),
                           project(mid2_r - 0.008, mid2_c - 0.008),
                           project(tgt_r - 0.008, tgt_c - 0.008)]

                pygame.draw.lines(surface, fissure_shadow, False, pts, 2)
                pygame.draw.aalines(surface, fissure_lit, False, lit_pts)

                if i % 2 == 0:
                    trib_r = mid1_r + (mid2_c - mid1_c) * 0.45
                    trib_c = mid1_c - (mid2_r - mid1_r) * 0.45
                    t_pts = [project(mid1_r, mid1_c), project(trib_r, trib_c)]
                    pygame.draw.lines(surface, fissure_shadow, False, t_pts, 1)
                    pygame.draw.aalines(surface, fissure_lit, False, [project(mid1_r - 0.006, mid1_c - 0.006), project(trib_r - 0.006, trib_c - 0.006)])

            for k in range(3):
                p_r = er + ((seed + k * 17) % 9 - 4) * 0.02
                p_c = ec + ((seed + k * 31) % 9 - 4) * 0.02
                chip_pt = project(p_r, p_c)
                pygame.draw.circle(surface, fissure_shadow, (round(chip_pt[0]), round(chip_pt[1])), 1)
                pygame.draw.circle(surface, dust_col, (round(chip_pt[0] - 1), round(chip_pt[1] - 1)), 1)

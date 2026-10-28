"""Bàn chơi isometric với animation lật quanh cạnh như thật, vẽ bằng polygon của Pygame."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import math
from math import cos, sin, pi, floor, ceil
import random
import time
import pygame
from src.gui import theme
from src.engine.loader import StageData, TileType
from src.engine.problem import BloxorzProblem
from src.engine.state import Action, GameState, Orientation
from src.gui.contracts import MotionFrame

Point = tuple[float, float, float]
FACES = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


# ---------------------------------------------------------------------------
# Các góc nhìn camera
#   'iso'  : góc nhìn isometric cổ điển của game gốc. Mỗi phím mũi tên đưa
#            khối đi chéo trên màn hình.
#   'original': mặc định. Camera của bản Flash gốc: phía trước bên trái và
#            trên cao, có phối cảnh thật (ô xa nhỏ đi), nên các bàn bị tách
#            thành nhiều đảo vẫn rõ ràng nằm trên một mặt phẳng. Các hàng gần như
#            nằm ngang và thấy được cạnh trái và cạnh trước của bàn.
#            UP = đi ra xa, LEFT/RIGHT = sang trái/phải trên màn hình.
# ---------------------------------------------------------------------------
VIEWS = ('original', 'iso')
DEFAULT_VIEW = 'original'
HEIGHT_SCALE = 0.6  # 'iso': một đơn vị chiều cao khối = 0.6 * bề rộng ô (xem project())

# Camera phối cảnh 'original', nhắm vào tâm bàn chơi.
# Chỉnh theo ảnh chụp stage 1 của bản Flash.
ORIGINAL_YAW = 0.2        # số radian camera lệch sang trái so với nhìn thẳng từ phía trước
ORIGINAL_PITCH = 0.58     # số radian camera nhìn xuống (~33 độ)
ORIGINAL_DISTANCE = 2.5   # khoảng cách tới tâm bàn, tính theo kích thước bàn (càng nhỏ phối cảnh càng mạnh)
ORIGINAL_HEIGHT = 1.0     # một đơn vị chiều cao khối, tính theo bề rộng ô


# Ô sàn là các tấm dày tách rời (xem _build_static).
TILE_GAP = .03            # thụt vào mỗi bên, để giữa các tấm cạnh nhau có khe
TILE_THICKNESS = {'iso': .5, 'original': .55}  # tính theo đơn vị khối

# Một nguồn sáng chính cho sàn và khối, từ phía trước bên trái và từ trên, là
# vector đơn vị trong (row, col, z): mặt trên sáng nhất, mặt trước trái vừa,
# mặt phải trong bóng, nên mọi tấm sàn và khối đều trông khối 3D rõ ràng.
_LIGHT = (.35, -.55, 1.0)
LIGHT = tuple(v / sum(w * w for w in _LIGHT) ** .5 for v in _LIGHT)


SWITCH_LABELS = {'SOFT': 'O', 'HEAVY': 'X', 'SPLIT': '<>'}
HIGH_CONTRAST_FLOOR = (178, 200, 193)
SHOCKWAVE_SECONDS = .35


def tile_thickness(view: str) -> float:
    return TILE_THICKNESS.get(view, .3)


def height_scale(view: str) -> float:
    return ORIGINAL_HEIGHT if view == 'original' else HEIGHT_SCALE


def perspective_eye(row: float, col: float, distance: float) -> tuple:
    """Tư thế camera nhìn vào (row, col, 0): vị trí, phải, lên, phía trước.

    Trục thế giới: x = col (sang phải), y = row (về phía người xem), z = lên trên.
    """
    ch, sh = cos(ORIGINAL_PITCH), sin(ORIGINAL_PITCH)
    position = (col - distance * ch * sin(ORIGINAL_YAW), row + distance * ch * cos(ORIGINAL_YAW), distance * sh)
    forward = tuple((t - p) / distance for t, p in zip((col, row, 0), position))
    right = (-forward[1], forward[0], 0)  # trục lên của thế giới x phía trước
    length = (right[0] ** 2 + right[1] ** 2) ** .5
    right = (right[0] / length, right[1] / length, 0)
    up = (forward[1] * right[2] - forward[2] * right[1],  # phía trước x phải
          forward[2] * right[0] - forward[0] * right[2],
          forward[0] * right[1] - forward[1] * right[0])
    return position + right + up + forward


def perspective_raw(eye, row: float, col: float, z: float) -> tuple[float, float, float]:
    """Phép chiếu lỗ kim với tiêu cự 1: (x, y, khoảng cách theo hướng nhìn).

    eye lấy từ perspective_eye(); y màn hình tăng xuống dưới; z tính theo đơn vị khối.
    """
    # Tích vô hướng viết tay: đoạn này chạy ~100k lần mỗi lần dựng lại bàn.
    vx, vy, vz = col - eye[0], row - eye[1], z * ORIGINAL_HEIGHT - eye[2]
    x = vx * eye[3] + vy * eye[4] + vz * eye[5]
    y = vx * eye[6] + vy * eye[7] + vz * eye[8]
    forward = vx * eye[9] + vy * eye[10] + vz * eye[11]
    if forward < 1e-3:
        forward = 1e-3
    return x / forward, -y / forward, forward


class _Bridges:
    """Thay cho GameState khi chỉ cần đọc bridges_status (lúc dựng bàn)."""
    __slots__ = ('bridges_status',)

    def __init__(self, bridges_status):
        self.bridges_status = bridges_status


@dataclass(frozen=True)
class Camera3D:
    origin: tuple[float, float] = (360, 120)
    tile_width: float = 54
    tile_depth: float = 27
    tile_height: float = 12
    # Camera phối cảnh cần có bàn để nhắm vào, nên mặc định khi chưa có màn
    # là 'iso'; IsometricRenderer.resize() dựng camera thật cho từng màn.
    view: str = 'iso'
    eye: tuple = ()  # chỉ dùng cho 'original': perspective_eye() + tiêu cự

    def project(self, row: float, col: float, height: float = 0) -> tuple[float, float]:
        """Chiều cao tính theo pixel màn hình (đơn vị khối * tile_width * height_scale)."""
        if self.view == 'original':
            x, y, _ = perspective_raw(self.eye, row, col, height / (self.tile_width * ORIGINAL_HEIGHT))
            return self.origin[0] + x * self.eye[12], self.origin[1] + y * self.eye[12]
        return (self.origin[0] + (col - row) * self.tile_width / 2,
                self.origin[1] + (col + row) * self.tile_depth / 2 - height)

    def sees(self, normal: Point, offset: float) -> bool:
        """True nếu camera nằm ở phía mà pháp tuyến hướng tới, so với mặt phẳng
        normal . p = offset (p = (row, col, z))."""
        if self.view == 'original':
            eye = (self.eye[1], self.eye[0], self.eye[2] / ORIGINAL_HEIGHT)
            return sum(n * e for n, e in zip(normal, eye)) > offset
        return normal[0] + normal[1] + normal[2] * (5 / 6) > 0  # về phía người xem, xem depth()

    def depth(self, row: float, col: float, z: float) -> float:
        """Khoá sắp xếp theo thuật toán hoạ sĩ: càng lớn càng gần người xem, vẽ sau.

        Đó là tích vô hướng với hướng chiếu, tức là hướng 3D chiếu xuống thành
        một điểm trên màn hình. Với 'iso' nó đúng bằng khoá cũ row + col + z * 5/6.
        Với 'original' nó là âm của khoảng cách phía trước camera.
        """
        if self.view == 'original':
            return -perspective_raw(self.eye, row, col, z)[2]
        return row + col + z * (5 / 6)


def in_front(solid: list[Point], other: list[Point], camera: Camera3D) -> bool:
    """Thứ tự hoạ sĩ của hai khối lồi không chồng lên nhau, mỗi khối cho bởi 8 góc
    cuboid: True nếu `solid` nằm trước `other` theo góc nhìn của `camera`. Một mặt
    phẳng của khối này mà khối kia nằm hẳn bên ngoài sẽ tách chúng ra; khối nào nằm
    ở phía camera thì ở trước. Không có mặt phẳng như vậy thì khối có tâm gần hơn thắng."""
    for inside, outside, outside_is_solid in ((other, solid, True), (solid, other, False)):
        centre = [sum(p[i] for p in inside) / 8 for i in range(3)]
        for face in FACES:
            a, b, c = (inside[i] for i in face[:3])
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            offset = sum(n * x for n, x in zip(normal, a))
            if sum(n * x for n, x in zip(normal, centre)) > offset:  # cho nó hướng ra ngoài
                normal, offset = tuple(-n for n in normal), -offset
            if all(sum(n * x for n, x in zip(normal, p)) >= offset - 1e-6 for p in outside):
                return camera.sees(normal, offset) == outside_is_solid
    middle = [[sum(p[i] for p in points) / len(points) for i in range(3)] for points in (solid, other)]
    return camera.depth(*middle[0]) > camera.depth(*middle[1])


def cuboid(r, c, z, rows, cols, height) -> list[Point]:
    return [(r, c, z), (r, c + cols, z), (r + rows, c + cols, z), (r + rows, c, z),
            (r, c, z + height), (r, c + cols, z + height),
            (r + rows, c + cols, z + height), (r + rows, c, z + height)]


@lru_cache(maxsize=32)
def _bevel_template(amount):
    """Cache cấu trúc lưới và trọng số affine theo góc; phép xoay chỉ biến đổi đỉnh."""
    vertices = cuboid(0, 0, 0, 1, 1, 1)
    points, faces = _build_bevel(vertices, amount)
    return tuple(points), tuple(faces)


def bevel_mesh(vertices, amount=.025, uniform=False):
    # Độ vát cố định theo tỉ lệ giữ một mẫu dùng chung cho mọi tư thế.
    template, faces = _bevel_template(amount)
    axes = [tuple(vertices[j][k] - vertices[0][k] for k in range(3)) for j in (3, 1, 4)]
    if uniform:
        lengths = [sum(v * v for v in axis) ** .5 for axis in axes]
        template = [tuple(value / max(1, lengths[k]) if value < .5 else 1 - (1 - value) / max(1, lengths[k])
                          for k, value in enumerate(point)) for point in template]
    points = [tuple(vertices[0][k] + sum(p[axis] * axes[axis][k] for axis in range(3)) for k in range(3))
              for p in template]
    return points, faces


def _build_bevel(vertices, amount):
    """26 mặt low-poly; biến đổi các góc đã lăn mà không làm đổi chuyển động."""
    result, faces, corners, edges = [], [], {}, {}
    for face in FACES:
        indices = []
        for j, index in enumerate(face):
            p = vertices[index]
            adjacent = (vertices[face[j - 1]], vertices[face[(j + 1) % 4]])
            inset = list(p)
            for q in adjacent:
                length = sum((q[k] - p[k]) ** 2 for k in range(3)) ** .5
                for k in range(3):
                    inset[k] += (q[k] - p[k]) * min(amount / max(length, 1e-9), .12)
            new = len(result)
            result.append(tuple(inset))
            indices.append(new)
            corners.setdefault(index, []).append(new)
        faces.append(tuple(indices))
        for j, index in enumerate(face):
            other = face[(j + 1) % 4]
            edges.setdefault(tuple(sorted((index, other))), []).append({index: indices[j], other: indices[(j + 1) % 4]})
    for (a, b), pair in edges.items():
        faces.append((pair[0][a], pair[0][b], pair[1][b], pair[1][a]))
    faces.extend(tuple(indices) for indices in corners.values())
    # Phép chiếu hiện có cần các mặt quấn vào trong. Thứ tự thêm cạnh/góc là
    # tuỳ ý, nên chuẩn hoá một lần trong mẫu đã cache để không bị hở.
    fixed = []
    for face in faces:
        a, b, c = (result[i] for i in face[:3])
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        center = [sum(result[i][k] for i in face) / len(face) - .5 for k in range(3)]
        fixed.append(tuple(reversed(face)) if sum(normal[k] * center[k] for k in range(3)) > 0 else face)
    return result, fixed


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
    """Xoay quanh cạnh đáy phía trước, có quán tính theo trọng tâm và đệm khi va chạm."""
    axis = 0 if action in (Action.UP, Action.DOWN) else 1
    positive = action in (Action.DOWN, Action.RIGHT)
    pivot = (max if positive else min)(p[axis] for p in vertices)

    p = max(0.0, min(1.0, progress))

    # Phân biệt theo trọng tâm:
    if before_orient == Orientation.STANDING and after_orient in (Orientation.LYING_H, Orientation.LYING_V):
        # STANDING -> LYING: rơi từ z=1.0 xuống z=0.5 -> trọng lực tăng tốc khi qua đỉnh
        eased_p = p * (1.0 + (1.0 - p) * 0.14)
        angle = eased_p * pi / 2 * (1 if positive else -1)
        # Đệm tiếp đất nặng, chắc
        squash = (sin(pi * (p - 0.78) / 0.22) * 0.052) if p > 0.78 else 0.0
    elif before_orient in (Orientation.LYING_H, Orientation.LYING_V) and after_orient == Orientation.STANDING:
        # LYING -> STANDING: nâng từ z=0.5 lên z=1.0 -> gắng sức lên đỉnh, rồi khoá thẳng đứng
        eased_p = p * (1.0 - sin(pi * p) * 0.22)
        angle = eased_p * pi / 2 * (1 if positive else -1)
        # Giảm chấn khi bật lại ở tư thế đứng
        squash = (sin(pi * (p - 0.85) / 0.15) * 0.024) if p > 0.85 else 0.0
    else:
        # LYING -> LYING hoặc SPLIT: lăn đều, cân bằng
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
        # Nhảy nhẹ trên khối nhỏ đang được chọn
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
        # Đường cong hút vào khi hợp khối/dịch chuyển
        t = (motion.progress - 0.65) / 0.35
        snap_t = t * t * (3.0 - 2.0 * t)  # Hội tụ kiểu smoothstep
        assert raw is not None
        r, c = raw.pos1
        source = [cuboid(r, c, z, 1, 1, 1) for z in (0, 1)]
        return [([tuple(a + (b - a) * snap_t for a, b in zip(p, q))
                  for p, q in zip(source[i], vertices)], active)
                for i, (vertices, active) in enumerate(state_meshes(after))]
    return rotated


FALL_ROLL_END = 0.3   # 30% đầu của cú rơi: lăn bình thường vào tư thế không hợp lệ
FALL_DISTANCE = 9.0   # khối rơi xuống bao xa (đơn vị khối) trước khi chơi lại

# Cách khối lật qua mép: (axis, direction, pivot)
#   axis 0 = hàng, 1 = cột; direction = +1/-1 về phía trống;
#   pivot = đường lưới ở mép bàn mà khối lật qua.
Tip = tuple[int, int, float]


def tip_mesh(vertices: list[Point], tip: Tip, fraction: float) -> list[Point]:
    """Xoay quanh mép bàn để phần vượt ra ngoài đi XUỐNG.

    u = khoảng cách có dấu vượt qua mép (về phía trống). Điểm ở (u=1, z=0)
    tới (cos a, -sin a): nó rơi xuống. Điểm ở trên mép (u=0, z=1) tới
    (sin a, cos a): khối đổ qua mép.
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


FALL_TIP_ANGLE = pi / 4  # khối xoay quanh mép bàn tới góc này...
FALL_TIP_TIME = .36      # ...mất phần này của pha rơi (lúc đầu chậm)


def _tip_free(vertices: list[Point], tip: Tip, t: float, centre: Point) -> list[Point]:
    """Lật qua mép bàn như một vật rắn, t trong 0..1.

    Đầu tiên khối xoay quanh mép (tip_mesh, góc ~ t^2). Trục xoay nằm trên mép,
    nên phần trên bàn chỉ nhấc lên: không có gì lấn vào ô. Tới FALL_TIP_ANGLE thì
    nó rời mép: tâm giữ nguyên vận tốc đang có và rơi theo trọng lực, khối vẫn
    xoay với cùng tốc độ, nên nó vừa rơi vừa rời xa bàn.
    centre: tâm của khối đang chuyển động trước khi lật.
    """
    axis, direction, pivot = tip
    spin = 2 * FALL_TIP_ANGLE / FALL_TIP_TIME  # tốc độ góc lúc rời mép
    if t <= FALL_TIP_TIME:
        return tip_mesh(vertices, tip, (t / FALL_TIP_TIME) ** 2 * FALL_TIP_ANGLE / (pi / 2))
    free = t - FALL_TIP_TIME
    released = tip_mesh(vertices + [centre], tip, FALL_TIP_ANGLE / (pi / 2))
    centre = released.pop()
    # (u, z): khoảng cách vượt qua mép (về phía trống) và độ cao.
    u0, z0 = (centre[axis] - pivot) * direction, centre[2]
    gravity = 2 * FALL_DISTANCE / (1 - FALL_TIP_TIME) ** 2
    u1 = u0 + spin * z0 * free  # d(u, z)/d(angle) = (z, -u) theo phép xoay của tip_mesh
    z1 = z0 - spin * u0 * free - gravity * free * free / 2
    angle = spin * free
    result = []
    for point in released:
        u, z = (point[axis] - pivot) * direction - u0, point[2] - z0
        v = list(point)
        v[axis] = pivot + (u1 + u * cos(angle) + z * sin(angle)) * direction
        v[2] = z1 - u * sin(angle) + z * cos(angle)
        result.append(tuple(v))
    return result


# Các cách khối có thể rời bàn, tự nhiên nhất trước. Renderer dùng cách đầu
# tiên giữ khối không lấn vào ô nào (IsometricRenderer._fall_plan):
# khối nằm trên lỗ to bằng nó thì rơi thẳng qua lỗ.
FALL_PLANS = ('tumble', 'straight')


def fall_meshes(motion: MotionFrame, tip: Tip | None,
                plan: str = 'tumble') -> list[tuple[list[Point], bool, bool]]:
    """Hình học của khối đang rơi. Trả về (vertices, active, moving) cho mỗi mesh.

    Pha 1 (progress < FALL_ROLL_END): lăn bình thường vào tư thế không hợp lệ.
    Pha 2: nếu một phần khối treo trên chỗ trống, nó lật qua mép bàn và rơi ra
    xa ('tumble', _tip_free), hoặc rơi thẳng qua một lỗ to bằng nó ('straight').
    tip=None nghĩa là mọi ô dưới khối đều có sàn (một ô fragile bị vỡ): rơi thẳng.
    Ở chế độ tách chỉ khối đang chọn di chuyển; khối kia đứng yên.
    """
    split = motion.before.orientation == Orientation.SPLIT
    if motion.progress < FALL_ROLL_END:
        roll = MotionFrame(motion.before, motion.after, motion.action,
                           motion.progress / FALL_ROLL_END)
        return [(v, active, not split or i == motion.before.active_cube)
                for i, (v, active) in enumerate(motion_meshes(roll))]
    t = (motion.progress - FALL_ROLL_END) / (1 - FALL_ROLL_END)
    # Ô fragile vỡ (tip=None) sụp ngay, nên khối rơi xuống
    # với một ít vận tốc ngay từ đầu.
    drop = FALL_DISTANCE * t * (0.4 + 0.6 * t)
    # Hai khối nhỏ có thể hợp lại ở tư thế không hợp lệ, nên ở đây xét `after`.
    split_after = motion.after.orientation == Orientation.SPLIT
    meshes = [(vertices, active, not split_after or i == motion.after.active_cube)
              for i, (vertices, active) in enumerate(state_meshes(motion.after))]
    corners = [p for vertices, _, moving in meshes if moving for p in vertices]
    centre = tuple(sum(p[i] for p in corners) / len(corners) for i in range(3))
    result = []
    for vertices, active, moving in meshes:
        if moving:
            if tip is None or plan == 'straight':
                vertices = [(r, c, z - drop) for r, c, z in vertices]
            else:
                vertices = _tip_free(vertices, tip, t, centre)
        result.append((vertices, active, moving))
    return result


def cuboid_samples(corners: list[Point], steps: int = 4) -> list[Point]:
    """Các điểm rải trên bề mặt một cuboid (đã di chuyển) cho bởi 8 góc theo thứ
    tự của cuboid(): mỗi mặt có một lưới (steps+1)^2 điểm."""
    grid = [i / steps for i in range(steps + 1)]
    points = []
    for a in grid:
        for b in grid:
            low = [(1 - a) * (1 - b) * corners[0][i] + (1 - a) * b * corners[1][i]
                   + a * b * corners[2][i] + a * (1 - b) * corners[3][i] for i in range(3)]
            high = [(1 - a) * (1 - b) * corners[4][i] + (1 - a) * b * corners[5][i]
                    + a * b * corners[6][i] + a * (1 - b) * corners[7][i] for i in range(3)]
            for h in (grid if a in (0, 1) or b in (0, 1) else (0, 1)):
                points.append(tuple(lo + (hi - lo) * h for lo, hi in zip(low, high)))
    return points


SINK_DEPTH = 2.05  # khối đứng cao 2 đơn vị: chìm tới khi lọt hẳn vào trong


def sink_meshes(motion: MotionFrame) -> list[tuple[list[Point], bool]]:
    """Animation thắng: khối trượt thẳng xuống lỗ đích.

    Bắt đầu chậm rồi nhanh dần (t^2). Mọi phần dưới mặt bàn (z < 0) bị
    clip_below_floor() cắt đi, nên khối trông như bị lỗ nuốt vào.
    """
    t = motion.progress
    drop = SINK_DEPTH * t * t
    return [([(r, c, z - drop) for r, c, z in vertices], active)
            for vertices, active in state_meshes(motion.after)]


# Intro của màn: các ô bay vào, rồi khối rơi xuống ô xuất phát và nảy như
# một hòn đá nặng. Nó rơi theo trọng lực; mỗi lần nảy giữ lại INTRO_BOUNCE
# vận tốc va chạm, và mỗi lần va chạm khối bị ép dẹt trong chốc lát.
INTRO_SECONDS = 1.4        # toàn bộ intro; app đổi thành intro_t 0..1
INTRO_TILES_SECONDS = .85  # các ô bay vào trong .85 s đầu
INTRO_DROP_START = .3      # số giây trước khi thả khối
INTRO_DROP_SECONDS = .42   # lần rơi đầu tiên
INTRO_DROP_HEIGHT = 7.0    # độ cao so với sàn, theo đơn vị khối
INTRO_BOUNCE = .36         # lần nảy đầu cao ~0.9 đơn vị, lần hai ~0.12
INTRO_SQUASH = .1          # lần va chạm đầu ép khối còn 90% chiều cao
INTRO_CONTACT = .07        # số giây nằm trên sàn ở lần va chạm đầu


def _intro_impacts() -> tuple[tuple[float, float], ...]:
    """(thời điểm, vận tốc) của mỗi lần va chạm; vận tốc 1.0 là lần đầu, mạnh nhất."""
    impacts, t, speed = [], INTRO_DROP_START + INTRO_DROP_SECONDS, 1.0
    while speed >= .05:
        impacts.append((t, speed))
        t += INTRO_CONTACT * speed + 2 * INTRO_BOUNCE * speed * INTRO_DROP_SECONDS
        speed *= INTRO_BOUNCE
    return tuple(impacts)


INTRO_IMPACTS = _intro_impacts()


def intro_drop(t: float) -> tuple[float, float] | None:
    """(độ cao so với sàn, độ ép 0..1) của khối sau t giây kể từ đầu intro,
    hoặc None nếu khối chưa được thả."""
    fall = t - INTRO_DROP_START
    if fall < 0:
        return None
    if fall < INTRO_DROP_SECONDS:
        u = fall / INTRO_DROP_SECONDS
        return INTRO_DROP_HEIGHT * (1 - u * u), 0.0
    hit, speed = next(i for i in reversed(INTRO_IMPACTS) if t >= i[0])
    since, contact = t - hit, INTRO_CONTACT * speed
    if since < contact:
        return 0.0, INTRO_SQUASH * speed * sin(pi * since / contact)
    u, up = (since - contact) / INTRO_DROP_SECONDS, INTRO_BOUNCE * speed
    return max(0.0, INTRO_DROP_HEIGHT * (2 * up * u - u * u)), 0.0


def squash_mesh(vertices: list[Point], squash: float) -> list[Point]:
    """Ép khối xuống sàn theo `squash` và nới rộng ra một chút, giữ thể tích
    gần như không đổi."""
    if not squash:
        return vertices
    cr = sum(p[0] for p in vertices) / len(vertices)
    cc = sum(p[1] for p in vertices) / len(vertices)
    wide = 1 + squash / 2
    return [(cr + (r - cr) * wide, cc + (c - cc) * wide, z * (1 - squash)) for r, c, z in vertices]


def clip_below_floor(vertices: list[Point], faces) -> tuple[list[Point], list[tuple[int, ...]]]:
    """Cắt mọi mặt tại mặt phẳng mặt bàn z = 0 và giữ phần phía trên.

    Cắt Sutherland-Hodgman theo một mặt phẳng: đi quanh mỗi đa giác, giữ các
    đỉnh ở phía cần giữ và thêm giao điểm trên các cạnh cắt qua mặt phẳng. Mặt
    nằm hẳn ở phía bên kia sẽ biến mất.
    """
    def keep(point):
        return point[2] >= 0

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
        if self.style == 'dream':
            return (226, 212, 218)
        elif self.style == 'forest':
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
        self.stats={'static_builds':0,'dynamic_frames':0,'frame_cache_hits':0}
        self.style='dream'
        self.stone_texture=None
        self._frame = pygame.Surface(self.size, pygame.SRCALPHA)
        self._base = pygame.Surface(self.size, pygame.SRCALPHA)
        self._top_mask = pygame.Surface(self.size, pygame.SRCALPHA)
        self._tile_sprites = []
        self._base_cache = {}
        self._fall_plans = {}
        self._wanted_states = ()
        self._prebuild = None
        self._prebuild_key = None
        self._bridge_area_key = None
        self._bridge_area_cache = None
        self._still_block_key = None
        self._still_block_sprite = None
        self._tile_sprite_key = None
        self._tile_sprite_cache = {}
        self.pixel_scale = 1

    def set_style(self, name, stone_texture=None):
        self.style = name
        self.FLOOR, self.BLOCK, self.BACKGROUND = theme.FLOOR, theme.BLOCK, theme.BG
        self._static_key = self._frame_key = None
        self.material_cache.clear()
        self.stone_texture = stone_texture

    def set_stage(self, stage: StageData) -> None:
        self.stage = stage
        self.bridge_cells = {cell: i for i, cells in enumerate(stage.bridges.values()) for cell in cells}
        self.resize(self.size)
        self._static_key=None
        self._frame_key=None
        self.material_cache.clear()
        self._tile_sprites = []
        self._fall_plans = {}

    def set_view(self, view: str) -> None:
        """Đổi góc nhìn camera (một trong VIEWS) và căn lại bàn."""
        if view not in VIEWS:
            raise ValueError(f'Unknown view: {view!r}')
        self.view = view
        self.resize(self.size)  # camera mới -> khoá cache tĩnh đổi -> dựng lại

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        if self.stage is None:
            return
        cells = [(r, c) for r, row in enumerate(self.stage.grid) for c, tile in enumerate(row)
                 if tile != TileType.VOID or (r, c) in self.bridge_cells]
        cells = cells or [(0, 0)]
        avail_w = min(size[0], size[0] - 368) if size[0] >= 900 else size[0] * 0.82
        avail_h = size[1]
        if self.view == 'original':
            corners = [(r + dr, c + dc) for r, c in cells for dr in (0, 1) for dc in (0, 1)]
            rows = [r for r, _ in corners]
            cols = [c for _, c in corners]
            distance = ORIGINAL_DISTANCE * max(max(rows) - min(rows), max(cols) - min(cols), 4)
            eye = perspective_eye((min(rows) + max(rows)) / 2, (min(cols) + max(cols)) / 2, distance)
            points = [perspective_raw(eye, r, c, z) for r, c in corners
                      for z in (-.35, 2.35)]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            focal = min(avail_w * .86 / (max(xs) - min(xs)), avail_h * .86 / (max(ys) - min(ys)))
            cap = 112 * self.pixel_scale  # bề rộng ô 2..112 px logic ở tâm
            focal = max(2 * distance, min(cap * distance, focal))
            origin = (size[0] / 2 - (min(xs) + max(xs)) * focal / 2,
                      size[1] / 2 - (min(ys) + max(ys)) * focal / 2)
            width = focal / distance  # bề rộng ô ở tâm bàn, dùng cho marker và rêu
            self.camera = Camera3D(origin, width, width / 2, width * .24, 'original', eye + (focal,))
            return
        xs = [(c - r + delta) / 2 for r, c in cells for delta in (-1, 1)]
        ys = [(r + c) / 4 + delta for r, c in cells for delta in (-1.5, .8)]
        width = max(2, min(112 * self.pixel_scale, avail_w * .86 / (max(xs) - min(xs)),
                            avail_h * .86 / (max(ys) - min(ys))))
        origin = (size[0] / 2 - (min(xs) + max(xs)) * width / 2,
                  size[1] / 2 - (min(ys) + max(ys)) * width / 2)
        self.camera = Camera3D(origin, width, width / 2, width * .24, 'iso')

    def project(self, point: Point) -> tuple[float, float]:
        x, y = self.camera.project(point[0], point[1],
                                   point[2] * self.camera.tile_width * height_scale(self.camera.view))
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
            depth = sum(self.camera.depth(*p) for p in points) / len(points)
            a, b, c = points[:3]
            u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            length = max(1e-9, sum(n*n for n in normal) ** .5)
            top=abs(normal[2])/length
            # Mesh quấn vào trong -> pháp tuyến hướng ra ngoài, chiếu sáng bằng LIGHT.
            nx,ny,nz=(-value/length for value in normal)
            diffuse=max(0.,nx*LIGHT[0]+ny*LIGHT[1]+nz*LIGHT[2])
            if player:
                # Mặt trên sáng nhất, mặt trước trái vừa, mặt phải trong bóng.
                hemisphere=max(0.,nz)
                bevel_light=min(1.,4*abs(nz)*(abs(nx)+abs(ny)))
                strength=.4+.62*diffuse+.05*hemisphere+.06*bevel_light
                cream=(13,16,21)
                shaded=tuple(max(0,min(255,round(v*strength+cream[k]*hemisphere))) for k,v in enumerate(color))
            else:
                # Cùng ba tông rõ ràng trên mọi tấm sàn.
                strength=.42+.6*diffuse
                shaded=tuple(min(255,int(x*strength)) for x in color)
                if top<.4 and color[0]<=color[1]*1.12:
                    tint=(154,143,126) if self.style=='blueprint' else (91,105,81) if self.style=='forest' else (161,132,163)
                    shaded=tuple(int(a*.88+b*.12) for a,b in zip(shaded,tint))
            result.append((depth, projected, shaded, outline))
        return result

    def _active_cells(self, shown, broken=None, changing_bridges=()):
        """Các ô đang có sàn: sàn thường (trừ ô vừa vỡ) và cầu đang mở."""
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
        """Chỉ dựng lại khi màn / cầu / camera / độ tương phản thay đổi.

        broken: ô fragile vừa vỡ; nó bị bỏ khỏi bàn, nên biến mất và khối rơi
        qua lỗ.

        Vài bàn gần nhất được giữ lại (xem _compose_board): khi bấm công tắc, bàn
        trong lúc cầu bay vào là bàn ngay trước đó, còn bàn mà cầu đáp xuống đã
        được dựng trong lúc cầu bay."""
        self.stats['static_builds']+=1
        active_cells = self._active_cells(shown, broken, changing_bridges)
        base_key = self._base_key(active_cells)
        if base_key not in self._base_cache:
            for _ in self._compose_board(shown, active_cells, base_key):
                pass
        self._base_cache[base_key] = entry = self._base_cache.pop(base_key)  # dùng gần nhất thì đặt cuối
        self._base, self._top_mask, self._tile_sprites = entry
        if self._frame.get_size() != self.size:
            self._frame=pygame.Surface(self.size,pygame.SRCALPHA)
        self._frame_key=None
        self.stats['cached_layer_bytes']=self.size[0]*self.size[1]*4*3

    def _bridge_area(self, changing_bridges):
        """Vùng màn hình khác nhau giữa bàn có và không có các cầu này."""
        key = (self._base_key(()), tuple(changing_bridges))
        if self._bridge_area_key != key:
            area = None
            for cell, index in self.bridge_cells.items():
                if index in changing_bridges:
                    sprite, position, _ = self._tile_sprite(*cell)
                    rect = sprite.get_rect(topleft=position)
                    area = rect if area is None else area.union(rect)
            margin = int(4 * self.pixel_scale)
            area = (area or pygame.Rect(0, 0, 0, 0)).inflate(2 * margin, 2 * margin)
            self._bridge_area_cache = area.clip(pygame.Rect((0, 0), self.size))
            self._bridge_area_key = key
        return self._bridge_area_cache

    def _draw_falling(self, canvas, meshes):
        """Vẽ khối đang rơi lên bàn, rồi vẽ đè lại các ô nằm trước nó (in_front).
        Khối không bao giờ lấn vào ô (xem _fall_plan), nên cách này đúng dù khối
        rơi về phía nào: về phía người xem, ra xa, hay xuống một lỗ."""
        faces = self._block_faces(meshes)
        if not faces:
            return
        self._paint_block(canvas, faces)
        xs = [x for _, pts, _, _ in faces for x, _ in pts]
        ys = [y for _, pts, _, _ in faces for _, y in pts]
        area = pygame.Rect(floor(min(xs)) - 2, floor(min(ys)) - 2, ceil(max(xs) - min(xs)) + 5,
                           ceil(max(ys) - min(ys)) + 5).clip(canvas.get_rect())
        if not area.width or not area.height:
            return
        corners = [p for vertices, _ in meshes for p in vertices]
        gap, thickness = TILE_GAP, tile_thickness(self.camera.view)
        cover = None  # chỗ có ô nằm trước khối: alpha của sprite của chúng
        for _, sprite, (x0, y0), (r, c), *_ in self._tile_sprites:
            if not area.colliderect(sprite.get_rect(topleft=(x0, y0))):
                continue
            tile = cuboid(r + gap, c + gap, -thickness, 1 - 2 * gap, 1 - 2 * gap, thickness)
            if in_front(corners, tile, self.camera):
                continue
            if cover is None:
                cover = pygame.Surface(area.size, pygame.SRCALPHA)
                cover.fill((255, 255, 255, 0))
            cover.blit(sprite, (x0 - area.x, y0 - area.y), special_flags=pygame.BLEND_RGBA_MAX)
        if cover is not None:
            # Viền trên mặt mỗi ô được vẽ bán trong suốt; nó vẫn phải che
            # được khối, nên tăng độ che lên (alpha x4).
            for _ in range(2):
                cover.blit(cover.copy(), (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            if canvas.get_flags() & pygame.SRCALPHA:
                # Xoá khối ở đó trước, để nó không lộ qua các pixel bán trong
                # suốt của bàn.
                hole = pygame.Surface(area.size, pygame.SRCALPHA)
                hole.fill((0, 0, 0, 255))
                hole.blit(cover, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)  # alpha = 255 - cover
                hole.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)
                canvas.blit(hole, area, special_flags=pygame.BLEND_RGBA_MULT)
            # Bàn đã dựng xong (cả rêu) lộ ra qua hình các ô đó.
            patch = pygame.Surface(area.size, pygame.SRCALPHA)
            patch.blit(self._base, (0, 0), area)
            patch.blit(cover, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            canvas.blit(patch, area)

    def _block_shadow(self, canvas, meshes, fade=1.0):
        """Bóng của khối đổ lên mặt các ô, nhân với fade (0..1)."""
        # Chỉ xử lý trên vùng bóng chiếu nhỏ, không phải toàn khung nhìn.
        hulls=[self._hull([self.project((r+z*.65,c-z*.16,.01)) for r,c,z in vertices]) for vertices,_ in meshes]
        all_points=[p for hull in hulls for p in hull]
        bounds=pygame.Rect(0,0,0,0)
        if all_points:
            x,y=floor(min(p[0] for p in all_points))-4,floor(min(p[1] for p in all_points))-4
            bounds=pygame.Rect(x,y,ceil(max(p[0] for p in all_points))-x+5,ceil(max(p[1] for p in all_points))-y+5).clip(canvas.get_rect())
        min_z = max(0.0, min((p[2] for vertices, _ in meshes for p in vertices), default=0.0))
        shadow_alpha = int(max(24, int(82 - min(min_z, 1.2) * 48)) * fade)
        if bounds.width and bounds.height and shadow_alpha > 0:
            shadow_tint = {'dream': (92, 58, 88), 'forest': (18, 30, 22), 'blueprint': (14, 38, 54)}.get(self.style, (72, 52, 78))
            contact=pygame.Surface(bounds.size,pygame.SRCALPHA)
            for hull in hulls:
                if len(hull)>=3:
                    pygame.draw.polygon(contact,(*shadow_tint, shadow_alpha),[(a-bounds.x,b-bounds.y) for a,b in hull])
            contact.blit(self._top_mask,(0,0),bounds,special_flags=pygame.BLEND_RGBA_MULT)
            canvas.blit(contact,bounds)

    def _landing_dust(self, canvas, meshes, t, front):
        """Bụi bị đẩy ra từ dưới khối ở các lần va chạm mạnh của intro.
        front=False vẽ các làn bụi phía sau khối, front=True vẽ phần còn lại."""
        points = [p for vertices, _ in meshes for p in vertices]
        r0, r1 = min(p[0] for p in points), max(p[0] for p in points)
        c0, c1 = min(p[1] for p in points), max(p[1] for p in points)
        cr, cc, hr, hc = (r0 + r1) / 2, (c0 + c1) / 2, (r1 - r0) / 2, (c1 - c0) / 2
        middle = self.camera.depth(cr, cc, 0)
        color = {'dream': (196, 166, 176), 'forest': (226, 214, 180), 'blueprint': (146, 182, 202)}.get(self.style, (204, 190, 176))
        puffs = []
        for hit, speed in INTRO_IMPACTS:
            u = (t - hit) / .55
            if speed < .3 or not 0.0 <= u < 1.0:
                continue
            ease = 1.0 - (1.0 - u) ** 3
            alpha = int(170 * speed * (1.0 - u) ** 1.5)
            for i in range(16):
                seed = (i * 53) % 10 / 10
                ang = i * pi / 8 + seed * .3
                er, ec = cos(ang), sin(ang)
                k = min(hr / max(abs(er), 1e-6), hc / max(abs(ec), 1e-6))  # từ tâm ra tới mép vùng khối chiếm
                spread = (.18 + .3 * seed) * speed * ease
                pr, pc = cr + er * (k + spread), cc + ec * (k + spread)
                if (self.camera.depth(pr, pc, 0) > middle) != front:
                    continue
                x, y = self.project((pr, pc, .3 * speed * ease * (.5 + seed)))
                puffs.append((x, y, self.camera.tile_width * (.04 + .06 * ease) * (.7 + seed * .6), alpha))
        if not puffs:
            return
        x0, y0 = floor(min(x - s for x, _, s, _ in puffs)) - 1, floor(min(y - s for _, y, s, _ in puffs)) - 1
        x1, y1 = ceil(max(x + s for x, _, s, _ in puffs)) + 1, ceil(max(y + s for _, y, s, _ in puffs)) + 1
        # Vẽ trên lớp riêng, để bụi hoà lên các ô thay vì thay
        # pixel của chúng bằng pixel trong suốt.
        layer = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)), pygame.SRCALPHA)
        for x, y, s, alpha in puffs:
            pygame.draw.circle(layer, (*color, alpha), (x - x0, y - y0), max(1.0, s))
        canvas.blit(layer, (x0, y0))

    def _still_block(self, state, meshes):
        """Khối đứng yên được vẽ một lần vào một sprite nhỏ: (surface, vị trí)."""
        key = (state, self.size, self.camera, self.zoom, tuple(self.pan), self.style, self.high_contrast, self.BLOCK)
        if self._still_block_key != key:
            faces = self._block_faces(meshes)
            points = [p for _, pts, _, _ in faces for p in pts] or [(0, 0)]
            x0, y0 = floor(min(p[0] for p in points)) - 2, floor(min(p[1] for p in points)) - 2
            x1, y1 = ceil(max(p[0] for p in points)) + 2, ceil(max(p[1] for p in points)) + 2
            sprite = pygame.Surface((max(1, x1 - x0), max(1, y1 - y0)), pygame.SRCALPHA)
            for _, pts, color, cut in sorted(faces, key=lambda item: item[0]):
                self._block_face(sprite, [(x - x0, y - y0) for x, y in pts], color, cut, origin=(x0, y0))
            self._still_block_sprite = (sprite, (x0, y0))
            self._still_block_key = key
        return self._still_block_sprite

    def want_boards(self, bridge_states):
        """Các bố cục cầu (tuple bridges_status) người chơi sắp có thể gặp.

        Bàn của chúng được dựng trước, ~2 ms mỗi frame (xem _prebuild_wanted),
        nên bấm công tắc không bao giờ phải dựng bàn ngay lúc đó."""
        self._wanted_states = tuple(bridge_states)

    def _prebuild_wanted(self, budget):
        if self.stage is None or not self._base_cache:
            return
        deadline = time.perf_counter() + budget
        for status in self._wanted_states:
            shown = _Bridges(tuple(status))
            cells = self._active_cells(shown)
            if not self._advance_board(shown, cells, self._base_key(cells), deadline):
                return

    def _advance_board(self, shown, cells, key, deadline):
        """Dựng bàn `key` cho tới `deadline`; True khi bàn đã nằm trong cache."""
        if key in self._base_cache:
            return True
        if self._prebuild_key != key:
            self._prebuild = self._compose_board(shown, cells, key)
            self._prebuild_key = key
        for _ in self._prebuild:  # thoát vòng lặp giữa chừng vẫn giữ generator chạy tiếp được
            if time.perf_counter() > deadline:
                return False
        self._prebuild_key = None  # đã xong (hoặc đã bị loại khỏi cache): lần sau dựng lại từ đầu
        return key in self._base_cache

    def _compose_board(self, shown, active_cells, base_key):
        """Dựng một bàn (đường gióng blueprint, các ô) vào cache.

        Là generator, nhường lượt giữa các bước, để draw() có thể rải việc dựng bàn
        mà cầu sắp đáp xuống ra các frame trong lúc cầu bay."""
        base = pygame.Surface(self.size, pygame.SRCALPHA)
        yield
        top_mask = pygame.Surface(self.size, pygame.SRCALPHA)
        yield
        if self.style == 'blueprint':
            # Mặt bằng nền chuẩn và đường chiếu kiến trúc của blueprint
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
        # Bàn được dựng từ sprite của từng ô (xem _tile_sprite). Chúng được cache
        # theo camera, nên bật/tắt cầu hay vỡ một ô chỉ cần blit lại sprite thay vì
        # chiếu và tô vân lại mọi ô, việc từng làm animation cầu bị giật. Các
        # sprite này cũng dùng cho intro ráp bàn.
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
        yield
        for r, c in active_cells:
            pygame.draw.polygon(top_mask, (255, 255, 255, 255), self._tile_top(r, c))
        if self.stage.goal in active_cells:
            r, c = self.stage.goal
            pygame.draw.polygon(top_mask, (0, 0, 0, 0), [self.project(p) for p in cuboid(r + .16, c + .16, 0, .68, .68, 0)[:4]])
        if self.style == 'forest':
            self._moss_edges(shown, base)
        # Ô cầu được vẽ trước, nên frame cầu đáp xuống
        # chỉ cần blit lại sprite.
        for r, c in self.bridge_cells:
            if (r, c) not in self._tile_sprite_cache:
                yield
                self._tile_sprite(r, c)
        if len(self._base_cache) >= 6:  # có giới hạn: bỏ bàn ít dùng gần đây nhất,
            for old_key, old_entry in self._base_cache.items():  # không bao giờ bỏ bàn đang hiển thị
                if old_entry[0] is not self._base:
                    self._base_cache.pop(old_key)
                    break
        self._base_cache[base_key] = (base, top_mask, tile_sprites)

    def _tile_sprite(self, r, c):
        """Một ô sàn hoặc ô cầu đang mở, vẽ một lần cho mỗi camera rồi dùng lại.

        Trả về (surface, vị trí góc trên trái trên màn hình, độ sâu hoạ sĩ)."""
        key = (id(self.stage), self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast, self.style)
        if self._tile_sprite_key != key:
            self._tile_sprite_cache = {}
            self._tile_sprite_key = key
        cached = self._tile_sprite_cache.get((r, c))
        if cached is not None:
            return cached
        coord = (r, c)
        tile = self.stage.grid[r][c]
        bridge = self.bridge_cells.get(coord)
        vertices, indices = bevel_mesh(cuboid(r + .012, c + .012, -.32, .976, .976, .32), .02)
        if bridge is not None:  # ô cầu đang mở: có kiểu giống khối người chơi
            t_faces = self._faces(vertices, self.BLOCK, faces=indices, player=True)
        else:
            color = self._floor_color()
            if tile == TileType.FRAGILE:
                color = self.FRAGILE
            t_faces = self._faces(vertices, color, faces=indices)
        top = self._tile_top(r, c)
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
            label = SWITCH_LABELS[self.stage.switches[coord].type.value]
        if label:
            self._marker(tile_surf, (r + .5, c + .5, .01), label, offset=(min_x, min_y))
        result = (tile_surf, (min_x, min_y), self.camera.depth(r + .5, c + .5, 0))
        self._tile_sprite_cache[coord] = result
        return result

    def _supported(self, cell, bridges_status) -> bool:
        """Dưới ô này có sàn (không phải void / ngoài bàn / cầu đang đóng)."""
        r, c = cell
        grid = self.stage.grid
        if not (0 <= r < len(grid) and 0 <= c < len(grid[r])):
            return False
        bridge = self.bridge_cells.get(cell)
        if bridge is not None:
            return bridge < len(bridges_status) and bridges_status[bridge]
        return grid[r][c] != TileType.VOID

    def _broken_tile(self, pose: GameState) -> tuple[int, int] | None:
        """Ô fragile dưới khối đang đứng thẳng trên nó (ô sẽ vỡ), ngược lại None."""
        if self.stage is None or pose.orientation != Orientation.STANDING:
            return None
        r, c = pose.pos1
        grid = self.stage.grid
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]) and grid[r][c] == TileType.FRAGILE:
            return (r, c)
        return None

    def _fall_plan(self, motion: MotionFrame, tip: Tip | None) -> str:
        """Cách đầu tiên trong FALL_PLANS giữ khối đang rơi không lấn vào ô nào.
        Kiểm tra một lần cho mỗi cú rơi, tại vài chục thời điểm của nó."""
        if tip is None:
            return 'straight'
        plans = self._fall_plans
        key = (motion.before, motion.after, motion.action, self.camera.view)
        if key not in plans:
            plans[key] = next((plan for plan in FALL_PLANS if not self._fall_hits_tiles(motion, tip, plan)),
                              FALL_PLANS[0])
        return plans[key]

    def _fall_hits_tiles(self, motion: MotionFrame, tip: Tip, plan: str) -> bool:
        thickness, margin = tile_thickness(self.camera.view), .02
        tiles = {}
        for k in range(1, 21):
            frame = MotionFrame(motion.before, motion.after, motion.action,
                                FALL_ROLL_END + (1 - FALL_ROLL_END) * k / 20, falling=True)
            for vertices, _, moving in fall_meshes(frame, tip, plan):
                if not moving or min(p[2] for p in vertices) > -margin:
                    continue
                if max(p[2] for p in vertices) < -thickness:
                    continue  # đã ở dưới bàn
                for r, c, z in cuboid_samples(vertices, 3):
                    if not -thickness + margin < z < -margin:
                        continue
                    cell = (floor(r), floor(c))
                    if cell not in tiles:
                        tiles[cell] = self._supported(cell, motion.after.bridges_status)
                    if tiles[cell] and min(r - cell[0], cell[0] + 1 - r, c - cell[1], cell[1] + 1 - c) > margin:
                        return True
        return False

    def _tip(self, pose: GameState, action: Action) -> Tip | None:
        """Khối đang rơi lật qua mép nào (xem tip_mesh).

        - Mọi ô đều có sàn (ô fragile vỡ) -> None: rơi thẳng.
        - Khối nằm, một nửa có sàn -> lật dọc theo khối về phía nửa trống,
          quanh cạnh giữa hai nửa.
        - Không ô nào có sàn -> chúi về phía trước theo hướng lăn, quanh cạnh
          đáy phía sau của khối.
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
        points = sorted(set(points))

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        halves = []
        for sequence in (points, list(reversed(points))):
            half = []
            for point in sequence:
                while len(half) > 1 and cross(half[-2], half[-1], point) <= 0:
                    half.pop()
                half.append(point)
            halves.extend(half[:-1])
        return halves

    def _block_face(self, surface, points, color, cut=None, origin=(0, 0)):
        """origin: vị trí của `surface` trên bàn khi vẽ vào một sprite; các đốm lấp
        lánh được seed theo vị trí của mặt trên bàn, nên chúng khớp nhau."""
        pts = [(round(x), round(y)) for x, y in points]
        if not self._can_texture(surface, pts):
            return

        min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
        min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
        bw = max(2, max_x - min_x + 1)
        bh = max(2, max_y - min_y + 1)
        strength = min(1.3, max(0.5, sum(color) / 540.0))
        (c_top, c_mid, c_bot, edge_color, sheen_color, sparkle_colors,
         seam_dark, seam_light) = self._block_palette(color, strength)

        # Dải màu dọc 3 điểm dừng
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

        # Dải bóng sáng chéo
        sheen_y = int(bh * 0.25)
        pygame.draw.line(grad, sheen_color, (0, sheen_y), (bw, sheen_y + int(bh * 0.18)), 2)

        # Đốm lấp lánh và tia sáng hợp với theme
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        seed = int(abs((cx + origin[0]) * 73 + (cy + origin[1]) * 127)) % 10000
        rng = random.Random(seed)

        # Đốm lấp lánh nhỏ
        for _ in range(max(4, min(14, (bw * bh) // 120))):
            gx = rng.randint(1, max(1, bw - 2))
            gy = rng.randint(1, max(1, bh - 2))
            grad.set_at((gx, gy), rng.choice(sparkle_colors))

        # Tia sáng hình thoi
        for _ in range(max(1, min(4, (bw * bh) // 320))):
            sx = rng.randint(3, max(3, bw - 4))
            sy = rng.randint(3, max(3, bh - 4))
            grad.set_at((sx, sy), (255, 255, 255, 255))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if 0 <= sx + dx < bw and 0 <= sy + dy < bh:
                    grad.set_at((sx + dx, sy + dy), sparkle_colors[0])

        # Cắt đúng theo đa giác
        local_pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
        mask = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), local_pts)
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, (min_x, min_y))

        # Viền mượt
        self._outline(surface, edge_color, pts, cut)

        # Đường chia giữa trên các mặt dài (chia khối 1x1x2)
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

    def _block_palette(self, color, strength):
        if self.style == 'forest':
            # Dải màu vàng nắng cổ kính và đồng hổ phách đậm (gọn, không rối màu vàng)
            c_top = tuple(min(255, int(c * strength)) for c in (255, 240, 172))  # Đỉnh vàng ánh nắng
            c_mid = tuple(min(255, int(c * strength)) for c in (226, 174, 62))   # Vàng hổ phách ấm
            c_bot = tuple(min(255, int(c * strength)) for c in (148, 102, 28))   # Đồng sẫm
            edge_color = tuple(min(255, int(c * 1.12)) for c in c_top)
            sheen_color = (255, 255, 235, 75)
            sparkle_colors = ((255, 255, 220, 240), (255, 240, 160, 200), (245, 205, 90, 180), (255, 248, 225, 220))
            seam_dark = (88, 58, 16)
            seam_light = (255, 238, 145)

        elif self.style == 'blueprint':
            # Dải màu cam đất nung kiến trúc hợp với bản vẽ kỹ thuật blueprint
            c_top = tuple(min(255, int(c * strength)) for c in (255, 172, 115))  # Đỉnh đất nung san hô sáng
            c_mid = tuple(min(255, int(c * strength)) for c in (228, 92, 38))    # Đất nung bản vẽ rực
            c_bot = tuple(min(255, int(c * strength)) for c in (148, 48, 20))    # Nâu đất nung sẫm
            edge_color = (255, 185, 140) if sum(color) > 300 else (210, 110, 60)
            sheen_color = (255, 225, 205, 80)
            sparkle_colors = ((255, 240, 230, 230), (255, 200, 165, 200), (255, 160, 110, 180), (255, 250, 245, 210))
            seam_dark = (68, 20, 10)
            seam_light = (255, 160, 120)

        else:  # 'dream' và mặc định
            # Dải màu hồng nhiều sắc với đốm lấp lánh, hợp với bầu trời pastel của dream
            c_top = tuple(min(255, int(c * strength)) for c in (255, 226, 236))  # Đỉnh hồng đào sáng
            c_mid = tuple(min(255, int(c * strength)) for c in (246, 148, 178))  # Hồng hoa rực
            c_bot = tuple(min(255, int(c * strength)) for c in (210, 98, 140))   # Hồng hoàng hôn sẫm
            edge_color = tuple(min(255, int(c * 1.15)) for c in c_top)
            sheen_color = (255, 255, 255, 80)
            sparkle_colors = ((255, 255, 255, 230), (255, 235, 245, 200), (255, 218, 235, 190), (255, 248, 220, 210))
            seam_dark = (198, 92, 132)
            seam_light = (255, 230, 242)
        return c_top, c_mid, c_bot, edge_color, sheen_color, sparkle_colors, seam_dark, seam_light

    @staticmethod
    def _outline(surface, color, pts, cut=None):
        if not cut or not any(cut):
            pygame.draw.aalines(surface, color, True, pts)
            return
        for (a, b), skip in zip(zip(pts, pts[1:] + pts[:1]), cut):
            if not skip:
                pygame.draw.aaline(surface, color, a, b)

    @staticmethod
    def _can_texture(surface, pts):
        # SDL_gfx báo lỗi với đa giác cao bằng 0 hoặc bị cắt hết, ví dụ khối rơi ra ngoài màn hình.
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        box = pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
        return max(ys) > min(ys) and box.colliderect(surface.get_clip())

    def _clear(self, surface):
        surface.fill((0, 0, 0, 0) if surface.get_flags() & pygame.SRCALPHA else self.BACKGROUND)

    def _tile_top(self, r, c):
        return [self.project(p) for p in cuboid(r + .012, c + .012, 0, .976, .976, 0)[:4]]

    def _floor_color(self):
        return HIGH_CONTRAST_FLOOR if self.high_contrast else self.FLOOR

    def _block_faces(self, meshes, clip_floor=False):
        faces = []
        for vertices, active in meshes:
            vertices, indices = bevel_mesh(vertices, .04, uniform=True)
            color = tuple(min(255, c + 18) for c in self.BLOCK) if active else self.BLOCK
            if clip_floor:
                vertices, indices = clip_below_floor(vertices, indices)
            faces.extend(self._faces(vertices, color, faces=indices, player=True))
        return faces

    def _paint_block(self, canvas, faces):
        for _, pts, color, cut in sorted(faces, key=lambda item: item[0]):
            self._block_face(canvas, pts, color, cut)

    def draw(self, surface, state, motion=None, intro_t=None, outro_t=None, shockwave=None,
             bridges=None, clear=True):
        """Vẽ bàn cho `state` (cùng `motion`, nếu đang lăn) lên `surface`.

        bridges: (trạng thái cũ, trạng thái mới, tiến độ) khi cầu của công tắc
        bay vào hoặc vỡ ra. Nó chạy theo dòng thời gian riêng (xem
        BloxorzApp.bridge_fx), nên khối vẫn lăn với tốc độ bình thường.

        clear=False: vẽ đè lên nội dung `surface` đang có thay vì xoá trước; khi
        đó frame chuyển động được dựng thẳng lên nó, tiết kiệm một lần chép toàn
        khung mỗi frame. `surface` nên có alpha từng pixel (hiệu ứng phát sáng và
        hạt dùng màu bán trong suốt).
        """
        if surface.get_size() != self.size:
            self.resize(surface.get_size())
        if self._frame.get_size() != self.size:
            self._frame = pygame.Surface(self.size, pygame.SRCALPHA)
        if self.stage is None:
            if clear:
                self._clear(surface)
            return

        changing_bridges = ()
        if bridges is not None:
            old_bridges, new_bridges, _ = bridges
            changing_bridges = tuple(i for i, (b_old, b_new) in enumerate(zip(old_bridges, new_bridges)) if b_old != b_new)
        shown = motion.before if motion and motion.progress < .65 else state
        broken = (self._broken_tile(motion.after)
                  if motion and motion.falling and motion.progress >= FALL_ROLL_END else None)
        static_key = (self.size, self.camera, self.zoom, tuple(self.pan), self.high_contrast, shown.bridges_status,
                      changing_bridges, broken)
        material_key = (self.size, self.camera, self.zoom, self.high_contrast, self.style)
        if material_key != self._material_key:
            self.material_cache.clear()
            self._material_key = material_key
        busy_frame = static_key != self._static_key  # không dựng trước khi vừa đổi bàn
        if busy_frame:
            self._build_static(shown, broken, changing_bridges=changing_bridges)
            self._static_key = static_key

        # Khi cầu bay vào (hoặc vỡ ra), dựng bàn mà nó sẽ đáp xuống, mỗi frame
        # vài mili giây, để frame tiếp đất không bị khựng.
        target = None
        if changing_bridges:
            landed = _Bridges(tuple(new_bridges))
            target_cells = self._active_cells(landed)
            target_key = self._base_key(target_cells)
            target = self._base_cache.get(target_key)
            if target is None:
                self._advance_board(landed, target_cells, target_key, time.perf_counter() + .002)
                target = self._base_cache.get(target_key)

        if intro_t is not None:
            self._draw_intro(surface, state, intro_t, clear)
            return
        if outro_t is not None:
            self._draw_outro(surface, outro_t, clear)
            return
        key = (state, motion, static_key, bridges)
        # Frame chuyển động (lăn, rơi, cầu bay) đằng nào cũng đổi mỗi frame:
        # với clear=False nó được dựng thẳng lên `surface`. Frame tĩnh được
        # dựng một lần vào self._frame rồi dùng lại.
        direct = not clear and (motion is not None or bridges is not None)
        canvas = surface if direct else self._frame
        busy_frame = busy_frame or (not direct and key != self._frame_key)  # frame tĩnh đang được dựng lại
        if direct or key != self._frame_key:
            self.stats['dynamic_frames'] += 1
            if not direct:
                self._frame.fill((0, 0, 0, 0))
            self._compose_frame(canvas, state, motion, shown, broken, bridges, changing_bridges, target)
            self._frame_key = None if direct else key
        else:
            self.stats['frame_cache_hits'] += 1
        if not direct:
            if clear:
                self._clear(surface)
            surface.blit(self._frame, (0, 0))
        if not changing_bridges and not busy_frame:
            self._prebuild_wanted(.002)

        moving = motion is not None and not motion.falling and not motion.sinking
        if motion is None or moving:
            self._draw_beacon(surface, state, motion)
        if shockwave is not None:
            self._draw_shockwave(surface, shockwave)
        if moving:
            self._draw_split_tracer(surface, motion)
            self._draw_merge_arcs(surface, motion)
        if motion and motion.sinking:
            self._draw_goal_portal(surface, motion)
        self.stats['material_cache_bytes'] = sum(s.get_pitch() * s.get_height() for s in self.material_cache.values())

    def _draw_intro(self, surface, state, intro_t, clear):
        # Intro của màn: các ô bay vào từ mọi phía, rồi khối rơi xuống
        # ô xuất phát và nảy lên (xem intro_drop()).
        t = intro_t * INTRO_SECONDS
        tiles_t = t / INTRO_TILES_SECONDS
        self._frame.fill((0, 0, 0, 0))

        for depth, spr, (x0, y0), (r, c), delay, theta_base, radius_base in self._tile_sprites:
            p = max(0.0, min(1.0, (tiles_t - delay) / 0.55))
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

        drop = intro_drop(t)
        if drop is not None:
            height, squash = drop
            meshes = state_meshes(state)
            # Bóng đậm dần khi khối hạ xuống.
            self._block_shadow(self._frame, meshes, fade=(1.0 - height / INTRO_DROP_HEIGHT) ** 2)
            self._landing_dust(self._frame, meshes, t, front=False)
            lifted = [([(r, c, z + height) for r, c, z in squash_mesh(vertices, squash)], active)
                      for vertices, active in meshes]
            self._paint_block(self._frame, self._block_faces(lifted))
            self._landing_dust(self._frame, meshes, t, front=True)

        # Bàn lún nhẹ mỗi lần va chạm: một nhịp nhún ngắn có giảm chấn.
        jolt = 0.0
        for hit, speed in INTRO_IMPACTS:
            if 0.0 <= t - hit < .3:
                since = t - hit
                jolt += self.camera.tile_width * .05 * speed * math.exp(-since * 14) * sin(since * 2 * pi / .16)
        if clear:
            self._clear(surface)
        surface.blit(self._frame, (0, round(jolt)))
        self._frame_key = None

    def _draw_outro(self, surface, outro_t, clear):
        # Outro thắng: sau khi khối chìm vào ô đích, các ô rơi đi theo
        # làn sóng lan ra từ lỗ đích. Mỗi ô bắt đầu nhẹ nhàng rồi rơi nhanh
        # dần và mờ đi, nên bàn trống dần một cách mượt mà; tại
        # outro_t = 1 không còn gì (bàn vẫn trống phía sau hộp thoại
        # "Stage complete").
        p = min(1.0, max(0.0, outro_t))
        self._frame.fill((0, 0, 0, 0))
        if p < 1.0 and self._tile_sprites:
            gr, gc = self.stage.goal
            reach = max(1.0, max(((r - gr) ** 2 + (c - gc) ** 2) ** .5
                                 for _, _, _, (r, c), *_ in self._tile_sprites))
            fall = self.camera.tile_width * 3.2   # pixel thiết bị, để Retina và 1x khớp nhau
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
            self._clear(surface)
        surface.blit(self._frame, (0, 0))
        self._frame_key = None

    def _compose_frame(self, canvas, state, motion, shown, broken, bridges, changing_bridges, target):
        falling = bool(motion and motion.falling)
        if falling:
            tip = self._tip(motion.after, motion.action)
            tagged = fall_meshes(motion, tip, self._fall_plan(motion, tip))
            dropping = motion.progress >= FALL_ROLL_END
            meshes = [(v, a) for v, a, _ in tagged]
        else:
            sinking = bool(motion and motion.sinking)
            meshes = sink_meshes(motion) if sinking else motion_meshes(motion) if motion else state_meshes(state)
        canvas.blit(self._base, (0, 0))
        if changing_bridges:
            old_bridges, new_bridges, b_p = bridges
            b_p = max(0.0, min(1.0, b_p))
            # Cầu đang hiện ra hoà dần vào bàn cuối cùng khi nó tới nơi, để nó
            # không bật ra sau đó. Chỉ vùng quanh các cầu đang đổi là khác
            # nhau, nên chỉ hoà phần đó.
            opening = any(n and not o for o, n in zip(old_bridges, new_bridges))
            fade = (b_p - .55) / .45 if opening else 0.0
            if target is not None and fade > 0:
                area = self._bridge_area(changing_bridges)
                target[0].set_alpha(min(255, int(255 * fade)))
                canvas.blit(target[0], area.topleft, area)
                target[0].set_alpha(255)
        self._draw_pressed_switches(canvas, shown)
        if changing_bridges:
            self._draw_bridge_transition(canvas, old_bridges, new_bridges, b_p)

        shadow_meshes = ([(v, a) for v, a, moving in tagged if not moving] if falling and dropping
                         else [] if motion and motion.sinking else meshes)
        self._block_shadow(canvas, shadow_meshes)
        if motion is None:
            # Khối đứng yên (ví dụ khi cầu đang bay): dùng lại hình của nó.
            sprite, position = self._still_block(state, meshes)
            canvas.blit(sprite, position)
            meshes = []
        if falling:
            self._draw_falling(canvas, [(v, a) for v, a, m in tagged if m])
            meshes = [(v, a) for v, a, m in tagged if not m]  # khối nhỏ còn lại vẫn nằm trên bàn
        # khi khối chìm, lỗ nuốt mất phần nằm dưới sàn
        self._paint_block(canvas, self._block_faces(meshes, clip_floor=bool(motion and motion.sinking)))

        if broken is not None and falling and motion.progress >= FALL_ROLL_END:
            self._draw_fragile_shatter(canvas, broken, motion.progress)

    def _draw_pressed_switches(self, canvas, shown):
        # Công tắc lún xuống khi bị đè lên
        for coord in (shown.pos1, shown.pos2):
            if coord in self.stage.switches:
                sw_label = SWITCH_LABELS[self.stage.switches[coord].type.value]
                r, c = coord
                bridge = self.bridge_cells.get(coord)
                color = self.BLOCK if bridge is not None else self._floor_color()
                self._material(canvas, self._tile_top(r, c), color)
                self._marker(canvas, (r + 0.5, c + 0.5, -0.05), sw_label)

    def _draw_bridge_transition(self, canvas, old_bridges, new_bridges, b_p):
        # Cầu bay lên và vỡ sụp
        for coord, b_idx in self.bridge_cells.items():
            if b_idx < len(old_bridges) and b_idx < len(new_bridges):
                old_s = old_bridges[b_idx]
                new_s = new_bridges[b_idx]
                if old_s != new_s:
                    br_r, br_c = coord
                    if not old_s and new_s:
                        # 1. Cầu mở: phóng lên từ dưới khung cửa sổ game thẳng vào vị trí
                        spr, (bx, by), _ = self._tile_sprite(*coord)
                        y_start = self.size[1] + 60
                        b_ease = 1.0 - (1.0 - b_p) ** 3.0
                        cur_y = int(by + (y_start - by) * (1.0 - b_ease))

                        # Vệt lực đẩy khi bay lên
                        streak_h = max(4, int(52 * (1.0 - b_ease)))
                        trail_col = {'dream': (255, 180, 220, 160), 'forest': (255, 215, 60, 160), 'blueprint': (80, 220, 255, 160)}.get(self.style, (255, 255, 255, 160))
                        trail_y = cur_y + spr.get_height() - 4
                        for sx in (bx + 8, bx + spr.get_width() - 8, bx + spr.get_width() // 2):
                            pygame.draw.line(canvas, trail_col, (sx, trail_y), (sx, trail_y + streak_h), 2)

                        # Blit sprite ô cầu đã dựng sẵn (0.005 ms)
                        canvas.blit(spr, (bx, cur_y))

                        # Vòng sáng khi tới nơi
                        if b_p >= 0.84:
                            snap_a = int(240 * (b_p - 0.84) / 0.16)
                            top_p = [self.project(p) for p in cuboid(br_r, br_c, 0.01, 1, 1, 0)[:4]]
                            snap_col = {'dream': (255, 220, 240, snap_a), 'forest': (255, 245, 160, snap_a), 'blueprint': (140, 240, 255, snap_a)}.get(self.style, (255, 255, 255, snap_a))
                            pygame.draw.aalines(canvas, snap_col, True, top_p)
                    elif old_s and not new_s:
                        # 2. Cầu đóng: ô lún xuống một chút rồi mờ dần.
                        spr, (bx, by), _ = self._tile_sprite(*coord)
                        sink = self.camera.tile_width * .3 * (1.0 - (1.0 - min(1.0, b_p / .6)) ** 2)
                        alpha = int(255 * (1.0 - max(0.0, (b_p - .2) / .8)) ** 1.3)
                        if alpha > 0:
                            spr.set_alpha(alpha)
                            canvas.blit(spr, (bx, round(by + sink)))
                            spr.set_alpha(255)

    def _draw_fragile_shatter(self, canvas, broken, progress):
        # Ô fragile vỡ: mảnh đá to và bụi khoáng mịn
        br, bc = broken
        t = max(0.0, min(1.0, (progress - FALL_ROLL_END) / (1.0 - FALL_ROLL_END)))

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

    def _draw_beacon(self, surface, state, motion):
        # Beacon kim cương 3D nhiều mặt đi kèm (hiện trong suốt quá trình chơi)
        # Lơ lửng trên khối 1x1 đang đứng, ở giữa khối 1x2 đang nằm, hoặc trên khối nhỏ đang chọn ở chế độ SPLIT
        ticks = int(motion.progress * 1000) if motion else pygame.time.get_ticks()
        # Tính tâm beacon và chiều cao đỉnh khối
        if motion is not None:
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
            else:  # LYING_H hoặc LYING_V: ở giữa hai ô
                ar = (state.pos1[0] + state.pos2[0]) * 0.5 + 0.5
                ac = (state.pos1[1] + state.pos2[1]) * 0.5 + 0.5
                block_top_z = 1.0

        # Nhấp nhô theo chiều dọc (+- 0.22 chiều cao ô, mượt 60 FPS)
        z_mid = block_top_z + 0.68 + sin(ticks * 0.0055) * 0.22
        z_top = z_mid + 0.38
        z_bot = z_mid - 0.38
        rot_ang = ticks * 0.0035
        r_rad = 0.26

        eq = [self.project((ar + r_rad * cos(rot_ang + k * pi / 2),
                            ac + r_rad * sin(rot_ang + k * pi / 2), z_mid)) for k in range(4)]
        top_p = self.project((ar, ac, z_top))
        bot_p = self.project((ar, ac, z_bot))

        # Bảng màu theo theme:
        # Dream City: hồng
        # Forest Ruins: vàng hổ phách
        # Blueprint Studio: đỏ
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
        else:  # 'blueprint' / giấy
            c_light = (255, 180, 180, 245)
            c_mid = (245, 55, 55, 230)
            c_dark = (185, 20, 20, 210)
            ring_col = (255, 105, 105)

        # 4 mặt trên (vẽ thẳng lên surface)
        pygame.draw.polygon(surface, c_light, [top_p, eq[0], eq[1]])
        pygame.draw.polygon(surface, c_mid, [top_p, eq[1], eq[2]])
        pygame.draw.polygon(surface, c_dark, [top_p, eq[2], eq[3]])
        pygame.draw.polygon(surface, c_mid, [top_p, eq[3], eq[0]])

        # 4 mặt dưới
        pygame.draw.polygon(surface, c_mid, [bot_p, eq[1], eq[0]])
        pygame.draw.polygon(surface, c_dark, [bot_p, eq[2], eq[1]])
        pygame.draw.polygon(surface, c_dark, [bot_p, eq[3], eq[2]])
        pygame.draw.polygon(surface, c_mid, [bot_p, eq[0], eq[3]])

        # Cạnh các mặt pha lê màu trắng
        for k in range(4):
            pygame.draw.aaline(surface, (255, 255, 255), top_p, eq[k])
            pygame.draw.aaline(surface, (255, 255, 255), bot_p, eq[k])
            pygame.draw.aaline(surface, (255, 255, 255), eq[k], eq[(k + 1) % 4])

        # Vòng hào quang nghiêng quanh eo kim cương (nhấp nhô theo z_mid)
        ring_pts = [self.project((ar + 0.38 * cos(rot_ang * 1.6 + i * pi / 8),
                                  ac + 0.38 * sin(rot_ang * 1.6 + i * pi / 8),
                                  z_mid + 0.08 * sin(i * pi / 4))) for i in range(16)]
        pygame.draw.aalines(surface, (*ring_col, 200), True, ring_pts)
        for k in (0, 4, 8, 12):
            node_pt = ring_pts[k]
            pygame.draw.circle(surface, (255, 255, 255, 220), (round(node_pt[0]), round(node_pt[1])), 1)

    def _draw_shockwave(self, surface, shockwave):
        # Vòng sóng xung kích lan rộng khi hợp khối (vẽ thẳng lên surface)
        sr, sc, st = shockwave
        p = max(0.0, min(1.0, st / SHOCKWAVE_SECONDS))
        center = self.project((sr + 0.5, sc + 0.5, 0.02))
        rx = int((20.0 + p * 65.0) * self.zoom)
        ry = int(rx * 0.48)
        alpha = int(180 * (1.0 - p))
        if rx > 2 and ry > 2 and alpha > 0:
            wave_color = (255, 235, 170, alpha) if self.style == 'dream' else ((60, 240, 255, alpha) if self.style == 'blueprint' else (160, 255, 140, alpha))
            pygame.draw.ellipse(surface, wave_color, (center[0] - rx, center[1] - ry, rx * 2, ry * 2), max(1, int(3 * (1.0 - p) * self.zoom)))

    def _draw_split_tracer(self, surface, motion):
        # Luồng sáng dịch chuyển khi tách khối
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

    def _draw_merge_arcs(self, surface, motion):
        # Tia điện giữa hai khối nhỏ đang hút vào nhau khi hợp khối
        is_merge = (motion.before.orientation == Orientation.SPLIT
                    and motion.after.orientation != Orientation.SPLIT)
        if is_merge and motion.progress > 0.60:
            mp = (motion.progress - 0.60) / 0.40
            arc_alpha = max(0, int(230 * sin(pi * mp)))
            c1_pt = self.project((motion.after.pos1[0] + 0.5, motion.after.pos1[1] + 0.5, 0.5))
            c2_pt = self.project((motion.after.pos2[0] + 0.5, motion.after.pos2[1] + 0.5, 0.5))
            ticks = int(motion.progress * 1000)
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

    def _draw_goal_portal(self, surface, motion):
        # Cổng ánh sáng ở ô đích (cột sáng thể tích và các hạt bay lên)
        gr, gc = self.stage.goal
        sp = max(0.0, min(1.0, motion.progress))
        beam_alpha = min(255, int(255 * sin(pi * sp * 0.90)))
        if beam_alpha <= 0:
            return
        ticks = int(motion.progress * 1000)

        # Bảng màu theo theme
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
        else:  # blueprint / giấy (tông đỏ thẫm)
            c_core = (255, 245, 245)
            c_inner = (255, 60, 60)
            c_outer = (205, 20, 20)
            c_ground = (255, 55, 55)

        # 1. Vũng sáng dịu trên mặt đất và viền ô đích phát sáng
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

        # 2. Cột sáng thể tích (bay lên và mờ dần lên trời)
        layers = [
            (0.72, 1.10, c_outer, 0.18),  # Sương mờ bên ngoài
            (0.48, 0.75, c_inner, 0.38),  # Quầng sáng xung quanh
            (0.26, 0.42, c_inner, 0.65),  # Cột sáng bên trong
            (0.12, 0.18, c_core,  0.88),  # Lõi sáng rực
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

        # 3. Các dải sáng uốn lượn bay lơ lửng
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

        # 4. Hiệu ứng riêng của từng theme
        if self.style == 'dream':
            self._portal_petals(surface, gr, gc, ticks, beam_alpha)
        elif self.style == 'forest':
            self._portal_fireflies(surface, gr, gc, ticks, beam_alpha)
        else:
            self._portal_data_stream(surface, gr, gc, ticks, beam_alpha)

    def _portal_petals(self, surface, gr, gc, ticks, beam_alpha):
        # Cánh hoa anh đào phát sáng bay lên, nghiêng theo gió, kèm bụi sao
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
                # Tia sao 4 cánh
                glint_col = (255, 255, 255, p_a)
                g_rad = 3 if p_a > 140 else 2
                pygame.draw.line(surface, glint_col, (p_pos[0] - g_rad, p_pos[1]), (p_pos[0] + g_rad, p_pos[1]), 1)
                pygame.draw.line(surface, glint_col, (p_pos[0], p_pos[1] - g_rad), (p_pos[0], p_pos[1] + g_rad), 1)
                pygame.draw.circle(surface, (255, 240, 250, p_a), (round(p_pos[0]), round(p_pos[1])), 1)
            else:
                # Cánh hoa anh đào hồng bán trong suốt, nghiêng 3D theo gió
                tilt = sin(ticks * 0.006 + i * 2.0)
                pw = max(3, int(7 * (0.6 + 0.4 * abs(tilt))))
                ph = max(2, int(5 * (0.6 + 0.4 * (1.0 - abs(tilt)))))
                pet_col = (255, 180 + (i % 3) * 25, 220 + (i % 2) * 20, p_a)
                pygame.draw.ellipse(surface, pet_col, (p_pos[0] - pw // 2, p_pos[1] - ph // 2, pw, ph))

    def _portal_fireflies(self, surface, gr, gc, ticks, beam_alpha):
        # Bầy đom đóm phát sáng của rừng
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

    def _portal_data_stream(self, surface, gr, gc, ticks, beam_alpha):
        # Luồng dữ liệu: các vòng xung màu đỏ thẫm bay lên và dấu toạ độ
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

    def _material(self, surface, points, color):
        x, y = floor(min(p[0] for p in points)), floor(min(p[1] for p in points))
        local = [(p[0] - x, p[1] - y) for p in points]
        key = (tuple((round(a, 2), round(b, 2)) for a, b in local), color)
        stamp = self.material_cache.get(key)
        if stamp is None:
            stamp = pygame.Surface((max(1, ceil(max(p[0] for p in local)) + 1), max(1, ceil(max(p[1] for p in local)) + 1)),
                                   pygame.SRCALPHA)
            self._paint_material(stamp, local, color)
            if len(self.material_cache) > 3000:  # ~1 bàn lớn + các cầu của nó
                self.material_cache.clear()
            self.material_cache[key] = stamp
        surface.blit(stamp, (x, y))

    def _paint_material(self, surface, points, color):
        pygame.draw.polygon(surface, color, points)
        if self.style == 'forest' and self.stone_texture is not None:
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
        """Rêu treo dựng sẵn, chỉ dọc các cạnh trước bị lộ ra."""
        surface = self._base if surface is None else surface
        rng = random.Random(842)
        cells = set(self._active_cells(shown))
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
        draw = {'goal': self._goal_marker, 'O': self._soft_switch_marker, 'X': self._heavy_switch_marker,
                '<>': self._split_switch_marker, '!': self._fragile_marker}.get(kind)
        if draw is not None:
            draw(surface, project, r, c, pressed)

    def _goal_marker(self, surface, project, r, c, pressed):
        # Hố xoáy 3D: viền đồng tâm nhiều lớp, thành trong 3D và lõi cổng
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

    def _soft_switch_marker(self, surface, project, r, c, pressed):
        # CÔNG TẮC MỀM: viên đá thạch anh vàng nhiều mặt với vòng quỹ đạo và đỉnh phản chiếu
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

    def _heavy_switch_marker(self, surface, project, r, c, pressed):
        # CÔNG TẮC NẶNG: chữ thập hồng ngọc nhiều mặt theo hai đường chéo của ô (đúng hình 'X')
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

        # 4 cánh theo các góc chéo tạo thành chữ 'X' rõ, đậm trên hai đường chéo của ô
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

    def _split_switch_marker(self, surface, project, r, c, pressed):
        # CÔNG TẮC TÁCH: cổng dịch chuyển tương phản cao với bảng màu neon theo theme
        dz_q = 0.038 if not pressed else -0.015

        # Bảng màu tối ưu tương phản, đảm bảo nhìn thấy ngay trên cả theme sáng lẫn tối
        if self.style == 'dream':  # Ô hồng pastel nhạt -> tím thạch anh / đỏ tươi / vàng rực
            c_light = (255, 175, 235) if not pressed else (210, 130, 195)
            c_mid = (195, 45, 175) if not pressed else (145, 25, 125)
            c_dark = (115, 18, 105) if not pressed else (80, 10, 75)
            c_glow = (225, 65, 205) if not pressed else (160, 35, 145)
            c_gold = (255, 215, 60) if not pressed else (210, 175, 40)
            well_col = (85, 22, 75, 65)
        elif self.style == 'blueprint':  # Giấy vẽ xanh nhạt/trắng -> xanh coban kiến trúc đậm / xanh lơ
            c_light = (110, 220, 255) if not pressed else (60, 170, 215)
            c_mid = (20, 110, 215) if not pressed else (10, 75, 160)
            c_dark = (8, 48, 115) if not pressed else (5, 30, 80)
            c_glow = (25, 140, 255) if not pressed else (15, 95, 190)
            c_gold = (0, 230, 255) if not pressed else (0, 175, 210)
            well_col = (14, 45, 95, 75)
        else:  # forest ruins -> ngọc lục bảo sáng / ngọc bích / vàng nắng
            c_light = (160, 255, 205) if not pressed else (105, 215, 155)
            c_mid = (35, 205, 120) if not pressed else (20, 150, 85)
            c_dark = (12, 105, 55) if not pressed else (8, 70, 35)
            c_glow = (50, 240, 140) if not pressed else (30, 175, 95)
            c_gold = (255, 225, 70) if not pressed else (210, 180, 45)
            well_col = (10, 32, 20, 85)

        # 1. Giếng rune khắc chìm nhẹ (tạo nền tối tương phản trên mọi ô)
        well_pts = [project(0.38 * cos(k * pi / 6), 0.38 * sin(k * pi / 6), 0.002) for k in range(12)]
        pygame.draw.polygon(surface, well_col, well_pts)
        pygame.draw.aalines(surface, c_dark, True, well_pts)

        # 2. Các vòng rune phát sáng đồng tâm và điểm neo ở góc
        outer_ring = [project(0.34 * cos(k * pi / 6), 0.34 * sin(k * pi / 6), 0.006) for k in range(12)]
        pygame.draw.aalines(surface, c_glow, True, outer_ring)
        inner_ring = [project(0.23 * cos(k * pi / 6), 0.23 * sin(k * pi / 6), 0.006) for k in range(12)]
        pygame.draw.aalines(surface, c_gold, True, inner_ring)

        for dr, dc in ((-.34, -.34), (-.34, .34), (.34, .34), (.34, -.34)):
            p_c = project(dr, dc, 0.006)
            pygame.draw.circle(surface, c_gold, (round(p_c[0]), round(p_c[1])), 2)
            p_in = project(dr * 0.65, dc * 0.65, 0.006)
            pygame.draw.aaline(surface, c_glow, p_c, p_in)

        # 3. Lăng trụ chevron trái `<` nhiều mặt
        c_tip_l = project(0, -.28, dz_q)
        c_top_l = project(-.22, -.07, dz_q)
        c_bot_l = project(.22, -.07, dz_q)
        c_in_l = project(0, -.13, dz_q + 0.03)

        f_left_top = [c_top_l, c_tip_l, c_in_l]
        f_left_bot = [c_tip_l, c_bot_l, c_in_l]
        pygame.draw.polygon(surface, c_light, f_left_top)
        pygame.draw.polygon(surface, c_mid, f_left_bot)
        pygame.draw.aalines(surface, (255, 255, 255), True, f_left_top)
        pygame.draw.aalines(surface, c_light, True, f_left_bot)

        # 4. Lăng trụ chevron phải `>` nhiều mặt
        c_tip_r = project(0, .28, dz_q)
        c_top_r = project(-.22, .07, dz_q)
        c_bot_r = project(.22, .07, dz_q)
        c_in_r = project(0, .13, dz_q + 0.03)

        f_right_top = [c_top_r, c_tip_r, c_in_r]
        f_right_bot = [c_tip_r, c_bot_r, c_in_r]
        pygame.draw.polygon(surface, c_light, f_right_top)
        pygame.draw.polygon(surface, c_mid, f_right_bot)
        pygame.draw.aalines(surface, (255, 255, 255), True, f_right_top)
        pygame.draw.aalines(surface, c_light, True, f_right_bot)

        # 5. Hai viên đá nhỏ ở giữa (tượng trưng cho 2 khối đã tách)
        for gem_dc, gem_col in ((-0.055, c_gold), (0.055, c_light)):
            g_top = project(0, gem_dc, dz_q + 0.055)
            g_eq = [project(0.045 * cos(k * pi / 2), gem_dc + 0.045 * sin(k * pi / 2), dz_q + 0.02) for k in range(4)]
            pygame.draw.polygon(surface, (255, 255, 255), [g_top, g_eq[0], g_eq[1]])
            pygame.draw.polygon(surface, gem_col, [g_top, g_eq[1], g_eq[2]])
            pygame.draw.polygon(surface, c_dark, [g_top, g_eq[2], g_eq[3]])
            pygame.draw.polygon(surface, gem_col, [g_top, g_eq[3], g_eq[0]])
            pygame.draw.aalines(surface, (255, 255, 255), True, g_eq)
            pygame.draw.circle(surface, (255, 255, 255), (round(g_top[0]), round(g_top[1])), 2)

    def _fragile_marker(self, surface, project, r, c, pressed):
        # Ô FRAGILE: mạng vết nứt nhiều nhánh sinh theo thủ tục, có nổi khối sáng tối 3D
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

"""Procedural isometric SVG illustrations of LEGO parts in their real colour.

Used whenever a part has no uploaded photo, so every colour of every part has
an accurate preview.  Shapes are chosen from the part's official name
("Brick 2 x 4", "Technic Beam 1 x 7 Thick", "Slope 45° 2 x 2" ...) with a few
explicit overrides for well known designs.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

C30 = math.cos(math.radians(30))
S30 = 0.5
SCALE = 34.0
PLATE = 0.4
BRICK = 1.2
STUD_R = 0.3
STUD_H = 0.18
LIGHT = (0.25, 0.55, 0.8)
VIEW = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# colour helpers
# ---------------------------------------------------------------------------
def _rgb(hexstr: str) -> tuple[int, int, int]:
    h = (hexstr or "CCCCCC").lstrip("#")
    if len(h) != 6:
        h = "CCCCCC"
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _shade(rgb, t: float) -> str:
    f = 0.62 + 0.42 * t
    lum = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    # dark colours (black, dark blue...) get lifted so their faces stay readable
    lift = 0.0 if lum > 90 else (90 - lum) / 90 * 70 * max(t + 0.15, 0.0)
    return _hex(tuple(c * f + lift for c in rgb))


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    n = math.sqrt(_dot(v, v)) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


def proj(x: float, y: float, z: float) -> tuple[float, float]:
    return (x - y) * C30 * SCALE, (x + y) * S30 * SCALE - z * SCALE


class Canvas:
    def __init__(self, hexcolor: str, transparent: bool = False, finish: str = "solid"):
        self.rgb = _rgb(hexcolor)
        self.trans = transparent
        self.finish = finish
        self.layers: list[tuple[float, str]] = []
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.seq = 0
        dark = sum(self.rgb) < 160
        self.edge = _hex(tuple(min(255, c * 0.6 + 70) for c in self.rgb)) if dark else _shade(self.rgb, -0.6)

    # -- bookkeeping ---------------------------------------------------
    def _track(self, pts2):
        for x, y in pts2:
            self.xs.append(x)
            self.ys.append(y)

    def add(self, depth: float, svg: str):
        self.seq += 1
        self.layers.append((depth + self.seq * 1e-6, svg))

    def fill(self, t: float) -> str:
        return _shade(self.rgb, t)

    def style(self, t: float, extra: str = "") -> str:
        op = ' fill-opacity="0.62"' if self.trans else ""
        return (f'fill="{self.fill(t)}"{op} stroke="{self.edge}" stroke-width="1.1" '
                f'stroke-linejoin="round" stroke-opacity="{0.8 if self.trans else 0.55}"{extra}')

    # -- primitives ----------------------------------------------------
    def face(self, pts3, normal=None, depth=None, t=None, extra=""):
        if normal is None:
            normal = _face_normal(pts3)
        if t is None:
            t = _dot(_norm(normal), LIGHT)
        pts2 = [proj(*p) for p in pts3]
        self._track(pts2)
        d = sum(p[0] + p[1] + p[2] for p in pts3) / len(pts3) if depth is None else depth
        path = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z"
        self.add(d, f'<path d="{path}" {self.style(t, extra)}/>')
        return path

    def raw(self, depth: float, svg: str, pts2=()):
        self._track(pts2)
        self.add(depth, svg)

    def render(self, size: int = 320, pad: float = 14) -> str:
        if not self.xs:
            return _empty_svg(size)
        minx, maxx, miny, maxy = min(self.xs), max(self.xs), min(self.ys), max(self.ys)
        w, h = maxx - minx, maxy - miny
        side = max(w, h) + pad * 2
        vx = minx - (side - w) / 2
        vy = miny - (side - h) / 2
        body = "".join(svg for _, svg in sorted(self.layers, key=lambda it: it[0]))
        defs = ""
        if self.finish in ("chrome", "metallic", "pearl"):
            defs = ('<defs><linearGradient id="gl" x1="0" y1="0" x2="1" y2="1">'
                    '<stop offset="0" stop-color="#fff" stop-opacity=".55"/>'
                    '<stop offset=".5" stop-color="#fff" stop-opacity="0"/>'
                    '<stop offset="1" stop-color="#000" stop-opacity=".15"/></linearGradient></defs>')
            body += (f'<rect x="{vx:.1f}" y="{vy:.1f}" width="{side:.1f}" height="{side:.1f}" '
                     f'fill="url(#gl)" style="mix-blend-mode:soft-light"/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.1f} {vy:.1f} {side:.1f} {side:.1f}" '
                f'width="{size}" height="{size}" role="img">{defs}{body}</svg>')


def _empty_svg(size: int) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" width="{size}" height="{size}"></svg>'


def _face_normal(pts3):
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts3[0], pts3[1], pts3[2]
    u = (x1 - x0, y1 - y0, z1 - z0)
    v = (x2 - x0, y2 - y0, z2 - z0)
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return n


# ---------------------------------------------------------------------------
# solids
# ---------------------------------------------------------------------------
def stud(cv: Canvas, x: float, y: float, z: float, r: float = STUD_R, h: float = STUD_H, hollow=False, depth=None):
    bx, by = proj(x, y, z)
    tx, ty = proj(x, y, z + h)
    rx, ry = 1.2247 * r * SCALE, 0.7071 * r * SCALE
    side = cv.fill(0.42)
    top = cv.fill(0.95)
    op = ' fill-opacity="0.7"' if cv.trans else ""
    edge = f'stroke="{cv.edge}" stroke-width="1" stroke-opacity="0.5"'
    svg = (
        f'<ellipse cx="{bx:.1f}" cy="{by:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{side}"{op} {edge}/>'
        f'<rect x="{bx - rx:.1f}" y="{ty:.1f}" width="{2 * rx:.1f}" height="{by - ty:.1f}" fill="{side}"{op}/>'
        f'<path d="M{bx - rx:.1f} {ty:.1f} L{bx - rx:.1f} {by:.1f} M{bx + rx:.1f} {ty:.1f} L{bx + rx:.1f} {by:.1f}" {edge}/>'
        f'<ellipse cx="{tx:.1f}" cy="{ty:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{top}"{op} {edge}/>'
    )
    if hollow:
        svg += f'<ellipse cx="{tx:.1f}" cy="{ty:.1f}" rx="{rx * .55:.1f}" ry="{ry * .55:.1f}" fill="{cv.fill(-0.2)}"/>'
    cv.raw(x + y + z + h + 0.5 if depth is None else depth, svg, [(bx - rx, by + ry), (tx + rx, ty - ry)])


def studs_on(cv: Canvas, cells, x0: float, y0: float, z: float, base_depth: float, hollow=False):
    """Studs drawn right after the surface they sit on (back to front)."""
    for i, j in sorted(cells, key=lambda c: c[0] + c[1]):
        stud(cv, x0 + i + 0.5, y0 + j + 0.5, z, hollow=hollow, depth=base_depth + 0.02 + 0.001 * (i + j))


def box(cv: Canvas, x0, y0, z0, dx, dy, dz, studs=True, stud_cells=None):
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    cv.face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], normal=(1, 0, 0))
    cv.face([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)], normal=(0, 1, 0))
    top_depth = x0 + y0 + z1 + (dx + dy) / 2 - 0.01
    cv.face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], normal=(0, 0, 1), depth=top_depth)
    if studs:
        cells = stud_cells if stud_cells is not None else [
            (i, j) for i in range(int(round(dx))) for j in range(int(round(dy)))]
        studs_on(cv, cells, x0, y0, z1, top_depth)


def extrude_profile(cv: Canvas, profile, y0: float, length: float):
    """Extrude an (x, z) profile along +y from y0 to y0 + length."""
    n = len(profile)
    cx = sum(p[0] for p in profile) / n
    cz = sum(p[1] for p in profile) / n
    y1 = y0 + length
    for i in range(n):
        (xa, za), (xb, zb) = profile[i], profile[(i + 1) % n]
        dx, dz = xb - xa, zb - za
        nrm = (dz, 0.0, -dx)
        mx, mz = (xa + xb) / 2, (za + zb) / 2
        if nrm[0] * (cx - mx) + nrm[2] * (cz - mz) > 0:
            nrm = (-nrm[0], 0.0, -nrm[2])
        if _dot(nrm, VIEW) <= 1e-6:
            continue
        cv.face([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], normal=nrm)
    cv.face([(x, y1, z) for x, z in profile], normal=(0, 1, 0), depth=cx + y1 + cz + 0.3)


def extrude_up(cv: Canvas, outline, z0: float, z1: float, top_t=None):
    """Extrude an (x, y) outline from z0 to z1 (outline in any winding)."""
    n = len(outline)
    cx = sum(p[0] for p in outline) / n
    cy = sum(p[1] for p in outline) / n
    faces = []
    for i in range(n):
        (xa, ya), (xb, yb) = outline[i], outline[(i + 1) % n]
        nrm = (yb - ya, -(xb - xa), 0.0)
        mx, my = (xa + xb) / 2, (ya + yb) / 2
        if nrm[0] * (cx - mx) + nrm[1] * (cy - my) > 0:
            nrm = (-nrm[0], -nrm[1], 0.0)
        if nrm[0] + nrm[1] <= 1e-6:
            continue
        faces.append(([(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)], nrm, mx + my))
    for pts, nrm, d in sorted(faces, key=lambda f: f[2]):
        cv.face(pts, normal=nrm, depth=d + z0)
    cv.face([(x, y, z1) for x, y in outline], normal=(0, 0, 1), depth=cx + cy + z1 + 0.2, t=top_t)


def cylinder_z(cv: Canvas, x, y, z0, z1, r, top_studs=0, cap_t=0.95, depth_bias=0.0):
    bx, by = proj(x, y, z0)
    tx, ty = proj(x, y, z1)
    rx, ry = 1.2247 * r * SCALE, 0.7071 * r * SCALE
    op = ' fill-opacity="0.62"' if cv.trans else ""
    edge = f'stroke="{cv.edge}" stroke-width="1.1" stroke-opacity="0.55"'
    gid = f"cz{abs(hash((x, y, z0, r))) % 99999}"
    svg = (
        f'<defs><linearGradient id="{gid}" x1="0" x2="1"><stop offset="0" stop-color="{cv.fill(0.7)}"/>'
        f'<stop offset=".55" stop-color="{cv.fill(0.45)}"/><stop offset="1" stop-color="{cv.fill(0.1)}"/></linearGradient></defs>'
        f'<path d="M{bx - rx:.1f} {by:.1f} A{rx:.1f} {ry:.1f} 0 0 0 {bx + rx:.1f} {by:.1f} L{tx + rx:.1f} {ty:.1f} '
        f'L{tx - rx:.1f} {ty:.1f} Z" fill="url(#{gid})"{op} {edge}/>'
        f'<ellipse cx="{tx:.1f}" cy="{ty:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{cv.fill(cap_t)}"{op} {edge}/>'
    )
    d = x + y + z1 + depth_bias
    cv.raw(d, svg, [(bx - rx, by + ry), (tx + rx, ty - ry), (tx - rx, ty - ry)])
    return d


def _hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def rod(cv: Canvas, axis: str, a0: float, a1: float, c1: float, c2: float, r: float, cross=False, cap_color=None,
        depth_bias=0.0):
    """Horizontal cylinder (or Technic axle when cross=True) along 'x' or 'y'."""
    steps = 28
    if cross:
        w = r * 0.36
        shape = [(w, r), (w, w), (r, w), (r, -w), (w, -w), (w, -r), (-w, -r), (-w, -w), (-r, -w), (-r, w), (-w, w),
                 (-w, r)]
    else:
        shape = [(r * math.cos(2 * math.pi * k / steps), r * math.sin(2 * math.pi * k / steps)) for k in range(steps)]

    def p3(a, u, v):
        return (a, c1 + u, c2 + v) if axis == "x" else (c1 + u, a, c2 + v)

    far = [proj(*p3(a0, u, v)) for u, v in shape]
    near = [proj(*p3(a1, u, v)) for u, v in shape]
    hull = _hull([(round(x, 2), round(y, 2)) for x, y in far + near])
    op = ' fill-opacity="0.62"' if cv.trans else ""
    edge = f'stroke="{cv.edge}" stroke-width="1.1" stroke-opacity="0.55" stroke-linejoin="round"'
    hull_d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in hull) + " Z"
    cap_d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in near) + " Z"
    cap_fill = cap_color or cv.fill(0.62 if axis == "y" else 0.35)
    mid = (a0 + a1) / 2
    depth = (mid + c1 + c2) if axis == "x" else (c1 + mid + c2)
    cv.raw(depth + depth_bias,
           f'<path d="{hull_d}" fill="{cv.fill(0.55)}"{op} {edge}/><path d="{cap_d}" fill="{cap_fill}"{op} {edge}/>',
           hull)


def _circle_xy(cx, cy, r, steps=32, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * k / steps), cy + r * math.sin(start + 2 * math.pi * k / steps))
            for k in range(steps)]


def hole_top(cv: Canvas, x, y, z, r=0.26, axle=False):
    if axle:
        w, rr = r * 0.35, r
        cross = [(x - w, y - rr), (x + w, y - rr), (x + w, y - w), (x + rr, y - w), (x + rr, y + w), (x + w, y + w),
                 (x + w, y + rr), (x - w, y + rr), (x - w, y + w), (x - rr, y + w), (x - rr, y - w), (x - w, y - w)]
        pts2 = [proj(px, py, z) for px, py in cross]
    else:
        pts2 = [proj(px, py, z) for px, py in _circle_xy(x, y, r)]
    d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts2) + " Z"
    cv.raw(x + y + z + 0.6, f'<path d="{d}" fill="{cv.fill(-0.55)}" stroke="{cv.edge}" stroke-width=".8" '
                            f'stroke-opacity=".5"/>')


def hole_side_y(cv: Canvas, x, y, z, r=0.25):
    """Pin hole on a face whose normal is +y."""
    pts2 = [proj(x + r * math.cos(t), y, z + r * math.sin(t)) for t in [2 * math.pi * k / 28 for k in range(28)]]
    d = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts2) + " Z"
    cv.raw(x + y + z + 0.7, f'<path d="{d}" fill="{cv.fill(-0.5)}" stroke="{cv.edge}" stroke-width=".8" '
                            f'stroke-opacity=".5"/>')


# ---------------------------------------------------------------------------
# part families
# ---------------------------------------------------------------------------
def draw_block(cv, w, l, h, studs=True):
    box(cv, 0, 0, 0, w, l, h, studs=studs)


def draw_corner(cv, h, size=2, studs=True):
    box(cv, 0, 0, 0, size, 1, h, studs=studs)
    box(cv, 0, 1, 0, 1, size - 1, h, studs=studs)


def draw_slope(cv, depth, width, height=BRICK, flat=1.0, low=0.2, curved=False, inverted=False, studs=True):
    if inverted:
        prof = [(0, height), (depth, height), (depth, low), (flat, 0), (0, 0)]
    elif curved:
        pts = [(0, 0), (depth, 0), (depth, low)]
        for k in range(1, 8):
            t = k / 8
            x = depth - (depth - flat) * t
            z = low + (height - low) * (1 - (1 - t) ** 2)
            pts.append((x, z))
        pts += [(flat, height), (0, height)]
        prof = pts
    else:
        prof = [(0, 0), (depth, 0), (depth, low), (flat, height), (0, height)]
    extrude_profile(cv, prof, 0, width)
    top_depth = (flat if not inverted else depth) / 2 + width / 2 + height
    if studs and flat >= 1 and not inverted:
        studs_on(cv, [(i, j) for i in range(int(flat)) for j in range(int(width))], 0, 0, height, top_depth)
    if inverted and studs:
        studs_on(cv, [(i, j) for i in range(int(depth)) for j in range(int(width))], 0, 0, height, top_depth + 1)


def draw_round(cv, d, h, studs=True, hole=False, cone=False, dome=False):
    r = d / 2 * 0.96
    if cone:
        cylinder_z(cv, r, r, 0, h * 0.25, r)
        d = cylinder_z(cv, r, r, h * 0.25, h, r * 0.62, depth_bias=0.1)
        stud(cv, r, r, h, depth=d + 0.05)
        return
    if dome:
        cylinder_z(cv, r, r, 0, h * 0.35, r)
        cylinder_z(cv, r, r, h * 0.35, h * 0.7, r * 0.8, depth_bias=0.1)
        cylinder_z(cv, r, r, h * 0.7, h, r * 0.45, depth_bias=0.2)
        return
    top_depth = cylinder_z(cv, r, r, 0, h, r)
    if studs:
        n = int(round(d))
        studs_on(cv, [(i, j) for i in range(n) for j in range(n)], 0, 0, h, top_depth, hollow=hole and n == 1)
    if hole and int(round(d)) > 1:
        hole_top(cv, r, r, h + 0.001, 0.2, axle=True)


def draw_beam(cv, n, thick=True, l_shape=None):
    w = 0.88
    h = 0.84 if thick else 0.42
    r = w / 2

    def stadium(x0, x1):
        pts = []
        for k in range(15):
            t = -math.pi / 2 + math.pi * k / 14
            pts.append((x1 + r * math.cos(t), r + r * math.sin(t)))
        for k in range(15):
            t = math.pi / 2 + math.pi * k / 14
            pts.append((x0 + r * math.cos(t), r + r * math.sin(t)))
        return pts

    if l_shape:
        a, b = l_shape
        extrude_up(cv, stadium(0, (b - 1)), 0, h)
        for i in range(b):
            hole_top(cv, i, r, h + 0.001)
        # vertical arm drawn as a second beam along y
        arm = [(y, x) for x, y in stadium(0, (a - 1))]
        arm = [(x, y + 0.0) for x, y in arm]
        extrude_up(cv, [(px - r + r, py) for px, py in arm], 0, h)
        for j in range(1, a):
            hole_top(cv, r, j, h + 0.001)
        return
    extrude_up(cv, stadium(0, n - 1), 0, h)
    for i in range(n):
        hole_top(cv, i, r, h + 0.001)


def draw_technic_brick(cv, n):
    box(cv, 0, 0, 0, n, 1, BRICK)
    for i in range(max(1, n - 1)):
        x = i + 1.0 if n > 1 else 0.5
        hole_side_y(cv, x, 1.0, BRICK * 0.5)


def draw_axle(cv, n, stop=False):
    rod(cv, "x", 0, n * 0.95, 0, 0, 0.24, cross=True)
    if stop:
        rod(cv, "x", 0.05, 0.25, 0, 0, 0.34, depth_bias=0.05)


def draw_pin(cv, length=2, axle_end=False, half=False):
    if half:
        rod(cv, "x", 0, 0.5, 0, 0, 0.24)
        rod(cv, "x", 0.5, 0.62, 0, 0, 0.32, depth_bias=0.05)
        return
    rod(cv, "x", 0, length / 2 - 0.08, 0, 0, 0.24)
    rod(cv, "x", length / 2 - 0.08, length / 2 + 0.08, 0, 0, 0.31, depth_bias=0.05)
    rod(cv, "x", length / 2 + 0.08, length, 0, 0, 0.24, cross=axle_end, depth_bias=0.1)


def draw_bush(cv, half=False):
    rod(cv, "x", 0, 0.45 if half else 0.95, 0, 0, 0.36)


def draw_connector(cv, kind="axle"):
    if kind == "perp":
        rod(cv, "x", 0, 0.9, 0, 0, 0.36)
        rod(cv, "y", 0.4, 1.4, 0.45, 0, 0.36, depth_bias=0.1)
    elif kind == "angled":
        rod(cv, "x", 0, 0.9, 0, 0, 0.36)
        rod(cv, "y", -0.2, 0.7, 0.9, 0.0, 0.36, depth_bias=0.1)
    else:
        rod(cv, "x", 0, 1.8, 0, 0, 0.34, cross=False)
        hole_side_y(cv, 1.8, 0.0, 0.0, 0.18)


def draw_gear(cv, teeth, bevel=False, rack=None):
    if rack:
        prof = []
        n = rack * 3
        for k in range(n + 1):
            x = k / 3
            prof.append((x, 0.84 if k % 2 == 0 else 1.05))
        extrude_up(cv, [(0, 0), (rack, 0), (rack, 0.9), (0, 0.9)], 0, 0.84)
        for k in range(rack * 2):
            box(cv, k * 0.5 + 0.08, 0.05, 0.84, 0.28, 0.8, 0.18, studs=False)
        return
    r_out = max(0.5, teeth / 16.0)
    r_in = r_out * (0.86 if teeth > 12 else 0.78)
    pts = []
    for k in range(teeth):
        a = 2 * math.pi * k / teeth
        da = math.pi / teeth
        for aa, rr in ((a - da * 0.55, r_in), (a - da * 0.25, r_out), (a + da * 0.25, r_out), (a + da * 0.55, r_in)):
            pts.append((r_out + rr * math.cos(aa), r_out + rr * math.sin(aa)))
    thickness = 0.42 if not bevel else 0.5
    extrude_up(cv, pts, 0, thickness)
    if bevel:
        cylinder_z(cv, r_out, r_out, thickness, thickness + 0.16, r_in * 0.8, depth_bias=0.4)
    hole_top(cv, r_out, r_out, thickness + (0.17 if bevel else 0.001), 0.22, axle=True)
    if teeth >= 24:
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2
            hole_top(cv, r_out + r_out * 0.5 * math.cos(a), r_out + r_out * 0.5 * math.sin(a), thickness + 0.001,
                     0.16)


def draw_wheel(cv, diameter, width, tyre=False):
    r = diameter / 2
    if tyre:
        rod(cv, "y", 0, width, r, r, r, cap_color=cv.fill(0.25))
        pts2 = [proj(r + r * 0.62 * math.cos(t), width, r + r * 0.62 * math.sin(t)) for t in
                [2 * math.pi * k / 30 for k in range(30)]]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z"
        cv.raw(r + width + r + 1, f'<path d="{d}" fill="#e9eaee" stroke="{cv.edge}" stroke-width="1"/>')
        return
    rod(cv, "y", 0, width, r, r, r)
    for rr, t in ((r * 0.72, 0.1), (r * 0.32, 0.9)):
        pts2 = [proj(r + rr * math.cos(a), width, r + rr * math.sin(a)) for a in [2 * math.pi * k / 30 for k in range(30)]]
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z"
        cv.raw(r + width + r + 1 + (0.1 if t > 0.5 else 0),
               f'<path d="{d}" fill="{cv.fill(t)}" stroke="{cv.edge}" stroke-width="1" stroke-opacity=".5"/>')
    pts2 = [proj(r + 0.16 * math.cos(a), width + 0.01, r + 0.16 * math.sin(a)) for a in
            [2 * math.pi * k / 20 for k in range(20)]]
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts2) + " Z"
    cv.raw(r + width + r + 1.3, f'<path d="{d}" fill="{cv.fill(-0.6)}"/>')


def draw_window(cv, w, h_bricks, depth=1, glass=False, door=False, frame=False):
    h = h_bricks * BRICK
    if glass:
        box(cv, 0, depth * 0.45, 0.06, w, 0.1, h - 0.12, studs=False)
        return
    if door:
        box(cv, 0, 0.4, 0, w * 0.96, 0.22, h, studs=False)
        for k in range(2):
            pane = [(0.2 + k * 0.0, 0.62, h * (0.55 if k else 0.1)), (w * 0.96 - 0.2, 0.62, h * (0.55 if k else 0.1)),
                    (w * 0.96 - 0.2, 0.62, h * (0.9 if k else 0.45)), (0.2, 0.62, h * (0.9 if k else 0.45))]
            cv.face(pane, normal=(0, 1, 0), t=0.2, depth=w + 2)
        rod(cv, "y", 0.62, 0.8, w * 0.8, h * 0.5, 0.12, depth_bias=3)
        return
    t = 0.18
    x0, x1 = 0.0, float(w)
    # right side, top with studs
    cv.face([(x1, 0, 0), (x1, depth, 0), (x1, depth, h), (x1, 0, h)], normal=(1, 0, 0))
    cv.face([(x0, 0, h), (x1, 0, h), (x1, depth, h), (x0, depth, h)], normal=(0, 0, 1), depth=w / 2 + depth / 2 + h)
    # front frame with opening (even-odd fill)
    outer = [(x0, depth, 0), (x1, depth, 0), (x1, depth, h), (x0, depth, h)]
    inner = [(x0 + t, depth, t + (0 if frame else 0.12)), (x1 - t, depth, t + (0 if frame else 0.12)),
             (x1 - t, depth, h - t), (x0 + t, depth, h - t)]
    if frame:
        inner[0] = (x0 + t, depth, 0)
        inner[1] = (x1 - t, depth, 0)
    o2 = [proj(*p) for p in outer]
    i2 = [proj(*p) for p in inner]
    d = ("M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in o2) + " Z M" +
         " L".join(f"{x:.1f} {y:.1f}" for x, y in i2) + " Z")
    # inner reveal: left post inner face and sill
    cv.face([(x0 + t, 0, inner[0][2]), (x0 + t, depth, inner[0][2]), (x0 + t, depth, h - t), (x0 + t, 0, h - t)],
            normal=(1, 0, 0), depth=w / 2 + depth / 2 + h / 2 - 0.5, t=0.15)
    if not frame:
        cv.face([(x0 + t, 0, inner[0][2]), (x1 - t, 0, inner[0][2]), (x1 - t, depth, inner[0][2]),
                 (x0 + t, depth, inner[0][2])], normal=(0, 0, 1), depth=w / 2 + depth / 2 - 0.4, t=0.6)
    cv.raw(w + depth + h, f'<path d="{d}" fill-rule="evenodd" {cv.style(0.55)}/>', o2)
    for i in range(int(w)):
        for j in range(int(depth)):
            stud(cv, i + 0.5, j + 0.5, h)


def draw_wedge_plate(cv, length, width, side="right", cut=False, triangle=False, h=PLATE, studs=True):
    if triangle:
        outline = [(0, 0), (length, 0), (0, width)]
    elif cut:
        c = max(1.0, min(length, width) - 1)
        outline = [(0, 0), (length, 0), (length, width - c), (length - c, width), (0, width)]
    else:
        if side == "right":
            outline = [(0, 0), (length, 0), (length, width * 0.5), (0, width)]
        else:
            outline = [(0, 0), (length, width * 0.5), (length, width), (0, width)]
    extrude_up(cv, outline, 0, h)
    if not studs:
        return

    def inside(px, py):
        n = len(outline)
        ok = False
        for i in range(n):
            (xa, ya), (xb, yb) = outline[i], outline[(i + 1) % n]
            if (ya > py) != (yb > py) and px < (xb - xa) * (py - ya) / (yb - ya + 1e-9) + xa:
                ok = not ok
        return ok

    cells = [(i, j) for i in range(int(length)) for j in range(int(width))
             if all(inside(i + 0.5 + dx, j + 0.5 + dy) for dx in (-0.3, 0.3) for dy in (-0.3, 0.3))]
    n = len(outline)
    top_depth = sum(p[0] for p in outline) / n + sum(p[1] for p in outline) / n + h + 0.2
    studs_on(cv, cells, 0, 0, h, top_depth)


def draw_flower(cv, petals=5, leaves=False):
    cylinder_z(cv, 0.5, 0.5, 0, 0.2, 0.38)
    z = 0.22
    for k in range(petals if not leaves else 3):
        a = 2 * math.pi * k / (petals if not leaves else 3) + 0.3
        cx, cy = 0.5 + 0.42 * math.cos(a), 0.5 + 0.42 * math.sin(a)
        pts = []
        for s in range(18):
            t = 2 * math.pi * s / 18
            lx, ly = (0.34 if not leaves else 0.5) * math.cos(t), (0.22 if not leaves else 0.18) * math.sin(t)
            pts.append((cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a), z))
        cv.face(pts, normal=(0, 0, 1), depth=cx + cy + z + 0.1 * k)
    stud(cv, 0.5, 0.5, z, r=0.2, h=0.08, depth=50)


def draw_leaves(cv, size=4):
    s = size / 4
    for k, (ox, oy, rot, zz) in enumerate([(0.2, 0.4, 0.4, 0.0), (1.2, 0.0, -0.5, 0.3), (0.6, 1.4, 1.6, 0.15)]):
        pts = []
        for i in range(24):
            t = 2 * math.pi * i / 24
            lx, ly = 1.4 * s * math.cos(t), 0.55 * s * math.sin(t) * (1 - 0.35 * math.cos(t))
            pts.append((ox * s + 1.4 * s + lx * math.cos(rot) - ly * math.sin(rot),
                        oy * s + 0.7 * s + lx * math.sin(rot) + ly * math.cos(rot), zz))
        cv.face(pts, normal=(0, 0, 1), depth=k)


def draw_cherries(cv):
    for k, (x, y) in enumerate([(0.3, 0.6), (0.9, 0.4)]):
        cx, cy = proj(x, y, 0.3)
        cv.raw(k + 1, f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{0.32 * SCALE:.1f}" fill="{cv.fill(0.6)}" '
                      f'stroke="{cv.edge}" stroke-width="1"/><circle cx="{cx - 4:.1f}" cy="{cy - 4:.1f}" r="3" '
                      f'fill="#fff" fill-opacity=".5"/>', [(cx - 12, cy - 12), (cx + 12, cy + 12)])
    a, b = proj(0.3, 0.6, 0.6), proj(0.9, 0.4, 0.6)
    top = proj(0.7, 0.5, 1.6)
    cv.raw(5, f'<path d="M{a[0]:.1f} {a[1]:.1f} Q{top[0] - 6:.1f} {top[1]:.1f} {top[0]:.1f} {top[1]:.1f} '
              f'Q{top[0] + 4:.1f} {top[1] + 6:.1f} {b[0]:.1f} {b[1]:.1f}" fill="none" stroke="{cv.fill(-0.2)}" '
              f'stroke-width="3" stroke-linecap="round"/>', [top])


def draw_panel(cv, w, h_bricks, corner=False):
    h = h_bricks * BRICK
    box(cv, 0, 0, 0, 1, w, PLATE, studs=False)
    box(cv, 0, 0, PLATE, 0.16, w, h - PLATE, studs=False)
    if corner:
        box(cv, 0.16, 0, PLATE, 0.84, 0.16, h - PLATE, studs=False)
    for j in range(int(w)):
        stud(cv, 0.5, j + 0.5, h if False else PLATE)


def draw_turntable(cv, top=False):
    if top:
        d = cylinder_z(cv, 1, 1, 0, 0.25, 0.92)
        studs_on(cv, [(0, 0), (0, 1), (1, 0), (1, 1)], 0, 0, 0.25, d)
        return
    box(cv, 0, 0, 0, 2, 2, PLATE, studs=False)
    cylinder_z(cv, 1, 1, PLATE, PLATE + 0.12, 0.7, depth_bias=0.4)


def draw_hinge_brick(cv, top=False):
    if top:
        box(cv, 0, 0, 0, 2, 2, PLATE * 0.6, studs=True)
        rod(cv, "y", 0, 2, 0, 0.3, 0.28, depth_bias=-1)
        return
    box(cv, 0, 0, 0, 1, 2, BRICK * 0.6, studs=False)
    rod(cv, "y", 0, 2, 0.5, BRICK * 0.6 + 0.25, 0.27, depth_bias=0.5)


def draw_fence(cv, w=4):
    box(cv, 0, 0, 0, 0.2, w, PLATE, studs=False)
    for k in range(int(w * 2) + 1):
        y = k * 0.5
        box(cv, 0.04, max(0, y - 0.05), PLATE, 0.12, 0.1, BRICK - PLATE, studs=False)
    box(cv, 0, 0, BRICK, 0.2, w, 0.1, studs=False)


def draw_bar(cv, n):
    rod(cv, "x", 0, n * 0.95, 0, 0, 0.13)


def draw_hilt(cv):
    rod(cv, "x", 0, 1.2, 0, 0, 0.18)
    rod(cv, "x", 0.0, 0.14, 0, 0, 0.21, depth_bias=0.1)
    rod(cv, "x", 1.06, 1.2, 0, 0, 0.21, depth_bias=0.2)


def draw_cup(cv, goblet=False):
    if goblet:
        cylinder_z(cv, 0.5, 0.5, 0, 0.08, 0.32)
        cylinder_z(cv, 0.5, 0.5, 0.08, 0.6, 0.08, depth_bias=0.1)
        cylinder_z(cv, 0.5, 0.5, 0.6, 1.1, 0.3, depth_bias=0.2, cap_t=-0.3)
        return
    cylinder_z(cv, 0.5, 0.5, 0, 0.9, 0.34, cap_t=-0.3)
    rod(cv, "y", 0.82, 1.0, 0.5, 0.45, 0.18, depth_bias=-0.5)


# Simple flat silhouettes (viewBox 0 0 100 100) for minifigure accessories.
ICONS = {
    "sword": "M48 8 L56 8 L56 64 L52 70 L48 64 Z M34 64 L70 64 L70 71 L34 71 Z M48 71 L56 71 L56 90 L48 90 Z",
    "wand": "M20 84 L72 22 L78 27 L26 89 Z",
    "hammer": "M30 18 L70 18 L70 38 L30 38 Z M46 38 L54 38 L54 90 L46 90 Z",
    "wrench": "M28 14 a14 14 0 1 0 14 22 L76 80 L84 72 L48 30 a14 14 0 0 0 -8 -18 L36 26 L30 22 Z",
    "blaster": "M14 34 L86 34 L86 46 L44 46 L40 74 L26 74 L28 46 L14 46 Z",
    "helmet": "M18 64 C18 30 82 30 82 64 L82 74 L18 74 Z",
    "crown": "M14 74 L18 30 L36 50 L50 22 L64 50 L82 30 L86 74 Z",
    "binoculars": "M14 40 a16 16 0 1 0 32 0 L54 40 a16 16 0 1 0 32 0 L86 30 L54 30 L46 30 L14 30 Z",
}


def draw_icon(cv: Canvas, name: str):
    d = ICONS[name]
    svg = (f'<g transform="translate(-50 -50)"><path d="{d}" fill="{cv.fill(0.6)}" stroke="{cv.edge}" '
           f'stroke-width="2.4" stroke-linejoin="round"/><path d="{d}" fill="#fff" fill-opacity=".12" '
           f'transform="translate(-2 -2)"/></g>')
    cv.raw(0, svg, [(-50, -50), (50, 50)])


# ---------------------------------------------------------------------------
# name parser
# ---------------------------------------------------------------------------
_FRAC = {"1/3": 1 / 3, "2/3": 2 / 3, "1/2": 0.5}
DIM_RE = re.compile(r"(\d+(?:\.\d+)?)(?: (\d/\d))? x (\d+(?:\.\d+)?)(?: (\d/\d))?(?: x (\d+(?:\.\d+)?)?(?: ?(\d/\d))?)?")


def _num(whole, frac):
    v = float(whole) if whole else 0.0
    if frac:
        v += _FRAC.get(frac, 0)
    return v


def dims(name: str):
    m = DIM_RE.search(name)
    if not m:
        return None
    a = _num(m.group(1), m.group(2))
    b = _num(m.group(3), m.group(4))
    c = _num(m.group(5), m.group(6)) if (m.group(5) or m.group(6)) else None
    return a, b, c


OVERRIDES = {
    "54200": ("slope", dict(depth=1, width=1, height=0.8, flat=0.0, low=0.08, studs=False)),
    "85984": ("slope", dict(depth=1, width=2, height=0.8, flat=0.0, low=0.08, studs=False)),
    "3039": ("slope", dict(depth=2, width=2, height=BRICK, flat=1.0, low=0.2)),
    "3040b": ("slope", dict(depth=2, width=1, height=BRICK, flat=1.0, low=0.2)),
    "3665": ("slope", dict(depth=2, width=1, height=BRICK, flat=1.0, low=0.2, inverted=True)),
    "11477": ("slope", dict(depth=2, width=1, height=0.8, flat=0.0, low=0.1, curved=True, studs=False)),
    "15068": ("slope", dict(depth=2, width=2, height=0.8, flat=0.0, low=0.1, curved=True, studs=False)),
    "93273": ("slope", dict(depth=4, width=1, height=0.8, flat=0.0, low=0.1, curved=True, studs=False)),
    "6091": ("slope", dict(depth=2, width=1, height=1.6, flat=0.0, low=BRICK, curved=True, studs=False)),
    "47456": ("slope", dict(depth=3, width=2, height=0.8, flat=1.0, low=0.1, curved=True)),
    "47458": ("slope", dict(depth=2, width=1, height=0.8, flat=0.0, low=0.1, curved=True, studs=False)),
    "2357": ("corner", dict(h=BRICK)),
    "2420": ("corner", dict(h=PLATE)),
    "14719": ("corner", dict(h=PLATE, studs=False)),
    "59900": ("round", dict(d=1, h=BRICK, cone=True)),
    "4740": ("round", dict(d=2, h=0.6, dome=True)),
    "3062b": ("round", dict(d=1, h=BRICK, hole=True)),
    "3941": ("round", dict(d=2, h=BRICK, hole=True)),
    "6141": ("round", dict(d=1, h=PLATE)),
    "85861": ("round", dict(d=1, h=PLATE, hole=True)),
    "4032a": ("round", dict(d=2, h=PLATE, hole=True)),
    "98138": ("round", dict(d=1, h=PLATE, studs=False)),
    "14769": ("round", dict(d=2, h=PLATE, studs=False)),
    "25269": ("wedge", dict(length=1, width=1, triangle=False, cut=True, studs=False)),
    "24246": ("wedge", dict(length=1, width=1, side="right", studs=False)),
    "27925": ("wedge", dict(length=2, width=2, cut=True, studs=False)),
    "35787": ("wedge", dict(length=2, width=2, triangle=True, studs=False)),
    "26601": ("wedge", dict(length=2, width=2, cut=True)),
    "2450": ("wedge", dict(length=3, width=3, cut=True)),
    "51739": ("wedge", dict(length=4, width=2, side="right")),
    "43722": ("wedge", dict(length=3, width=2, side="right")),
    "43723": ("wedge", dict(length=3, width=2, side="left")),
    "41769": ("wedge", dict(length=4, width=2, side="right")),
    "41770": ("wedge", dict(length=4, width=2, side="left")),
    "54383": ("wedge", dict(length=6, width=3, side="right")),
    "54384": ("wedge", dict(length=6, width=3, side="left")),
    "2340": ("wedge", dict(length=4, width=3, side="right", h=0.3, studs=False)),
    "3659": ("arch", dict(length=4)),
    "15573": ("block", dict(w=2, l=1, h=PLATE, studs=False, jumper=True)),
    "87580": ("block", dict(w=2, l=2, h=PLATE, studs=False, jumper=True)),
    "99780": ("bracket", dict()),
    "44728": ("bracket", dict(wide=True)),
    "60478": ("block", dict(w=2, l=1, h=PLATE)),
    "2412b": ("block", dict(w=2, l=1, h=PLATE, studs=False, grille=True)),
    "15712": ("block", dict(w=1, l=1, h=PLATE, studs=False)),
    "87087": ("block", dict(w=1, l=1, h=BRICK, side_stud=1)),
    "11211": ("block", dict(w=2, l=1, h=BRICK, side_stud=2)),
    "4070": ("block", dict(w=1, l=1, h=BRICK, side_stud=1)),
    "30136": ("block", dict(w=2, l=1, h=BRICK, log=True)),
    "98283": ("block", dict(w=2, l=1, h=BRICK, masonry=True)),
    "3245c": ("block", dict(w=2, l=1, h=BRICK * 2)),
    "14716": ("block", dict(w=1, l=1, h=BRICK * 3)),
    "60592": ("window", dict(w=2, h_bricks=2)),
    "60593": ("window", dict(w=2, h_bricks=3)),
    "60594": ("window", dict(w=4, h_bricks=3)),
    "30044": ("window", dict(w=2, h_bricks=2.67)),
    "60596": ("window", dict(w=4, h_bricks=6, frame=True)),
    "60601": ("window", dict(w=2, h_bricks=2, glass=True)),
    "60602": ("window", dict(w=2, h_bricks=3, glass=True)),
    "60603": ("window", dict(w=4, h_bricks=3, glass=True)),
    "57895": ("window", dict(w=4, h_bricks=6, glass=True)),
    "60616b": ("window", dict(w=4, h_bricks=6, door=True)),
    "60623": ("window", dict(w=4, h_bricks=6, door=True)),
    "3823": ("slope", dict(depth=2, width=4, height=BRICK * 2, flat=0.0, low=0.2, studs=False, curved=True)),
    "35336": ("slope", dict(depth=2, width=6, height=BRICK * 2, flat=0.0, low=0.2, studs=False, curved=True)),
    "55981": ("wheel", dict(diameter=2.2, width=1.7)),
    "42610": ("wheel", dict(diameter=1.4, width=1.0)),
    "6014b": ("wheel", dict(diameter=1.4, width=1.5)),
    "56145": ("wheel", dict(diameter=3.8, width=2.5)),
    "34337": ("wheel", dict(diameter=1.0, width=0.75)),
    "13971": ("wheel", dict(diameter=2.2, width=1.0)),
    "87697": ("wheel", dict(diameter=2.6, width=1.5, tyre=True)),
    "59895": ("wheel", dict(diameter=1.75, width=0.5, tyre=True)),
    "92402": ("wheel", dict(diameter=3.8, width=1.75, tyre=True)),
    "50951": ("wheel", dict(diameter=1.75, width=0.75, tyre=True)),
    "64179": ("frame", dict()),
    "32140": ("beam", dict(n=4, l_shape=(2, 4))),
    "32526": ("beam", dict(n=5, l_shape=(3, 5))),
    "60483": ("beam", dict(n=2)),
    "3713": ("bush", dict()),
    "32123b": ("bush", dict(half=True)),
    "2780": ("pin", dict()),
    "3673": ("pin", dict()),
    "43093": ("pin", dict(axle_end=True)),
    "6558": ("pin", dict(length=3)),
    "4274": ("pin", dict(half=True)),
    "2736": ("pin", dict(length=2)),
    "59443": ("connector", dict(kind="axle")),
    "6536": ("connector", dict(kind="perp")),
    "32013": ("connector", dict(kind="angled")),
    "3743": ("gear", dict(teeth=0, rack=4)),
    "87761": ("gear", dict(teeth=0, rack=7)),
    "32072": ("gear", dict(teeth=4)),
    "24866": ("flower", dict(petals=5)),
    "33291": ("flower", dict(petals=4)),
    "32607": ("flower", dict(petals=3, leaves=True)),
    "30176": ("flower", dict(petals=3, leaves=True)),
    "2423": ("leaves", dict(size=3)),
    "2417": ("leaves", dict(size=5)),
    "37695": ("leaves", dict(size=2)),
    "33183": ("leaves", dict(size=1.6)),
    "22667": ("cherries", dict()),
    "64567": ("hilt", dict()),
    "30374": ("bar", dict(n=4)),
    "87994": ("bar", dict(n=3)),
    "3899": ("cup", dict()),
    "2343": ("cup", dict(goblet=True)),
    "30162": ("icon", dict(name="binoculars")),
    "4006": ("icon", dict(name="wrench")),
    "21459": ("icon", dict(name="sword")),
    "36752a": ("icon", dict(name="wand")),
    "4522": ("icon", dict(name="hammer")),
    "92738": ("icon", dict(name="blaster")),
    "58247": ("icon", dict(name="blaster")),
    "2446": ("icon", dict(name="helmet")),
    "39262": ("icon", dict(name="crown")),
    "3937": ("hinge", dict()),
    "6134": ("hinge", dict(top=True)),
    "3680": ("turntable", dict()),
    "3679": ("turntable", dict(top=True)),
    "4865b": ("panel", dict(w=2, h_bricks=1)),
    "87552": ("panel", dict(w=2, h_bricks=2)),
    "6231": ("panel", dict(w=1, h_bricks=1, corner=True)),
    "3633": ("fence", dict(w=4)),
}


def classify(design_id: str, name: str):
    if design_id in OVERRIDES:
        return OVERRIDES[design_id]
    n = name or ""
    low = n.lower()
    d = dims(n)
    m = re.search(r"technic gear (\d+) tooth", low)
    if m:
        return "gear", dict(teeth=int(m.group(1)), bevel="bevel" in low)
    m = re.search(r"technic axle (\d+)", low)
    if m and "pin" not in low and "connector" not in low:
        return "axle", dict(n=int(m.group(1)), stop="stop" in low)
    m = re.search(r"technic beam 1 x (\d+)", low)
    if m:
        return "beam", dict(n=int(m.group(1)), thick="thin" not in low)
    m = re.search(r"technic brick 1 x (\d+)", low)
    if m:
        return "technic_brick", dict(n=int(m.group(1)))
    if low.startswith("technic pin"):
        return "pin", dict(length=3 if "long" in low else 2, half="1/2" in low)
    if low.startswith(("tyre", "tire")) and d:
        return "wheel", dict(diameter=d[0] / 8, width=d[1] / 8, tyre=True)
    if low.startswith("wheel") and d:
        return "wheel", dict(diameter=d[0] / 8, width=max(0.5, d[1] / 8))
    if low.startswith("bar ") and re.search(r"(\d+)l", low):
        return "bar", dict(n=int(re.search(r"(\d+)l", low).group(1)))
    if d:
        a, b, c = d
        if low.startswith(("brick round", "plate round", "tile round", "cone")) and a == b:
            h = PLATE if low.startswith(("plate", "tile")) else BRICK
            return "round", dict(d=a, h=h, studs=not low.startswith("tile"), cone=low.startswith("cone"))
        if low.startswith("slope"):
            height = (c * BRICK) if c else BRICK
            if "curved" in low:
                return "slope", dict(depth=a, width=b, height=min(height, 0.8), flat=0.0, low=0.1, curved=True,
                                     studs=False)
            return "slope", dict(depth=a, width=b, height=height, flat=1.0 if a >= 2 else 0.0, low=0.2,
                                 inverted="inverted" in low, studs=a >= 2)
        if low.startswith("wedge plate"):
            return "wedge", dict(length=max(a, b), width=min(a, b), side="left" if "left" in low else "right",
                                 cut="cut" in low)
        if low.startswith(("brick", "plate", "tile", "technic brick")):
            h = PLATE if low.startswith(("plate", "tile")) else BRICK
            if c:
                h = c * BRICK
            w_, l_ = (b, a) if b >= a else (a, b)
            return "block", dict(w=w_, l=l_, h=h, studs=not low.startswith("tile"))
        if low.startswith("window"):
            return "window", dict(w=b, h_bricks=c or 2)
        if low.startswith("door"):
            return "window", dict(w=b, h_bricks=c or 3, door=True)
        if low.startswith("panel"):
            return "panel", dict(w=b, h_bricks=c or 1)
    return "block", dict(w=2, l=2, h=BRICK, studs=True)


def _draw(cv: Canvas, kind: str, p: dict):
    if kind == "block":
        w, l, h = p.get("w", 2), p.get("l", 1), p.get("h", BRICK)
        box(cv, 0, 0, 0, w, l, h, studs=p.get("studs", True) and not p.get("jumper"))
        if p.get("jumper"):
            stud(cv, w / 2, l / 2, h)
        if p.get("side_stud"):
            for k in range(p["side_stud"]):
                rod(cv, "y", l, l + STUD_H, k + 0.5, h * 0.5, STUD_R, depth_bias=2,
                    cap_color=cv.fill(0.9))
        if p.get("grille"):
            for k in range(3):
                cv.face([(0.2, 0.2 + k * 0.25, h + 0.001), (w - 0.2, 0.2 + k * 0.25, h + 0.001),
                         (w - 0.2, 0.3 + k * 0.25, h + 0.001), (0.2, 0.3 + k * 0.25, h + 0.001)],
                        normal=(0, 0, 1), t=-0.3, depth=w + l + h + 1)
        if p.get("log") or p.get("masonry"):
            for k in range(1, 3 if p.get("log") else 4):
                z = h * k / (3 if p.get("log") else 4)
                a, b = proj(0, l, z), proj(w, l, z)
                cv.raw(w + l + h + 1, f'<path d="M{a[0]:.1f} {a[1]:.1f} L{b[0]:.1f} {b[1]:.1f}" '
                                      f'stroke="{cv.edge}" stroke-width="1.4" stroke-opacity=".6"/>')
        return
    if kind == "corner":
        draw_corner(cv, p.get("h", BRICK), studs=p.get("studs", True))
        return
    if kind == "slope":
        draw_slope(cv, **p)
        return
    if kind == "round":
        draw_round(cv, **p)
        return
    if kind == "wedge":
        draw_wedge_plate(cv, **p)
        return
    if kind == "arch":
        length = p.get("length", 4)
        prof = [(0, 0), (0.6, 0)]
        for k in range(1, 12):
            t = math.pi * k / 12
            prof.append((length / 2 - (length / 2 - 0.6) * math.cos(t), (BRICK - 0.35) * math.sin(t)))
        prof += [(length - 0.6, 0), (length, 0), (length, BRICK), (0, BRICK)]
        extrude_profile(cv, [(x, z) for x, z in prof], 0, 1)
        studs_on(cv, [(i, 0) for i in range(int(length))], 0, 0, BRICK, length / 2 + 0.5 + BRICK)
        return
    if kind == "bracket":
        wide = p.get("wide")
        box(cv, 0, 0, 0, 2, 1, PLATE)
        box(cv, 0, 1, 0, 2 if not wide else 2, PLATE, BRICK, studs=False)
        for i in range(2):
            rod(cv, "y", 1 + PLATE, 1 + PLATE + STUD_H, i + 0.5, BRICK * 0.6, STUD_R, depth_bias=2,
                cap_color=cv.fill(0.9))
        return
    if kind == "window":
        draw_window(cv, **p)
        return
    if kind == "wheel":
        draw_wheel(cv, **p)
        return
    if kind == "beam":
        draw_beam(cv, p.get("n", 3), thick=p.get("thick", True), l_shape=p.get("l_shape"))
        return
    if kind == "frame":
        outline = [(0, 0), (5, 0), (5, 7), (0, 7)]
        extrude_up(cv, outline, 0, 0.84)
        cv.face([(1, 1, 0.845), (4, 1, 0.845), (4, 6, 0.845), (1, 6, 0.845)], normal=(0, 0, 1), t=-0.6, depth=20)
        for i in range(5):
            hole_top(cv, i + 0.5, 0.5, 0.85)
            hole_top(cv, i + 0.5, 6.5, 0.85)
        for j in range(1, 6):
            hole_top(cv, 0.5, j + 0.5, 0.85)
            hole_top(cv, 4.5, j + 0.5, 0.85)
        return
    if kind == "technic_brick":
        draw_technic_brick(cv, p["n"])
        return
    if kind == "axle":
        draw_axle(cv, p["n"], p.get("stop", False))
        return
    if kind == "pin":
        draw_pin(cv, **p)
        return
    if kind == "bush":
        draw_bush(cv, **p)
        return
    if kind == "connector":
        draw_connector(cv, **p)
        return
    if kind == "gear":
        draw_gear(cv, p.get("teeth", 8) or 8, bevel=p.get("bevel", False), rack=p.get("rack"))
        return
    if kind == "flower":
        draw_flower(cv, **p)
        return
    if kind == "leaves":
        draw_leaves(cv, **p)
        return
    if kind == "cherries":
        draw_cherries(cv)
        return
    if kind == "hilt":
        draw_hilt(cv)
        return
    if kind == "bar":
        draw_bar(cv, p["n"])
        return
    if kind == "cup":
        draw_cup(cv, **p)
        return
    if kind == "icon":
        draw_icon(cv, p["name"])
        return
    if kind == "hinge":
        draw_hinge_brick(cv, **p)
        return
    if kind == "turntable":
        draw_turntable(cv, **p)
        return
    if kind == "panel":
        draw_panel(cv, **p)
        return
    if kind == "fence":
        draw_fence(cv, **p)
        return
    box(cv, 0, 0, 0, 2, 2, BRICK)


@lru_cache(maxsize=4096)
def render_part_svg(design_id: str, name: str, hexcolor: str, transparent: bool = False, finish: str = "solid",
                    size: int = 320) -> str:
    kind, params = classify(design_id, name)
    cv = Canvas(hexcolor, transparent, finish)
    try:
        _draw(cv, kind, dict(params))
    except Exception:  # never break a page because of an illustration
        cv = Canvas(hexcolor, transparent, finish)
        box(cv, 0, 0, 0, 2, 2, BRICK)
    return cv.render(size)


# ---------------------------------------------------------------------------
# fallbacks for sets and minifigures without photos
# ---------------------------------------------------------------------------
def render_minifig_svg(accent: str = "#E3000B", size: int = 360) -> str:
    a = accent
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">'
        f'<rect x="38" y="10" width="24" height="20" rx="7" fill="#FFD43B" stroke="#00000022"/>'
        f'<rect x="44" y="6" width="12" height="6" rx="2" fill="#FFD43B"/>'
        f'<circle cx="45" cy="19" r="1.8" fill="#222"/><circle cx="55" cy="19" r="1.8" fill="#222"/>'
        f'<path d="M44 24 q6 4 12 0" stroke="#222" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
        f'<path d="M34 32 L66 32 L70 58 L30 58 Z" fill="{a}"/>'
        f'<rect x="24" y="34" width="9" height="20" rx="4" fill="{a}" transform="rotate(10 28 44)"/>'
        f'<rect x="67" y="34" width="9" height="20" rx="4" fill="{a}" transform="rotate(-10 72 44)"/>'
        f'<rect x="31" y="58" width="38" height="6" fill="#30343b"/>'
        f'<rect x="31" y="64" width="18" height="26" rx="2" fill="#30343b"/>'
        f'<rect x="51" y="64" width="18" height="26" rx="2" fill="#30343b"/>'
        f'</svg>'
    )

"""Removing a plain background from product photos (Pillow only — no AI service, no heavy libraries).

Works for photos taken on an even surface: white paper, a plain table or wall, a light box or a gradient
backdrop. The background is modelled from the frame of the photo (allowing for uneven light and for an object
that touches an edge); everything that looks like it and is connected to the frame becomes transparent. Edges of
the object act as barriers, so light parts inside the object stay. A shadow cast on the background is kept as a
soft neutral shadow, and the object is cropped with a small margin.

When the frame does not show such a background (carpet, a busy room, the object fills the photo), nothing is
changed and the reason is reported.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath, ImageStat

WORK_SIDE = 480          # the mask is found on a copy this big, then refined at full size
SEGMENTS = 10            # pieces of every frame side used to model the background
SHADOW_STRENGTH = 0.8    # 1 keeps shadows as dark as on the photo, 0 removes them
SHADOW_SIDE = 640        # shadows are measured on a copy this big


@dataclass
class Cutout:
    image: Image.Image | None   # RGBA cut-out, or None when the photo is left as it is
    status: str                 # "removed" | "transparent" | "skipped"
    note: str = ""


def _percentile(hist: list[int], q: float) -> int:
    total = sum(hist)
    if not total:
        return 0
    need, acc = total * q, 0
    for value, count in enumerate(hist):
        acc += count
        if acc >= need:
            return value
    return len(hist) - 1


def _max_channel(img: Image.Image) -> Image.Image:
    r, g, b = img.split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def _threshold(img: Image.Image, limit: float, above: bool = False) -> Image.Image:
    return img.point([(255 if v > limit else 0) if above else (255 if v <= limit else 0) for v in range(256)])


def _fraction(binary: Image.Image, mask: Image.Image | None = None) -> float:
    hist = binary.histogram(mask=mask)
    total = sum(hist)
    return hist[255] / total if total else 0.0


# --- background model --------------------------------------------------------------------------------------
def _side_colours(img: Image.Image, box, horizontal: bool) -> list[tuple[int, int, int]]:
    strip = img.crop(box)
    w, h = strip.size
    n = max(2, min(SEGMENTS, w if horizontal else h))
    out = []
    for i in range(n):
        piece = (strip.crop((i * w // n, 0, max(i * w // n + 1, (i + 1) * w // n), h)) if horizontal else
                 strip.crop((0, i * h // n, w, max(i * h // n + 1, (i + 1) * h // n))))
        out.append(tuple(int(v) for v in ImageStat.Stat(piece).median))
    return out


def _repair(colours, bad):
    """Replace the segments covered by the object with values interpolated from their neighbours."""
    good = [i for i, b in enumerate(bad) if not b]
    if not good:
        return None
    fixed = []
    for i, colour in enumerate(colours):
        if not bad[i]:
            fixed.append(colour)
            continue
        left = max((g for g in good if g < i), default=None)
        right = min((g for g in good if g > i), default=None)
        if left is None or right is None:
            fixed.append(colours[left if left is not None else right])
        else:
            t = (i - left) / (right - left)
            fixed.append(tuple(round(a + (b - a) * t) for a, b in zip(colours[left], colours[right])))
    return fixed


def _line(colours, horizontal: bool, length: int) -> Image.Image:
    line = Image.new("RGB", (len(colours), 1) if horizontal else (1, len(colours)))
    line.putdata(colours)
    return line.resize((length, 1) if horizontal else (1, length), Image.Resampling.BILINEAR)


def _plate(img: Image.Image, ring: int):
    """(smooth picture of the background alone, share of the frame covered by the object) or (None, share)."""
    w, h = img.size
    sides = {"top": (_side_colours(img, (0, 0, w, ring), True), True),
             "bottom": (_side_colours(img, (0, h - ring, w, h), True), True),
             "left": (_side_colours(img, (0, 0, ring, h), False), False),
             "right": (_side_colours(img, (w - ring, 0, w, h), False), False)}
    every = [c for colours, _ in sides.values() for c in colours]

    def gap(a, b):
        return max(abs(x - y) for x, y in zip(a, b))

    # the most typical frame colour (a real one, not a mix of the object and the background)
    ref = min(every, key=lambda c: sum(gap(c, other) for other in every))
    devs = [gap(c, ref) for c in every]
    limit = min(60, max(34, 3 * sorted(devs)[len(devs) // 2]))
    bad_share = sum(d > limit for d in devs) / len(devs)
    if bad_share > 0.2:
        return None, bad_share
    lines = {}
    for name, (colours, horizontal) in sides.items():
        bad = [gap(c, ref) > limit for c in colours]
        fixed = _repair(colours, bad) or [ref] * len(colours)
        lines[name] = _line(fixed, horizontal, w if horizontal else h).resize((w, h), Image.Resampling.NEAREST)
    down = Image.linear_gradient("L").resize((w, h), Image.Resampling.BILINEAR)
    across = Image.linear_gradient("L").transpose(Image.Transpose.ROTATE_90).resize((w, h), Image.Resampling.BILINEAR)
    vertical = Image.composite(lines["bottom"], lines["top"], down)
    horizontal = Image.composite(lines["right"], lines["left"], across)
    # near the top and bottom edges trust the vertical blend, near the sides the horizontal one
    dist_tb = ImageChops.darker(down, ImageChops.invert(down)).convert("F")
    dist_lr = ImageChops.darker(across, ImageChops.invert(across)).convert("F")
    weight = ImageMath.lambda_eval(lambda a: a["lr"] * 255.0 / (a["lr"] + a["tb"] + 0.5),
                                   lr=dist_lr, tb=dist_tb).convert("L")
    return Image.composite(vertical, horizontal, weight), bad_share


def _edges(img: Image.Image) -> Image.Image:
    """Outline strength in both directions (dark-to-light and light-to-dark) over all colour channels."""
    out = None
    for channel in img.split():
        both = ImageChops.lighter(channel.filter(ImageFilter.FIND_EDGES),
                                  ImageChops.invert(channel).filter(ImageFilter.FIND_EDGES))
        out = both if out is None else ImageChops.lighter(out, both)
    return out


def _shading(img: Image.Image, plate: Image.Image, max_dev: float):
    """(how much darker than the background, 0..255; mask of pixels that are only a shadow on it).

    A shadow keeps the colour of the surface and only lowers its brightness by the same factor in every channel.
    """
    ratios = [ImageMath.lambda_eval(lambda a: a["p"] / (a["q"] + 1.0), p=c.convert("F"), q=b.convert("F"))
              for c, b in zip(img.split(), plate.split())]
    k = ImageMath.lambda_eval(lambda a: (a["r"] + a["g"] + a["b"]) / 3.0, r=ratios[0], g=ratios[1], b=ratios[2])
    dev = ImageMath.lambda_eval(
        lambda a: a["max"](a["max"](abs(a["r"] - a["k"]), abs(a["g"] - a["k"])), abs(a["b"] - a["k"])),
        r=ratios[0], g=ratios[1], b=ratios[2], k=k)
    darkness = ImageMath.lambda_eval(lambda a: (1.0 - a["k"]) * 255.0, k=k).convert("L")
    flat = ImageMath.lambda_eval(lambda a: (a["d"] < max_dev) * 255, d=dev).convert("L")
    # a shadow is 5–70 % darker than the background; darker than that is the object itself
    shadowish = ImageChops.multiply(flat, darkness.point([255 if 12 <= v <= 178 else 0 for v in range(256)]))
    return darkness, shadowish


# --- connectivity ------------------------------------------------------------------------------------------
def _dilate4(img: Image.Image) -> Image.Image:
    out = img
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        out = ImageChops.lighter(out, ImageChops.offset(img, dx, dy))
    return out


def _reconstruct(seed: Image.Image, allowed: Image.Image, limit: int = 3000) -> Image.Image:
    """Everything in ``allowed`` that is connected to ``seed`` (both 0/255), 4-connected."""
    w, h = seed.size
    mask = Image.new("L", (w + 2, h + 2), 0)
    mask.paste(allowed, (1, 1))
    cur = Image.new("L", (w + 2, h + 2), 0)
    cur.paste(ImageChops.darker(seed, allowed), (1, 1))
    for step in range(limit):
        nxt = ImageChops.darker(_dilate4(cur), mask)
        if step % 6 == 5 and ImageChops.difference(nxt, cur).getbbox() is None:
            cur = nxt
            break
        cur = nxt
    return cur.crop((1, 1, w + 1, h + 1))


def has_transparency(img: Image.Image) -> bool:
    if img.mode not in ("RGBA", "LA", "PA") and "transparency" not in img.info:
        return False
    hist = img.convert("RGBA").getchannel("A").histogram()
    return sum(hist[:250]) / max(1, sum(hist)) > 0.02


def remove_background(img: Image.Image) -> Cutout:
    if has_transparency(img):
        return Cutout(None, "transparent", "Фон уже прозорий")
    rgb = img.convert("RGB")
    full_w, full_h = rgb.size
    if min(full_w, full_h) < 40:
        return Cutout(None, "skipped", "Фото замале")
    small = rgb.copy()
    small.thumbnail((WORK_SIDE, WORK_SIDE), Image.Resampling.BOX)
    w, h = small.size
    ring_w = max(3, round(min(w, h) * 0.03))
    ring = Image.new("L", (w, h), 255)
    ImageDraw.Draw(ring).rectangle((ring_w, ring_w, w - 1 - ring_w, h - 1 - ring_w), fill=0)

    plate, covered = _plate(small, ring_w)
    if plate is None:
        return Cutout(None, "skipped", "Фон неоднотонний або предмет закриває краї фото — фото залишено як є")
    dist = _max_channel(ImageChops.difference(small, plate))
    noise = _percentile(dist.histogram(mask=ring), 0.6)
    if noise > 18:
        return Cutout(None, "skipped", "Фон строкатий — фото залишено як є")
    tolerance = min(46.0, max(16.0, noise * 2.6 + 10))
    max_dev = 0.05 + noise / 255 * 2

    edges = _edges(small)
    edge_noise = _percentile(edges.histogram(mask=ring), 0.9)
    barrier = _threshold(edges, max(26.0, edge_noise * 2.5), above=True).filter(ImageFilter.MaxFilter(3))
    # shadows are soft, so a much weaker outline already stops the shadow from spreading into a grey object
    soft_barrier = _threshold(edges, max(10.0, edge_noise * 1.3), above=True).filter(ImageFilter.MaxFilter(3))

    similar = _threshold(dist, tolerance)
    _darkness, shadowish = _shading(small, plate, max_dev)
    seeds = ImageChops.multiply(ImageChops.subtract(similar, barrier), ring)
    if _fraction(seeds, ring) < 0.5:
        return Cutout(None, "skipped", "По краях фото немає однотонного фону — фото залишено як є")
    allowed = ImageChops.lighter(ImageChops.subtract(similar, barrier), ImageChops.subtract(shadowish, soft_barrier))
    surface = _reconstruct(seeds, allowed)                 # background and the shadows on it
    obj = ImageChops.invert(surface).filter(ImageFilter.MedianFilter(3))
    share = _fraction(obj)
    if share < 0.015:
        return Cutout(None, "skipped", "Не вдалося знайти предмет на фото")
    if share > 0.93:
        return Cutout(None, "skipped", "Предмет займає майже все фото — фон не прибрано")

    # full size: refine the outline where the small mask is uncertain
    up = obj.resize((full_w, full_h), Image.Resampling.BILINEAR)
    k = max(3, round(full_w / w) * 2 + 1)
    band = _threshold(ImageChops.difference(up.filter(ImageFilter.MaxFilter(k)), up.filter(ImageFilter.MinFilter(k))),
                      8, above=True)
    plate_full = plate.resize((full_w, full_h), Image.Resampling.BILINEAR)
    soft = rgb.filter(ImageFilter.BoxBlur(1))
    similar_full = _threshold(_max_channel(ImageChops.difference(soft, plate_full)), tolerance)
    # shadows are smooth, so they are measured on a copy of at most SHADOW_SIDE px (saves memory and time)
    scale = min(1.0, SHADOW_SIDE / max(full_w, full_h))
    mid = (max(1, round(full_w * scale)), max(1, round(full_h * scale)))
    darkness_mid, shadow_mid = _shading(soft.resize(mid, Image.Resampling.BOX), plate.resize(mid, Image.Resampling.BILINEAR),
                                        max_dev)
    darkness_full = darkness_mid.resize((full_w, full_h), Image.Resampling.BILINEAR)
    shadow_full = _threshold(shadow_mid.resize((full_w, full_h), Image.Resampling.BILINEAR), 127, above=True)
    surface_full = ImageChops.lighter(similar_full, shadow_full)
    obj_mask = Image.composite(ImageChops.invert(surface_full), _threshold(up, 127, above=True), band)
    obj_mask = obj_mask.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MinFilter(3))
    obj_alpha = obj_mask.filter(ImageFilter.GaussianBlur(0.8))

    # the shadow becomes a soft neutral one: transparency follows how much it darkened the background, starting
    # above the normal unevenness of the background (so paper texture or wood grain does not become a shadow)
    shadow_zone = ImageChops.multiply(ImageChops.invert(obj_mask), shadow_full)
    floor = tolerance * 1.1
    ramp = [0 if v <= floor else min(255, int((v - floor) * SHADOW_STRENGTH * 255 / (255 - floor))) for v in range(256)]
    shadow_alpha = ImageChops.multiply(darkness_full.point(ramp), shadow_zone).filter(ImageFilter.GaussianBlur(1.5))
    alpha = ImageChops.lighter(obj_alpha, shadow_alpha)
    # the outermost pixels of a photo are unreliable (lens, JPEG, blur); never keep a frame line from them
    edge = max(2, round(min(full_w, full_h) * 0.004))
    inner = Image.new("L", rgb.size, 0)
    ImageDraw.Draw(inner).rectangle((edge, edge, full_w - 1 - edge, full_h - 1 - edge), fill=255)
    alpha = ImageChops.darker(alpha, inner)
    colour = Image.composite(rgb, Image.new("RGB", rgb.size, (24, 24, 28)), obj_alpha)

    box = _threshold(alpha, 20, above=True).getbbox()
    if box is None:
        return Cutout(None, "skipped", "Не вдалося знайти предмет на фото")
    out = colour.convert("RGBA")
    out.putalpha(alpha)
    bw, bh = box[2] - box[0], box[3] - box[1]
    margin = max(4, round(max(bw, bh) * 0.05))
    canvas = Image.new("RGBA", (bw + 2 * margin, bh + 2 * margin), (0, 0, 0, 0))
    canvas.paste(out.crop(box), (margin, margin))
    note = "Фон прибрано" + (" (предмет торкається краю фото — перевірте результат)" if covered > 0.08 else "")
    return Cutout(canvas, "removed", note)

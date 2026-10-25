# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Editor image operations (Pillow): geometry, light/colour adjustments, filters, annotations."""
import copy
import math

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from .i18n import N_

try:
    import cairo
except ImportError:  # pragma: no cover
    cairo = None

ADJUSTMENTS = [
    # (key, label, icon, section)
    ("brightness", N_("Brightness"), "brightness", N_("Lighting")),
    ("exposure", N_("Exposure"), "sparkle", N_("Lighting")),
    ("contrast", N_("Contrast"), "aspect", N_("Lighting")),
    ("highlights", N_("Highlights"), "star", N_("Lighting")),
    ("shadows", N_("Shadows"), "photo", N_("Lighting")),
    ("vignette", N_("Vignette"), "select", N_("Lighting")),
    ("saturation", N_("Saturation"), "wand", N_("Color")),
    ("warmth", N_("Warmth"), "sparkle", N_("Color")),
    ("tint", N_("Tint"), "pen", N_("Color")),
    ("sharpness", N_("Sharpness"), "crop", N_("Color")),
]

FILTERS = [
    N_("Original"), N_("Punch"), N_("Golden"), N_("Radiate"), N_("Warm Contrast"), N_("Calm"), N_("Cool Light"),
    N_("Vivid Cool"), N_("Dramatic Cool"), N_("Black & White"), N_("Cool B&W"), N_("Warm B&W"),
    N_("High-Contrast B&W"), N_("Engrave"), N_("Film"),
]

ASPECTS = [(N_("Original"), None), (N_("Square"), 1.0), ("9:16", 9 / 16), ("16:9", 16 / 9), ("4:5", 4 / 5), ("5:4", 5 / 4),
           ("3:4", 3 / 4), ("4:3", 4 / 3), ("2:3", 2 / 3), ("3:2", 3 / 2), ("5:7", 5 / 7), ("7:5", 7 / 5), ("1:2", 1 / 2)]

PEN_COLORS = ["#ffd02f", "#ffaa00", "#ff5500", "#e61b1b", "#5c2d91", "#9b4fc4", "#e3008c", "#c30052",
              "#2bc3ff", "#0078d4", "#0050b3", "#7fba00", "#00b050", "#ebebeb", "#b3b3b3", "#000000"]


class EditState:
    def __init__(self):
        self.ops = []                # 'rot' | 'fh' | 'fv'
        self.angle = 0.0
        self.crop = (0.0, 0.0, 1.0, 1.0)
        self.adjust = {k: 0 for k, *_ in ADJUSTMENTS}
        self.filter = "Original"
        self.intensity = 100
        self.auto = False
        self.strokes = []            # dicts: kind, color, size, pts[(u,v)]
        self.aspect_name = "Free"

    def snapshot(self):
        return copy.deepcopy(self.__dict__)

    def restore(self, snap):
        self.__dict__.update(copy.deepcopy(snap))

    def is_default(self):
        d = EditState()
        return (self.ops == d.ops and abs(self.angle) < 0.01 and self.crop == d.crop and self.adjust == d.adjust
                and self.filter == "Original" and not self.auto and not self.strokes)


# ───────────────────────── geometria ─────────────────────────

def apply_ops(im, ops):
    for op in ops:
        if op == "rot":
            im = im.transpose(Image.ROTATE_270)
        elif op == "fh":
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        elif op == "fv":
            im = im.transpose(Image.FLIP_TOP_BOTTOM)
    return im


def straighten(im, angle):
    if abs(angle) < 0.01:
        return im
    w, h = im.size
    th = math.radians(abs(angle))
    # zoom factor needed to cover the empty corners
    s = math.cos(th) + math.sin(th) * max(w / h, h / w)
    rot = im.rotate(-angle, resample=Image.BICUBIC, expand=False)
    cw, ch = w / s, h / s
    box = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
    return rot.resize((w, h), Image.BICUBIC, box=box)


def geometry(im, state):
    return straighten(apply_ops(im, state.ops), state.angle)


def transform_point_for_op(u, v, op):
    if op == "rot":
        return 1 - v, u
    if op == "fh":
        return 1 - u, v
    return u, 1 - v


# ───────────────────────── ajustes ─────────────────────────

def _lut_for(adj):
    b, e, c = adj["brightness"], adj["exposure"], adj["contrast"]
    hi, sh = adj["highlights"], adj["shadows"]
    lut = []
    for v in range(256):
        x = v / 255.0
        if e:
            x = x ** (2 ** (-e / 60.0))
        x = x + b / 100.0 * 0.35
        if c:
            x = (x - 0.5) * (1 + c / 100.0 * (1 if c < 0 else 1.2)) + 0.5
        if hi:
            x += hi / 100.0 * 0.3 * (max(0.0, x - 0.4) / 0.6) ** 1.5
        if sh:
            x += sh / 100.0 * 0.3 * (max(0.0, 0.6 - x) / 0.6) ** 1.5
        lut.append(max(0, min(255, int(round(x * 255)))))
    return lut


def _channel_lut(delta):
    return [max(0, min(255, int(round(v + delta)))) for v in range(256)]


def _vignette(im, amount):
    w, h = im.size
    g = Image.radial_gradient("L").resize((w, h), Image.BICUBIC)
    g = g.point([min(255, int((v / 255.0) ** 2.2 * 255 * 1.15)) for v in range(256)])
    a = abs(amount) / 100.0
    mask = g.point([int(v * a) for v in range(256)])
    if amount < 0:
        return Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), im, mask)
    return Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), im, mask)


def apply_adjust(im, adj):
    if not any(adj.values()):
        return im
    alpha = None
    if im.mode == "RGBA":
        alpha = im.getchannel("A")
        im = im.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")
    if any(adj[k] for k in ("brightness", "exposure", "contrast", "highlights", "shadows")):
        lut = _lut_for(adj)
        im = im.point(lut * 3)
    if adj["saturation"]:
        im = ImageEnhance.Color(im).enhance(max(0.0, 1 + adj["saturation"] / 100.0))
    if adj["warmth"] or adj["tint"]:
        w, t = adj["warmth"], adj["tint"]
        r, g, b = im.split()
        r = r.point(_channel_lut(w * 0.28))
        b = b.point(_channel_lut(-w * 0.28))
        g = g.point(_channel_lut(-t * 0.22))
        im = Image.merge("RGB", (r, g, b))
    if adj["vignette"]:
        im = _vignette(im, adj["vignette"])
    k = adj["sharpness"]
    if k > 0:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=int(k * 2.2), threshold=2))
    elif k < 0:
        im = im.filter(ImageFilter.GaussianBlur(radius=-k / 100.0 * 2.5))
    if alpha is not None:
        im.putalpha(alpha)
    return im


# ───────────────────────── filtros ─────────────────────────

def _tint(im, rgb, amount):
    layer = Image.new("RGB", im.size, rgb)
    return Image.blend(im, layer, amount)


def _gray(im):
    return ImageOps.grayscale(im).convert("RGB")


def _filter_core(im, name):
    if name == "Punch":
        return ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(1.22)).enhance(1.25)
    if name == "Golden":
        im = ImageEnhance.Brightness(im).enhance(1.06)
        return _tint(ImageEnhance.Color(im).enhance(1.1), (255, 200, 110), 0.18)
    if name == "Radiate":
        glow = im.filter(ImageFilter.GaussianBlur(max(2, im.size[0] // 60)))
        out = Image.blend(im, ImageChops.screen(im, glow), 0.55)
        return _tint(ImageEnhance.Contrast(ImageEnhance.Brightness(out).enhance(1.05)).enhance(0.92), (255, 230, 200), 0.1)
    if name == "Warm Contrast":
        return _tint(ImageEnhance.Contrast(im).enhance(1.3), (255, 170, 90), 0.12)
    if name == "Calm":
        im = ImageEnhance.Color(im).enhance(0.78)
        im = im.point(([min(255, 14 + int(v * 0.94)) for v in range(256)]) * 3)
        return _tint(im, (170, 205, 200), 0.1)
    if name == "Cool Light":
        return _tint(ImageEnhance.Brightness(im).enhance(1.05), (120, 170, 255), 0.17)
    if name == "Vivid Cool":
        return _tint(ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.45)).enhance(1.1), (90, 150, 255), 0.1)
    if name == "Dramatic Cool":
        out = _tint(ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(0.78)).enhance(1.4), (70, 110, 190), 0.16)
        return _vignette(out, -45)
    if name == "Black & White":
        return _gray(im)
    if name == "Cool B&W":
        return _tint(_gray(ImageEnhance.Contrast(im).enhance(1.1)), (110, 150, 220), 0.22)
    if name == "Warm B&W":
        return _tint(_gray(ImageEnhance.Contrast(im).enhance(1.1)), (230, 170, 110), 0.3)
    if name == "High-Contrast B&W":
        return ImageEnhance.Contrast(_gray(im)).enhance(1.7)
    if name == "Engrave":
        g = ImageEnhance.Contrast(_gray(im)).enhance(1.35)
        return g.filter(ImageFilter.UnsharpMask(radius=2.2, percent=220, threshold=1))
    if name == "Film":
        im = im.point(([int(24 + v * 0.88) for v in range(256)]) * 3)
        im = _tint(ImageEnhance.Color(im).enhance(0.9), (255, 220, 170), 0.1)
        return _vignette(im, -30)
    return im


def apply_filter(im, name, intensity=100):
    if name == "Original" or name not in FILTERS:
        return im
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    out = _filter_core(rgb, name)
    if intensity < 100:
        out = Image.blend(rgb, out, intensity / 100.0)
    if alpha is not None:
        out.putalpha(alpha)
    return out


def apply_auto(im):
    alpha = im.getchannel("A") if im.mode == "RGBA" else None
    rgb = im.convert("RGB")
    out = ImageOps.autocontrast(rgb, cutoff=0.6)
    out = ImageEnhance.Color(out).enhance(1.08)
    if alpha is not None:
        out.putalpha(alpha)
    return out


def tone(im, state):
    """Auto, ajustes e filtro (tudo antes do corte)."""
    if state.auto:
        im = apply_auto(im)
    im = apply_adjust(im, state.adjust)
    im = apply_filter(im, state.filter, state.intensity)
    return im


# ───────────────────────── annotations ─────────────────────────

def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def stroke_path(cr, pts, w, h):
    if not pts:
        return
    p0 = (pts[0][0] * w, pts[0][1] * h)
    cr.move_to(*p0)
    if len(pts) == 1:
        cr.line_to(p0[0] + 0.01, p0[1])
        return
    if len(pts) == 2:
        cr.line_to(pts[1][0] * w, pts[1][1] * h)
        return
    for i in range(1, len(pts) - 1):
        x1, y1 = pts[i][0] * w, pts[i][1] * h
        x2, y2 = pts[i + 1][0] * w, pts[i + 1][1] * h
        cr.curve_to(x1, y1, x1, y1, (x1 + x2) / 2, (y1 + y2) / 2)
    cr.line_to(pts[-1][0] * w, pts[-1][1] * h)


def stroke_width_px(st, ref):
    base = st["size"] * (3.0 if st["kind"] == "highlighter" else 1.0)
    return max(1.0, base / 600.0 * ref * (1.0 if st["kind"] != "pencil" else 0.6))


def burn_strokes(im, strokes, crop):
    """Burns the annotations (normalised on the whole geometric image) onto the ALREADY cropped image."""
    if not strokes:
        return im
    cw, ch = im.size
    x0, y0, x1, y1 = crop
    fw, fh = cw / max(1e-6, (x1 - x0)), ch / max(1e-6, (y1 - y0))
    ref = max(fw, fh)
    base = im.convert("RGBA")
    result = base
    for st in strokes:
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, cw, ch)
        cr = cairo.Context(surf)
        pts = [((u - x0) * fw, (v - y0) * fh) for u, v in st["pts"]]
        path_pts = [(p[0] / cw, p[1] / ch) for p in pts]
        stroke_path(cr, path_pts, cw, ch)
        lw = stroke_width_px(st, ref)
        cr.set_line_width(lw)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_cap(cairo.LINE_CAP_BUTT if st["kind"] == "highlighter" else cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(1, 1, 1, 1)
        cr.stroke()
        surf.flush()
        mask = Image.frombuffer("RGBA", (cw, ch), bytes(surf.get_data()), "raw", "BGRa", surf.get_stride(), 1).getchannel("A")
        r, g, b = [int(round(c * 255)) for c in _hex(st["color"])]
        solid = Image.new("RGBA", (cw, ch), (r, g, b, 255))
        if st["kind"] == "highlighter":
            mult = ImageChops.multiply(result.convert("RGB"), solid.convert("RGB")).convert("RGBA")
            result = Image.composite(mult, result, mask)
        else:
            result = Image.composite(solid, result, mask)
    if im.mode != "RGBA":
        return result.convert(im.mode if im.mode in ("RGB", "L") else "RGB")
    return result


def render_final(base, state):
    """Full-resolution render: geometry → adjustments/filter → crop → annotations."""
    im = geometry(base, state)
    im = tone(im, state)
    w, h = im.size
    x0, y0, x1, y1 = state.crop
    box = (round(x0 * w), round(y0 * h), max(round(x0 * w) + 1, round(x1 * w)), max(round(y0 * h) + 1, round(y1 * h)))
    im = im.crop(box)
    x0b, y0b = box[0] / w, box[1] / h
    x1b, y1b = box[2] / w, box[3] / h
    return burn_strokes(im, state.strokes, (x0b, y0b, x1b, y1b))

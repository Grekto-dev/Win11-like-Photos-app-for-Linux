# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Markup tools: sizes, colours, line modes, arrow heads and how a stroke is painted.

The numbers come from measurements of the Windows Photos app (docs/DESIGN-NOTES.md):

* A stroke is as wide on the screen as the chosen level says, whatever the zoom: drawing while zoomed out
  gives a thicker line in the saved picture. The width is therefore converted to image pixels when the stroke is
  created (`image_width`) and stored in it as "w".
* The highlighter is the colour at 50 % opacity, normal blending, flat ends. Two strokes add up, one stroke
  crossing itself does not.
* An arrow head is two arms at 45 degrees to the line, 3.8 times the stroke width long, drawn with the same width.

Canvas and final render both paint through `paint_stroke`, so what is seen is what is saved.
"""
import math
import re

import cairo

from . import settings
from .i18n import _, N_

LEVELS = 6
DEFAULT_LEVEL = 3
HIGHLIGHTER_ALPHA = 0.5
ARROW_ANGLE = math.pi / 4
ARROW_PER_WIDTH = 3.8

# stroke width on the screen (device independent pixels) per level
WIDTHS = {"pen": (1, 2, 4, 6, 8, 12), "highlighter": (8, 12, 16, 24, 28, 32)}
# thickness of the wide end of the preview wedge in the flyout, per level
PREVIEW_TIP = {"pen": (2, 4, 7, 10, 12, 14), "highlighter": (2, 4, 6, 9, 11, 13)}

TOOLS = ("pen", "pen2", "highlighter")          # two pens (blue and black by default) and the highlighter

PALETTE = [
    ("#fed430", N_("Dark yellow")), ("#fbae17", N_("Light orange")), ("#f36323", N_("Orange")),
    ("#e3182d", N_("Red")), ("#5b318d", N_("Dark purple")), ("#914bb8", N_("Purple")),
    ("#cf1278", N_("Magenta")), ("#c10051", N_("Dark red")),
    ("#3eccfd", N_("Light blue")), ("#0078d7", N_("Blue")), ("#0051ba", N_("Dark blue")),
    ("#7ec400", N_("Light green")), ("#00b44b", N_("Green")), ("#ebebeb", N_("Light gray")),
    ("#b6b6b6", N_("Gray")), ("#1f1f1f", N_("Black")),
]

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def kind_of(tool):
    return "highlighter" if tool == "highlighter" else "pen"


def modes_for(tool):
    """[(straight, arrows)] offered by the flyout. The highlighter has no arrows."""
    if tool == "highlighter":
        return [(False, 0), (True, 0)]
    return [(False, 0), (False, 1), (False, 2), (True, 0), (True, 1), (True, 2)]


# ───────────────────────── remembered choices ─────────────────────────

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def load_cfg(tool):
    """{'color', 'size' (level 1-6), 'mode' (index in modes_for)} of a tool; invalid fields fall back to the default."""
    default = settings.DEFAULTS["markup_tools"][tool]
    raw = settings.get("markup_tools")
    entry = raw.get(tool) if isinstance(raw, dict) else None
    if not isinstance(entry, dict):
        entry = {}
    color = entry.get("color")
    size = entry.get("size")
    mode = entry.get("mode")
    return {
        "color": color.lower() if isinstance(color, str) and _HEX.fullmatch(color) else default["color"],
        "size": size if _is_int(size) and 1 <= size <= LEVELS else default["size"],
        "mode": mode if _is_int(mode) and 0 <= mode < len(modes_for(tool)) else default["mode"],
    }


def save_cfg(tool, cfg):
    data = {t: load_cfg(t) for t in TOOLS}
    data[tool] = {"color": cfg["color"], "size": cfg["size"], "mode": cfg["mode"]}
    settings.set("markup_tools", data)


# ───────────────────────── sizes ─────────────────────────

def width_ui(tool, level):
    widths = WIDTHS[kind_of(tool)]
    return widths[max(1, min(LEVELS, int(level))) - 1]


def image_width(tool, level, zoom):
    """Width in image pixels of a stroke drawn at `zoom` (screen pixels per image pixel)."""
    w = width_ui(tool, level)
    return w / zoom if zoom and zoom > 0 else float(w)


def stroke_width(stroke, ref):
    """Width in image pixels of a stored stroke. Strokes without "w" are from before widths were fixed on the
    screen and scale with the picture (`ref` is its longest side)."""
    w = stroke.get("w")
    if w is not None:
        return w
    from . import imgops
    return imgops.stroke_width_px(stroke, ref)


# ───────────────────────── arrows ─────────────────────────

def arrow_length(width):
    return ARROW_PER_WIDTH * width


def arrow_arms(tip, direction, width):
    """End points of the two arms of an arrow head whose tip is `tip` on a line moving along `direction`."""
    length = arrow_length(width)
    bx, by = -direction[0], -direction[1]
    out = []
    for sign in (1, -1):
        a = sign * ARROW_ANGLE
        ca, sa = math.cos(a), math.sin(a)
        out.append((tip[0] + length * (bx * ca - by * sa), tip[1] + length * (bx * sa + by * ca)))
    return out[0], out[1]


MIN_EXTENT = 0.5          # a stroke that never got this far from its end has no direction (a tap)


def end_direction(pts, back):
    """Unit vector of the line at its last point, measured against the first point that is at least `back` away.

    Small strokes and loops never get `back` away from their end: the look-back then shrinks to half of the
    farthest distance reached, so a circle still gets a direction close to its tangent (an exactly closed loop
    included). Returns None when the stroke has no extent (a tap)."""
    if len(pts) < 2:
        return None
    ex, ey = pts[-1]
    dists = [math.hypot(ex - x, ey - y) for x, y in pts]
    far = max(dists)
    if far < MIN_EXTENT:
        return None
    back = min(back, far / 2.0)
    ref = pts[0]
    for (x, y), d in zip(reversed(pts[:-1]), reversed(dists[:-1])):
        if d >= back:
            ref = (x, y)
            break
    dx, dy = ex - ref[0], ey - ref[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-9 else None


def hit_radius(stroke, disp):
    """Reach of the eraser around a stroke, in widget pixels: at least 12, more for wide strokes and arrow heads.
    `disp` is widget pixels per image pixel."""
    w = (stroke.get("w") or 0.0) * disp
    reach = w / 2.0
    if stroke.get("arrows") and stroke.get("kind") != "highlighter":
        reach = max(reach, arrow_length(w) * 0.7)
    return max(12.0, reach)


# ───────────────────────── painting ─────────────────────────

def _smooth_path(cr, pts):
    cr.move_to(*pts[0])
    if len(pts) == 2:
        cr.line_to(*pts[1])
        return
    for i in range(1, len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        cr.curve_to(x1, y1, x1, y1, (x1 + x2) / 2, (y1 + y2) / 2)
    cr.line_to(*pts[-1])


def add_path(cr, pts, width, arrows=0):
    """Adds the stroke (and its arrow heads) to the current path, `pts` in the target's pixels."""
    if not pts:
        return
    if len(pts) == 1:
        pts = [pts[0], (pts[0][0] + 0.01, pts[0][1])]
    _smooth_path(cr, pts)
    if not arrows:
        return
    back = max(4.0 * width, 2.0)
    for index in range(2 if arrows >= 2 else 1):
        line = pts if index == 0 else list(reversed(pts))
        d = end_direction(line, back)
        if d is None:
            continue
        a, b = arrow_arms(line[-1], d, width)
        cr.move_to(*a)
        cr.line_to(*line[-1])
        cr.line_to(*b)


def paint_stroke(cr, kind, color, pts, width, arrows=0):
    """Paints one stroke. Pen: opaque, round ends. Highlighter: 50 % as a whole, flat ends, no arrows."""
    highlighter = kind == "highlighter"
    r, g, b = (int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    cr.save()
    if highlighter:
        cr.push_group()
    cr.new_path()
    add_path(cr, pts, width, 0 if highlighter else arrows)
    cr.set_source_rgb(r, g, b)
    cr.set_line_width(width)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_cap(cairo.LINE_CAP_BUTT if highlighter else cairo.LINE_CAP_ROUND)
    cr.stroke()
    if highlighter:
        cr.pop_group_to_source()
        cr.paint_with_alpha(HIGHLIGHTER_ALPHA)
    cr.restore()


# ───────────────────────── texts ─────────────────────────

def color_name(color):
    for c, name in PALETTE:
        if c == color.lower():
            return _(name)
    return color


def mode_name(tool, mode):
    straight, arrows = modes_for(tool)[mode]
    if tool == "highlighter":
        return _("Straight line") if straight else _("Freehand line")
    if straight:
        return (_("Straight line"), _("Straight line with an arrow at the end"),
                _("Straight line with arrows at both ends"))[arrows]
    return (_("Freehand line without arrow"), _("Freehand line with an arrow at the end"),
            _("Freehand line with arrows at both ends"))[arrows]


def mode_tooltip(tool, mode):
    text = mode_name(tool, mode)
    if modes_for(tool)[mode] == (True, 0):
        text += "\n" + _("To draw a straight line quickly, hold Shift while you click and drag with the left mouse button.")
    return text


def tool_tooltip(tool, cfg, selected=False):
    template = _("Highlighter: %(color)s, Thickness: %(size)d, %(mode)s") if tool == "highlighter" \
        else _("Pen: %(color)s, Thickness: %(size)d, %(mode)s")
    text = template % {"color": color_name(cfg["color"]), "size": cfg["size"], "mode": mode_name(tool, cfg["mode"])}
    if selected:
        text += "\n" + _("Select again to change the ink properties.")
    return text

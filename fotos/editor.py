# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Image editor: Crop, Adjust, Filters and Markup (shown inside the viewer window)."""
import math
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GLib, GObject, GdkPixbuf, Gtk  # noqa: E402

import cairo  # noqa: E402
from PIL import Image

from . import actions, dialogs, icons, imgops, settings, theme, ui
from .i18n import _, ngettext  # noqa: F401
from .canvas import next_zoom
from .imgops import EditState

HANDLE = 16


def pil_to_pixbuf(im):
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    has_alpha = im.mode == "RGBA"
    data = GLib.Bytes.new(im.tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, has_alpha, 8, im.width, im.height,
                                           im.width * (4 if has_alpha else 3))


def normalize_mode(im):
    if im.mode in ("RGB", "RGBA"):
        return im
    if im.mode in ("LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA")
    return im.convert("RGB")


# ───────────────────────── rotation ruler ─────────────────────────

class Ruler(Gtk.DrawingArea):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
                    "released": (GObject.SignalFlags.RUN_FIRST, None, ())}
    PX = 6.0

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, 26)
        self.value = 0.0
        self.drag = None
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._motion)
        self.connect("scroll-event", self._scroll)

    def set_value(self, v, emit=False):
        self.value = max(-45.0, min(45.0, v))
        self.queue_draw()
        if emit:
            self.emit("changed", self.value)

    def _press(self, w, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            self.set_value(0.0, True)
            self.emit("released")
            return True
        self.drag = (ev.x, self.value)
        return True

    def _release(self, w, ev):
        if self.drag:
            self.drag = None
            self.emit("released")
        return True

    def _motion(self, w, ev):
        if self.drag:
            x0, v0 = self.drag
            self.set_value(round((v0 - (ev.x - x0) / self.PX) * 10) / 10.0, True)
        return True

    def _scroll(self, w, ev):
        d = 1 if ev.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.LEFT) else -1
        if ev.direction == Gdk.ScrollDirection.SMOOTH:
            d = -1 if ev.delta_y > 0 else 1
        self.set_value(round(self.value + d), True)
        self.emit("released")
        return True

    def _draw(self, w, cr):
        W, H = self.get_allocated_width(), self.get_allocated_height()
        cx = W / 2
        theme.set_source(cr, "faint")
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for d in range(-45, 46):
            x = cx + (d - self.value) * self.PX
            if x < 4 or x > W - 4:
                continue
            fade = 1.0 - min(1.0, abs(x - cx) / (W / 2)) ** 3 * 0.8
            if d % 10 == 0:
                cr.set_source_rgba(*self._rgb("muted"), 0.9 * fade)
                cr.set_line_width(2)
                cr.move_to(x, H / 2 - 6)
                cr.line_to(x, H / 2 + 6)
                cr.stroke()
            else:
                cr.set_source_rgba(*self._rgb("faint"), 0.9 * fade)
                cr.arc(x, H / 2, 1.3, 0, 2 * math.pi)
                cr.fill()
        theme.set_source(cr, "fg")
        ui.rounded_rect(cr, cx - 2, H / 2 - 9, 4, 18, 2)
        cr.fill()
        return False

    def _rgb(self, role):
        c = theme.rgba(role)
        return c.red, c.green, c.blue


# ───────────────────────── edit canvas ─────────────────────────

class EditCanvas(Gtk.DrawingArea):
    __gsignals__ = {"zoom-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
                    "crop-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
                    "gesture-done": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, editor):
        super().__init__()
        self.ed = editor
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.pb = None
        self.pw = self.ph = 1
        self.zmul = 1.0
        self.pan = [0.0, 0.0]
        self.drag = None
        self.dragging_crop = False
        self.cur = None   # stroke in progress
        self.erased = False
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._motion)
        self.connect("scroll-event", self._scroll)
        self.connect("size-allocate", lambda *_: self.queue_draw())

    # view geometry
    def view_rect(self):
        """Rectangle (in preview pixels) currently being displayed."""
        if self.ed.tab == "crop":
            return 0.0, 0.0, float(self.pw), float(self.ph)
        x0, y0, x1, y1 = self.ed.state.crop
        return x0 * self.pw, y0 * self.ph, (x1 - x0) * self.pw, (y1 - y0) * self.ph

    def base_scale(self):
        vx, vy, vw, vh = self.view_rect()
        W, H = self.get_allocated_width(), self.get_allocated_height()
        m = 28
        return max(0.01, min((W - 2 * m) / max(1, vw), (H - 2 * m) / max(1, vh)))

    def scale(self):
        return self.base_scale() * self.zmul

    def origin(self):
        """Canto superior esquerdo (widget) da imagem de preview inteira."""
        vx, vy, vw, vh = self.view_rect()
        s = self.scale()
        W, H = self.get_allocated_width(), self.get_allocated_height()
        cx = W / 2 + self.pan[0]
        cy = H / 2 + self.pan[1]
        return cx - (vx + vw / 2) * s, cy - (vy + vh / 2) * s

    def percent(self):
        """Real zoom (relative to the full-resolution image)."""
        full_w = self.ed.full_size()[0]
        return self.scale() * self.pw / max(1, full_w)

    def set_percent(self, p):
        full_w = self.ed.full_size()[0]
        target = p * full_w / max(1, self.pw)
        self.zmul = max(0.05, min(40.0, target / self.base_scale()))
        self._clamp_pan()
        self.emit("zoom-changed")
        self.queue_draw()

    def fit(self):
        self.zmul = 1.0
        self.pan = [0.0, 0.0]
        self.emit("zoom-changed")
        self.queue_draw()

    def _clamp_pan(self):
        vx, vy, vw, vh = self.view_rect()
        s = self.scale()
        W, H = self.get_allocated_width(), self.get_allocated_height()
        mx = max(0.0, (vw * s - W) / 2 + 40)
        my = max(0.0, (vh * s - H) / 2 + 40)
        self.pan[0] = max(-mx, min(mx, self.pan[0]))
        self.pan[1] = max(-my, min(my, self.pan[1]))

    def set_pixbuf(self, pb):
        self.pb = pb
        self.pw, self.ph = pb.get_width(), pb.get_height()
        self.queue_draw()
        self.emit("zoom-changed")

    # coordinates
    def to_norm(self, x, y):
        ox, oy = self.origin()
        s = self.scale()
        return (x - ox) / (self.pw * s), (y - oy) / (self.ph * s)

    def crop_rect_widget(self):
        ox, oy = self.origin()
        s = self.scale()
        x0, y0, x1, y1 = self.ed.state.crop
        return (ox + x0 * self.pw * s, oy + y0 * self.ph * s, ox + x1 * self.pw * s, oy + y1 * self.ph * s)

    # drawing
    def _draw(self, w, cr):
        if self.pb is None:
            return False
        W, H = self.get_allocated_width(), self.get_allocated_height()
        s = self.scale()
        ox, oy = self.origin()
        vx, vy, vw, vh = self.view_rect()
        cr.save()
        # visible area of the image
        cr.rectangle(ox + vx * s, oy + vy * s, vw * s, vh * s)
        cr.clip()
        cr.translate(ox, oy)
        cr.scale(s, s)
        Gdk.cairo_set_source_pixbuf(cr, self.pb, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD if s < 1.0 else cairo.FILTER_BILINEAR)
        cr.paint()
        cr.restore()
        self._draw_strokes(cr, s, ox, oy)
        if self.ed.tab == "crop":
            self._draw_crop(cr, W, H)
        return False

    def _draw_strokes(self, cr, s, ox, oy):
        st = self.ed.state
        if not st.strokes and self.cur is None:
            return
        vx, vy, vw, vh = self.view_rect()
        cr.save()
        cr.rectangle(ox + vx * s, oy + vy * s, vw * s, vh * s)
        cr.clip()
        full_w, full_h = self.ed.full_size()
        ref = max(full_w, full_h)
        disp = s * self.pw / max(1, full_w)
        strokes = list(st.strokes) + ([self.cur] if self.cur else [])
        for stroke in strokes:
            pts = [(ox + u * self.pw * s, oy + v * self.ph * s) for u, v in stroke["pts"]]
            cr.new_path()
            if len(pts) == 1:
                pts = [pts[0], (pts[0][0] + 0.01, pts[0][1])]
            cr.move_to(*pts[0])
            if len(pts) == 2:
                cr.line_to(*pts[1])
            else:
                for i in range(1, len(pts) - 1):
                    cr.curve_to(pts[i][0], pts[i][1], pts[i][0], pts[i][1],
                                (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
                cr.line_to(*pts[-1])
            c = imgops._hex(stroke["color"])
            lw = imgops.stroke_width_px(stroke, ref) * disp
            if stroke["kind"] == "highlighter":
                cr.set_operator(cairo.OPERATOR_MULTIPLY)
                cr.set_line_cap(cairo.LINE_CAP_BUTT)
            else:
                cr.set_operator(cairo.OPERATOR_OVER)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_source_rgb(*c)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.set_line_width(max(1.0, lw))
            cr.stroke()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.restore()

    def _draw_crop(self, cr, W, H):
        x0, y0, x1, y1 = self.crop_rect_widget()
        ox, oy = self.origin()
        s = self.scale()
        ix0, iy0, ix1, iy1 = ox, oy, ox + self.pw * s, oy + self.ph * s
        cr.save()
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.rectangle(ix0, iy0, ix1 - ix0, iy1 - iy0)
        cr.rectangle(x0, y0, x1 - x0, y1 - y0)
        cr.set_source_rgba(0, 0, 0, 0.55)
        cr.fill()
        cr.restore()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.set_line_width(1)
        cr.rectangle(x0 + .5, y0 + .5, x1 - x0 - 1, y1 - y0 - 1)
        cr.stroke()
        if self.dragging_crop:
            cr.set_source_rgba(1, 1, 1, 0.5)
            for i in (1, 2):
                cr.move_to(x0 + (x1 - x0) * i / 3, y0)
                cr.line_to(x0 + (x1 - x0) * i / 3, y1)
                cr.move_to(x0, y0 + (y1 - y0) * i / 3)
                cr.line_to(x1, y0 + (y1 - y0) * i / 3)
            cr.set_line_width(0.8)
            cr.stroke()
        # handles
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(3)
        cr.set_line_cap(cairo.LINE_CAP_SQUARE)
        L = 16
        for (cx, cy, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            cr.move_to(cx + dx * L, cy)
            cr.line_to(cx, cy)
            cr.line_to(cx, cy + dy * L)
            cr.stroke()
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        for (hx, hy, horiz) in ((mx, y0, True), (mx, y1, True), (x0, my, False), (x1, my, False)):
            if horiz:
                cr.move_to(hx - 10, hy)
                cr.line_to(hx + 10, hy)
            else:
                cr.move_to(hx, hy - 10)
                cr.line_to(hx, hy + 10)
            cr.stroke()
        # tamanho final
        fw, fh = self.ed.full_size()
        cx0, cy0, cx1, cy1 = self.ed.state.crop
        label = "%d x %d" % (round((cx1 - cx0) * fw), round((cy1 - cy0) * fh))
        cr.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12)
        ext = cr.text_extents(label)
        bx = (x0 + x1) / 2 - ext.width / 2 - 8
        by = y1 + 10
        if by + 22 > H:
            by = y1 - 32
        ui.rounded_rect(cr, bx, by, ext.width + 16, 22, 4)
        cr.set_source_rgba(0.12, 0.12, 0.12, 0.9)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(bx + 8, by + 15)
        cr.show_text(label)

    # events
    def _hit_crop(self, x, y):
        x0, y0, x1, y1 = self.crop_rect_widget()
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        h = HANDLE
        pts = {"nw": (x0, y0), "ne": (x1, y0), "sw": (x0, y1), "se": (x1, y1),
               "n": (mx, y0), "s": (mx, y1), "w": (x0, my), "e": (x1, my)}
        for name in ("nw", "ne", "sw", "se", "n", "s", "w", "e"):
            px, py = pts[name]
            if abs(x - px) <= h and abs(y - py) <= h:
                return name
        if x0 < x < x1 and y0 < y < y1:
            return "move"
        return None

    CURSORS = {"nw": "nw-resize", "ne": "ne-resize", "sw": "sw-resize", "se": "se-resize", "n": "n-resize",
               "s": "s-resize", "w": "w-resize", "e": "e-resize", "move": "move"}

    def _set_cursor(self, name):
        win = self.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), name) if name else None)

    def _press(self, w, ev):
        self.grab_focus()
        if ev.button != 1:
            return False
        tab = self.ed.tab
        if tab == "crop":
            hit = self._hit_crop(ev.x, ev.y)
            if hit:
                self.drag = ("crop", hit, ev.x, ev.y, self.ed.state.crop)
                self.dragging_crop = True
                self.queue_draw()
                return True
        elif tab == "markup":
            tool = self.ed.tool
            if tool == "eraser":
                self.drag = ("erase",)
                self.erased = self._erase_at(ev.x, ev.y)
                return True
            u, v = self.to_norm(ev.x, ev.y)
            kind, color, size = self.ed.tool_style()
            self.cur = {"kind": kind, "color": color, "size": size, "pts": [(u, v)]}
            self.drag = ("draw",)
            self.queue_draw()
            return True
        if self.zmul > 1.001 or True:
            self.drag = ("pan", ev.x, ev.y, self.pan[0], self.pan[1])
            self._set_cursor("grabbing")
        return True

    def _release(self, w, ev):
        d = self.drag
        self.drag = None
        if not d:
            return True
        if d[0] == "crop":
            self.dragging_crop = False
            self.emit("gesture-done")
        elif d[0] == "draw" and self.cur:
            if len(self.cur["pts"]) >= 1:
                self.ed.state.strokes.append(self.cur)
            self.cur = None
            self.emit("gesture-done")
        elif d[0] == "erase":
            if self.erased:
                self.emit("gesture-done")
            self.erased = False
        self._set_cursor(None if self.ed.tab != "markup" else "crosshair")
        self.queue_draw()
        return True

    def _motion(self, w, ev):
        d = self.drag
        if d is None:
            if self.ed.tab == "crop":
                hit = self._hit_crop(ev.x, ev.y)
                self._set_cursor(self.CURSORS.get(hit))
            elif self.ed.tab == "markup":
                self._set_cursor("crosshair")
            return False
        if d[0] == "pan":
            self.pan = [d[3] + ev.x - d[1], d[4] + ev.y - d[2]]
            self._clamp_pan()
            self.queue_draw()
        elif d[0] == "draw" and self.cur is not None:
            u, v = self.to_norm(ev.x, ev.y)
            lu, lv = self.cur["pts"][-1]
            if abs(u - lu) * self.pw * self.scale() + abs(v - lv) * self.ph * self.scale() > 1.5:
                self.cur["pts"].append((u, v))
                self.queue_draw()
        elif d[0] == "erase":
            if self._erase_at(ev.x, ev.y):
                self.erased = True
        elif d[0] == "crop":
            self._drag_crop(d, ev.x, ev.y)
        return True

    def _scroll(self, w, ev):
        up = ev.direction == Gdk.ScrollDirection.UP or (ev.direction == Gdk.ScrollDirection.SMOOTH and ev.delta_y < 0)
        p = next_zoom(self.percent(), 1 if up else -1)
        self.set_percent(p)
        return True

    def _erase_at(self, x, y):
        st = self.ed.state
        ox, oy = self.origin()
        s = self.scale()
        hit = None
        for i, stroke in enumerate(st.strokes):
            pts = [(ox + u * self.pw * s, oy + v * self.ph * s) for u, v in stroke["pts"]]
            for a, b in zip(pts, pts[1:] or pts):
                if _seg_dist(x, y, a, b) < 12:
                    hit = i
                    break
            if hit is not None:
                break
        if hit is not None:
            del st.strokes[hit]
            self.queue_draw()
            return True
        return False

    def _drag_crop(self, d, x, y):
        _kind, hit, x0, y0, crop0 = d
        ox, oy = self.origin()
        s = self.scale()
        fw, fh = self.pw * s, self.ph * s
        du, dv = (x - x0) / fw, (y - y0) / fh
        cx0, cy0, cx1, cy1 = crop0
        ratio = self.ed.aspect_ratio()   # width/height in real pixels
        full_w, full_h = self.ed.full_size()
        minu = 24 / fw
        minv = 24 / fh
        if hit == "move":
            w, h = cx1 - cx0, cy1 - cy0
            nx0 = max(0.0, min(1.0 - w, cx0 + du))
            ny0 = max(0.0, min(1.0 - h, cy0 + dv))
            new = (nx0, ny0, nx0 + w, ny0 + h)
        else:
            nx0, ny0, nx1, ny1 = cx0, cy0, cx1, cy1
            if "w" in hit:
                nx0 = max(0.0, min(cx1 - minu, cx0 + du))
            if "e" in hit:
                nx1 = min(1.0, max(cx0 + minu, cx1 + du))
            if "n" in hit:
                ny0 = max(0.0, min(cy1 - minv, cy0 + dv))
            if "s" in hit:
                ny1 = min(1.0, max(cy0 + minv, cy1 + dv))
            if ratio:
                nx0, ny0, nx1, ny1 = self._apply_ratio(hit, (nx0, ny0, nx1, ny1), ratio, full_w, full_h, minu, minv)
            new = (nx0, ny0, nx1, ny1)
        self.ed.state.crop = new
        self.emit("crop-changed")
        self.queue_draw()

    def _apply_ratio(self, hit, r, ratio, fw, fh, minu, minv):
        x0, y0, x1, y1 = r
        # ratio in normalised coords: (w_n*fw)/(h_n*fh) = ratio → h_n = w_n*fw/(fh*ratio)
        k = fw / (fh * ratio)
        w = x1 - x0
        h = y1 - y0
        if len(hit) == 2:
            # corner: anchor the opposite one; decide by the dimension that changed most
            ax = x1 if "w" in hit else x0
            ay = y1 if "n" in hit else y0
            if h < w * k:
                h = w * k
            else:
                w = h / k
            # clamp inside the image
            maxw = ax if "w" in hit else 1.0 - ax
            maxh = ay if "n" in hit else 1.0 - ay
            if w > maxw:
                w, h = maxw, maxw * k
            if h > maxh:
                h, w = maxh, maxh / k
            x0, x1 = (ax - w, ax) if "w" in hit else (ax, ax + w)
            y0, y1 = (ay - h, ay) if "n" in hit else (ay, ay + h)
        elif hit in ("n", "s"):
            cx = (x0 + x1) / 2
            w = h / k
            w = min(w, 2 * min(cx, 1 - cx))
            h = w * k
            x0, x1 = cx - w / 2, cx + w / 2
            if hit == "n":
                y0 = y1 - h
            else:
                y1 = y0 + h
        else:
            cy = (y0 + y1) / 2
            h = w * k
            h = min(h, 2 * min(cy, 1 - cy))
            w = h / k
            y0, y1 = cy - h / 2, cy + h / 2
            if hit == "w":
                x0 = x1 - w
            else:
                x1 = x0 + w
        return max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)


def _seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ───────────────────────── editor ─────────────────────────

class EditorView(Gtk.Box):
    def __init__(self, window, item):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = window
        self.item = item
        self.get_style_context().add_class("viewer-bg")
        base = dialogs.open_oriented(item.path)
        self.base = normalize_mode(base)
        long_edge = max(self.base.size)
        scale = min(1.0, 2400.0 / long_edge)
        self.pscale = scale
        self.pbase = self.base if scale >= 1 else self.base.resize(
            (max(1, round(self.base.width * scale)), max(1, round(self.base.height * scale))), Image.LANCZOS)
        self.state = EditState()
        self.undo = [self.state.snapshot()]
        self.redo = []
        self.tab = "crop"
        self.tool = "pen"
        self.geo_cache = None
        self.busy = False
        self.again = False
        self.render_timer = 0
        self.tool_cfg = {
            "pen": {"color": settings.get("pen_color"), "size": 3},
            "pencil": {"color": "#ffffff", "size": 2},
            "highlighter": {"color": settings.get("highlighter_color"), "size": 3},
        }
        self.updating = False
        self._build()
        self.show_all()
        self.set_tab("crop", first=True)
        self.schedule_render(geo=True)
        threading.Thread(target=self._make_filter_thumbs, daemon=True).start()
        self.connect("key-press-event", self._key)
        self.set_can_focus(True)
        self.win.title_lb.set_text(item.name)

    # utilidades
    def full_size(self):
        w, h = self.base.size
        if self.state.ops.count("rot") % 2:
            w, h = h, w
        return w, h

    def aspect_ratio(self):
        name = self.state.aspect_name
        if name == "Free":
            return None
        if name == "Original":
            w, h = self.full_size()
            return w / h
        for n, r in imgops.ASPECTS:
            if n == name:
                return r
        return None

    # ── construction ──
    def _build(self):
        row = Gtk.Box()
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_top(4)
        row.set_margin_bottom(6)
        self.pack_start(row, False, False, 0)
        # left card
        card = Gtk.Box(spacing=2)
        card.get_style_context().add_class("editor-card")
        card.set_valign(Gtk.Align.CENTER)
        self.b_zin = ui.icon_button("zoom-in", _("Zoom in"), classes=["flat-icon"], size=18, on_click=lambda: self._zoom(1))
        self.b_zout = ui.icon_button("zoom-out", _("Zoom out"), classes=["flat-icon"], size=18, on_click=lambda: self._zoom(-1))
        self.b_actual = ui.icon_button("actual", _("Actual size"), classes=["flat-icon"], size=18, on_click=self._actual)
        self.lb_zoom = ui.label("100%", xalign=0.5)
        self.lb_zoom.set_size_request(48, -1)
        self.b_restore = ui.icon_button(label=_("Reset"), on_click=self.restore_all)
        self.b_undo = ui.icon_button("undo", _("Undo (Ctrl+Z)"), classes=["flat-icon"], size=18, on_click=self.do_undo)
        self.b_redo = ui.icon_button("redo", _("Redo (Ctrl+Y)"), classes=["flat-icon"], size=18, on_click=self.do_redo)
        for w in (self.b_zin, self.b_zout, self.b_actual, self.lb_zoom, ui.separator_v(), self.b_restore, self.b_undo,
                  self.b_redo):
            card.pack_start(w, False, False, 0)
        row.pack_start(card, False, False, 0)
        # tabs
        tabs = Gtk.Box(spacing=8)
        self.tab_btns = {}
        for name, icon, tip in (("crop", "crop", _("Crop, rotate and flip the image.")),
                                ("adjust", "brightness", _("Adjust the light and color values of the image.")),
                                ("filters", "wand", _("Apply a filter to the image.")),
                                ("markup", "pen", _("Add annotations to the image."))):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            b = ui.icon_button(icon, tip, classes=["flat-icon"], size=20)
            b.set_size_request(40, 36)
            b.connect("clicked", lambda _b, n=name: self.set_tab(n))
            bar = Gtk.Box()
            bar.get_style_context().add_class("editor-tab-bar")
            bar.set_halign(Gtk.Align.CENTER)
            bar.set_size_request(16, 3)
            col.pack_start(b, False, False, 0)
            col.pack_start(bar, False, False, 0)
            tabs.pack_start(col, False, False, 0)
            self.tab_btns[name] = (b, bar)
        row.set_center_widget(tabs)
        # right side
        right = Gtk.Box(spacing=8)
        right.set_valign(Gtk.Align.CENTER)
        self.save_btn = ui.icon_button(label=_("Save options"), classes=["accent"], icon_after="chev-down")
        self.save_btn.icon_after.set_role("onaccent")
        self.save_btn.set_size_request(200, 32)
        ui.menu_button(self.save_btn, self._build_save_menu, min_width=260)
        cancel = ui.icon_button(label=_("Cancel"), classes=["subtle"], on_click=self.cancel)
        cancel.set_size_request(100, 32)
        right.pack_start(self.save_btn, False, False, 0)
        right.pack_start(cancel, False, False, 0)
        row.pack_end(right, False, False, 0)

        # body
        body = Gtk.Box()
        self.pack_start(body, True, True, 0)
        self.canvas = EditCanvas(self)
        self.canvas.connect("zoom-changed", lambda c: self._sync_zoom())
        self.canvas.connect("crop-changed", lambda c: self._on_crop_changed())
        self.canvas.connect("gesture-done", lambda c: self.push_undo())
        body.pack_start(self.canvas, True, True, 0)
        # right panel
        self.panel_rev = Gtk.Revealer()
        self.panel_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.panel_rev.set_transition_duration(180)
        self.panel_stack = Gtk.Stack()
        self.panel_stack.set_size_request(340, -1)
        panel_wrap = Gtk.Box()
        panel_wrap.set_margin_end(16)
        panel_wrap.set_margin_bottom(8)
        panel_wrap.set_margin_start(4)
        panel_wrap.get_style_context().add_class("editor-panel")
        panel_wrap.pack_start(self.panel_stack, True, True, 0)
        self.panel_rev.add(panel_wrap)
        body.pack_start(self.panel_rev, False, False, 0)
        self._build_adjust_panel()
        self._build_filter_panel()
        # bottom: per-tab controls
        self.bottom = Gtk.Stack()
        self.bottom.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.bottom.set_transition_duration(120)
        self.pack_start(self.bottom, False, False, 0)
        self.bottom.add_named(Gtk.Box(), "none")
        self._build_crop_controls()
        self._build_aspect_row()
        self._build_markup_bar()

    # ── abas ──
    def set_tab(self, name, first=False):
        self.tab = name
        for n, (b, bar) in self.tab_btns.items():
            bar.set_opacity(1.0 if n == name else 0.0)
            b.get_style_context().remove_class("sel-on")
            if n == name:
                b.get_style_context().add_class("sel-on")
        self.panel_rev.set_reveal_child(name in ("adjust", "filters"))
        if name == "adjust":
            self.panel_stack.set_visible_child_name("adjust")
        elif name == "filters":
            self.panel_stack.set_visible_child_name("filters")
        self.bottom.set_visible_child_name({"crop": "crop", "markup": "markup"}.get(name, "none"))
        win = self.canvas.get_window()
        if win:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "crosshair") if name == "markup" else None)
        self.canvas.fit()
        self.canvas.queue_draw()
        self._sync_buttons()

    # ── render ──
    def schedule_render(self, geo=False):
        if geo:
            self.geo_cache = None
        if self.render_timer:
            return
        self.render_timer = GLib.timeout_add(45, self._kick)

    def _kick(self):
        self.render_timer = 0
        if self.busy:
            self.again = True
            return False
        self.busy = True
        st = EditState()
        st.restore(self.state.snapshot())
        threading.Thread(target=self._render_thread, args=(st,), daemon=True).start()
        return False

    def _render_thread(self, st):
        try:
            key = (tuple(st.ops), round(st.angle, 2))
            if self.geo_cache is None or self.geo_cache[0] != key:
                self.geo_cache = (key, imgops.geometry(self.pbase, st))
            im = imgops.tone(self.geo_cache[1], st)
            GLib.idle_add(self._rendered, im)
        except Exception as exc:  # noqa: BLE001
            print("render error:", exc)
            GLib.idle_add(self._rendered, None)

    def _rendered(self, im):
        self.busy = False
        if im is not None:
            first = self.canvas.pb is None
            self.canvas.set_pixbuf(pil_to_pixbuf(im))
            if first:
                self.canvas.fit()
        if self.again:
            self.again = False
            self.schedule_render()
        return False

    # ── undo/redo ──
    def push_undo(self):
        snap = self.state.snapshot()
        if snap != self.undo[-1]:
            self.undo.append(snap)
            self.redo = []
        self._sync_buttons()

    def do_undo(self):
        if len(self.undo) > 1:
            self.redo.append(self.undo.pop())
            self._apply_snapshot(self.undo[-1])

    def do_redo(self):
        if self.redo:
            snap = self.redo.pop()
            self.undo.append(snap)
            self._apply_snapshot(snap)

    def _apply_snapshot(self, snap):
        self.state.restore(snap)
        self._sync_controls()
        self.schedule_render(geo=True)
        self.canvas.queue_draw()
        self._sync_buttons()

    def restore_all(self):
        self.state = EditState()
        self.push_undo()
        self._sync_controls()
        self.schedule_render(geo=True)
        self.canvas.fit()
        self._sync_buttons()

    def _sync_buttons(self):
        self.b_undo.set_sensitive(len(self.undo) > 1)
        self.b_redo.set_sensitive(bool(self.redo))
        dirty = not self.state.is_default()
        self.b_restore.set_sensitive(dirty)
        self.save_dirty = dirty

    def _sync_controls(self):
        self.updating = True
        for k, sc in self.adjust_scales.items():
            sc.set_value(self.state.adjust[k])
            self.adjust_vals[k].set_text(str(int(self.state.adjust[k])))
        self.ruler.set_value(self.state.angle)
        self.lb_angle.set_text("%s °" % self._fmt_angle(self.state.angle))
        self._sync_filters()
        self.auto_btn.get_style_context().remove_class("sel-on")
        if self.state.auto:
            self.auto_btn.get_style_context().add_class("sel-on")
        self.lb_aspect.set_text(_(self.state.aspect_name))
        self.updating = False

    # ── zoom ──
    def _zoom(self, d):
        self.canvas.set_percent(next_zoom(self.canvas.percent(), d))

    def _actual(self):
        self.canvas.set_percent(1.0)

    def _sync_zoom(self):
        self.lb_zoom.set_text("%d%%" % round(self.canvas.percent() * 100))

    # ───────────────────────── Cortar ─────────────────────────
    def _build_crop_controls(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_bottom(10)
        self.lb_angle = ui.label("0 °", xalign=0.5)
        box.pack_start(self.lb_angle, False, False, 0)
        self.ruler = Ruler()
        self.ruler.set_size_request(680, 26)
        self.ruler.set_halign(Gtk.Align.CENTER)
        self.ruler.connect("changed", self._on_angle)
        self.ruler.connect("released", lambda r: self.push_undo())
        box.pack_start(self.ruler, False, False, 0)
        row = Gtk.Box()
        row.set_size_request(700, -1)
        row.set_halign(Gtk.Align.CENTER)
        left = Gtk.Box(spacing=8)
        left.pack_start(ui.icon_button("rotate-left", _("Rotate counterclockwise"), classes=["flat-icon"],
                                       on_click=lambda: self._rot(3)), False, False, 0)
        left.pack_start(ui.icon_button("rotate-right", _("Rotate clockwise"), classes=["flat-icon"],
                                       on_click=lambda: self._rot(1)), False, False, 0)
        row.pack_start(left, False, False, 0)
        self.aspect_btn = ui.icon_button("aspect", _("Free aspect ratio"), classes=[])
        self.lb_aspect = ui.label(_("Free"))
        self.aspect_btn.get_children()[0].pack_start(self.lb_aspect, False, False, 0)
        self.aspect_btn.get_children()[0].show_all()
        self.aspect_btn.connect("clicked", lambda b: self.bottom.set_visible_child_name("aspect"))
        row.set_center_widget(self.aspect_btn)
        right = Gtk.Box(spacing=8)
        right.pack_start(ui.icon_button("flip-h", _("Flip image horizontally"), classes=["flat-icon"],
                                        on_click=lambda: self._flip("fh")), False, False, 0)
        right.pack_start(ui.icon_button("flip-v", _("Flip image vertically"), classes=["flat-icon"],
                                        on_click=lambda: self._flip("fv")), False, False, 0)
        row.pack_end(right, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.bottom.add_named(box, "crop")

    @staticmethod
    def _fmt_angle(v):
        return ("%.1f" % v).rstrip("0").rstrip(".") if abs(v - round(v)) > 0.04 else "%d" % round(v)

    def _on_angle(self, r, v):
        if self.updating:
            return
        self.state.angle = v
        self.lb_angle.set_text("%s °" % self._fmt_angle(v))
        self.schedule_render(geo=True)

    def _rot(self, n):
        for _i in range(n):
            self._geo_op("rot")
        self.push_undo()

    def _flip(self, op):
        self._geo_op(op)
        self.push_undo()

    def _geo_op(self, op):
        st = self.state
        st.ops.append(op)
        for s in st.strokes:
            s["pts"] = [imgops.transform_point_for_op(u, v, op) for u, v in s["pts"]]
        x0, y0, x1, y1 = st.crop
        a = imgops.transform_point_for_op(x0, y0, op)
        b = imgops.transform_point_for_op(x1, y1, op)
        st.crop = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        if op == "rot" and st.aspect_name not in ("Free", "Original"):
            pass
        self.schedule_render(geo=True)
        self.canvas.fit()

    def _on_crop_changed(self):
        self.canvas.queue_draw()

    def _build_aspect_row(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_bottom(10)
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sc.set_halign(Gtk.Align.CENTER)
        sc.set_size_request(760, 74)
        row = Gtk.Box(spacing=4)
        for name, ratio in imgops.ASPECTS:
            b = Gtk.Button()
            b.set_can_focus(False)
            b.get_style_context().add_class("fbtn")
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.set_halign(Gtk.Align.CENTER)
            icon_box = Gtk.DrawingArea()
            icon_box.set_size_request(24, 24)
            icon_box.connect("draw", self._draw_aspect_icon, name, ratio)
            col.pack_start(icon_box, False, False, 0)
            col.pack_start(ui.label(_(name), ["filter-name"], xalign=0.5), False, False, 0)
            b.add(col)
            b.set_size_request(60, 62)
            b.connect("clicked", lambda _b, n=name: self.set_aspect(n))
            row.pack_start(b, False, False, 0)
        sc.add(row)
        outer.pack_start(sc, False, False, 0)
        done = ui.icon_button(label=_("Done"), on_click=lambda: self.bottom.set_visible_child_name("crop"))
        done.set_halign(Gtk.Align.CENTER)
        outer.pack_start(done, False, False, 0)
        self.bottom.add_named(outer, "aspect")

    def _draw_aspect_icon(self, w, cr, name, ratio):
        if name == "Original":
            fw, fh = self.full_size()
            ratio = fw / fh
        if ratio is None:
            ratio = 1.0
        W = 22
        if ratio >= 1:
            bw, bh = W, W / ratio
        else:
            bw, bh = W * ratio, W
        bw, bh = max(8, bw * 0.8), max(8, bh * 0.8)
        x, y = (24 - bw) / 2, (24 - bh) / 2
        ui.rounded_rect(cr, x, y, bw, bh, 3)
        theme.set_source(cr, "muted")
        cr.set_line_width(1.5)
        cr.stroke()
        return False

    def set_aspect(self, name):
        self.state.aspect_name = name
        self.lb_aspect.set_text(_(name))
        r = self.aspect_ratio()
        if r:
            fw, fh = self.full_size()
            x0, y0, x1, y1 = self.state.crop
            cw, ch = (x1 - x0) * fw, (y1 - y0) * fh
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            # largest rectangle with the ratio inside the whole image, centred on the current crop
            nw = fw
            nh = nw / r
            if nh > fh:
                nh = fh
                nw = nh * r
            u, v = nw / fw, nh / fh
            ax = max(u / 2, min(1 - u / 2, cx))
            ay = max(v / 2, min(1 - v / 2, cy))
            self.state.crop = (ax - u / 2, ay - v / 2, ax + u / 2, ay + v / 2)
        self.canvas.queue_draw()
        self.push_undo()
        self.bottom.set_visible_child_name("crop")

    # ───────────────────────── Ajustar ─────────────────────────
    def _build_adjust_panel(self):
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(16)
        self.adjust_scales = {}
        self.adjust_vals = {}
        section = None
        for key, label, icon, sec in imgops.ADJUSTMENTS:
            if sec != section:
                section = sec
                box.pack_start(ui.label(_(sec), ["section-title"]), False, False, 0)
            head = Gtk.Box(spacing=8)
            head.pack_start(icons.Icon(icon, 16, "fg"), False, False, 0)
            head.pack_start(ui.label(_(label)), True, True, 0)
            val = ui.label("0", ["slider-val"], xalign=1.0)
            head.pack_end(val, False, False, 0)
            box.pack_start(head, False, False, 0)
            sc_ = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 1)
            sc_.set_draw_value(False)
            sc_.set_value(0)
            sc_.get_style_context().add_class("fscale")
            sc_.get_style_context().add_class("on-card")
            sc_.set_has_origin(False)
            sc_.connect("value-changed", self._on_adjust, key)
            sc_.connect("button-release-event", lambda *_: (self.push_undo(), False)[1])
            sc_.connect("key-release-event", lambda *_: (self.push_undo(), False)[1])
            sc_.connect("button-press-event", self._maybe_reset, key)
            sc_.set_margin_bottom(10)
            box.pack_start(sc_, False, False, 0)
            self.adjust_scales[key] = sc_
            self.adjust_vals[key] = val
        sc.add(box)
        self.panel_stack.add_named(sc, "adjust")

    def _maybe_reset(self, sc, ev, key):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            sc.set_value(0)
            self.push_undo()
            return True
        return False

    def _on_adjust(self, sc, key):
        if self.updating:
            return
        v = int(round(sc.get_value()))
        self.state.adjust[key] = v
        self.adjust_vals[key].set_text(str(v))
        self.schedule_render()

    # ───────────────────────── Filtros ─────────────────────────
    def _build_filter_panel(self):
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(16)
        self.auto_btn = ui.icon_button("sparkle", None, label=_("Auto enhance"), classes=["subtle"])
        self.auto_btn.connect("clicked", self._toggle_auto)
        box.pack_start(self.auto_btn, False, False, 0)
        grid = Gtk.Grid(column_spacing=8, row_spacing=10)
        grid.set_column_homogeneous(True)
        self.filter_tiles = {}
        for n, name in enumerate(imgops.FILTERS):
            b = Gtk.Button()
            b.set_can_focus(False)
            b.get_style_context().add_class("fbtn")
            b.set_size_request(-1, 120)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            img = Gtk.Image()
            img.set_size_request(94, 94)
            lb = ui.label(_(name), ["filter-name"], xalign=0.5, wrap=True)
            lb.set_justify(Gtk.Justification.CENTER)
            col.pack_start(img, False, False, 0)
            col.pack_start(lb, False, False, 0)
            b.add(col)
            b.connect("clicked", lambda _b, nm=name: self.set_filter(nm))
            grid.attach(b, n % 3, n // 3, 1, 1)
            self.filter_tiles[name] = (b, img, lb)
        box.pack_start(grid, False, False, 0)
        self.int_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.int_box.pack_start(ui.label(_("Filter intensity"), ["section-title"]), False, False, 0)
        self.int_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.int_scale.set_draw_value(True)
        self.int_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.int_scale.set_value(100)
        self.int_scale.get_style_context().add_class("fscale")
        self.int_scale.get_style_context().add_class("on-card")
        self.int_scale.connect("value-changed", self._on_intensity)
        self.int_scale.connect("button-release-event", lambda *_: (self.push_undo(), False)[1])
        self.int_box.pack_start(self.int_scale, False, False, 0)
        box.pack_start(self.int_box, False, False, 0)
        sc.add(box)
        self.panel_stack.add_named(sc, "filters")
        self._sync_filters()

    def _make_filter_thumbs(self):
        src = self.pbase.copy()
        src.thumbnail((200, 200))
        w, h = src.size
        s = min(w, h)
        thumb = src.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((94, 94), Image.LANCZOS)
        thumb = thumb.convert("RGB")
        for name in imgops.FILTERS:
            out = imgops.apply_filter(thumb, name)
            GLib.idle_add(self._set_thumb, name, pil_to_pixbuf(out))

    def _set_thumb(self, name, pb):
        tile = self.filter_tiles.get(name)
        if tile:
            tile[1].set_from_pixbuf(pb)
        return False

    def set_filter(self, name):
        self.state.filter = name
        self.state.intensity = 100
        self.int_scale.set_value(100)
        self._sync_filters()
        self.schedule_render()
        self.push_undo()

    def _sync_filters(self):
        for name, (b, img, lb) in self.filter_tiles.items():
            on = name == self.state.filter
            ctx = b.get_style_context()
            (ctx.add_class if on else ctx.remove_class)("sel-on")
            lctx = lb.get_style_context()
            (lctx.add_class if on else lctx.remove_class)("on")
        self.int_box.set_visible(self.state.filter != "Original")
        self.int_box.set_no_show_all(self.state.filter == "Original")
        if self.state.filter != "Original":
            self.int_box.show_all()
        self.int_scale.set_value(self.state.intensity)

    def _on_intensity(self, sc):
        if self.updating:
            return
        self.state.intensity = int(sc.get_value())
        self.schedule_render()

    def _toggle_auto(self, b):
        self.state.auto = not self.state.auto
        ctx = b.get_style_context()
        (ctx.add_class if self.state.auto else ctx.remove_class)("sel-on")
        self.schedule_render()
        self.push_undo()

    # ───────────────────────── Markup ─────────────────────────
    def _build_markup_bar(self):
        wrap = Gtk.Box()
        wrap.set_halign(Gtk.Align.CENTER)
        wrap.set_margin_bottom(14)
        bar = Gtk.Box(spacing=6)
        bar.get_style_context().add_class("editor-panel")
        bar.set_border_width(6)
        self.tool_btns = {}
        for name, icon, tip in (("pen", "pen", _("Pen")), ("pencil", "pencil", _("Pencil")),
                                ("highlighter", "highlighter", _("Highlighter")), ("eraser", "eraser", _("Eraser"))):
            b = ui.icon_button(icon, tip, classes=["flat-icon"], size=22)
            b.set_size_request(48, 40)
            b.connect("clicked", lambda _b, n=name: self._pick_tool(n))
            bar.pack_start(b, False, False, 0)
            self.tool_btns[name] = b
        self.clear_btn = ui.icon_button("clear-all", _("Clear all markup"), classes=["flat-icon"], size=22,
                                        on_click=self.clear_strokes)
        self.clear_btn.set_size_request(48, 40)
        bar.pack_start(self.clear_btn, False, False, 0)
        wrap.pack_start(bar, False, False, 0)
        self.bottom.add_named(wrap, "markup")
        self._sync_tools()

    def tool_style(self):
        cfg = self.tool_cfg.get(self.tool)
        return self.tool, cfg["color"], cfg["size"]

    def _pick_tool(self, name):
        if name == self.tool and name != "eraser":
            self._tool_flyout(name)
            return
        self.tool = name
        self._sync_tools()

    def _sync_tools(self):
        for n, b in self.tool_btns.items():
            ctx = b.get_style_context()
            (ctx.add_class if n == self.tool else ctx.remove_class)("sel-on")

    def _tool_flyout(self, name):
        cfg = self.tool_cfg[name]
        pop = ui.FlyoutMenu(self.tool_btns[name], Gtk.PositionType.TOP, 300)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(10)
        preview = Gtk.DrawingArea()
        preview.set_size_request(280, 22)

        def draw_prev(w, cr):
            c = imgops._hex(cfg["color"])
            cr.set_source_rgb(*c)
            cr.set_line_cap(cairo.LINE_CAP_BUTT if name == "highlighter" else cairo.LINE_CAP_ROUND)
            cr.set_line_width(cfg["size"] * (4 if name == "highlighter" else 1.3) + 1)
            cr.move_to(12, 11)
            cr.line_to(268, 11)
            cr.stroke()
            return False
        preview.connect("draw", draw_prev)
        box.pack_start(preview, False, False, 0)
        srow = Gtk.Box(spacing=10)
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 10, 1)
        sc.set_draw_value(False)
        sc.set_value(cfg["size"])
        sc.get_style_context().add_class("fscale")
        sc.get_style_context().add_class("on-card")
        sv = ui.label(str(cfg["size"]))

        def size_changed(s):
            cfg["size"] = int(s.get_value())
            sv.set_text(str(cfg["size"]))
            preview.queue_draw()
        sc.connect("value-changed", size_changed)
        srow.pack_start(sc, True, True, 0)
        srow.pack_start(sv, False, False, 0)
        box.pack_start(srow, False, False, 0)
        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        grid.set_halign(Gtk.Align.CENTER)
        for i, col in enumerate(imgops.PEN_COLORS):
            sw = Gtk.Button()
            sw.set_can_focus(False)
            sw.get_style_context().add_class("fbtn")
            area = Gtk.DrawingArea()
            area.set_size_request(24, 24)
            area.connect("draw", self._draw_swatch, col, cfg)
            sw.add(area)
            sw.set_size_request(32, 32)

            def pick(_b, c=col):
                cfg["color"] = c
                if name == "pen":
                    settings.set("pen_color", c)
                elif name == "highlighter":
                    settings.set("highlighter_color", c)
                preview.queue_draw()
                for ch in grid.get_children():
                    ch.queue_draw()
            sw.connect("clicked", pick)
            grid.attach(sw, i % 8, i // 8, 1, 1)
        box.pack_start(grid, False, False, 0)
        pop.add_widget(box)
        pop.popup()

    def _draw_swatch(self, w, cr, col, cfg):
        cr.arc(12, 12, 10, 0, 2 * math.pi)
        cr.set_source_rgb(*imgops._hex(col))
        cr.fill_preserve()
        if col.lower() in ("#000000",):
            theme.set_source(cr, "faint")
            cr.set_line_width(1)
            cr.stroke_preserve()
        cr.new_path()
        if cfg["color"].lower() == col.lower():
            cr.arc(12, 12, 11.5, 0, 2 * math.pi)
            theme.set_source(cr, "fg")
            cr.set_line_width(2)
            cr.stroke()
        return False

    def clear_strokes(self):
        if self.state.strokes:
            self.state.strokes = []
            self.canvas.queue_draw()
            self.push_undo()

    # ───────────────────────── salvar ─────────────────────────
    def _build_save_menu(self, m):
        m.add_item(_("Save as copy"), self.save_copy)
        m.add_item(_("Save"), self.save_overwrite, sensitive=not self.state.is_default())
        m.add_item(_("Copy to clipboard"), self.copy_clipboard)

    def _render_final(self):
        return imgops.render_final(self.base, self.state)

    def _write(self, path):
        im = self._render_final()
        dialogs.pil_save(im, path)

    def save_copy(self):
        stem = os.path.splitext(self.item.name)[0]
        name = _("%s (edited)%s") % (stem, self.item.ext)
        dest_dir = self.item.folder

        def go(path):
            self._do_save(path, copy=True)
        dialogs.file_chooser_save(self.win, name, dest_dir, go)

    def save_overwrite(self):
        self._do_save(self.item.path, copy=False)

    def _do_save(self, path, copy):
        ui.toast(self.win.overlay, _("Saving…"), 900)

        def work():
            try:
                self._write(path)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._saved, None, str(exc))
                return
            GLib.idle_add(self._saved, path, None)
        threading.Thread(target=work, daemon=True).start()

    def _saved(self, path, err):
        if err:
            ui.toast(self.win.overlay, _("Could not save: %s") % err)
        else:
            ui.toast(self.win.overlay, _("Image saved: %s") % os.path.basename(path))
            self.win.close_editor(saved_path=path)
        return False

    def copy_clipboard(self):
        try:
            actions.copy_image_to_clipboard(pil_to_pixbuf(self._render_final()))
            ui.toast(self.win.overlay, _("Image copied"))
        except Exception as exc:  # noqa: BLE001
            ui.toast(self.win.overlay, _("Copy failed: %s") % exc)

    def cancel(self):
        if self.state.is_default():
            self.win.close_editor()
            return

        def discard():
            self.win.close_editor()
        ui.confirm(self.win.overlay, _("Discard changes?"), _("Changes made to this image will be lost."),
                   _("Discard"), _("Keep editing"), lambda _x: discard())

    def _key(self, w, ev):
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if ui.dialog_open():
            return False
        if ev.keyval == Gdk.KEY_Escape:
            if ui.popover_recent():
                return True
            if self.bottom.get_visible_child_name() == "aspect":
                self.bottom.set_visible_child_name("crop")
            else:
                self.cancel()
            return True
        if ctrl and ev.keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            self.do_undo()
            return True
        if ctrl and ev.keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self.do_redo()
            return True
        return False

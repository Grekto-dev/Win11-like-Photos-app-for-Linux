# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Viewer image canvas: smooth zoom, drag to pan, transitions and animated GIF."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GLib, GObject, GdkPixbuf, Gtk  # noqa: E402

import cairo  # noqa: E402

from . import settings, ui

MIN_ZOOM = 0.01
MAX_ZOOM = 8.0


def next_zoom(z, direction):
    """Step of the +/− buttons: 5/10/25/50 % depending on the range (measured on the Windows Photos app)."""
    pct = z * 100.0
    eps = 0.01
    if direction > 0:
        step = 5 if pct < 50 - eps else 10 if pct < 200 - eps else 25 if pct < 600 - eps else 50
        nxt = (math.floor(pct / step + eps) + 1) * step
        step2 = 5 if nxt < 50 else 10 if nxt < 200 else 25 if nxt < 600 else 50
        if step2 != step:
            nxt = (math.floor(pct / step2 + eps) + 1) * step2
    else:
        step = 5 if pct <= 50 + eps else 10 if pct <= 200 + eps else 25 if pct <= 600 + eps else 50
        nxt = (math.ceil(pct / step - eps) - 1) * step
    return max(MIN_ZOOM, min(MAX_ZOOM, nxt / 100.0))


class ImageCanvas(Gtk.DrawingArea):
    __gsignals__ = {
        "zoom-changed": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "navigate": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "double-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "activity": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.pb = None            # pixbuf completo
        self.ph = None            # placeholder (thumbnail) carrying the true iw/ih
        self.iw = 0
        self.ih = 0
        self.zoom = 1.0
        self.off_x = 0.0
        self.off_y = 0.0
        self.fit_mode = 'default'  # 'default' | 'fit' | None (free): follows the window size on resize
        self.alpha = 1.0
        self.slide = 0.0
        self.pop = 1.0
        self.anim = None
        self.zanim = None
        self.mips = {}
        self.drag = None
        self.gif_iter = None
        self.gif_id = 0
        self.gif_pb = None
        self.old = None
        self.ztarget = 1.0
        self.force_fit = False
        self.last_size = (0, 0)
        self.connect("draw", self._draw)
        self.connect("size-allocate", self._on_alloc)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("motion-notify-event", self._motion)
        self.connect("scroll-event", self._scroll)
        self.connect("destroy", lambda *_: self._stop_gif())

    # ── content ──
    def clear(self):
        self.pb = None
        self.ph = None
        self.gif_iter = None
        self._stop_gif()
        self.mips = {}
        self.queue_draw()

    def show_placeholder(self, ph, iw, ih):
        self.ph = ph
        self.pb = None
        self.mips = {}
        self.iw, self.ih = iw, ih
        self._reset_view()

    def set_pixbuf(self, pb, animation=None, transition=None):
        """Define a imagem completa. transition: None | 'fade' | 'next' | 'prev' | 'open'."""
        self._stop_gif()
        self.gif_iter = None
        self.old = None
        if transition == 'cross' and (self.pb is not None):
            self.old = (self.pb, self.iw, self.ih, self.zoom, self.off_x, self.off_y)
        first = self.pb is None and self.ph is None
        keep_view = self.ph is not None and self.pb is None and not self.fit_mode
        self.pb = pb
        self.ph = None
        self.mips = {}
        self.iw, self.ih = pb.get_width(), pb.get_height()
        if animation is not None and not animation.is_static_image():
            self.gif_iter = animation.get_iter(None)
            self._gif_step()
        if not keep_view:
            self._reset_view()
        self._start_transition(transition)
        self.queue_draw()

    def _start_transition(self, kind):
        if self.anim:
            self.anim.cancel()
        self.slide = 0.0
        self.pop = 1.0
        self.alpha = 1.0
        if not kind:
            return
        direction = {"next": 1, "prev": -1}.get(kind, 0)

        def step(t):
            self.alpha = t
            self.slide = (1 - t) * 36 * direction
            self.pop = 1.0 - (1 - t) * (0.06 if kind == "open" else 0.0)
            self.queue_draw()

        def done():
            self.old = None
            self.queue_draw()
        self.alpha = 0.0
        dur = 260 if kind == "open" else 700 if kind == "cross" else 200
        self.anim = ui.Anim(self, dur, step, done=done)

    def _stop_gif(self):
        if self.gif_id:
            GLib.source_remove(self.gif_id)
            self.gif_id = 0

    def _gif_step(self):
        it = self.gif_iter
        if it is None:
            return False
        self.gif_pb = it.get_pixbuf()
        self.queue_draw()
        delay = it.get_delay_time()
        if delay < 0:
            return False
        self.gif_id = GLib.timeout_add(max(20, delay), self._gif_tick)
        return False

    def _gif_tick(self):
        self.gif_id = 0
        if self.gif_iter is None:
            return False
        self.gif_iter.advance(None)
        self._gif_step()
        return False

    # ── zoom/position ──
    def view_size(self):
        return self.get_allocated_width(), self.get_allocated_height()

    def fit_zoom(self):
        w, h = self.view_size()
        if self.iw <= 0 or self.ih <= 0 or w <= 0 or h <= 0:
            return 1.0
        return max(MIN_ZOOM, min(MAX_ZOOM, min(w / self.iw, h / self.ih)))

    def default_zoom(self):
        fz = self.fit_zoom()
        if self.force_fit or settings.get("zoom_pref") == "fit":
            return fz
        return min(1.0, fz)

    def is_fit(self):
        return abs(self.zoom - self.fit_zoom()) < 0.002

    def _reset_view(self):
        if self.zanim:
            self.zanim.cancel()
        self.fit_mode = 'default'
        self.zoom = self.default_zoom()
        self.off_x = self.off_y = 0.0
        self.emit("zoom-changed", self.zoom)
        self.queue_draw()

    def _clamp(self, ox, oy, z):
        w, h = self.view_size()
        mx = max(0.0, (self.iw * z - w) / 2)
        my = max(0.0, (self.ih * z - h) / 2)
        return max(-mx, min(mx, ox)), max(-my, min(my, oy))

    def can_pan(self):
        w, h = self.view_size()
        return self.iw * self.zoom > w + 0.5 or self.ih * self.zoom > h + 0.5

    def zoom_to(self, z, px=None, py=None, animate=True, mode=None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        w, h = self.view_size()
        if px is None:
            px, py = w / 2, h / 2
        z1 = self.zoom
        ox = px - w / 2 - (px - w / 2 - self.off_x) * z / z1 if z1 else 0
        oy = py - h / 2 - (py - h / 2 - self.off_y) * z / z1 if z1 else 0
        ox, oy = self._clamp(ox, oy, z)
        self.fit_mode = mode
        self.ztarget = z
        if self.zanim:
            self.zanim.cancel()
        if not animate or self.pb is None and self.ph is None:
            self.zoom, self.off_x, self.off_y = z, ox, oy
            self.emit("zoom-changed", z)
            self.queue_draw()
            return
        z0, x0, y0 = self.zoom, self.off_x, self.off_y

        def step(t):
            self.zoom = z0 + (z - z0) * t
            self.off_x = x0 + (ox - x0) * t
            self.off_y = y0 + (oy - y0) * t
            self.emit("zoom-changed", self.zoom)
            self.queue_draw()
        self.zanim = ui.Anim(self, 140, step)

    def fit(self, animate=True):
        self.zoom_to(self.fit_zoom(), animate=animate, mode='fit')

    def actual(self, animate=True):
        self.zoom_to(1.0, animate=animate)

    def toggle_fit(self):
        if self.is_fit():
            self.actual()
        else:
            self.fit()

    def zoom_step(self, direction, px=None, py=None):
        base = self.ztarget if (self.zanim and not self.zanim.cancelled) else self.zoom
        self.zoom_to(next_zoom(base, direction), px, py)

    def _on_alloc(self, w, alloc):
        size = (alloc.width, alloc.height)
        if size != self.last_size:
            self.last_size = size
            if self.fit_mode and (self.pb or self.ph):
                self.zoom = self.fit_zoom() if self.fit_mode == 'fit' else self.default_zoom()
                self.off_x = self.off_y = 0.0
                self.emit("zoom-changed", self.zoom)
            else:
                self.off_x, self.off_y = self._clamp(self.off_x, self.off_y, self.zoom)
            self.queue_draw()

    # ── desenho ──
    def _mip_for(self, z):
        """Picks a pre-shrunk pixbuf (powers of 1/2) for zoom < 0.5."""
        pb = self.gif_pb if (self.gif_iter is not None and self.gif_pb is not None) else self.pb
        if pb is None:
            return None, 1.0
        if z >= 0.5 or self.gif_iter is not None:
            return pb, 1.0
        k = int(math.floor(math.log2(1.0 / z)))
        k = max(1, min(k, 6))
        level = 0.5 ** k
        m = self.mips.get(k)
        if m is None:
            if len(self.mips) == 0 and (pb.get_width() * pb.get_height() > 20_000_000):
                GLib.idle_add(self._build_mip, k)
                return pb, 1.0
            m = self._build_mip(k, True)
        return m, level

    def _build_mip(self, k, ret=False):
        if k in self.mips or self.pb is None:
            return self.mips.get(k) if ret else False
        src = self.pb
        w = max(1, int(src.get_width() * 0.5 ** k))
        h = max(1, int(src.get_height() * 0.5 ** k))
        m = src.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        self.mips[k] = m
        if not ret:
            self.queue_draw()
        return m if ret else False

    def _draw(self, w, cr):
        W, H = self.view_size()
        if self.pb is None and self.ph is None:
            return False
        if self.old is not None:
            opb, oiw, oih, oz, oox, ooy = self.old
            cr.save()
            cr.translate(W / 2 + oox, H / 2 + ooy)
            cr.scale(oz, oz)
            cr.translate(-oiw / 2, -oih / 2)
            Gdk.cairo_set_source_pixbuf(cr, opb, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint_with_alpha(1.0 - self.alpha)
            cr.restore()
        z = self.zoom
        cx = W / 2 + self.off_x + self.slide
        cy = H / 2 + self.off_y
        cr.save()
        cr.translate(cx, cy)
        cr.scale(self.pop, self.pop)
        if self.pb is not None:
            src, level = self._mip_for(z)
            s = z / level
            cr.scale(s, s)
            cr.translate(-self.iw * level / 2, -self.ih * level / 2)
            Gdk.cairo_set_source_pixbuf(cr, src, 0, 0)
            pat = cr.get_source()
            pat.set_filter(cairo.FILTER_GOOD if z < 1.0 else (cairo.FILTER_BILINEAR if z < 3.0 else cairo.FILTER_NEAREST if z >= 6.0 else cairo.FILTER_BILINEAR))
            cr.paint_with_alpha(self.alpha)
        else:
            pw, ph = self.ph.get_width(), self.ph.get_height()
            s = z * self.iw / pw
            cr.scale(s, s)
            cr.translate(-pw / 2, -ph / 2)
            Gdk.cairo_set_source_pixbuf(cr, self.ph, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR)
            cr.paint_with_alpha(self.alpha)
        cr.restore()
        return False

    # ── eventos ──
    def _press(self, w, ev):
        self.grab_focus()
        self.emit("activity")
        if ev.button == 1:
            if ev.type == Gdk.EventType._2BUTTON_PRESS:
                self.drag = None
                self.emit("double-clicked")
                return True
            if self.can_pan():
                self.drag = (ev.x, ev.y, self.off_x, self.off_y)
                self._cursor("grabbing")
        return False

    def _release(self, w, ev):
        if ev.button == 1:
            self.drag = None
            self._cursor("grab" if self.can_pan() else None)
        return False

    def _motion(self, w, ev):
        self.emit("activity")
        if self.drag:
            x0, y0, ox, oy = self.drag
            if self.zanim:
                self.zanim.cancel()
            self.off_x, self.off_y = self._clamp(ox + ev.x - x0, oy + ev.y - y0, self.zoom)
            self.fit_mode = False
            self.queue_draw()
        else:
            self._cursor("grab" if self.can_pan() else None)
        return False

    def _cursor(self, name):
        win = self.get_window()
        if win is None:
            return
        if name is None:
            win.set_cursor(None)
        else:
            win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), name))

    def _scroll(self, w, ev):
        self.emit("activity")
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if ev.direction == Gdk.ScrollDirection.SMOOTH:
            dy = ev.delta_y
            up = dy < 0
            if abs(dy) < 0.01:
                return True
        else:
            up = ev.direction == Gdk.ScrollDirection.UP
            if ev.direction not in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
                return True
        if ctrl or settings.get("wheel") == "zoom":
            f = 1.1 if up else 1 / 1.1
            base = self.ztarget if (self.zanim and not self.zanim.cancelled) else self.zoom
            self.zoom_to(base * f, ev.x, ev.y, animate=True)
        else:
            self.emit("navigate", -1 if up else 1)
        return True

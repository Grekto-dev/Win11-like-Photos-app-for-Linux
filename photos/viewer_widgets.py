# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Viewer widgets: zoom combo, Information panel, filmstrip."""
import math
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk  # noqa: E402

import cairo  # noqa: E402

from . import actions, icons, library, theme, thumbs, ui
from .i18n import _, ngettext  # noqa: F401

ZOOM_PRESETS = [800, 700, 600, 500, 400, 300, 200, 100, 75, 50, 25, 10]


class ZoomCombo(Gtk.Box):
    __gsignals__ = {"zoom-requested": (GObject.SignalFlags.RUN_FIRST, None, (float,))}

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.get_style_context().add_class("zoombox")
        self.entry = Gtk.Entry()
        self.entry.get_style_context().add_class("fzoom")
        self.entry.set_width_chars(5)
        self.entry.set_max_width_chars(5)
        self.entry.set_alignment(0.5)
        self.entry.set_has_frame(False)
        self.entry.connect("activate", self._activate)
        self.entry.connect("focus-out-event", lambda *_: (self.set_percent(self._last), False)[1])
        self.arrow = ui.icon_button("chev-down", _("Zoom selection"), classes=["flat-icon"], size=14, role="muted")
        self.arrow.set_size_request(22, 24)
        self.arrow.set_valign(Gtk.Align.CENTER)
        ui.menu_button(self.arrow, self._build, position=Gtk.PositionType.TOP, min_width=110)
        self.pack_start(self.entry, False, False, 2)
        self.pack_start(self.arrow, False, False, 0)
        self._last = 1.0
        self.set_valign(Gtk.Align.CENTER)

    def set_percent(self, z):
        self._last = z
        if not self.entry.has_focus():
            self.entry.set_text("%d%%" % round(z * 100))

    def _activate(self, e):
        txt = e.get_text().replace("%", "").replace(",", ".").strip()
        try:
            v = float(txt)
        except ValueError:
            self.set_percent(self._last)
            return
        v = max(1.0, min(800.0, v))
        self.emit("zoom-requested", v / 100.0)
        self.get_toplevel().set_focus(None)

    def _build(self, m):
        for p in ZOOM_PRESETS:
            m.add_item("%d%%" % p, lambda p=p: self.emit("zoom-requested", p / 100.0),
                       mark=(round(self._last * 100) == p), indent_mark=True)


class InfoPanel(Gtk.Box):
    """"Information" panel (Alt+Enter)."""

    def __init__(self, on_close, on_resize, on_copy_path, on_open_folder, on_rename):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.get_style_context().add_class("info-panel")
        self.set_size_request(336, -1)
        self.on_rename = on_rename
        head = Gtk.Box(spacing=8)
        head.set_border_width(16)
        head.pack_start(ui.label(_("Information"), ["info-title"]), True, True, 0)
        close = ui.icon_button("close", _("Close"), classes=["flat-icon"], size=16, on_click=on_close)
        head.pack_end(close, False, False, 0)
        self.pack_start(head, False, False, 0)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_border_width(0)
        grid.set_margin_start(16)
        grid.set_margin_end(16)
        grid.set_margin_bottom(12)
        grid.set_column_homogeneous(True)
        for n, (text, icon, cb) in enumerate([(_("Resize image"), "image-size", on_resize),
                                              (_("Copy path"), "copy", on_copy_path),
                                              (_("Open location"), "folder-open", on_open_folder)]):
            b = Gtk.Button()
            b.set_can_focus(False)
            b.get_style_context().add_class("info-btn")
            box = Gtk.Box(spacing=6)
            box.set_halign(Gtk.Align.CENTER)
            box.pack_start(icons.Icon(icon, 16, "fg"), False, False, 0)
            lb = ui.label(text)
            lb.set_ellipsize(3)
            box.pack_start(lb, False, False, 0)
            b.add(box)
            b.connect("clicked", lambda _b, cb=cb: cb())
            grid.attach(b, n % 2, n // 2, 1, 1)
        self.pack_start(grid, False, False, 0)
        sep = Gtk.Box()
        sep.get_style_context().add_class("info-sep")
        sep.set_size_request(-1, 1)
        self.pack_start(sep, False, False, 0)
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.fields.set_border_width(16)
        sc.add(self.fields)
        self.pack_start(sc, True, True, 0)

    def update(self, item, w, h):
        for c in self.fields.get_children():
            self.fields.remove(c)
        dpi, depth = actions.image_dpi_depth(item.path)
        self._field(_("File name"), item.name, rename=True)
        self._field(_("Date and time"), library.fmt_datetime(item.taken))
        self._field(_("Size information"), "%d x %d\n%s    %d dpi    %d bit" % (w, h, library.fmt_size(item.size), dpi, depth))
        for lab, val in actions.exif_fields(item.path):
            self._field(lab, val)
        self._field(_("Source and folder location"), _("This computer") + "\n" + item.folder, link=True)
        self.fields.show_all()

    def _field(self, title, value, rename=False, link=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        top = Gtk.Box(spacing=6)
        top.pack_start(ui.label(title, ["info-label"]), True, True, 0)
        if rename:
            top.pack_end(ui.icon_button("rename", _("Rename (F2)"), classes=["flat-icon"], size=14, on_click=self.on_rename),
                         False, False, 0)
        box.pack_start(top, False, False, 0)
        v = ui.label(value, ["info-value"] + (["link"] if link else []), wrap=True, selectable=True)
        v.set_line_wrap_mode(2)
        v.set_max_width_chars(34)
        box.pack_start(v, False, False, 0)
        self.fields.pack_start(box, False, False, 0)


class Filmstrip(Gtk.DrawingArea):
    __gsignals__ = {"picked": (GObject.SignalFlags.RUN_FIRST, None, (int,))}
    H = 64
    S = 48
    GAP = 6

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, self.H)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.items = []
        self.index = 0
        self.scroll = 0.0
        self.hover = -1
        self.anim = None
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("scroll-event", self._wheel)
        self.connect("motion-notify-event", self._motion)
        self.connect("leave-notify-event", lambda *_: self._set_hover(-1))
        self.connect("size-allocate", lambda *_: self.center_current(False))

    def set_items(self, items, index):
        self.items = items
        self.index = index
        self.center_current(False)
        self.queue_draw()

    def set_index(self, i):
        self.index = i
        self.center_current(True)
        self.queue_draw()

    def _stride(self):
        return self.S + self.GAP

    def center_current(self, animate):
        w = self.get_allocated_width()
        target = self.index * self._stride() + self.S / 2 - w / 2
        total = len(self.items) * self._stride() - self.GAP
        target = max(0, min(max(0, total - w), target)) if total > w else -(w - total) / 2
        if self.anim:
            self.anim.cancel()
        if not animate:
            self.scroll = target
            self.queue_draw()
            return
        s0 = self.scroll

        def step(t):
            self.scroll = s0 + (target - s0) * t
            self.queue_draw()
        self.anim = ui.Anim(self, 220, step)

    def _index_at(self, x):
        i = int((x + self.scroll) // self._stride())
        if 0 <= i < len(self.items) and ((x + self.scroll) % self._stride()) <= self.S:
            return i
        return -1

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.queue_draw()
        return False

    def _motion(self, w, ev):
        self._set_hover(self._index_at(ev.x))
        return False

    def _press(self, w, ev):
        if ev.button == 1:
            i = self._index_at(ev.x)
            if i >= 0:
                self.emit("picked", i)
        return True

    def _wheel(self, w, ev):
        d = 0
        if ev.direction == Gdk.ScrollDirection.SMOOTH:
            d = ev.delta_y or ev.delta_x
        elif ev.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.LEFT):
            d = -1
        elif ev.direction in (Gdk.ScrollDirection.DOWN, Gdk.ScrollDirection.RIGHT):
            d = 1
        total = len(self.items) * self._stride() - self.GAP
        wd = self.get_allocated_width()
        if total > wd:
            self.scroll = max(0, min(total - wd, self.scroll + d * 80))
            self.queue_draw()
        return True

    def _draw(self, w, cr):
        wd = self.get_allocated_width()
        y = (self.H - self.S) / 2
        st = self._stride()
        i0 = max(0, int(self.scroll // st) - 1)
        i1 = min(len(self.items), int((self.scroll + wd) // st) + 2)
        for i in range(i0, i1):
            x = i * st - self.scroll
            item = self.items[i]
            sel = i == self.index
            bucket = thumbs.BUCKETS[0]
            pb = thumbs.cache.peek(item, bucket)
            if pb is None:
                thumbs.cache.request(item, bucket, lambda *_: self.queue_draw())
                pb = thumbs.cache.best(item)
            cr.save()
            ui.rounded_rect(cr, x, y, self.S, self.S, 4)
            cr.clip()
            theme.set_source(cr, "tile")
            cr.paint()
            if pb is not None:
                pw, ph = pb.get_width(), pb.get_height()
                s = max(self.S / pw, self.S / ph)
                cr.translate(x + (self.S - pw * s) / 2, y + (self.S - ph * s) / 2)
                cr.scale(s, s)
                Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
                cr.get_source().set_filter(cairo.FILTER_GOOD)
                cr.paint_with_alpha(1.0 if (sel or i == self.hover) else 0.8)
            cr.restore()
            if sel:
                ui.rounded_rect(cr, x + 1, y + 1, self.S - 2, self.S - 2, 4)
                theme.set_source(cr, "fg")
                cr.set_line_width(2)
                cr.stroke()
        return False

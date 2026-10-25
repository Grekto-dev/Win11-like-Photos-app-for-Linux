# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Grade da Galeria: linhas justificadas (Cascata) ou quadradas, agrupadas por data."""
import bisect
import math
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, GObject, Gtk, Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

from . import i18n, icons, library, settings, theme, thumbs, ui

NOMINAL = {
    "cascade": {"small": 190, "medium": 280, "large": 400},
    "square": {"small": 130, "medium": 190, "large": 280},
}
GAP = {"cascade": 14, "square": 6}
HEADER_H = 52
TOP_PAD = 4
CHECK = 18


class GalleryGrid(Gtk.DrawingArea):
    __gsignals__ = {
        "open-item": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "context-menu": (GObject.SignalFlags.RUN_FIRST, None, (int, float, float)),
        "delete-request": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "rename-request": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.set_can_focus(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.items = []
        self.layout_mode = "cascade"
        self.tile_size = "medium"
        self.sort_by = "taken"
        self.select_mode = False
        self.selected = set()
        self.hover = -1
        self.kidx = -1
        self.anchor = -1
        self.pos = {}
        self.rows = []
        self.row_y0 = []
        self.headers = []
        self.total_h = 100
        self.width = 0
        self.dirty = True
        self.vadj = None
        self.fade = {}
        self.fading = False
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self._tooltip)
        self.connect("size-allocate", self._on_alloc)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("motion-notify-event", self._motion)
        self.connect("leave-notify-event", self._leave)
        self.connect("key-press-event", self._key)
        theme.on_change(self.queue_draw)

    # ── dados ──
    def set_items(self, items, keep_selection=True):
        self.items = items
        if keep_selection:
            paths = {i.path for i in items}
            self.selected &= paths
        else:
            self.selected = set()
        self.hover = -1
        self.kidx = -1
        self.dirty = True
        self._relayout()
        self.emit("selection-changed")

    def configure(self, layout_mode=None, tile_size=None, sort_by=None):
        if layout_mode:
            self.layout_mode = layout_mode
        if tile_size:
            self.tile_size = tile_size
        if sort_by:
            self.sort_by = sort_by
        self.dirty = True
        self._relayout()

    def selected_items(self):
        return [i for i in self.items if i.path in self.selected]

    def set_select_mode(self, on):
        self.select_mode = on
        if not on:
            self.selected = set()
            self.emit("selection-changed")
        self.queue_draw()

    def select_all(self):
        self.selected = {i.path for i in self.items}
        self.emit("selection-changed")
        self.queue_draw()

    def clear_selection(self):
        if self.selected:
            self.selected = set()
            self.emit("selection-changed")
            self.queue_draw()

    # ── layout ──
    def _on_alloc(self, w, alloc):
        if alloc.width != self.width:
            self.width = alloc.width
            self.dirty = True
            GLib.idle_add(self._relayout)

    def _relayout(self):
        if not self.dirty or self.width <= 0:
            return False
        self.dirty = False
        w = self.width
        pad = 48 if w > 700 else max(12, int(w * 0.04))
        gap = GAP[self.layout_mode]
        avail = max(60, w - 2 * pad)
        nominal = NOMINAL[self.layout_mode][self.tile_size]
        groups = library.make_groups(self.items, self.sort_by)
        self.pos = {}
        self.rows = []
        self.headers = []
        y = TOP_PAD
        for title, idxs in groups:
            if title is not None:
                self.headers.append((y, title))
                y += HEADER_H
            if self.layout_mode == "square":
                rows = self._square_rows(idxs, avail, nominal, gap)
            else:
                rows = self._cascade_rows(idxs, avail, nominal, gap)
            for row_h, tiles in rows:
                self.rows.append((y, y + row_h, [t[0] for t in tiles]))
                for idx, tx, tw in tiles:
                    px = pad + tx
                    if i18n.is_rtl():
                        px = w - px - tw
                    self.pos[idx] = (px, y, tw, row_h)
                y += row_h + gap
            y += 6
        self.total_h = y + 24
        self.row_y0 = [r[0] for r in self.rows]
        self.set_size_request(-1, int(self.total_h))
        self.queue_draw()
        return False

    def _cascade_rows(self, idxs, avail, nominal, gap):
        out = []
        cur = []
        sumw = 0.0

        def finish(row, sw, last=False):
            n = len(row)
            s = (avail - gap * (n - 1)) / sw
            if last and s > 1:
                s = 1.0
            h = nominal * s
            x = 0.0
            tiles = []
            for i in row:
                tw = self.items[i].aspect * h
                x0 = round(x)
                x1 = round(x + tw)
                tiles.append((i, x0, max(1, x1 - x0)))
                x += tw + gap
            out.append((int(round(h)), tiles))

        for i in idxs:
            wn = self.items[i].aspect * nominal
            if cur and sumw + wn + gap * len(cur) > avail:
                s_cur = (avail - gap * (len(cur) - 1)) / sumw
                s_inc = (avail - gap * len(cur)) / (sumw + wn)
                if s_inc > 0 and abs(math.log(s_inc)) < abs(math.log(s_cur)):
                    cur.append(i)
                    finish(cur, sumw + wn)
                    cur, sumw = [], 0.0
                else:
                    finish(cur, sumw)
                    cur, sumw = [i], wn
                continue
            cur.append(i)
            sumw += wn
        if cur:
            finish(cur, sumw, last=True)
        return out

    def _square_rows(self, idxs, avail, nominal, gap):
        cols = max(2, int(round((avail + gap) / (nominal + gap))))
        size = (avail - gap * (cols - 1)) / cols
        out = []
        for r in range(0, len(idxs), cols):
            chunk = idxs[r:r + cols]
            tiles = []
            for c, i in enumerate(chunk):
                x0 = round(c * (size + gap))
                x1 = round(c * (size + gap) + size)
                tiles.append((i, x0, x1 - x0))
            out.append((int(round(size)), tiles))
        return out

    # ── hit-testing ──
    def index_at(self, x, y):
        k = bisect.bisect_right(self.row_y0, y) - 1
        if k < 0:
            return -1
        y0, y1, idxs = self.rows[k]
        if y > y1:
            return -1
        for i in idxs:
            tx, ty, tw, th = self.pos[i]
            if tx <= x <= tx + tw:
                return i
        return -1

    def _check_rect(self, i):
        tx, ty, tw, th = self.pos[i]
        return (tx + tw - CHECK - 8, ty + 8, CHECK, CHECK)

    # ── desenho ──
    def _bucket(self, tw, th):
        return thumbs.bucket_for(max(tw, th))

    def _draw(self, w, cr):
        ok, clip = Gdk.cairo_get_clip_rectangle(cr)
        if not ok:
            return False
        y0, y1 = clip.y, clip.y + clip.height
        # headers
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription()
        fd.set_family("Segoe UI Variable, Segoe UI, Inter, Noto Sans, Ubuntu Sans, sans-serif")
        fd.set_weight(Pango.Weight.SEMIBOLD)
        fd.set_absolute_size(14 * Pango.SCALE)
        layout.set_font_description(fd)
        pad = 48 if self.width > 700 else max(12, int(self.width * 0.04))
        for hy, text in self.headers:
            if hy + HEADER_H < y0 or hy > y1:
                continue
            theme.set_source(cr, "fg")
            layout.set_text(text, -1)
            if i18n.is_rtl():
                layout.set_text(text, -1)
                cr.move_to(self.width - pad - 1 - layout.get_pixel_size()[0], hy + 18)
            else:
                cr.move_to(pad + 1, hy + 18)
            PangoCairo.show_layout(cr, layout)
        # tiles
        k0 = max(0, bisect.bisect_right(self.row_y0, y0) - 2)
        animating = False
        t_now = time.monotonic()
        for k in range(k0, len(self.rows)):
            ry0, ry1, idxs = self.rows[k]
            if ry0 > y1:
                break
            if ry1 < y0:
                continue
            for i in idxs:
                if self._draw_tile(cr, i, t_now):
                    animating = True
        if animating and not self.fading:
            self.fading = True
            GLib.timeout_add(16, self._fade_tick)
        return False

    def _fade_tick(self):
        self.queue_draw()
        t = time.monotonic()
        self.fade = {p: s for p, s in self.fade.items() if t - s < 0.25}
        if not self.fade:
            self.fading = False
            return False
        return True

    def _draw_tile(self, cr, i, t_now):
        item = self.items[i]
        tx, ty, tw, th = self.pos[i]
        bucket = self._bucket(tw, th)
        pb = thumbs.cache.peek(item, bucket)
        placeholder = False
        if pb is None:
            thumbs.cache.request(item, bucket, self._thumb_ready)
            pb = thumbs.cache.best(item)
            placeholder = True
        selected = item.path in self.selected
        hovered = (i == self.hover)
        animating = False
        cr.save()
        ui.rounded_rect(cr, tx, ty, tw, th, 4)
        cr.clip()
        theme.set_source(cr, "tile")
        cr.paint()
        if pb is not None:
            pw, ph = pb.get_width(), pb.get_height()
            if self.layout_mode == "square":
                s = max(tw / pw, th / ph)
            else:
                s = tw / pw
            alpha = 1.0
            started = self.fade.get(item.path)
            if started is not None:
                alpha = min(1.0, (t_now - started) / 0.2)
                if alpha < 1.0:
                    animating = True
            cr.save()
            cr.translate(tx + (tw - pw * s) / 2, ty + (th - ph * s) / 2)
            cr.scale(s, s)
            Gdk.cairo_set_source_pixbuf(cr, pb, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint_with_alpha(alpha)
            cr.restore()
        if item.kind == "video" and pb is not None:
            cx, cy = tx + tw / 2, ty + th / 2
            cr.arc(cx, cy, 20, 0, 2 * math.pi)
            cr.set_source_rgba(0, 0, 0, 0.55)
            cr.fill()
            cr.move_to(cx - 6, cy - 9)
            cr.line_to(cx + 10, cy)
            cr.line_to(cx - 6, cy + 9)
            cr.close_path()
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.fill()
        cr.restore()
        if item.dup and settings.get("show_tile_attrs"):
            bx, by = tx + 8, ty + th - 26
            ui.rounded_rect(cr, bx, by, 18, 18, 4)
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.7)
            cr.fill()
            pbd = icons.pixbuf("copy", 14, "#ffffff")
            Gdk.cairo_set_source_pixbuf(cr, pbd, bx + 2, by + 2)
            cr.paint()
        if selected or hovered or i == self.kidx:
            cr.save()
            ui.rounded_rect(cr, tx + 1, ty + 1, tw - 2, th - 2, 4)
            theme.set_source(cr, "accent" if selected else "fg")
            cr.set_line_width(2)
            cr.stroke()
            cr.restore()
        if hovered or selected or self.select_mode:
            self._draw_check(cr, i, selected)
        return animating

    def _draw_check(self, cr, i, checked):
        x, y, s, _ = self._check_rect(i)
        cr.save()
        ui.rounded_rect(cr, x, y, s, s, 4)
        if checked:
            theme.set_source(cr, "accent")
            cr.fill_preserve()
            theme.set_source(cr, "accent")
            cr.set_line_width(1)
            cr.stroke()
            theme.set_source(cr, "onaccent")
            cr.set_line_width(1.8)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            cr.move_to(x + 4.5, y + 9.5)
            cr.line_to(x + 7.8, y + 12.6)
            cr.line_to(x + 13.6, y + 5.8)
            cr.stroke()
        else:
            cr.set_source_rgba(0.1, 0.1, 0.1, 0.55)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.set_line_width(1.2)
            cr.stroke()
        cr.restore()

    def _thumb_ready(self, item, bucket):
        self.fade[item.path] = time.monotonic()
        self.queue_draw()

    def refresh_item(self, path):
        """Drops the thumbnail (file changed) so it gets reloaded."""
        for it in self.items:
            if it.path == path:
                thumbs.cache.invalidate(path)
                break
        self.queue_draw()

    # ── eventos ──
    def _tooltip(self, w, x, y, kb, tip):
        i = self.hover
        if i < 0 or i >= len(self.items):
            return False
        tip.set_text(self.items[i].name)
        tx, ty, tw, th = self.pos[i]
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(tx), int(ty), int(tw), int(th)
        self.set_tooltip_tip = tip.set_tip_area(r)
        return True

    def _motion(self, w, ev):
        i = self.index_at(ev.x, ev.y)
        if i != self.hover:
            self.hover = i
            self.trigger_tooltip_query()
            self.queue_draw()
        return False

    def _leave(self, w, ev):
        if self.hover != -1:
            self.hover = -1
            self.queue_draw()
        return False

    def _toggle(self, i):
        p = self.items[i].path
        if p in self.selected:
            self.selected.discard(p)
        else:
            self.selected.add(p)
        self.anchor = i
        self.emit("selection-changed")
        self.queue_draw()

    def _press(self, w, ev):
        self.grab_focus()
        i = self.index_at(ev.x, ev.y)
        if ev.type != Gdk.EventType.BUTTON_PRESS:
            return False
        if i < 0:
            if ev.button == 1 and not self.select_mode:
                self.clear_selection()
            return False
        if ev.button == 3:
            self.kidx = i
            self.emit("context-menu", i, ev.x, ev.y)
            return True
        if ev.button != 1:
            return False
        cx, cy, cw, ch = self._check_rect(i)
        on_check = cx - 4 <= ev.x <= cx + cw + 4 and cy - 4 <= ev.y <= cy + ch + 4
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(ev.state & Gdk.ModifierType.SHIFT_MASK)
        if on_check or ctrl or self.select_mode and not shift:
            self._toggle(i)
        elif shift and self.anchor >= 0:
            a, b = sorted((self.anchor, i))
            self.selected = {self.items[k].path for k in range(a, b + 1)}
            self.emit("selection-changed")
            self.queue_draw()
        else:
            self.anchor = i
            self.kidx = i
            self.emit("open-item", i)
        return True

    def _key(self, w, ev):
        k = ev.keyval
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        n = len(self.items)
        if n == 0:
            return False
        if ctrl and k in (Gdk.KEY_a, Gdk.KEY_A):
            self.select_all()
            return True
        if (ctrl and k in (Gdk.KEY_d, Gdk.KEY_D)) or k == Gdk.KEY_Escape:
            self.clear_selection()
            return True
        if k == Gdk.KEY_Delete:
            self.emit("delete-request")
            return True
        if k == Gdk.KEY_F2:
            self.emit("rename-request")
            return True
        if k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.kidx >= 0:
                self.emit("open-item", self.kidx)
            return True
        if k == Gdk.KEY_space and self.kidx >= 0:
            self._toggle(self.kidx)
            return True
        move = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1}.get(k)
        if move is not None:
            self.kidx = max(0, min(n - 1, (self.kidx if self.kidx >= 0 else (0 if move > 0 else n)) + (move if self.kidx >= 0 else 0)))
            self._reveal(self.kidx)
            return True
        if k in (Gdk.KEY_Up, Gdk.KEY_Down):
            if self.kidx < 0:
                self.kidx = 0
            else:
                x, y, w_, h_ = self.pos[self.kidx]
                cxm = x + w_ / 2
                target_y = y - 10 if k == Gdk.KEY_Up else y + h_ + 10 + 0
                best = self.index_at(cxm, target_y)
                if best < 0:
                    # procura a linha vizinha
                    ri = bisect.bisect_right(self.row_y0, y) - 1 + (-1 if k == Gdk.KEY_Up else 1)
                    if 0 <= ri < len(self.rows):
                        cands = self.rows[ri][2]
                        best = min(cands, key=lambda c: abs(self.pos[c][0] + self.pos[c][2] / 2 - cxm))
                if best >= 0:
                    self.kidx = best
            self._reveal(self.kidx)
            return True
        return False

    def _reveal(self, i):
        self.queue_draw()
        if self.vadj is None or i not in self.pos:
            return
        x, y, w, h = self.pos[i]
        top = self.vadj.get_value()
        page = self.vadj.get_page_size()
        if y < top:
            self.vadj.set_value(max(0, y - 40))
        elif y + h > top + page:
            self.vadj.set_value(y + h - page + 24)

    def scroll_to(self, i):
        self._reveal(i)

# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Full-screen slideshow (cross-fade, controls that hide by themselves)."""
import random

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import icons, settings, ui
from .i18n import _, ngettext  # noqa: F401


class Slideshow:
    def __init__(self, win):
        self.win = win
        self.paused = False
        self.shuffle = settings.get("slideshow_shuffle")
        self.interval = max(2, int(settings.get("slideshow_interval")))
        self.timer = 0
        self.hide_timer = 0
        self.photos = [i for i, it in enumerate(win.items) if it.kind == "photo"]
        self.order = list(self.photos)
        self._reorder()
        self.win.canvas.force_fit = True
        self.win.bottom.hide()
        self.win.film_rev.hide()
        self.win.info_rev.hide()
        self.win.hb.hide()
        self.win.fullscreen()

        # overlays
        self.top = Gtk.Box()
        self.top.get_style_context().add_class("slide-top")
        self.top.set_halign(Gtk.Align.FILL)
        self.top.set_valign(Gtk.Align.START)
        btn = Gtk.Button()
        btn.set_can_focus(False)
        btn.get_style_context().add_class("fbtn")
        box = Gtk.Box(spacing=10)
        box.pack_start(icons.Icon("chev-left", 18, "#ffffff"), False, False, 0)
        lb = ui.label(_("Exit slideshow"), ["slide-title"])
        box.pack_start(lb, False, False, 0)
        btn.add(box)
        btn.connect("clicked", lambda b: self.win.stop_slideshow())
        btn.set_margin_start(24)
        btn.set_margin_top(16)
        btn.set_margin_bottom(32)
        self.top.pack_start(btn, False, False, 0)
        self.bar = Gtk.Box(spacing=2)
        self.bar.get_style_context().add_class("slide-bar")
        self.bar.set_halign(Gtk.Align.CENTER)
        self.bar.set_valign(Gtk.Align.START)
        self.bar.set_margin_top(16)
        self.b_shuffle = ui.icon_button("shuffle", _("Shuffle"), classes=["flat-icon"], role="#ffffff", on_click=self.toggle_shuffle)
        self.b_prev = ui.icon_button("skip-back", _("Previous"), classes=["flat-icon"], role="#ffffff", on_click=self.prev)
        self.b_play = ui.icon_button("pause", _("Pause"), classes=["flat-icon"], role="#ffffff", on_click=self.toggle_pause)
        self.b_exit = ui.icon_button("unfullscreen", _("Exit full screen"), classes=["flat-icon"], role="#ffffff",
                                     on_click=lambda: self.win.stop_slideshow())
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_exit):
            self.bar.pack_start(b, False, False, 0)
        self._sync_shuffle()
        ov = win.canvas_overlay
        ov.add_overlay(self.top)
        ov.add_overlay(self.bar)
        ov.set_overlay_pass_through(self.top, True)
        self.top.show_all()
        self.bar.show_all()
        self.activity()
        self._schedule()
        self._show_current()

    # ordem
    def _reorder(self):
        cur = self.win.index
        if self.shuffle:
            rest = [i for i in self.photos if i != cur]
            random.shuffle(rest)
            self.order = ([cur] if cur in self.photos else []) + rest
        else:
            self.order = list(self.photos)

    def _pos(self):
        try:
            return self.order.index(self.win.index)
        except ValueError:
            return 0

    def next(self):
        self._advance(1)
        self._schedule()

    def prev(self):
        self._advance(-1)
        self._schedule()

    def _advance(self, d):
        if not self.order:
            return
        i = self.order[(self._pos() + d) % len(self.order)]
        self.win.index = i
        self.win.film.set_index(i)
        self.win.load_current(transition="cross")

    def _show_current(self):
        pass

    def toggle_pause(self):
        self.paused = not self.paused
        self.b_play.icon.set_icon("play" if self.paused else "pause")
        self.b_play.set_tooltip_text(_("Play") if self.paused else _("Pause"))
        self._schedule()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        settings.set("slideshow_shuffle", self.shuffle)
        self._reorder()
        self._sync_shuffle()

    def _sync_shuffle(self):
        ctx = self.b_shuffle.get_style_context()
        (ctx.add_class if self.shuffle else ctx.remove_class)("sel-on")

    def _schedule(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        if not self.paused and len(self.order) > 1:
            self.timer = GLib.timeout_add_seconds(self.interval, self._tick)

    def _tick(self):
        self.timer = 0
        self._advance(1)
        self._schedule()
        return False

    # controls that fade away
    def activity(self):
        for w in (self.top, self.bar):
            w.set_opacity(1.0)
        win = self.win.get_window()
        if win is not None:
            win.set_cursor(None)
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
        self.hide_timer = GLib.timeout_add(3000, self._hide_controls)

    def _hide_controls(self):
        self.hide_timer = 0
        for w in (self.top, self.bar):
            ui.Anim(w, 300, lambda t, w=w: w.set_opacity(1 - t))
        win = self.win.get_window()
        if win is not None:
            blank = Gdk.Cursor.new_from_name(self.win.get_display(), "none")
            win.set_cursor(blank)
        return False

    def finish(self):
        for src in (self.timer, self.hide_timer):
            if src:
                GLib.source_remove(src)
        self.timer = self.hide_timer = 0
        ov = self.win.canvas_overlay
        for w in (self.top, self.bar):
            ov.remove(w)
        win = self.win.get_window()
        if win is not None:
            win.set_cursor(None)
        self.win.canvas.force_fit = False
        self.win.bottom.show()
        self.win.film_rev.show()
        self.win.info_rev.show()
        self.win.hb.show()
        self.win.canvas.fit_mode = "default"
        self.win.canvas.zoom_to(self.win.canvas.default_zoom(), animate=False, mode="default")

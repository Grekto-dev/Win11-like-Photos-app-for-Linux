# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Shared UI components: buttons, menus/flyouts, overlay dialogs, toasts, animations."""
import math
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import icons
from .i18n import _, ngettext  # noqa: F401


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


class Anim:
    """Per-tick widget animation: fn(t) with t in [0,1]; optional done()."""

    def __init__(self, widget, duration_ms, fn, done=None, ease=ease_out):
        self.widget = widget
        self.fn = fn
        self.done = done
        self.ease = ease
        self.duration = duration_ms / 1000.0
        self.start = None
        self.cancelled = False
        self.tid = widget.add_tick_callback(self._tick)

    def cancel(self):
        if not self.cancelled:
            self.cancelled = True
            try:
                self.widget.remove_tick_callback(self.tid)
            except Exception:  # noqa: BLE001
                pass

    def _tick(self, widget, clock):
        if self.cancelled:
            return False
        now = clock.get_frame_time() / 1e6
        if self.start is None:
            self.start = now
        t = min(1.0, (now - self.start) / self.duration) if self.duration > 0 else 1.0
        self.fn(self.ease(t))
        if t >= 1.0:
            self.cancelled = True
            if self.done:
                self.done()
            return False
        return True


def icon_button(icon=None, tooltip=None, label=None, classes=(), size=20, role="fg", on_click=None, icon_after=None):
    btn = Gtk.Button()
    btn.get_style_context().add_class("fbtn")
    for c in classes:
        btn.get_style_context().add_class(c)
    btn.set_can_focus(False)
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_halign(Gtk.Align.CENTER)
    btn.icon = None
    if icon:
        btn.icon = icons.Icon(icon, size, role)
        box.pack_start(btn.icon, False, False, 0)
    btn.label = None
    if label:
        btn.label = Gtk.Label(label=label)
        box.pack_start(btn.label, False, False, 0)
    if icon_after:
        btn.icon_after = icons.Icon(icon_after, 14, "muted")
        box.pack_start(btn.icon_after, False, False, 0)
    btn.add(box)
    if tooltip:
        btn.set_tooltip_text(tooltip)
    if on_click:
        btn.connect("clicked", lambda b: on_click())
    return btn


def label(text, classes=(), xalign=0.0, wrap=False, selectable=False, ellipsize=False):
    lb = Gtk.Label(label=text)
    lb.set_xalign(xalign)
    for c in classes:
        lb.get_style_context().add_class(c)
    if wrap:
        lb.set_line_wrap(True)
    if selectable:
        lb.set_selectable(True)
    if ellipsize:
        from gi.repository import Pango
        lb.set_ellipsize(Pango.EllipsizeMode.END)
    return lb


# ───────────────────────── Flyout / menu ─────────────────────────

_last_pop_close = [0.0]


def popover_recent(ms=250):
    """True if a menu closed a moment ago (the Esc that closed it must not close the window)."""
    return (time.monotonic() - _last_pop_close[0]) * 1000 < ms


class FlyoutMenu(Gtk.Popover):
    """Fluent-style menu: items with icon, shortcut, selection mark and subtitle."""

    def __init__(self, relative_to=None, position=Gtk.PositionType.BOTTOM, min_width=200):
        super().__init__()
        self.get_style_context().add_class("fmenu")
        if relative_to is not None:
            self.set_relative_to(relative_to)
        self.set_position(position)
        self.set_modal(True)
        self.connect("closed", lambda *_: _last_pop_close.__setitem__(0, time.monotonic()))
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box.set_size_request(min_width, -1)
        self.add(self.box)
        self.box.show()
        self._subs = []

    def add_widget(self, w):
        self.box.pack_start(w, False, False, 0)
        w.show_all()
        return w

    def add_header(self, text):
        lb = label(text, ["mhead"])
        return self.add_widget(lb)

    def add_sep(self):
        sep = Gtk.Box()
        sep.get_style_context().add_class("msep")
        sep.set_size_request(-1, 1)
        return self.add_widget(sep)

    def add_item(self, text, callback=None, icon=None, shortcut=None, subtitle=None, mark=False, danger=False,
                 sensitive=True, keep_open=False, indent_mark=False, submenu=None):
        btn = Gtk.Button()
        btn.set_can_focus(False)
        btn.get_style_context().add_class("mitem")
        if danger:
            btn.get_style_context().add_class("danger")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        if indent_mark or mark:
            m = Gtk.Box()
            m.set_size_request(3, 16)
            m.set_valign(Gtk.Align.CENTER)
            if mark:
                m.get_style_context().add_class("mmark")
            row.pack_start(m, False, False, 0)
        if icon:
            row.pack_start(icons.Icon(icon, 16, "danger" if danger else "fg"), False, False, 0)
        if subtitle:
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            col.pack_start(label(text), False, False, 0)
            col.pack_start(label(subtitle, ["msub"]), False, False, 0)
            row.pack_start(col, True, True, 0)
            btn.set_size_request(-1, 48)
        else:
            row.pack_start(label(text), True, True, 0)
        if shortcut:
            row.pack_end(label(shortcut, ["mshort"], xalign=1.0), False, False, 8)
        if submenu is not None:
            row.pack_end(icons.Icon("chev-right", 14, "muted"), False, False, 0)
        btn.add(row)
        btn.set_sensitive(sensitive)
        if submenu is not None:
            btn.connect("clicked", lambda b: self._open_sub(b, submenu))
        else:
            def clicked(_b):
                if not keep_open:
                    self.popdown()
                if callback:
                    GLib.idle_add(lambda: (callback(), False)[1])
            btn.connect("clicked", clicked)
        self.add_widget(btn)
        return btn

    def _open_sub(self, btn, builder):
        sub = FlyoutMenu(btn, Gtk.PositionType.RIGHT)
        builder(sub)
        sub.set_modal(False)
        sub.connect("closed", lambda *_: None)
        self._subs.append(sub)
        sub.popup()

    def popdown(self):
        for s in self._subs:
            s.popdown()
        super().popdown()


def popup_menu_at(widget, x, y, build):
    m = FlyoutMenu(widget, Gtk.PositionType.BOTTOM)
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
    m.set_pointing_to(rect)
    build(m)
    m.popup()
    return m


def menu_button(btn, build, position=Gtk.PositionType.BOTTOM, min_width=200):
    """Opens a FlyoutMenu when btn is clicked (built on every opening)."""
    def on_click(_b):
        m = FlyoutMenu(btn, position, min_width)
        build(m)
        m.connect("closed", lambda *_: GLib.idle_add(m.destroy))
        m.popup()
    btn.connect("clicked", on_click)


# ───────────────────────── Overlay dialog ─────────────────────────

_open_dialogs = []


def dialog_open():
    return bool(_open_dialogs)


class ContentDialog(Gtk.EventBox):
    """Modal dialog drawn over the window (Gtk.Overlay), dimming the background."""

    def __init__(self, overlay, title, content=None, buttons=(), width=420, primary=0, on_close=None,
                 close_on_scrim=False, footer=True):
        super().__init__()
        self.overlay = overlay
        self.on_close = on_close
        self.closed = False
        self.get_style_context().add_class("scrim")
        self.set_visible_window(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_above_child(False)
        self.set_events(Gdk.EventMask.ALL_EVENTS_MASK)
        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.card.get_style_context().add_class("dialog-card")
        self.card.set_halign(Gtk.Align.CENTER)
        self.card.set_valign(Gtk.Align.CENTER)
        self.card.set_size_request(width, -1)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_border_width(24)
        body.pack_start(label(title, ["dialog-title"]), False, False, 0)
        if content is not None:
            body.pack_start(content, True, True, 0)
        self.card.pack_start(body, True, True, 0)
        self.buttons = []
        if buttons:
            foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, homogeneous=True)
            foot.set_border_width(24)
            if footer:
                foot.get_style_context().add_class("dialog-footer")
            for i, (text, kind, cb) in enumerate(buttons):
                b = icon_button(label=text, classes=["subtle"] if kind != "accent" else ["accent"])
                b.set_size_request(-1, 32)
                b.connect("clicked", lambda _b, cb=cb: self._press(cb))
                foot.pack_start(b, True, True, 0)
                self.buttons.append(b)
            self.card.pack_start(foot, False, False, 0)
        self.add(self.card)
        if close_on_scrim:
            self.connect("button-press-event", self._scrim_click)
        self.connect("key-press-event", self._key)
        _open_dialogs.append(self)
        overlay.add_overlay(self)
        self.show_all()
        self.set_opacity(0.0)
        Anim(self, 160, lambda t: self.set_opacity(t))
        self.grab_focus()
        self.set_can_focus(True)
        self.grab_focus()
        if self.buttons:
            self.buttons[min(primary, len(self.buttons) - 1)].grab_focus()

    def _press(self, cb):
        close = True
        if cb:
            r = cb()
            if r is False:
                close = False
        if close:
            self.close()

    def _scrim_click(self, w, ev):
        alloc = self.card.get_allocation()
        if not (alloc.x <= ev.x <= alloc.x + alloc.width and alloc.y <= ev.y <= alloc.y + alloc.height):
            self.close()
        return False

    def _key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            _last_pop_close[0] = time.monotonic()
            self.close()
            return True
        return False

    def close(self):
        if self.closed:
            return
        self.closed = True

        def finish():
            if self in _open_dialogs:
                _open_dialogs.remove(self)
            self.overlay.remove(self)
            if self.on_close:
                self.on_close()
        Anim(self, 120, lambda t: self.set_opacity(1 - t), done=finish)


def confirm(overlay, title, text, ok_label, cancel_label=_("Cancel"), on_ok=None, checkbox=None):
    """Confirmation box; checkbox = text of the "don't show again" option → the CheckButton is passed to on_ok."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.pack_start(label(text, ["dialog-body"], wrap=True), False, False, 0)
    chk = None
    if checkbox:
        chk = Gtk.CheckButton(label=checkbox)
        chk.get_style_context().add_class("fcheck")
        box.pack_start(chk, False, False, 0)

    def ok():
        if on_ok:
            on_ok(chk.get_active() if chk else False)
    dlg = ContentDialog(overlay, title, box, [(ok_label, "accent", ok), (cancel_label, "", None)], width=360)
    return dlg


# ───────────────────────── Toast ─────────────────────────

def toast(overlay, text, ms=2600):
    box = Gtk.Box()
    box.get_style_context().add_class("toast")
    box.pack_start(label(text), False, False, 0)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.END)
    box.set_margin_bottom(64)
    box.set_no_show_all(False)
    overlay.add_overlay(box)
    overlay.set_overlay_pass_through(box, True)
    box.show_all()
    box.set_opacity(0)
    Anim(box, 180, lambda t: box.set_opacity(t))

    def hide():
        def fin():
            try:
                overlay.remove(box)
            except Exception:  # noqa: BLE001
                pass
        Anim(box, 200, lambda t: box.set_opacity(1 - t), done=fin)
        return False
    GLib.timeout_add(ms, hide)


# ───────────────────────── Utilidades ─────────────────────────

def separator_v():
    b = Gtk.Box()
    b.get_style_context().add_class("sep")
    b.set_size_request(1, 16)
    b.set_valign(Gtk.Align.CENTER)
    return b


def pointer_monitor_geometry(widget):
    disp = widget.get_display()
    seat = disp.get_default_seat()
    _scr, x, y = seat.get_pointer().get_position()
    mon = disp.get_monitor_at_point(x, y)
    return mon.get_geometry()


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def now():
    return time.monotonic()

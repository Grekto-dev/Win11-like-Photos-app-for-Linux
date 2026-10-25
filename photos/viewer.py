# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Image viewer window (top bar, canvas, bottom bar, Information panel, filmstrip, slideshow)."""
import os
import random
import threading
from collections import OrderedDict

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, Gio, GLib, GdkPixbuf, Gtk  # noqa: E402

from PIL import Image

from . import actions, dialogs, icons, library, settings, theme, thumbs, ui
from .i18n import _, ngettext  # noqa: F401
from .canvas import ImageCanvas
from .viewer_widgets import Filmstrip, InfoPanel, ZoomCombo

NARROW = 900


class ViewerWindow(Gtk.ApplicationWindow):
    def __init__(self, app, items, index, slideshow=False):
        super().__init__(application=app)
        self.app_ref = app
        self.items = list(items)
        self.index = max(0, min(index, len(self.items) - 1))
        self.get_style_context().add_class("photos")
        self.set_title(_("Photos"))
        self.set_icon_name("photos")
        self.set_default_size(*settings.get("viewer_size"))
        if settings.get("viewer_maximized"):
            self.maximize()
        self.load_token = 0
        self.cache = OrderedDict()
        self.compact = None
        self.slideshow = None
        self.editor = None
        self.zoom_updating = False
        self.fullscreen_on = False
        self.current_pb = None
        self._native_ref = None
        self._build()
        self.connect("key-press-event", self._on_key)
        self.connect("size-allocate", self._on_size)
        self.connect("window-state-event", self._on_state)
        self.connect("delete-event", lambda *_: False)
        self.show_all()
        self._apply_compact(self.get_allocated_width() < NARROW)
        self.info_rev.set_reveal_child(False)
        self.film_rev.set_reveal_child(False)
        self._set_arrows(False)
        if settings.get("filmstrip"):
            self.toggle_filmstrip(True)
        if settings.get("info_open"):
            self.toggle_info(True)
        self.load_current(transition="open")
        if slideshow:
            GLib.idle_add(self.start_slideshow)

    # ───────────────────────── construction ─────────────────────────
    def _build(self):
        hb = Gtk.HeaderBar()
        hb.get_style_context().add_class("photos-hb")
        hb.set_show_close_button(True)
        hb.set_decoration_layout(":minimize,maximize,close")
        self.hb = hb
        # left side (viewer)
        self.tools = Gtk.Box(spacing=2)
        self.btn_edit = ui.icon_button("edit", _("Edit image (Ctrl+E)"), label=_("Edit"), classes=["subtle"], on_click=self.open_editor)
        self.btn_rotate = ui.icon_button("rotate", _("Rotate (Ctrl+R)"), classes=["flat-icon"], on_click=self.rotate)
        self.btn_delete = ui.icon_button("trash", _("Delete (Del)"), classes=["flat-icon"], on_click=self.delete_current)
        self.btn_print = ui.icon_button("print", _("Print (Ctrl+P)"), classes=["flat-icon"], on_click=self.print_current)
        self.btn_share = ui.icon_button("share", _("Share (Alt+Up)"), classes=["flat-icon"])
        ui.menu_button(self.btn_share, self._build_share_menu)
        self.btn_more = ui.icon_button("more", _("See more"), classes=["flat-icon"])
        ui.menu_button(self.btn_more, self._build_more_menu, min_width=230)
        for b in (self.btn_edit, self.btn_rotate, self.btn_delete, self.btn_print, self.btn_share, self.btn_more):
            self.tools.pack_start(b, False, False, 0)
        hb.pack_start(self.tools)
        # editor: back
        self.editor_back = ui.icon_button("back", _("Back"), classes=["flat-icon"], on_click=self.close_editor)
        hb.pack_start(self.editor_back)
        self.title_lb = ui.label("", ["photos-hb-title"], xalign=0.5)
        self.title_lb.set_ellipsize(3)
        self.title_lb.set_max_width_chars(60)
        hb.set_custom_title(self.title_lb)
        # right side: open with
        self.btn_open_with = ui.icon_button(label=_("Open with"), icon_after="chev-down")
        ui.menu_button(self.btn_open_with, self._build_open_with_menu, min_width=260)
        hb.pack_end(self.btn_open_with)
        self.set_titlebar(hb)

        self.overlay = Gtk.Overlay()
        self.add(self.overlay)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(160)
        self.overlay.add(self.stack)

        vpage = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vpage.get_style_context().add_class("viewer-bg")
        self.stack.add_named(vpage, "viewer")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vpage.pack_start(row, True, True, 0)

        self.canvas_overlay = Gtk.Overlay()
        self.canvas = ImageCanvas()
        self.canvas_overlay.add(self.canvas)
        self.canvas.connect("zoom-changed", self._on_zoom_changed)
        self.canvas.connect("navigate", lambda c, d: self.go(d))
        self.canvas.connect("double-clicked", lambda c: self.canvas.toggle_fit())
        self.canvas.connect("activity", self._on_activity)
        self.canvas_overlay.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.canvas_overlay.connect("motion-notify-event", self._on_canvas_motion)
        self.canvas_overlay.connect("leave-notify-event", lambda *_: (self._set_arrows(False), False)[1])
        self.arrow_prev = Gtk.Button()
        self.arrow_next = Gtk.Button()
        for b, ic, al, tip in ((self.arrow_prev, "tri-left", Gtk.Align.START, _("Previous")),
                               (self.arrow_next, "tri-right", Gtk.Align.END, _("Next"))):
            b.get_style_context().add_class("navarrow")
            b.set_can_focus(False)
            b.add(icons.Icon(ic, 14, "muted"))
            b.set_halign(al)
            b.set_valign(Gtk.Align.CENTER)
            b.set_margin_start(10)
            b.set_margin_end(10)
            b.set_tooltip_text(tip)
            self.canvas_overlay.add_overlay(b)
        self.arrow_prev.connect("clicked", lambda b: self.go(-1))
        self.arrow_next.connect("clicked", lambda b: self.go(1))
        self.arrow_prev.connect("enter-notify-event", lambda *_: (self._set_arrows(True), False)[1])
        self.arrow_next.connect("enter-notify-event", lambda *_: (self._set_arrows(True), False)[1])
        row.pack_start(self.canvas_overlay, True, True, 0)

        self.info_panel = InfoPanel(lambda: self.toggle_info(False), self.open_resize, self.copy_path,
                                    self.open_location, self.rename_current)
        self.info_rev = Gtk.Revealer()
        self.info_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.info_rev.set_transition_duration(200)
        wrap = Gtk.Box()
        wrap.set_margin_end(8)
        wrap.set_margin_bottom(8)
        wrap.set_margin_start(4)
        wrap.pack_start(self.info_panel, True, True, 0)
        self.info_rev.add(wrap)
        row.pack_start(self.info_rev, False, False, 0)

        self.film = Filmstrip()
        self.film.connect("picked", lambda f, i: self.goto(i))
        self.film_rev = Gtk.Revealer()
        self.film_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.film_rev.set_transition_duration(200)
        self.film_rev.add(self.film)
        vpage.pack_start(self.film_rev, False, False, 0)

        # bottom bar
        self.bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.bottom.get_style_context().add_class("bottombar")
        self.bottom.set_size_request(-1, 32)
        left = Gtk.Box(spacing=2)
        self.btn_film = ui.icon_button("filmstrip", _("Show filmstrip (F)"), classes=["flat-icon", "bar"], size=18)
        self.btn_film.connect("clicked", lambda b: self.toggle_filmstrip())
        self.btn_slide = ui.icon_button("slideshow", _("Start slideshow (F5)"), classes=["flat-icon", "bar"], size=18,
                                        on_click=self.start_slideshow)
        left.pack_start(self.btn_film, False, False, 0)
        left.pack_start(self.btn_slide, False, False, 0)
        self.meta_box = Gtk.Box(spacing=2)
        self.lb_type = ui.label("")
        self.lb_dims = ui.label("")
        self.lb_size = ui.label("")
        self.meta_box.pack_start(ui.separator_v(), False, False, 4)
        self.meta_box.pack_start(self.lb_type, False, False, 4)
        self.meta_box.pack_start(ui.separator_v(), False, False, 4)
        self.meta_box.pack_start(icons.Icon("dimensions", 14, "muted"), False, False, 2)
        self.meta_box.pack_start(self.lb_dims, False, False, 2)
        self.meta_box.pack_start(ui.separator_v(), False, False, 4)
        self.meta_box.pack_start(icons.Icon("disk", 14, "muted"), False, False, 2)
        self.meta_box.pack_start(self.lb_size, False, False, 2)
        left.pack_start(self.meta_box, False, False, 0)
        self.bottom.pack_start(left, False, False, 6)

        self.btn_info = ui.icon_button("info", _("File info (Alt+Enter)"), classes=["flat-icon", "bar"], size=18)
        self.btn_info.connect("clicked", lambda b: self.toggle_info())
        self.bottom.set_center_widget(self.btn_info)

        right = Gtk.Box(spacing=2)
        self.btn_fit = ui.icon_button("fit", _("Fit to window (Ctrl+0)"), classes=["flat-icon", "bar"], size=18)
        self.btn_fit.connect("clicked", lambda b: self.toggle_fit_button())
        self.zoom_combo = ZoomCombo()
        self.zoom_combo.connect("zoom-requested", lambda c, z: self.canvas.zoom_to(z))
        self.btn_zout = ui.icon_button("zoom-out", _("Zoom out (Ctrl+Minus)"), classes=["flat-icon", "bar"], size=18,
                                       on_click=lambda: self.canvas.zoom_step(-1))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 800, 1)
        self.scale.set_draw_value(False)
        self.scale.set_size_request(130, -1)
        self.scale.get_style_context().add_class("fscale")
        self.scale.set_tooltip_text(_("Zoom"))
        self.scale.connect("value-changed", self._on_scale)
        self.btn_zin = ui.icon_button("zoom-in", _("Zoom in (Ctrl+Plus)"), classes=["flat-icon", "bar"], size=18,
                                      on_click=lambda: self.canvas.zoom_step(1))
        self.btn_zmore = ui.icon_button("more", _("More options for zoom controls"), classes=["flat-icon", "bar"], size=18)
        ui.menu_button(self.btn_zmore, self._build_zoom_menu, position=Gtk.PositionType.TOP, min_width=180)
        self.btn_full = ui.icon_button("fullscreen", _("Full screen (F11)"), classes=["flat-icon", "bar"], size=18,
                                       on_click=self.toggle_fullscreen)
        for w in (self.btn_fit, self.zoom_combo, self.btn_zout, self.scale, self.btn_zin, self.btn_zmore):
            right.pack_start(w, False, False, 0)
        right.pack_start(ui.separator_v(), False, False, 4)
        right.pack_start(self.btn_full, False, False, 0)
        self.bottom.pack_end(right, False, False, 6)
        vpage.pack_end(self.bottom, False, False, 0)
        self.vpage = vpage
        self._editor_widgets()

    def _editor_widgets(self):
        self.editor_back.set_no_show_all(True)

    # ───────────────────────── menus ─────────────────────────
    def _build_share_menu(self, m):
        it = self.item
        m.add_item(_("Copy file"), lambda: (actions.copy_file_to_clipboard([it.path]),
                                              ui.toast(self.overlay, _("File copied"))), icon="copy")
        m.add_item(_("Send by email"), lambda: actions.share_by_email(it.path), icon="mail")
        m.add_item(_("Copy path"), self.copy_path, icon="link")

    def _build_more_menu(self, m):
        if self.compact:
            m.add_item(_("Print"), self.print_current, icon="print", shortcut="Ctrl+P")
            m.add_item(_("Share"), None, icon="share", submenu=self._build_share_menu)
            m.add_item(_("Open with"), None, icon="open-with", submenu=self._build_open_with_menu)
            m.add_sep()
        m.add_item(_("Save as"), self.save_as, icon="save", shortcut="Ctrl+S")
        m.add_item(_("Copy"), self.copy_image, icon="copy", shortcut="Ctrl+C")
        m.add_sep()
        m.add_item(_("Resize image"), self.open_resize, icon="image-size")

        def sub(sm):
            sm.add_item(_("Desktop background"), self.set_wallpaper, shortcut="Ctrl+B")
        m.add_item(_("Set as"), None, icon="wallpaper", submenu=sub)
        m.add_sep()
        m.add_item(_("Settings"), self.app_ref.open_settings, icon="settings")

    def _build_open_with_menu(self, m):
        m.add_item(_("File manager"), lambda: actions.reveal_in_file_manager(self.item.path), icon="folder",
                   subtitle=_("Open the containing folder"))
        m.add_item(_("Gallery"), self.app_ref.open_gallery, icon="photo", subtitle=_("Browse the whole collection"))
        try:
            mime = Gio.content_type_guess(self.item.path, None)[0]
            apps = [a for a in Gio.AppInfo.get_all_for_type(mime) if "photos" not in (a.get_id() or "").lower()][:3]
        except Exception:  # noqa: BLE001
            apps = []
        if apps:
            m.add_sep()
        for a in apps:
            m.add_item(a.get_display_name(), lambda a=a: a.launch([Gio.File.new_for_path(self.item.path)], None),
                       icon="open-with")
        m.add_sep()
        m.add_item(_("Choose another app"), lambda: actions.open_with_chooser(self, self.item.path))

    def _build_zoom_menu(self, m):
        for p in ZOOM_PRESETS_MENU:
            m.add_item("%d%%" % p, lambda p=p: self.canvas.zoom_to(p / 100.0), mark=(round(self.canvas.zoom * 100) == p),
                       indent_mark=True)

    # ───────────────────────── carregamento ─────────────────────────
    @property
    def item(self):
        return self.items[self.index]

    def _read(self, path):
        """(pixbuf, animation|None) with the EXIF orientation applied."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".svg":
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, 2400, 2400)
            return pb, None
        anim = None
        if ext in (".gif", ".webp"):
            try:
                anim = GdkPixbuf.PixbufAnimation.new_from_file(path)
                if anim.is_static_image():
                    anim = None
            except GLib.Error:
                anim = None
        pb = GdkPixbuf.Pixbuf.new_from_file(path)
        pb = pb.apply_embedded_orientation() or pb
        return pb, anim

    def load_current(self, transition=None):
        item = self.item
        self.load_token += 1
        token = self.load_token
        self.title_lb.set_text(item.name)
        self.set_title(item.name)
        self._update_bar_meta()
        self.film.set_items(self.items, self.index)
        self.arrow_prev.set_visible(self.index > 0 and self.arrows_wanted)
        self.arrow_next.set_visible(self.index < len(self.items) - 1 and self.arrows_wanted)
        if item.kind == "video":
            ph = thumbs.cache.best(item)
            self.canvas.clear()
            if ph is not None:
                self.canvas.show_placeholder(ph, ph.get_width(), ph.get_height())
            try:
                Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(item.path).get_uri(), None)
            except GLib.Error:
                pass
            return
        cached = self.cache.get(item.path)
        if cached is not None:
            self.cache.move_to_end(item.path)
            self._show(item, cached[0], cached[1], transition)
            self._preload()
            return
        ph = thumbs.cache.best(item)
        if ph is not None and item.w and item.h:
            self.canvas.show_placeholder(ph, item.w, item.h)
        elif self.canvas.pb is None:
            self.canvas.clear()
        threading.Thread(target=self._load_thread, args=(item, token, transition), daemon=True).start()

    def _load_thread(self, item, token, transition):
        try:
            pb, anim = self._read(item.path)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._load_failed, token, str(exc))
            return
        GLib.idle_add(self._loaded, item, token, pb, anim, transition)

    def _load_failed(self, token, msg):
        if token == self.load_token:
            self.canvas.clear()
            ui.toast(self.overlay, _("Could not open this image."))
        return False

    def _loaded(self, item, token, pb, anim, transition):
        self._remember(item.path, pb, anim)
        if token == self.load_token:
            self._show(item, pb, anim, transition)
            self._preload()
        return False

    def _remember(self, path, pb, anim):
        self.cache[path] = (pb, anim)
        while len(self.cache) > 4:
            self.cache.popitem(last=False)

    def _show(self, item, pb, anim, transition):
        if self.slideshow:
            transition = "cross"
        self.canvas.set_pixbuf(pb, anim, transition)
        item.w, item.h = pb.get_width(), pb.get_height()
        self.current_pb = pb
        self._update_bar_meta()
        if self.info_rev.get_reveal_child():
            self.info_panel.update(item, item.w, item.h)

    def _preload(self):
        for d in (1, -1):
            j = self.index + d
            if 0 <= j < len(self.items) and self.items[j].kind == "photo" and self.items[j].path not in self.cache:
                it = self.items[j]
                threading.Thread(target=self._preload_thread, args=(it,), daemon=True).start()
                break

    def _preload_thread(self, it):
        try:
            pb, anim = self._read(it.path)
        except Exception:  # noqa: BLE001
            return
        GLib.idle_add(lambda: (self._remember(it.path, pb, anim), False)[1])

    def _update_bar_meta(self):
        item = self.item
        self.lb_type.set_text(item.ext.lstrip(".").upper())
        self.lb_dims.set_text("%d x %d" % (item.w, item.h) if item.w else "")
        self.lb_size.set_text(library.fmt_size(item.size))

    # ───────────────────────── navigation ─────────────────────────
    def go(self, d):
        self.goto(self.index + d)

    def goto(self, i):
        if i < 0 or i >= len(self.items) or i == self.index:
            return
        d = 1 if i > self.index else -1
        self.index = i
        self.film.set_index(i)
        self.load_current(transition="next" if d > 0 else "prev")

    # ───────────────────────── zoom ─────────────────────────
    def _on_zoom_changed(self, c, z):
        self.zoom_combo.set_percent(z)
        self.zoom_updating = True
        self.scale.set_value(max(1, min(800, z * 100)))
        self.zoom_updating = False
        fit = c.is_fit() and c.zoom < 0.999 or (c.is_fit() and c.zoom > 1.001)
        at_fit = c.is_fit()
        want = "actual" if at_fit and abs(c.zoom - 1.0) > 0.01 else "fit"
        self.btn_fit.icon.set_icon(want)
        self.btn_fit.set_tooltip_text(_("View actual size (Ctrl+1)") if want == "actual" else _("Fit to window (Ctrl+0)"))

    def _on_scale(self, sc):
        if not self.zoom_updating:
            self.canvas.zoom_to(sc.get_value() / 100.0, animate=False)

    def toggle_fit_button(self):
        if self.canvas.is_fit() and abs(self.canvas.zoom - 1.0) > 0.01:
            self.canvas.actual()
        else:
            self.canvas.fit()

    # ───────────────────────── arrows, filmstrip, panel ─────────────────────────
    arrows_wanted = False

    def _set_arrows(self, on):
        if on == self.arrows_wanted and self.arrow_prev.get_visible() == (on and self.index > 0):
            return
        self.arrows_wanted = on
        self.arrow_prev.set_visible(on and self.index > 0)
        self.arrow_next.set_visible(on and self.index < len(self.items) - 1)
        if on:
            for b in (self.arrow_prev, self.arrow_next):
                if b.get_visible():
                    b.set_opacity(0.0)
                    ui.Anim(b, 140, lambda t, b=b: b.set_opacity(t))

    def _on_canvas_motion(self, w, ev):
        W = w.get_allocated_width()
        near = ev.x < 90 or ev.x > W - 90
        self._set_arrows(near)
        self._on_activity()
        return False

    def toggle_filmstrip(self, force=None):
        on = (not self.film_rev.get_reveal_child()) if force is None else force
        self.film_rev.set_reveal_child(on)
        settings.set("filmstrip", on)
        (self.btn_film.get_style_context().add_class if on else self.btn_film.get_style_context().remove_class)("sel-on")
        if on:
            self.film.center_current(False)

    def toggle_info(self, force=None):
        on = (not self.info_rev.get_reveal_child()) if force is None else force
        self.info_rev.set_reveal_child(on)
        settings.set("info_open", on)
        (self.btn_info.get_style_context().add_class if on else self.btn_info.get_style_context().remove_class)("sel-on")
        if on:
            self.info_panel.update(self.item, self.item.w, self.item.h)

    # ───────────────────────── window ─────────────────────────
    def _on_size(self, w, alloc):
        self._apply_compact(alloc.width < NARROW)
        if not (self.is_maximized() or self.fullscreen_on):
            settings.set("viewer_size", list(self.get_size()))

    def _on_state(self, w, ev):
        if ev.changed_mask & Gdk.WindowState.MAXIMIZED:
            settings.set("viewer_maximized", bool(ev.new_window_state & Gdk.WindowState.MAXIMIZED))
        if ev.changed_mask & Gdk.WindowState.FULLSCREEN:
            self.fullscreen_on = bool(ev.new_window_state & Gdk.WindowState.FULLSCREEN)
            self.btn_full.icon.set_icon("unfullscreen" if self.fullscreen_on else "fullscreen")
            if not self.slideshow:
                if self.fullscreen_on:
                    self._fs_activity()
                else:
                    self._fs_show(True)
            if not self.fullscreen_on and self.slideshow:
                self.stop_slideshow()
        return False

    def _apply_compact(self, compact):
        if compact == self.compact:
            return
        self.compact = compact
        for w in (self.btn_print, self.btn_share, self.btn_open_with, self.btn_zout, self.scale, self.btn_zin):
            w.set_visible(not compact)
        self.btn_zmore.set_visible(compact)
        kids = self.meta_box.get_children()
        for k in kids[:3] + kids[5:]:
            k.set_visible(not compact)

    def toggle_fullscreen(self):
        if self.fullscreen_on:
            self.unfullscreen()
        else:
            self.fullscreen()

    # ───────────────────────── teclado ─────────────────────────
    def _on_key(self, w, ev):
        if ui.dialog_open():
            return False
        if ev.keyval == Gdk.KEY_Escape and ui.popover_recent():
            return True
        if self.stack.get_visible_child_name() == "editor":
            return False
        if isinstance(self.get_focus(), Gtk.Entry):
            if ev.keyval == Gdk.KEY_Escape:
                self.set_focus(None)
                return True
            return False
        k = ev.keyval
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(ev.state & Gdk.ModifierType.MOD1_MASK)
        if self.slideshow:
            if k == Gdk.KEY_Escape:
                self.stop_slideshow()
            elif k in (Gdk.KEY_Right, Gdk.KEY_space):
                self.slideshow.next()
            elif k == Gdk.KEY_Left:
                self.slideshow.prev()
            return True
        if k in (Gdk.KEY_Right, Gdk.KEY_Page_Down, Gdk.KEY_Down) and not ctrl:
            self.go(1)
        elif k in (Gdk.KEY_Left, Gdk.KEY_Page_Up, Gdk.KEY_Up) and not ctrl:
            self.go(-1)
        elif k == Gdk.KEY_Home:
            self.goto(0)
        elif k == Gdk.KEY_End:
            self.goto(len(self.items) - 1)
        elif k == Gdk.KEY_Escape:
            if self.fullscreen_on:
                self.unfullscreen()
            else:
                self.close()
        elif k == Gdk.KEY_F11:
            self.toggle_fullscreen()
        elif k == Gdk.KEY_F5:
            self.start_slideshow()
        elif k == Gdk.KEY_Delete:
            self.delete_current()
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and alt:
            self.toggle_info()
        elif k in (Gdk.KEY_f, Gdk.KEY_F) and not ctrl:
            self.toggle_filmstrip()
        elif k == Gdk.KEY_F2:
            self.rename_current()
        elif ctrl and k in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.canvas.fit()
        elif ctrl and k in (Gdk.KEY_1, Gdk.KEY_KP_1):
            self.canvas.actual()
        elif ctrl and k in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.canvas.zoom_step(1)
        elif ctrl and k in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.canvas.zoom_step(-1)
        elif ctrl and k in (Gdk.KEY_r, Gdk.KEY_R):
            self.rotate()
        elif ctrl and k in (Gdk.KEY_e, Gdk.KEY_E):
            self.open_editor()
        elif ctrl and k in (Gdk.KEY_p, Gdk.KEY_P):
            self.print_current()
        elif ctrl and k in (Gdk.KEY_s, Gdk.KEY_S):
            self.save_as()
        elif ctrl and k in (Gdk.KEY_c, Gdk.KEY_C):
            self.copy_image()
        elif ctrl and k in (Gdk.KEY_b, Gdk.KEY_B):
            self.set_wallpaper()
        elif alt and k == Gdk.KEY_Up:
            self.btn_share.clicked()
        else:
            return False
        return True

    # ───────────────────────── actions ─────────────────────────
    def delete_current(self):
        item = self.item

        def do():
            try:
                actions.move_to_trash(item.path)
            except GLib.Error as exc:
                ui.toast(self.overlay, _("Could not delete: %s") % exc.message)
                return
            self._after_removed(item)
        if settings.get("confirm_delete"):
            def ok(dont_show):
                if dont_show:
                    settings.set("confirm_delete", False)
                do()
            ui.confirm(self.overlay, _("Delete this file?"), _("Are you sure you want to delete this file?"),
                       _("Delete"), _("Cancel"), ok, checkbox=_("Don't show this warning again"))
        else:
            do()

    def _after_removed(self, item):
        self.cache.pop(item.path, None)
        pos = self.items.index(item)
        del self.items[pos]
        self.app_ref.notify_removed([item.path])
        if not self.items:
            self.close()
            return
        self.index = min(pos, len(self.items) - 1)
        self.load_current(transition="fade")

    def rotate(self):
        item = self.item
        try:
            with Image.open(item.path) as im:
                im.load()
                from PIL import ImageOps
                exif = im.getexif()
                im2 = ImageOps.exif_transpose(im).rotate(-90, expand=True)
                exif[274] = 1
                kwargs = {"exif": exif} if item.ext in (".jpg", ".jpeg", ".jpe", ".jfif") else {}
                if item.ext in (".jpg", ".jpeg", ".jpe", ".jfif"):
                    kwargs.update({"quality": 95})
                fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG", ".png": "PNG", ".webp": "WEBP",
                       ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF"}.get(item.ext)
                if fmt is None:
                    raise ValueError(_("Format not supported for rotation"))
                if fmt == "JPEG" and im2.mode not in ("RGB", "L"):
                    im2 = im2.convert("RGB")
                im2.save(item.path, fmt, **kwargs)
        except Exception as exc:  # noqa: BLE001
            ui.toast(self.overlay, _("Could not rotate: %s") % exc)
            return
        self._file_changed(item)

    def _file_changed(self, item):
        st = os.stat(item.path)
        item.size = st.st_size
        item.mtime = st.st_mtime
        self.cache.pop(item.path, None)
        thumbs.cache.invalidate(item.path)
        item.w = item.h = 0
        library.read_meta(item)
        if item is self.item:
            self.load_current(transition="fade")
        self.app_ref.notify_changed(item.path)

    def print_current(self):
        if self.current_pb:
            actions.print_pixbuf(self, self.current_pb, self.item.name)

    def copy_image(self):
        if self.current_pb:
            actions.copy_image_to_clipboard(self.current_pb)
            ui.toast(self.overlay, _("Image copied"))

    def copy_path(self):
        actions.copy_path_to_clipboard(self.item.path)
        ui.toast(self.overlay, _("Path copied"))

    def open_location(self):
        actions.reveal_in_file_manager(self.item.path)

    def set_wallpaper(self):
        ok = actions.set_wallpaper(self.item.path)
        ui.toast(self.overlay, _("Desktop background set") if ok else _("Could not set the desktop background"))

    def save_as(self):
        item = self.item
        stem = os.path.splitext(item.name)[0]

        def write(path):
            try:
                with Image.open(item.path) as im:
                    from PIL import ImageOps
                    im.load()
                    dialogs.pil_save(ImageOps.exif_transpose(im), path)
                ui.toast(self.overlay, _("Image saved: %s") % os.path.basename(path))
                self.app_ref.notify_library_changed()
            except Exception as exc:  # noqa: BLE001
                ui.toast(self.overlay, _("Could not save: %s") % exc)
        dialogs.file_chooser_save(self, stem + _(" (copy)") + item.ext, item.folder, write)

    def open_resize(self):
        try:
            dialogs.ResizeDialog(self, self.item)
        except Exception as exc:  # noqa: BLE001
            ui.toast(self.overlay, _("Could not open the image: %s") % exc)

    def rename_current(self):
        item = self.item

        def done(dest):
            old = item.path
            self.cache.pop(old, None)
            item.path = dest
            item.name = os.path.basename(dest)
            self.title_lb.set_text(item.name)
            self.info_panel.update(item, item.w, item.h)
            self.app_ref.notify_renamed(old, dest)
        dialogs.rename_dialog(self, item, done)

    # ───────────────────────── editor ─────────────────────────
    def open_editor(self):
        if self.item.kind != "photo":
            return
        from .editor import EditorView
        if self.editor is not None:
            return
        try:
            self.editor = EditorView(self, self.item)
        except Exception as exc:  # noqa: BLE001
            self.editor = None
            ui.toast(self.overlay, _("Could not open the editor: %s") % exc)
            return
        self.stack.add_named(self.editor, "editor")
        self.editor.show_all()
        self.tools.hide()
        self.btn_open_with.hide()
        self.editor_back.set_no_show_all(False)
        self.editor_back.show_all()
        self.stack.set_visible_child_name("editor")
        self.editor.grab_focus()

    def close_editor(self, saved_path=None):
        if self.editor is None:
            return
        ed = self.editor
        self.editor = None
        self.stack.set_visible_child_name("viewer")

        def cleanup():
            self.stack.remove(ed)
            ed.destroy()
            return False
        GLib.timeout_add(260, cleanup)
        self.tools.show()
        self.btn_open_with.set_visible(not self.compact)
        self.editor_back.hide()
        self.editor_back.set_no_show_all(True)
        self.title_lb.set_text(self.item.name)
        if saved_path:
            if saved_path == self.item.path:
                self._file_changed(self.item)
            else:
                self.app_ref.notify_library_changed()
        self.canvas.grab_focus()

    # ───────────────────────── slideshow ─────────────────────────
    def start_slideshow(self):
        if self.slideshow or self.editor is not None:
            return False
        photos = [i for i in self.items if i.kind == "photo"]
        if not photos:
            return False
        from .slideshow import Slideshow
        self.slideshow = Slideshow(self)
        return False

    def stop_slideshow(self):
        if self.slideshow:
            s = self.slideshow
            self.slideshow = None
            s.finish()
            if self.fullscreen_on:
                self.unfullscreen()

    def _on_activity(self, *_):
        if self.slideshow:
            self.slideshow.activity()
        elif self.fullscreen_on:
            self._fs_activity()

    _fs_timer = 0

    def _fs_show(self, on):
        """Viewer bars in full screen: they hide when the mouse stays still."""
        if self.editor is not None or self.slideshow:
            return
        self.hb.set_visible(on)
        self.bottom.set_visible(on)
        if not on:
            win = self.get_window()
            if win is not None:
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "none"))
        else:
            win = self.get_window()
            if win is not None:
                win.set_cursor(None)

    def _fs_activity(self):
        self._fs_show(True)
        if self._fs_timer:
            GLib.source_remove(self._fs_timer)
        self._fs_timer = GLib.timeout_add(2500, self._fs_idle) if self.fullscreen_on else 0

    def _fs_idle(self):
        self._fs_timer = 0
        if self.fullscreen_on:
            self._fs_show(False)
        return False


ZOOM_PRESETS_MENU = [800, 700, 600, 500, 400, 300, 200, 100, 75, 50, 25, 10]

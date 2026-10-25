# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Main window: sidebar, Gallery (grid), folders, favorites and settings."""
import datetime
import os
import shutil
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import actions, dialogs, icons, library, settings, theme, thumbs, ui
from .i18n import _, ngettext  # noqa: F401
from .grid import GalleryGrid


def count_text(items):
    p = sum(1 for i in items if i.kind == "photo")
    v = len(items) - p
    parts = []
    if p or not v:
        parts.append(ngettext("%d photo", "%d photos", p))
    if v:
        parts.append(ngettext("%d video", "%d videos", v))
    return _("%s and %s") % tuple(parts) if len(parts) == 2 else parts[0]


class SideItem(Gtk.EventBox):
    """Sidebar row: highlight bar + icon + label (+ extra action)."""

    def __init__(self, icon, text, on_click, extra=None, depth=0, expander=None):
        super().__init__()
        self.on_click = on_click
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.box = Gtk.Box(spacing=12)
        self.box.get_style_context().add_class("side-item")
        self.box.set_margin_start(4 + depth * 14)
        self.bar = Gtk.Box()
        self.bar.get_style_context().add_class("side-bar")
        self.bar.set_valign(Gtk.Align.CENTER)
        self.bar.set_opacity(0)
        self.overlay = Gtk.Overlay()
        self.overlay.add(self.box)
        self.bar.set_halign(Gtk.Align.START)
        self.bar.set_margin_start(0 + depth * 14)
        self.overlay.add_overlay(self.bar)
        self.overlay.set_overlay_pass_through(self.bar, True)
        self.icon = icons.Icon(icon, 20, "fg")
        self.label = ui.label(text, ellipsize=True)
        self.box.pack_start(self.icon, False, False, 0)
        self.box.pack_start(self.label, True, True, 0)
        self.extra = extra
        if expander:
            self.box.pack_end(expander, False, False, 0)
        if extra:
            self.box.pack_end(extra, False, False, 0)
        self.add(self.overlay)
        self.connect("button-press-event", self._press)

    def _press(self, w, ev):
        if ev.button == 1:
            self.on_click()
        return False

    def set_selected(self, on):
        ctx = self.box.get_style_context()
        (ctx.add_class if on else ctx.remove_class)("selected")
        self.bar.set_opacity(1 if on else 0)

    def set_collapsed(self, on):
        self.label.set_visible(not on)
        if self.extra:
            self.extra.set_visible(not on)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.app_ref = app
        self.get_style_context().add_class("photos")
        self.set_title(_("Photos"))
        self.set_icon_name("photos")
        self.set_default_size(*settings.get("main_size"))
        if settings.get("main_maximized"):
            self.maximize()
        self.all_items = []
        self.view = ("gallery", None)
        self.query = ""
        self.scanner = None
        self.refresh_timer = 0
        self.last_scan = 0
        self.side_items = {}
        self.folder_rows = {}
        self.sidebar_collapsed = not settings.get("sidebar_open")
        self._build()
        self.connect("size-allocate", self._on_size)
        self.connect("window-state-event", self._on_state)
        self.connect("key-press-event", self._on_key)
        self.connect("notify::is-active", self._on_active)
        self.show_all()
        self.set_view(("gallery", None))
        self.rescan()

    # ───────────────────────── construction ─────────────────────────
    def _build(self):
        hb = Gtk.HeaderBar()
        hb.get_style_context().add_class("photos-hb")
        hb.set_show_close_button(True)
        hb.set_decoration_layout(":minimize,maximize,close")
        self.hb = hb
        title = Gtk.Box(spacing=10)
        title.set_margin_start(8)
        title.pack_start(icons.Icon("photo", 20, "accent"), False, False, 0)
        title.pack_start(ui.label(_("Photos"), ["photos-hb-title"]), False, False, 0)
        hb.pack_start(title)
        self.search = Gtk.SearchEntry()
        self.search.get_style_context().add_class("fsearch")
        self.search.set_placeholder_text(_("Search the Gallery"))
        self.search.set_size_request(560, 32)
        self.search.connect("search-changed", self._on_search)
        self.search.set_valign(Gtk.Align.CENTER)
        hb.set_custom_title(self.search)
        self.btn_settings = ui.icon_button("settings", _("Settings"), classes=["flat-icon"], on_click=self.app_ref.open_settings)
        self.btn_import = ui.icon_button("import", _("Import photos"), label=_("Import"), classes=["subtle"])
        ui.menu_button(self.btn_import, self._build_import_menu, min_width=240)
        hb.pack_end(self.btn_settings)
        hb.pack_end(self.btn_import)
        self.set_titlebar(hb)

        self.overlay = Gtk.Overlay()
        self.add(self.overlay)
        self.pages = Gtk.Stack()
        self.pages.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pages.set_transition_duration(150)
        self.overlay.add(self.pages)

        main = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main.get_style_context().add_class("photos-root")
        main.get_style_context().add_class("fpaned")
        self.paned = main
        self.pages.add_named(main, "main")
        self._build_sidebar(main)
        self._build_content(main)
        main.set_position(52 if self.sidebar_collapsed else settings.get("sidebar_width"))
        main.connect("notify::position", self._on_paned)
        from .settingspage import SettingsPage
        self.settings_page = SettingsPage(self)
        self.pages.add_named(self.settings_page, "settings")

    def _build_sidebar(self, main):
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.get_style_context().add_class("sidebar")
        self.sidebar.set_size_request(52, -1)
        main.pack1(self.sidebar, False, False)
        burger = ui.icon_button("menu", _("Close navigation"), classes=["flat-icon"], on_click=self.toggle_sidebar)
        burger.set_halign(Gtk.Align.START)
        burger.set_margin_start(4)
        burger.set_margin_top(2)
        burger.set_margin_bottom(6)
        self.burger = burger
        self.sidebar.pack_start(burger, False, False, 0)

        add = ui.icon_button("folder-plus", _("Add folder"), classes=["flat-icon"], size=18, on_click=self.add_folder)
        add.set_size_request(28, 28)
        self.item_gallery = SideItem("photo", _("Gallery"), lambda: self.set_view(("gallery", None)), extra=add)
        self.item_fav = SideItem("heart", _("Favorites"), lambda: self.set_view(("favorites", None)))
        self.sidebar.pack_start(self.item_gallery, False, False, 0)
        self.sidebar.pack_start(self.item_fav, False, False, 0)
        sep = Gtk.Box()
        sep.get_style_context().add_class("side-sep")
        sep.set_size_request(-1, 1)
        sep.set_margin_start(4)
        sep.set_margin_end(4)
        self.sidebar.pack_start(sep, False, False, 6)

        chev = ui.icon_button("chev-down", None, classes=["flat-icon", "side-expander"], size=14, role="muted")
        chev.set_size_request(24, 24)
        self.item_pc = SideItem("computer", _("This computer"), self._toggle_tree, expander=chev)
        self.tree_chev = chev
        chev.connect("clicked", lambda b: self._toggle_tree())
        self.sidebar.pack_start(self.item_pc, False, False, 0)
        self.tree_rev = Gtk.Revealer()
        self.tree_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.tree_rev.set_reveal_child(True)
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(80)
        self.tree_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sc.add(self.tree_box)
        self.tree_rev.add(sc)
        self.sidebar.pack_start(self.tree_rev, True, True, 0)
        self.side_items = {("gallery", None): self.item_gallery, ("favorites", None): self.item_fav}
        self._rebuild_tree()

    def _toggle_tree(self):
        on = not self.tree_rev.get_reveal_child()
        self.tree_rev.set_reveal_child(on)
        self.tree_chev.icon.set_icon("chev-down" if on else "chev-right")

    def sources(self):
        out = [library.pictures_dir()]
        for f in settings.get("folders"):
            if f not in out and os.path.isdir(f):
                out.append(f)
        return [f for f in out if os.path.isdir(f)]

    def _rebuild_tree(self):
        for c in self.tree_box.get_children():
            self.tree_box.remove(c)
        for k in [k for k in self.side_items if k[0] == "folder"]:
            del self.side_items[k]
        for f in self.sources():
            self._add_folder_row(self.tree_box, f, 1, root=True)
        self.tree_box.show_all()
        self._sync_side_selection()

    def _subdirs(self, path):
        try:
            with os.scandir(path) as it:
                return sorted([e.path for e in it if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")],
                              key=lambda p: library.strip_accents(os.path.basename(p)))
        except OSError:
            return []

    def _add_folder_row(self, parent, path, depth, root=False):
        subs = self._subdirs(path)
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        chev = None
        if subs:
            chev = ui.icon_button("chev-right", None, classes=["flat-icon", "side-expander"], size=14, role="muted")
            chev.set_size_request(24, 24)
        name = os.path.basename(path.rstrip("/")) or path
        item = SideItem("folder", name, lambda p=path: self.set_view(("folder", p)), depth=depth, expander=chev)
        item.box.get_style_context().add_class("tree-item")
        item.set_tooltip_text(path)
        self.side_items[("folder", path)] = item
        wrap.pack_start(item, False, False, 0)
        if subs:
            rev = Gtk.Revealer()
            rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
            child_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            rev.add(child_box)
            wrap.pack_start(rev, False, False, 0)
            state = {"loaded": False}

            def toggle(_b=None, rev=rev, child_box=child_box, subs=subs, chev=chev, depth=depth, state=state):
                on = not rev.get_reveal_child()
                if on and not state["loaded"]:
                    state["loaded"] = True
                    for s in subs:
                        self._add_folder_row(child_box, s, depth + 1)
                    child_box.show_all()
                rev.set_reveal_child(on)
                chev.icon.set_icon("chev-down" if on else "chev-right")
            chev.connect("clicked", toggle)
        parent.pack_start(wrap, False, False, 0)
        wrap.show_all()

    def _on_paned(self, paned, _p):
        pos = paned.get_position()
        if not self.sidebar_collapsed and pos >= 160:
            settings.set("sidebar_width", pos)

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        settings.set("sidebar_open", not self.sidebar_collapsed)
        w = 52 if self.sidebar_collapsed else settings.get("sidebar_width")
        self.paned.set_position(w)
        for it in (self.item_gallery, self.item_fav, self.item_pc):
            it.set_collapsed(self.sidebar_collapsed)
        self.tree_rev.set_visible(not self.sidebar_collapsed)
        self.burger.set_tooltip_text(_("Open navigation") if self.sidebar_collapsed else _("Close navigation"))

    def _build_content(self, main):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.get_style_context().add_class("content-panel")
        main.pack2(panel, True, False)
        head = Gtk.Box()
        head.set_margin_start(48)
        head.set_margin_end(48)
        head.set_margin_top(28)
        head.set_margin_bottom(6)
        self.head_stack = Gtk.Stack()
        self.head_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.head_stack.set_transition_duration(120)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        trow = Gtk.Box(spacing=10)
        self.title_icon = icons.Icon("photo", 22, "fg")
        self.title_lb = ui.label(_("Gallery"), ["page-title"])
        trow.pack_start(self.title_icon, False, False, 0)
        trow.pack_start(self.title_lb, False, False, 0)
        left.pack_start(trow, False, False, 0)
        self.sub_lb = ui.label("", ["page-sub"])
        left.pack_start(self.sub_lb, False, False, 0)
        self.head_stack.add_named(left, "normal")
        selcard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        selcard.get_style_context().add_class("selection-card")
        self.sel_title = ui.label("", ["sel-title"])
        selcard.pack_start(self.sel_title, False, False, 0)
        self.sel_sub = ui.label(_("Gallery"), ["page-sub"])
        selcard.pack_start(self.sel_sub, False, False, 0)
        selcard.set_halign(Gtk.Align.START)
        self.head_stack.add_named(selcard, "select")
        self.head_stack.set_halign(Gtk.Align.START)
        self.head_stack.set_valign(Gtk.Align.CENTER)
        head.pack_start(self.head_stack, True, True, 0)

        tools = Gtk.Box(spacing=2)
        tools.set_valign(Gtk.Align.START)
        self.tool_stack = Gtk.Stack()
        self.tool_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.tool_stack.set_transition_duration(120)
        nb = Gtk.Box(spacing=2)
        self.btn_select = ui.icon_button("select", _("Select"), label=_("Select"), classes=["subtle"], on_click=lambda: self.set_select_mode(True))
        self.btn_slide = ui.icon_button("slideshow", _("Start slideshow (F5)"), classes=["flat-icon"], on_click=self.slideshow_all)
        self.btn_sort = ui.icon_button("sort", _("Sort options and directions"), icon_after="chev-down", classes=["bar"])
        self.btn_filter = ui.icon_button("filter", _("Filter"), icon_after="chev-down", classes=["bar"])
        self.btn_layout = ui.icon_button("layout", _("Gallery types and sizes"), icon_after="chev-down", classes=["bar"])
        self.btn_more = ui.icon_button("more", _("More options"), classes=["flat-icon"])
        ui.menu_button(self.btn_sort, self._build_sort_menu, min_width=220)
        ui.menu_button(self.btn_filter, self._build_filter_menu, min_width=200)
        ui.menu_button(self.btn_layout, self._build_layout_menu, min_width=200)
        ui.menu_button(self.btn_more, self._build_more_menu, min_width=240)
        for b in (self.btn_select, self.btn_slide, self.btn_sort, self.btn_filter, self.btn_layout, self.btn_more):
            nb.pack_start(b, False, False, 0)
        self.tool_stack.add_named(nb, "normal")
        sb = Gtk.Box(spacing=2)
        self.btn_cancel_sel = ui.icon_button("close", _("Cancel"), label=_("Cancel"), classes=["subtle"], on_click=lambda: self.set_select_mode(False))
        self.btn_del_sel = ui.icon_button("trash", _("Delete"), classes=["flat-icon"], on_click=self.delete_selected)
        self.btn_copy_sel = ui.icon_button("copy", _("Copy to folder"), classes=["flat-icon"], on_click=lambda: self.copy_move_selected(False))
        self.btn_move_sel = ui.icon_button("folder-open", _("Move to folder"), classes=["flat-icon"], on_click=lambda: self.copy_move_selected(True))
        self.btn_share_sel = ui.icon_button("share", _("Share"), classes=["flat-icon"], on_click=self.share_selected)
        self.btn_slide_sel = ui.icon_button("slideshow", _("Slideshow"), classes=["flat-icon"], on_click=self.slideshow_selected)
        self.btn_more_sel = ui.icon_button("more", _("More options"), classes=["flat-icon"])
        ui.menu_button(self.btn_more_sel, self._build_more_menu, min_width=240)
        for b in (self.btn_cancel_sel, self.btn_del_sel, self.btn_copy_sel, self.btn_move_sel, self.btn_share_sel,
                  self.btn_slide_sel, self.btn_more_sel):
            sb.pack_start(b, False, False, 0)
        self.tool_stack.add_named(sb, "select")
        tools.pack_start(self.tool_stack, False, False, 0)
        head.pack_end(tools, False, False, 0)
        panel.pack_start(head, False, False, 0)

        self.body = Gtk.Stack()
        self.body.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.body.set_transition_duration(120)
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.grid = GalleryGrid()
        self.grid.vadj = sc.get_vadjustment()
        sc.add(self.grid)
        self.scroll = sc
        self.grid.connect("open-item", self._on_open)
        self.grid.connect("selection-changed", self._on_selection)
        self.grid.connect("context-menu", self._on_context)
        self.grid.connect("delete-request", lambda g: self.delete_selected())
        self.grid.connect("rename-request", lambda g: self.rename_selected())
        self.body.add_named(sc, "grid")
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty.set_valign(Gtk.Align.CENTER)
        empty.set_halign(Gtk.Align.CENTER)
        empty.pack_start(icons.Icon("photo", 48, "faint"), False, False, 0)
        self.empty_title = ui.label(_("No photos here"), ["empty-title"], xalign=0.5)
        self.empty_sub = ui.label("", ["page-sub"], xalign=0.5)
        empty.pack_start(self.empty_title, False, False, 0)
        empty.pack_start(self.empty_sub, False, False, 0)
        add_btn = ui.icon_button("folder-plus", None, label=_("Add folder"), classes=["subtle"], on_click=self.add_folder)
        self.empty_add = add_btn
        add_btn.set_halign(Gtk.Align.CENTER)
        add_btn.set_margin_top(8)
        empty.pack_start(add_btn, False, False, 0)
        self.body.add_named(empty, "empty")
        loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        loading.set_valign(Gtk.Align.CENTER)
        loading.set_halign(Gtk.Align.CENTER)
        sp = Gtk.Spinner()
        sp.set_size_request(32, 32)
        sp.start()
        loading.pack_start(sp, False, False, 0)
        self.body.add_named(loading, "loading")
        panel.pack_start(self.body, True, True, 0)
        self.body.set_visible_child_name("loading")

    # ───────────────────────── menus ─────────────────────────
    def _build_sort_menu(self, m):
        by = settings.get("sort_by")
        for key, text in (("taken", _("Date taken")), ("created", _("Date created")), ("modified", _("Date modified")),
                          ("name", _("Name"))):
            m.add_item(text, lambda k=key: self._set_setting("sort_by", k), mark=(by == key), indent_mark=True)
        m.add_sep()
        d = settings.get("sort_desc")
        m.add_item(_("Ascending"), lambda: self._set_setting("sort_desc", False), mark=not d, indent_mark=True)
        m.add_item(_("Descending"), lambda: self._set_setting("sort_desc", True), mark=d, indent_mark=True)

    def _build_filter_menu(self, m):
        cur = settings.get("media_filter")
        for key, text in (("all", _("All media")), ("photos", _("Photos")), ("videos", _("Videos"))):
            m.add_item(text, lambda k=key: self._set_setting("media_filter", k), mark=(cur == key), indent_mark=True)

    def _build_layout_menu(self, m):
        lay = settings.get("layout")
        size = settings.get("tile_size")
        m.add_item(_("Cascade"), lambda: self._set_setting("layout", "cascade"), mark=(lay == "cascade"), indent_mark=True)
        m.add_item(_("Square"), lambda: self._set_setting("layout", "square"), mark=(lay == "square"), indent_mark=True)
        m.add_sep()
        for key, text in (("small", _("Small")), ("medium", _("Medium")), ("large", _("Large"))):
            m.add_item(text, lambda k=key: self._set_setting("tile_size", k), mark=(size == key), indent_mark=True)

    def _build_more_menu(self, m):
        m.add_item(_("Select all"), lambda: (self.set_select_mode(True), self.grid.select_all()), shortcut="Ctrl+A")
        m.add_item(_("Deselect all"), lambda: self.grid.clear_selection(), shortcut="Esc")
        m.add_sep()
        m.add_item(_("Refresh"), self.rescan, shortcut="F5")
        m.add_item(_("Add folder…"), self.add_folder, icon="folder-plus")
        m.add_item(_("Settings"), self.app_ref.open_settings, icon="settings")

    def _build_import_menu(self, m):
        m.add_item(_("From a folder"), self.import_from_folder, icon="folder", subtitle=_("Copy photos and videos into the Gallery"))
        m.add_item(_("Add folder to Gallery"), self.add_folder, icon="folder-plus", subtitle=_("Without copying files"))

    def _set_setting(self, key, value):
        settings.set(key, value)
        self.refresh_view()

    # ───────────────────────── contexto ─────────────────────────
    def targets(self):
        """Targets of the actions: right-clicking an item outside the selection acts on that item only."""
        if self.ctx_target is not None:
            return self.ctx_target
        return self.grid.selected_items()

    ctx_target = None

    def _with_target(self, fn):
        def run(*a):
            try:
                return fn(*a)
            finally:
                GLib.timeout_add(600, lambda: setattr(self, "ctx_target", None) or False)
        return run

    def _on_context(self, grid, idx, x, y):
        item = grid.items[idx]
        sel = grid.selected_items() if item.path in grid.selected else [item]
        self.ctx_target = sel
        multi = len(sel) > 1
        favs = set(settings.get("favorites"))

        def build(m):
            if not multi:
                m.add_item(_("Open"), lambda: self._on_open(grid, idx), icon="photo")
                m.add_item(_("Edit"), lambda: self.app_ref.open_viewer(grid.items, idx, edit=True), icon="edit", shortcut="Ctrl+E")
            m.add_item(_("Start slideshow"), self.slideshow_selected, icon="slideshow", shortcut="F5")
            if not multi:
                m.add_item(_("Print"), lambda: self._print(item), icon="print", shortcut="Ctrl+P")
            m.add_item(_("Copy"), lambda: (actions.copy_file_to_clipboard([i.path for i in sel]),
                                          ui.toast(self.overlay, _("Copied"))), icon="copy", shortcut="Ctrl+C")
            if not multi:
                m.add_item(_("Copy as path"), lambda: (actions.copy_path_to_clipboard(item.path),
                                                           ui.toast(self.overlay, _("Path copied"))), icon="link", shortcut="Ctrl+Shift+C")
            m.add_item(_("Share"), self.share_selected, icon="share")
            if not multi:
                fav = item.path in favs
                m.add_item(_("Remove from favorites") if fav else _("Add to favorites"),
                           lambda: self.toggle_favorite(item), icon="heart-fill" if fav else "heart")

            def sub(sm):
                sm.add_item(_("Copy to…"), lambda: self.copy_move_selected(False))
                sm.add_item(_("Move to…"), lambda: self.copy_move_selected(True))
            m.add_item(_("Move/Copy"), None, icon="folder-open", submenu=sub)
            if not multi:
                m.add_item(_("Rename"), self.rename_selected, icon="rename", shortcut="F2")
            m.add_sep()
            m.add_item(_("Open in file manager"), lambda: actions.reveal_in_file_manager(item.path),
                       icon="folder", shortcut="F3")
            m.add_sep()
            m.add_item(_("Delete"), self.delete_selected, icon="trash", shortcut="Delete", danger=True)
        m = ui.popup_menu_at(grid, x, y, build)
        m.connect("closed", lambda *_: GLib.timeout_add(800, lambda: setattr(self, "ctx_target", None) or False))

    # ───────────────────────── dados ─────────────────────────
    def rescan(self):
        if self.scanner:
            self.scanner.cancel()
        self.last_scan = GLib.get_monotonic_time()
        folders = self.sources()
        self.scanning = True
        self._fresh = []
        if not self.all_items:
            self.body.set_visible_child_name("loading")
        self.scanner = library.Scanner(folders, self._on_batch, self._on_scan_done)

    def _on_batch(self, batch):
        self._fresh.extend(batch)
        if not self.all_items:
            self.all_items = list(self._fresh)
            self._schedule_refresh()
        return None

    def _on_scan_done(self):
        self.scanning = False
        self.all_items = self._fresh
        self.refresh_view()
        self.app_ref.library = self.all_items

    def _schedule_refresh(self):
        if self.refresh_timer:
            return
        self.refresh_timer = GLib.timeout_add(250, self._refresh_tick)

    def _refresh_tick(self):
        self.refresh_timer = 0
        self.refresh_view()
        return False

    def set_view(self, view):
        self.view = view
        self._sync_side_selection()
        if self.sidebar_collapsed:
            pass
        kind, path = view
        if kind == "gallery":
            self.title_lb.set_text(_("Gallery"))
            self.title_icon.set_icon("photo")
        elif kind == "favorites":
            self.title_lb.set_text(_("Favorites"))
            self.title_icon.set_icon("heart")
        else:
            self.title_lb.set_text(os.path.basename(path.rstrip("/")) or path)
            self.title_icon.set_icon("folder")
        self.sel_sub.set_text(self.title_lb.get_text())
        self.pages.set_visible_child_name("main")
        self.refresh_view()

    def _sync_side_selection(self):
        for k, it in self.side_items.items():
            it.set_selected(k == self.view)

    def _view_items(self):
        kind, path = self.view
        items = self.all_items
        if kind == "favorites":
            favs = set(settings.get("favorites"))
            items = [i for i in items if i.path in favs]
        elif kind == "folder":
            prefix = path.rstrip("/") + "/"
            items = [i for i in items if i.path.startswith(prefix)]
        return items

    def refresh_view(self):
        library.mark_duplicates(self.all_items)
        items = self._view_items()
        items = library.filter_items(items, settings.get("media_filter"), self.query)
        items = library.sort_items(items, settings.get("sort_by"), settings.get("sort_desc"))
        self.grid.configure(settings.get("layout"), settings.get("tile_size"), settings.get("sort_by"))
        self.grid.set_items(items)
        self.sub_lb.set_text(count_text(items))
        if items:
            self.body.set_visible_child_name("grid")
        elif getattr(self, "scanning", False) and not self.all_items:
            self.body.set_visible_child_name("loading")
        else:
            kind = self.view[0]
            self.empty_add.set_visible(not self.query and kind != "favorites")
            if self.query:
                self.empty_title.set_text(_("No results"))
                self.empty_sub.set_text(_("No files match “%s”.") % self.query)
            elif kind == "favorites":
                self.empty_title.set_text(_("No favorites yet"))
                self.empty_sub.set_text(_("Use a photo's context menu to add it to your favorites."))
            else:
                self.empty_title.set_text(_("No photos found"))
                self.empty_sub.set_text(_("Add a folder with photos to get started."))
            self.empty_add.set_no_show_all(False)
            self.body.set_visible_child_name("empty")

    def _on_search(self, entry):
        self.query = entry.get_text()
        self.refresh_view()

    def _on_selection(self, grid):
        self.ctx_target = None
        n = len(grid.selected)
        self.sel_title.set_text(ngettext("%d item selected", "%d items selected", n))
        for b in (self.btn_del_sel, self.btn_copy_sel, self.btn_move_sel, self.btn_share_sel, self.btn_slide_sel):
            b.set_sensitive(n > 0)
        if n > 0 and not grid.select_mode:
            self.set_select_mode(True, keep=True)
        elif n == 0 and grid.select_mode and not self._explicit_select:
            self.set_select_mode(False)

    _explicit_select = False

    def set_select_mode(self, on, keep=False):
        if on:
            self._explicit_select = not keep
        else:
            self._explicit_select = False
        self.grid.select_mode = on
        if not on:
            self.grid.selected = set()
        self.head_stack.set_visible_child_name("select" if on else "normal")
        self.tool_stack.set_visible_child_name("select" if on else "normal")
        self._on_selection_title()
        self.grid.queue_draw()

    def _on_selection_title(self):
        n = len(self.grid.selected)
        self.sel_title.set_text(ngettext("%d item selected", "%d items selected", n))

    # ───────────────────────── open / actions ─────────────────────────
    def _on_open(self, grid, idx):
        self.app_ref.open_viewer(grid.items, idx)

    def slideshow_all(self):
        if self.grid.items:
            start = max(0, self.grid.kidx)
            self.app_ref.open_viewer(self.grid.items, start, slideshow=True)

    def slideshow_selected(self):
        sel = self.targets() or self.grid.items
        if sel:
            self.app_ref.open_viewer(sel, 0, slideshow=True)

    def _print(self, item):
        try:
            pb = actions.load_pixbuf(item.path)
            actions.print_pixbuf(self, pb, item.name)
        except Exception as exc:  # noqa: BLE001
            ui.toast(self.overlay, _("Could not print: %s") % exc)

    def share_selected(self):
        sel = self.targets()
        if not sel:
            return
        actions.copy_file_to_clipboard([i.path for i in sel])
        if len(sel) == 1:
            actions.share_by_email(sel[0].path)
        else:
            ui.toast(self.overlay, _("Files copied to the clipboard"))

    def toggle_favorite(self, item):
        favs = list(settings.get("favorites"))
        if item.path in favs:
            favs.remove(item.path)
        else:
            favs.append(item.path)
        settings.set("favorites", favs)
        if self.view[0] == "favorites":
            self.refresh_view()

    def delete_selected(self):
        sel = self.targets()
        if not sel and self.grid.kidx >= 0:
            sel = [self.grid.items[self.grid.kidx]]
        if not sel:
            return

        def do():
            removed = []
            for it in sel:
                try:
                    actions.move_to_trash(it.path)
                    removed.append(it.path)
                except GLib.Error as exc:
                    ui.toast(self.overlay, _("Could not delete %s: %s") % (it.name, exc.message))
            if removed:
                self.app_ref.notify_removed(removed)
        n = len(sel)
        if settings.get("confirm_delete"):
            def ok(dont):
                if dont:
                    settings.set("confirm_delete", False)
                do()
            ui.confirm(self.overlay, ngettext("Delete this file?", "Delete %d files?", n),
                       ngettext("Are you sure you want to delete this file?",
                                "Are you sure you want to delete these %d files?", n),
                       _("Delete"), _("Cancel"), ok, checkbox=_("Don't show this warning again"))
        else:
            do()

    def rename_selected(self):
        sel = self.targets()
        if len(sel) != 1:
            return
        item = sel[0]

        def done(dest):
            self.app_ref.notify_renamed(item.path, dest)
        dialogs.rename_dialog(self, item, done)

    def copy_move_selected(self, move):
        sel = self.targets()
        if not sel:
            return
        dlg = Gtk.FileChooserNative.new(_("Move to…") if move else _("Copy to…"), self,
                                        Gtk.FileChooserAction.SELECT_FOLDER, _("Select"), _("Cancel"))
        self._native_ref = dlg

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                folder = d.get_filename()
                errs = 0
                moved = []
                for it in sel:
                    try:
                        actions.copy_to(it.path, folder, move)
                        if move:
                            moved.append(it.path)
                    except OSError:
                        errs += 1
                if moved:
                    self.app_ref.notify_removed(moved)
                self.app_ref.notify_library_changed()
                done_n = len(sel) - errs
                ui.toast(self.overlay, ngettext("%d file moved", "%d files moved", done_n) if move
                         else ngettext("%d file copied", "%d files copied", done_n))
            d.destroy()
        dlg.connect("response", resp)
        dlg.show()

    # ───────────────────────── pastas ─────────────────────────
    def add_folder(self):
        dlg = Gtk.FileChooserNative.new(_("Add folder to Gallery"), self, Gtk.FileChooserAction.SELECT_FOLDER,
                                        _("Add folder"), _("Cancel"))
        self._native_ref = dlg

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                f = d.get_filename()
                folders = list(settings.get("folders"))
                if f and f not in folders and f != library.pictures_dir():
                    folders.append(f)
                    settings.set("folders", folders)
                    self._rebuild_tree()
                    self.rescan()
                    ui.toast(self.overlay, _("Folder added: %s") % os.path.basename(f))
            d.destroy()
        dlg.connect("response", resp)
        dlg.show()

    def remove_folder(self, f):
        folders = [x for x in settings.get("folders") if x != f]
        settings.set("folders", folders)
        self._rebuild_tree()
        self.rescan()

    def import_from_folder(self):
        dlg = Gtk.FileChooserNative.new(_("Import from a folder"), self, Gtk.FileChooserAction.SELECT_FOLDER,
                                        _("Import"), _("Cancel"))
        self._native_ref = dlg

        def resp(d, r):
            if r == Gtk.ResponseType.ACCEPT:
                src = d.get_filename()
                dest = os.path.join(library.pictures_dir(), _("Imported %s") % datetime.date.today().isoformat())
                threading.Thread(target=self._import_thread, args=(src, dest), daemon=True).start()
                ui.toast(self.overlay, _("Importing…"))
            d.destroy()
        dlg.connect("response", resp)
        dlg.show()

    def _import_thread(self, src, dest):
        n = 0
        try:
            items = library.list_folder(src, recursive=True)
            if items:
                os.makedirs(dest, exist_ok=True)
            for it in items:
                shutil.copy2(it.path, actions.unique_path(os.path.join(dest, it.name)))
                n += 1
        except OSError:
            pass
        GLib.idle_add(self._import_done, n)

    def _import_done(self, n):
        ui.toast(self.overlay, ngettext("%d file imported", "%d files imported", n))
        self.rescan()
        return False

    # ───────────────────────── window ─────────────────────────
    def show_settings(self):
        self.settings_page.refresh()
        self.pages.set_visible_child_name("settings")

    def show_main(self):
        self.pages.set_visible_child_name("main")

    def _on_size(self, w, alloc):
        if not self.is_maximized():
            settings.set("main_size", list(self.get_size()))

    def _on_state(self, w, ev):
        if ev.changed_mask & Gdk.WindowState.MAXIMIZED:
            settings.set("main_maximized", bool(ev.new_window_state & Gdk.WindowState.MAXIMIZED))
        return False

    def _on_active(self, *_):
        if self.is_active() and (GLib.get_monotonic_time() - self.last_scan) > 8 * 1_000_000 and not getattr(self, "scanning", False):
            self.rescan()

    def _on_key(self, w, ev):
        if ui.dialog_open():
            return False
        k = ev.keyval
        if k == Gdk.KEY_Escape and ui.popover_recent():
            return True
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if self.pages.get_visible_child_name() == "settings":
            if k == Gdk.KEY_Escape:
                self.show_main()
                return True
            return False
        if isinstance(self.get_focus(), Gtk.Entry):
            if k == Gdk.KEY_Escape:
                self.search.set_text("")
                self.grid.grab_focus()
                return True
            return False
        if ctrl and k in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        if k == Gdk.KEY_F5:
            self.slideshow_selected() if self.grid.selected else self.slideshow_all()
            return True
        if k == Gdk.KEY_F3 and self.grid.selected_items():
            actions.reveal_in_file_manager(self.grid.selected_items()[0].path)
            return True
        if ctrl and k in (Gdk.KEY_c, Gdk.KEY_C) and self.grid.selected_items():
            sel = self.grid.selected_items()
            if ev.state & Gdk.ModifierType.SHIFT_MASK:
                actions.copy_path_to_clipboard("\n".join(i.path for i in sel))
            else:
                actions.copy_file_to_clipboard([i.path for i in sel])
            return True
        if k == Gdk.KEY_Escape and (self.grid.selected or self.grid.select_mode):
            self.set_select_mode(False)
            return True
        if k == Gdk.KEY_Escape and self.query:
            self.search.set_text("")
            return True
        return False

    # ───────────────────────── updates coming from the viewers ─────────────────────────
    def apply_removed(self, paths):
        ps = set(paths)
        settings.set("favorites", [f for f in settings.get("favorites") if f not in ps])
        self.all_items = [i for i in self.all_items if i.path not in ps]
        self.refresh_view()

    def apply_renamed(self, old, new):
        favs = list(settings.get("favorites"))
        if old in favs:
            favs[favs.index(old)] = new
            settings.set("favorites", favs)
        for it in self.all_items:
            if it.path == old:
                it.path = new
                it.name = os.path.basename(new)
        self.refresh_view()

    def apply_changed(self, path):
        thumbs.cache.invalidate(path)
        self.refresh_view()

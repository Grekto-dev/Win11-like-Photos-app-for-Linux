# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Settings page (inside the main window)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import __version__ as VERSION
from . import i18n, icons, library, settings, theme, ui
from .i18n import _, ngettext  # noqa: F401



class SettingsPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.get_style_context().add_class("photos-root")
        top = Gtk.Box(spacing=12)
        top.set_margin_start(8)
        top.set_margin_top(4)
        top.pack_start(ui.icon_button("back", _("Back"), classes=["flat-icon"], on_click=win.show_main), False, False, 0)
        top.pack_start(icons.Icon("settings", 22, "fg"), False, False, 0)
        top.pack_start(ui.label(_("Settings"), ["settings-title"]), False, False, 0)
        self.pack_start(top, False, False, 0)
        sc = Gtk.ScrolledWindow()
        sc.get_style_context().add_class("fscroll")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(sc, True, True, 0)
        outer = Gtk.Box()
        sc.add(outer)
        self.col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.col.set_size_request(900, -1)
        self.col.set_halign(Gtk.Align.CENTER)
        self.col.set_margin_top(12)
        self.col.set_margin_bottom(40)
        self.col.set_margin_start(24)
        self.col.set_margin_end(24)
        outer.set_center_widget(self.col)
        self.rebuild()

    def refresh(self):
        self.rebuild()

    def rebuild(self):
        for c in self.col.get_children():
            self.col.remove(c)
        col = self.col
        col.pack_start(ui.label(_("Personalization"), ["settings-head"]), False, False, 0)
        self._combo_row(col, _("App theme"), _("Select which app theme to display"), "theme",
                        [("light", _("Light")), ("dark", _("Dark")), ("system", _("Use system setting"))],
                        after=lambda: theme.apply())
        self._combo_row(col, _("Language"), _("Choose the language used in the app interface"), "language",
                        list(i18n.LANGUAGES), after=self._language_changed)
        self._switch_row(col, _("Show gallery tile attributes"),
                         _("Show a badge for duplicate files on gallery tiles"), "show_tile_attrs",
                         after=lambda: win.grid.queue_draw())
        self._switch_row(col, _("Ask for permission to delete photos"),
                         _("Show a confirmation dialog when deleting items"), "confirm_delete")
        self._combo_row(col, _("Mouse wheel"),
                        _("Choose what the mouse wheel does when viewing a single file (Note: Ctrl + wheel always zooms in or out)"),
                        "wheel", [("zoom", _("Zoom in or out")), ("navigate", _("Navigate between files"))])
        self._combo_row(col, _("Zoom preference"),
                        _("Choose how to open and display photos and videos smaller than your window"),
                        "zoom_pref", [("actual", _("Display at actual size")), ("fit", _("Fit to window"))])
        self._combo_row(col, _("Slide duration"), _("How long each photo is shown in the slideshow"),
                        "slideshow_interval", [(n, _("%d seconds") % n) for n in (3, 5, 10, 30)])

        col.pack_start(ui.label(_("Gallery folders"), ["settings-head"]), False, False, 0)
        self._folder_row(col, library.pictures_dir(), removable=False)
        for f in settings.get("folders"):
            self._folder_row(col, f, removable=True)
        add = ui.icon_button("folder-plus", None, label=_("Add folder"), classes=["subtle"], on_click=self.win.add_folder)
        add.set_halign(Gtk.Align.START)
        add.set_margin_top(8)
        col.pack_start(add, False, False, 0)

        col.pack_start(ui.label(_("About"), ["settings-head"]), False, False, 0)
        card = self._card()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(ui.label(_("Photos for Linux  ·  version %s") % VERSION), False, False, 0)
        box.pack_start(ui.label(_("Independent recreation inspired by the Windows 11 Photos app. Contains no Microsoft code or assets. License: Apache 2.0."), ["settings-sub"], wrap=True), False, False, 0)
        card.pack_start(box, True, True, 0)
        col.pack_start(card, False, False, 0)
        col.show_all()

    def _language_changed(self):
        if i18n.normalize(settings.get("language")) == i18n.current():
            return
        ui.confirm(self.win.overlay, _("Restart to apply the language"),
                   _("The app needs to restart to apply the new language."), _("Restart now"), _("Later"),
                   lambda _dont: self.win.app_ref.restart())

    def _card(self):
        card = Gtk.Box(spacing=16)
        card.get_style_context().add_class("settings-card")
        return card

    def _text_block(self, title, desc):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(ui.label(title), False, False, 0)
        if desc:
            box.pack_start(ui.label(desc, ["settings-sub"], wrap=True), False, False, 0)
        return box

    def _combo_row(self, col, title, desc, key, options, after=None):
        card = self._card()
        card.pack_start(self._text_block(title, desc), True, True, 0)
        cur = settings.get(key)
        text = next((t for v, t in options if v == cur), str(cur))
        btn = ui.icon_button(label=text, classes=["subtle"], icon_after="chev-down")
        btn.set_size_request(230, 32)
        btn.set_valign(Gtk.Align.CENTER)

        def build(m):
            for v, t in options:
                def pick(v=v, t=t):
                    settings.set(key, v)
                    btn.label.set_text(t)
                    if after:
                        after()
                m.add_item(t, pick, mark=(settings.get(key) == v), indent_mark=True)
        ui.menu_button(btn, build, min_width=230)
        card.pack_end(btn, False, False, 0)
        col.pack_start(card, False, False, 0)

    def _switch_row(self, col, title, desc, key, after=None):
        card = self._card()
        card.pack_start(self._text_block(title, desc), True, True, 0)
        state = ui.label(_("On") if settings.get(key) else _("Off"))
        sw = Gtk.Switch()
        sw.get_style_context().add_class("fswitch")
        sw.set_active(bool(settings.get(key)))
        sw.set_valign(Gtk.Align.CENTER)

        def toggled(s, _p):
            settings.set(key, s.get_active())
            state.set_text(_("On") if s.get_active() else _("Off"))
            if after:
                after()
        sw.connect("notify::active", toggled)
        card.pack_end(sw, False, False, 0)
        card.pack_end(state, False, False, 8)
        col.pack_start(card, False, False, 0)

    def _folder_row(self, col, path, removable):
        card = self._card()
        card.pack_start(icons.Icon("folder", 20, "fg"), False, False, 0)
        card.pack_start(self._text_block(path.rstrip("/").split("/")[-1] or path, path), True, True, 0)
        if removable:
            card.pack_end(ui.icon_button("trash", _("Remove from Gallery"), classes=["flat-icon"], size=18,
                                         on_click=lambda: (self.win.remove_folder(path), self.rebuild())), False, False, 0)
        col.pack_start(card, False, False, 0)

# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Application (Gtk.Application): single instance, Gallery window and viewers."""
import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import i18n, library, settings, theme
from .i18n import _, ngettext  # noqa: F401

APP_ID = "dev.grekto.Photos"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class PhotosApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN | Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        GLib.set_prgname("photos")
        GLib.set_application_name(_("Photos"))
        self.gallery = None
        self.viewers = []
        self.library = []
        self.add_main_option("settings", ord("s"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Open Settings"), None)
        self.add_main_option("slideshow", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start a slideshow with the given files"), None)
        self.add_main_option("edit", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _("Open directly in the editor"), None)

    # ── lifecycle ──
    def do_startup(self):
        Gtk.Application.do_startup(self)
        icon = os.path.join(DATA_DIR, "photos.svg")
        if os.path.exists(icon):
            try:
                Gtk.Window.set_default_icon_from_file(icon)
            except GLib.Error:
                pass
        Gtk.Widget.set_default_direction(Gtk.TextDirection.RTL if i18n.is_rtl() else Gtk.TextDirection.LTR)
        theme.apply()
        gs = Gtk.Settings.get_default()
        gs.connect("notify::gtk-theme-name", lambda *_: settings.get("theme") == "system" and theme.apply())
        gs.connect("notify::gtk-application-prefer-dark-theme", lambda *_: None)

    def do_activate(self):
        self.open_gallery()

    def do_open(self, files, n_files, hint):
        self._open_paths([f.get_path() for f in files if f.get_path()], {})

    def do_command_line(self, cl):
        opts = cl.get_options_dict().end().unpack()
        args = [a for a in cl.get_arguments()[1:] if not a.startswith("-")]
        paths = []
        for a in args:
            p = cl.create_file_for_arg(a).get_path()
            if p:
                paths.append(p)
        if paths:
            self._open_paths(paths, opts)
        elif opts.get("settings"):
            self.open_settings()
        else:
            self.open_gallery()
        return 0

    # ── windows ──
    def open_gallery(self):
        from .gallery import MainWindow
        if self.gallery is None:
            self.gallery = MainWindow(self)
            self.gallery.connect("destroy", self._gallery_gone)
        self.gallery.present()
        return self.gallery

    def _gallery_gone(self, w):
        self.gallery = None

    def open_settings(self):
        g = self.open_gallery()
        g.show_settings()

    def open_viewer(self, items, index, slideshow=False, edit=False):
        from .viewer import ViewerWindow
        win = ViewerWindow(self, items, index, slideshow=slideshow)
        self.viewers.append(win)
        win.connect("destroy", lambda w: self.viewers.remove(w) if w in self.viewers else None)
        win.present()
        if edit:
            GLib.timeout_add(250, lambda: (win.open_editor(), False)[1])
        return win

    def _open_paths(self, paths, opts):
        if not paths:
            self.open_gallery()
            return
        if len(paths) == 1 and os.path.isdir(paths[0]):
            items = library.sort_items(library.list_folder(paths[0], recursive=False), "name", False)
            for it in items:
                library.read_meta(it)
            if items:
                self.open_viewer(items, 0, slideshow=bool(opts.get("slideshow")))
            else:
                self.open_gallery()
            return
        files = [p for p in paths if os.path.isfile(p) and library.is_media(p)]
        if not files:
            self.open_gallery()
            return
        if len(files) == 1:
            folder = os.path.dirname(files[0])
            sibs = [i for i in library.list_folder(folder, recursive=False)]
            sibs = library.sort_items(sibs, "name", False)
            idx = next((k for k, i in enumerate(sibs) if os.path.samefile(i.path, files[0])), -1)
            if idx < 0:
                import os as _os
                it = library.Item(files[0], _os.stat(files[0]))
                sibs, idx = [it], 0
            for it in sibs:
                library.read_meta(it)
            self.open_viewer(sibs, idx, slideshow=bool(opts.get("slideshow")), edit=bool(opts.get("edit")))
        else:
            items = [library.Item(p, os.stat(p)) for p in files]
            for it in items:
                library.read_meta(it)
            self.open_viewer(items, 0, slideshow=bool(opts.get("slideshow")))

    def restart(self):
        """Re-executes the app (used to apply a new language) and lands back on the settings page."""
        exe = sys.executable
        os.execv(exe, [exe, os.path.abspath(sys.argv[0]), "--settings"])

    # ── notifications between windows ──
    def notify_removed(self, paths):
        ps = set(paths)
        if self.gallery:
            self.gallery.apply_removed(paths)
        for v in list(self.viewers):
            gone = [i for i in v.items if i.path in ps]
            if gone and not (len(paths) == 1 and v.item.path in ps and False):
                cur = v.item
                v.items = [i for i in v.items if i.path not in ps]
                if not v.items:
                    v.close()
                elif cur.path in ps:
                    v.index = min(v.index, len(v.items) - 1)
                    v.load_current(transition="fade")
                else:
                    v.index = v.items.index(cur)
                    v.film.set_items(v.items, v.index)

    def notify_renamed(self, old, new):
        if self.gallery:
            self.gallery.apply_renamed(old, new)

    def notify_changed(self, path):
        if self.gallery:
            self.gallery.apply_changed(path)

    def notify_library_changed(self):
        if self.gallery:
            self.gallery.rescan()


def main(argv=None):
    app = PhotosApp()
    return app.run(argv if argv is not None else sys.argv)

# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""File actions: trash, rename, reveal in file manager, wallpaper, print, share, EXIF."""
import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, Gio, GLib, GdkPixbuf, Gtk  # noqa: E402

from .i18n import _  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def move_to_trash(path):
    f = Gio.File.new_for_path(path)
    f.trash(None)


def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists("%s (%d)%s" % (stem, n, ext)):
        n += 1
    return "%s (%d)%s" % (stem, n, ext)


def rename(path, new_name):
    new_name = new_name.strip().replace("/", "_")
    if not new_name:
        raise ValueError(_("Empty name"))
    dest = os.path.join(os.path.dirname(path), new_name)
    if dest != path and os.path.exists(dest):
        raise FileExistsError(_("A file with that name already exists."))
    os.rename(path, dest)
    return dest


def copy_to(path, folder, move=False):
    if move and os.path.realpath(os.path.dirname(path)) == os.path.realpath(folder):
        return path
    dest = unique_path(os.path.join(folder, os.path.basename(path)))
    if move:
        shutil.move(path, dest)
    else:
        shutil.copy2(path, dest)
    return dest


def reveal_in_file_manager(path):
    uri = Gio.File.new_for_path(path).get_uri()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                      "org.freedesktop.FileManager1", "ShowItems",
                      GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, 1500, None)
        return
    except GLib.Error:
        pass
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(os.path.dirname(path)).get_uri(), None)
    except GLib.Error:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def open_folder(folder):
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(folder).get_uri(), None)
    except GLib.Error:
        subprocess.Popen(["xdg-open", folder])


def copy_path_to_clipboard(path):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_text(path, -1)
    cb.store()


def copy_image_to_clipboard(pixbuf):
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_image(pixbuf)
    cb.store()


def copy_file_to_clipboard(paths):
    """Copies files to the clipboard (x-special/gnome-copied-files + text/uri-list)."""
    uris = [Gio.File.new_for_path(p).get_uri() for p in paths]
    targets = [Gtk.TargetEntry.new("x-special/gnome-copied-files", 0, 0),
               Gtk.TargetEntry.new("text/uri-list", 0, 1),
               Gtk.TargetEntry.new("UTF8_STRING", 0, 2)]

    def get(cb, sel, info, data):
        if info == 0:
            sel.set(Gdk.Atom.intern("x-special/gnome-copied-files", False), 8, ("copy\n" + "\n".join(uris)).encode())
        elif info == 1:
            sel.set_uris(uris)
        else:
            sel.set_text("\n".join(paths), -1)
    cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    cb.set_with_data(targets, get, lambda *_: None, None)


def set_wallpaper(path):
    uri = Gio.File.new_for_path(path).get_uri()
    for schema in ("org.cinnamon.desktop.background", "org.gnome.desktop.background", "org.mate.background"):
        src = Gio.SettingsSchemaSource.get_default()
        if src.lookup(schema, True):
            s = Gio.Settings.new(schema)
            if schema == "org.mate.background":
                s.set_string("picture-filename", path)
            else:
                s.set_string("picture-uri", uri)
                try:
                    s.set_string("picture-options", "zoom")
                except Exception:  # noqa: BLE001
                    pass
            Gio.Settings.sync()
            return True
    return False


def share_by_email(path):
    subprocess.Popen(["xdg-email", "--attach", path])


def print_pixbuf(parent, pixbuf, name):
    op = Gtk.PrintOperation()
    op.set_n_pages(1)
    op.set_job_name(name)

    def draw(op_, ctx, page):
        cr = ctx.get_cairo_context()
        pw, ph = ctx.get_width(), ctx.get_height()
        w, h = pixbuf.get_width(), pixbuf.get_height()
        s = min(pw / w, ph / h)
        cr.translate((pw - w * s) / 2, (ph - h * s) / 2)
        cr.scale(s, s)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
    op.connect("draw-page", draw)
    op.run(Gtk.PrintOperationAction.PRINT_DIALOG, parent)


def open_with_chooser(parent, path):
    """App chooser window (Gtk.AppChooserDialog); opens the file with the chosen app."""
    f = Gio.File.new_for_path(path)
    dlg = Gtk.AppChooserDialog.new(parent, Gtk.DialogFlags.MODAL, f)
    dlg.set_heading(_("Choose another app"))
    if dlg.run() == Gtk.ResponseType.OK:
        app = dlg.get_app_info()
        if app:
            app.launch([f], None)
    dlg.destroy()


def exif_fields(path):
    """Extra EXIF fields (camera, aperture, ISO…) as a list of [(label, value)]."""
    out = []
    if Image is None:
        return out
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            if not ex:
                return out
            try:
                sub = ex.get_ifd(0x8769)
            except Exception:  # noqa: BLE001
                sub = {}
            make, model = ex.get(271), ex.get(272)
            if model:
                cam = str(model).strip()
                if make and str(make).strip() not in cam:
                    cam = "%s %s" % (str(make).strip(), cam)
                out.append((_("Camera"), cam))
            fn = sub.get(33437)
            if fn:
                out.append((_("Aperture"), "f/%.1f" % float(fn)))
            et = sub.get(33434)
            if et:
                et = float(et)
                out.append((_("Exposure time"), "1/%d s" % round(1 / et) if 0 < et < 1 else "%.1f s" % et))
            iso = sub.get(34855)
            if iso:
                if isinstance(iso, (tuple, list)):
                    iso = iso[0]
                out.append(("ISO", "ISO %s" % iso))
            fl = sub.get(37386)
            if fl:
                out.append((_("Focal length"), "%.0f mm" % float(fl)))
    except Exception:  # noqa: BLE001
        pass
    return out


def image_dpi_depth(path):
    dpi, depth = 96, 32
    if Image is None:
        return dpi, depth
    try:
        with Image.open(path) as im:
            d = im.info.get("dpi")
            if d:
                dpi = int(round(float(d[0])))
            mode = im.mode
            depth = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32, "CMYK": 32, "I;16": 16, "LA": 16}.get(mode, 32)
    except Exception:  # noqa: BLE001
        pass
    return dpi, depth


def load_pixbuf(path):
    """Loads a pixbuf with the EXIF orientation applied."""
    pb = GdkPixbuf.Pixbuf.new_from_file(path)
    return pb.apply_embedded_orientation() or pb

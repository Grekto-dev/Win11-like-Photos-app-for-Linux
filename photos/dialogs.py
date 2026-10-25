# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Dialogs: resize, rename, save as, and image-writing helpers."""
import io
import os
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from PIL import Image, ImageOps

from . import actions, icons, library, ui
from .i18n import _, ngettext  # noqa: F401

FORMATS = [("JPG", ".jpg", "JPEG"), ("PNG", ".png", "PNG"), ("TIF", ".tif", "TIFF"), ("BMP", ".bmp", "BMP"),
           ("WEBP", ".webp", "WEBP")]


def pil_save(im, path, fmt=None, quality=95):
    ext = os.path.splitext(path)[1].lower()
    if fmt is None:
        fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG", ".png": "PNG", ".tif": "TIFF",
               ".tiff": "TIFF", ".bmp": "BMP", ".webp": "WEBP", ".gif": "GIF"}.get(ext, "PNG")
    if fmt == "JPEG" and im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    elif fmt == "JPEG" and im.mode != "RGB":
        im = im.convert("RGB")
    kw = {}
    if fmt == "JPEG":
        kw = {"quality": quality, "optimize": True}
    elif fmt == "WEBP":
        kw = {"quality": quality}
    im.save(path, fmt, **kw)


def open_oriented(path):
    im = Image.open(path)
    im.load()
    return ImageOps.exif_transpose(im)


def file_chooser_save(parent, suggested_name, folder, on_path):
    dlg = Gtk.FileChooserNative.new(_("Save as"), parent, Gtk.FileChooserAction.SAVE, _("Save"), _("Cancel"))
    dlg.set_do_overwrite_confirmation(True)
    dlg.set_current_name(suggested_name)
    if folder:
        dlg.set_current_folder(folder)
    for name, pats in ((_("Images"), ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff"]),):
        f = Gtk.FileFilter()
        f.set_name(name)
        for p in pats:
            f.add_pattern(p)
        dlg.add_filter(f)

    def resp(d, r):
        if r == Gtk.ResponseType.ACCEPT:
            on_path(d.get_filename())
        d.destroy()
    dlg.connect("response", resp)
    dlg.show()
    parent._native_ref = dlg  # evita coleta
    return dlg


class ResizeDialog:
    """Resize image (pixels or percentage), quality and file type."""

    def __init__(self, window, item):
        self.window = window
        self.item = item
        self.src = open_oriented(item.path)
        self.w0, self.h0 = self.src.size
        self.updating = False
        self.fmt_idx = [i for i, f in enumerate(FORMATS) if f[1] == item.ext or (item.ext in (".jpeg", ".jpe", ".jfif") and f[0] == "JPG")]
        self.fmt_idx = self.fmt_idx[0] if self.fmt_idx else 1
        self.mode = "px"
        self.keep = True
        self.quality = 100
        self.est_token = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        rr = Gtk.Box(spacing=18)
        self.r_px = Gtk.RadioButton.new_with_label(None, _("Pixels"))
        self.r_pct = Gtk.RadioButton.new_with_label_from_widget(self.r_px, _("Percentage"))
        for r in (self.r_px, self.r_pct):
            r.get_style_context().add_class("fradio")
            rr.pack_start(r, False, False, 0)
        self.r_px.connect("toggled", self._mode_changed)
        box.pack_start(rr, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        self.lb_w = ui.label(_("Width (px)"), ["faint"])
        self.lb_h = ui.label(_("Height (px)"), ["faint"])
        self.en_w = Gtk.Entry()
        self.en_h = Gtk.Entry()
        for e in (self.en_w, self.en_h):
            e.get_style_context().add_class("fnum")
            e.set_width_chars(8)
            e.set_input_purpose(Gtk.InputPurpose.DIGITS)
        self.en_w.set_text(str(self.w0))
        self.en_h.set_text(str(self.h0))
        self.link = ui.icon_button("link", _("Keep aspect ratio"), classes=["flat-icon", "sel-on"])
        self.link.connect("clicked", self._toggle_link)
        grid.attach(self.lb_w, 0, 0, 1, 1)
        grid.attach(self.lb_h, 2, 0, 1, 1)
        grid.attach(self.en_w, 0, 1, 1, 1)
        grid.attach(self.link, 1, 1, 1, 1)
        grid.attach(self.en_h, 2, 1, 1, 1)
        box.pack_start(grid, False, False, 0)
        self.en_w.connect("changed", lambda e: self._dim_changed("w"))
        self.en_h.connect("changed", lambda e: self._dim_changed("h"))

        self.lb_q = ui.label(self._quality_text(100))
        box.pack_start(self.lb_q, False, False, 4)
        self.scale_q = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.scale_q.set_value(100)
        self.scale_q.set_draw_value(False)
        self.scale_q.get_style_context().add_class("fscale")
        self.scale_q.get_style_context().add_class("on-bg")
        self.scale_q.connect("value-changed", self._q_changed)
        box.pack_start(self.scale_q, False, False, 0)

        box.pack_start(ui.label(_("File type"), ["faint"]), False, False, 4)
        self.type_btn = ui.icon_button(label=FORMATS[self.fmt_idx][0], classes=["subtle"], icon_after="chev-down")
        self.type_btn.set_halign(Gtk.Align.START)
        self.type_btn.set_size_request(120, 32)
        ui.menu_button(self.type_btn, self._build_type_menu, min_width=120)
        box.pack_start(self.type_btn, False, False, 0)

        self.lb_cur = ui.label("", ["faint"])
        self.lb_new = ui.label("", ["faint"])
        box.pack_start(self.lb_cur, False, False, 4)
        box.pack_start(self.lb_new, False, False, 0)
        self.lb_cur.set_text(_("Current: %d x %d pixels   %s   %s") % (self.w0, self.h0, library.fmt_size(item.size),
                                                                      item.ext.lstrip(".").upper()))
        self.dlg = ui.ContentDialog(window.overlay, _("Resize"), box,
                                    [(_("Save"), "accent", self._save), (_("Cancel"), "", None)], width=420)
        self._update_quality_state()
        self._schedule_estimate()

    def _build_type_menu(self, m):
        for i, f in enumerate(FORMATS):
            m.add_item(f[0], lambda i=i: self._set_fmt(i), mark=(i == self.fmt_idx), indent_mark=True)

    def _set_fmt(self, i):
        self.fmt_idx = i
        self.type_btn.label.set_text(FORMATS[i][0])
        self._update_quality_state()
        self._schedule_estimate()

    def _update_quality_state(self):
        lossy = FORMATS[self.fmt_idx][2] in ("JPEG", "WEBP")
        self.scale_q.set_sensitive(lossy)
        self.lb_q.set_opacity(1.0 if lossy else 0.5)

    @staticmethod
    def _quality_text(q):
        if q >= 80:
            return _("Quality: %d%% (High)") % q
        if q >= 50:
            return _("Quality: %d%% (Medium)") % q
        return _("Quality: %d%% (Low)") % q

    def _q_changed(self, sc):
        self.quality = int(sc.get_value())
        self.lb_q.set_text(self._quality_text(self.quality))
        self._schedule_estimate()

    def _mode_changed(self, r):
        px = self.r_px.get_active()
        self.mode = "px" if px else "pct"
        self.lb_w.set_text(_("Width (px)") if px else _("Percentage"))
        self.lb_h.set_visible(px)
        self.en_h.set_visible(px)
        self.link.set_visible(px)
        self.updating = True
        if px:
            self.en_w.set_text(str(self.w0))
            self.en_h.set_text(str(self.h0))
        else:
            self.en_w.set_text("100")
        self.updating = False
        self._schedule_estimate()

    def _toggle_link(self, b):
        self.keep = not self.keep
        ctx = b.get_style_context()
        (ctx.add_class if self.keep else ctx.remove_class)("sel-on")

    def _dim_changed(self, which):
        if self.updating:
            return
        try:
            w = int(self.en_w.get_text() or 0)
            h = int(self.en_h.get_text() or 0)
        except ValueError:
            return
        if self.mode == "px" and self.keep:
            self.updating = True
            if which == "w" and w > 0:
                self.en_h.set_text(str(max(1, round(w * self.h0 / self.w0))))
            elif which == "h" and h > 0:
                self.en_w.set_text(str(max(1, round(h * self.w0 / self.h0))))
            self.updating = False
        self._schedule_estimate()

    def target_size(self):
        try:
            if self.mode == "pct":
                p = max(1, min(1000, int(self.en_w.get_text() or 100)))
                return max(1, round(self.w0 * p / 100)), max(1, round(self.h0 * p / 100))
            return max(1, int(self.en_w.get_text())), max(1, int(self.en_h.get_text()))
        except ValueError:
            return None

    def _schedule_estimate(self):
        self.est_token += 1
        tok = self.est_token
        GLib.timeout_add(350, self._estimate, tok)

    def _estimate(self, tok):
        if tok != self.est_token:
            return False
        size = self.target_size()
        if not size:
            return False
        self.lb_new.set_text(_("New: %d x %d pixels   calculating…") % size)
        threading.Thread(target=self._estimate_thread, args=(tok, size), daemon=True).start()
        return False

    def _estimate_thread(self, tok, size):
        try:
            im = self.src.resize(size, Image.LANCZOS)
            buf = io.BytesIO()
            f = FORMATS[self.fmt_idx]
            tmp = im
            pil_buf_save(tmp, buf, f[2], self.quality)
            n = buf.tell()
            text = _("New: %d x %d pixels   %s   %s") % (size[0], size[1], library.fmt_size(n), f[0])
        except Exception:  # noqa: BLE001
            text = _("New: %d x %d pixels") % size
        GLib.idle_add(lambda: (self.lb_new.set_text(text) if tok == self.est_token else None, False)[1])

    def _save(self):
        size = self.target_size()
        if not size:
            return False
        f = FORMATS[self.fmt_idx]
        stem = os.path.splitext(self.item.name)[0]
        name = _("%s (resized)%s") % (stem, f[1])

        def write(path):
            try:
                im = self.src.resize(size, Image.LANCZOS)
                pil_save(im, path, f[2], self.quality)
                ui.toast(self.window.overlay, _("Image saved: %s") % os.path.basename(path))
                self.window.app_ref.notify_library_changed()
            except Exception as exc:  # noqa: BLE001
                ui.toast(self.window.overlay, _("Could not save: %s") % exc)
        file_chooser_save(self.window, name, self.item.folder, write)
        return True


def pil_buf_save(im, buf, fmt, quality):
    if fmt == "JPEG" and im.mode != "RGB":
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    kw = {}
    if fmt == "JPEG":
        kw = {"quality": quality}
    elif fmt == "WEBP":
        kw = {"quality": quality}
    im.save(buf, fmt, **kw)


def rename_dialog(window, item, on_done):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    entry = Gtk.Entry()
    entry.get_style_context().add_class("fnum")
    stem, ext = os.path.splitext(item.name)
    entry.set_text(item.name)
    box.pack_start(entry, False, False, 0)
    err = ui.label("", ["danger"])
    box.pack_start(err, False, False, 0)

    def ok():
        try:
            new = entry.get_text().strip()
            if "." not in new:
                new += ext
            dest = actions.rename(item.path, new)
        except (OSError, ValueError) as exc:
            err.set_text(str(exc))
            return False
        on_done(dest)
        return True
    dlg = ui.ContentDialog(window.overlay, _("Rename"), box, [(_("Rename"), "accent", ok), (_("Cancel"), "", None)], width=380)
    entry.grab_focus()
    entry.select_region(0, len(stem))
    entry.connect("activate", lambda e: dlg.buttons[0].clicked())
    return dlg

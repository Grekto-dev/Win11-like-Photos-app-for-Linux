# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Library: folder scanning, lightweight metadata, sorting and filters."""
import datetime
import os
import threading
import unicodedata

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, GdkPixbuf  # noqa: E402

from . import i18n  # noqa: E402
from .i18n import _  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".bmp", ".dib", ".webp", ".tif", ".tiff",
    ".ico", ".svg", ".heic", ".heif", ".avif", ".jxl", ".tga",
}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".3gp", ".mpg", ".mpeg", ".mts", ".m2ts"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".cache", ".thumbnails", ".Trash"}



def pictures_dir():
    d = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
    return d or os.path.expanduser("~/Pictures")


class Item:
    __slots__ = ("path", "name", "folder", "size", "mtime", "ctime", "taken", "w", "h", "kind", "ext", "dup")

    def __init__(self, path, st):
        self.path = path
        self.name = os.path.basename(path)
        self.folder = os.path.dirname(path)
        self.size = st.st_size
        self.mtime = st.st_mtime
        self.ctime = getattr(st, "st_birthtime", None) or min(st.st_ctime, st.st_mtime)
        self.taken = st.st_mtime
        self.w = 0
        self.h = 0
        self.dup = False
        self.ext = os.path.splitext(path)[1].lower()
        self.kind = "video" if self.ext in VIDEO_EXTS else "photo"

    @property
    def aspect(self):
        if self.w > 0 and self.h > 0:
            return self.w / self.h
        return 1.5

    def date_for(self, sort_by):
        if sort_by == "created":
            return self.ctime
        if sort_by == "modified":
            return self.mtime
        return self.taken


def is_media(path, *, sniff=False):
    """Match media extensions; sniff image headers only for explicitly opened files.

    Portals and other apps can supply real images with temporary or missing
    extensions. Keep library scans extension-only to avoid probing every file.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS or ext in VIDEO_EXTS:
        return True
    if sniff:
        try:
            info = GdkPixbuf.Pixbuf.get_file_info(path)
            return bool(info and info[0])
        except (GLib.Error, OSError):
            pass
    return False


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def read_meta(item):
    """Fills width/height (EXIF orientation applied) and the capture date."""
    if item.kind == "video":
        return
    done = False
    if Image is not None and item.ext not in (".svg", ".heic", ".heif", ".avif", ".jxl"):
        try:
            with Image.open(item.path) as im:
                w, h = im.size
                try:
                    ex = im.getexif()
                except Exception:  # noqa: BLE001
                    ex = None
                if ex:
                    ori = ex.get(274, 1)
                    if ori in (5, 6, 7, 8):
                        w, h = h, w
                    dt = None
                    try:
                        dt = ex.get_ifd(0x8769).get(36867)
                    except Exception:  # noqa: BLE001
                        dt = None
                    dt = dt or ex.get(36867) or ex.get(306)
                    if dt:
                        try:
                            item.taken = datetime.datetime.strptime(str(dt)[:19], "%Y:%m:%d %H:%M:%S").timestamp()
                        except ValueError:
                            pass
                item.w, item.h = w, h
                done = True
        except Exception:  # noqa: BLE001
            done = False
    if not done:
        try:
            info = GdkPixbuf.Pixbuf.get_file_info(item.path)
            if info and info[0]:
                item.w, item.h = info[1], info[2]
        except Exception:  # noqa: BLE001
            pass


def list_folder(folder, recursive=True, limit=200000):
    out = []
    stack = [folder]
    seen = set()
    while stack and len(out) < limit:
        d = stack.pop()
        try:
            real = os.path.realpath(d)
            if real in seen:
                continue
            seen.add(real)
            with os.scandir(d) as it:
                for e in it:
                    if e.name.startswith("."):
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if recursive and e.name not in SKIP_DIRS:
                                stack.append(e.path)
                        elif e.is_file() and is_media(e.name):
                            out.append(Item(e.path, e.stat()))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


class Scanner:
    """Varre pastas numa thread; entrega lotes via callbacks na thread principal."""

    def __init__(self, folders, on_batch, on_done, recursive=True):
        self.folders = list(folders)
        self.on_batch = on_batch
        self.on_done = on_done
        self.recursive = recursive
        self.cancelled = False
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self.cancelled = True

    def _run(self):
        seen = set()
        items = []
        for f in self.folders:
            for it in list_folder(f, self.recursive):
                if it.path not in seen:
                    seen.add(it.path)
                    items.append(it)
        batch = []
        for it in items:
            if self.cancelled:
                return
            read_meta(it)
            batch.append(it)
            if len(batch) >= 60:
                self._emit(batch)
                batch = []
        if batch:
            self._emit(batch)
        GLib.idle_add(self._finish)

    def _emit(self, batch):
        GLib.idle_add(lambda b=list(batch): (None if self.cancelled else self.on_batch(b)) and False)

    def _finish(self):
        if not self.cancelled:
            self.on_done()
        return False


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def sort_items(items, sort_by, desc):
    if sort_by == "name":
        key = lambda it: strip_accents(it.name)  # noqa: E731
    else:
        key = lambda it: (it.date_for(sort_by), strip_accents(it.name))  # noqa: E731
    return sorted(items, key=key, reverse=desc)


def filter_items(items, media="all", query=""):
    out = items
    if media == "photos":
        out = [i for i in out if i.kind == "photo"]
    elif media == "videos":
        out = [i for i in out if i.kind == "video"]
    q = strip_accents(query.strip())
    if q:
        out = [i for i in out if q in strip_accents(i.name)]
    return out


def fmt_date(ts):
    return i18n.format_date(datetime.datetime.fromtimestamp(ts))


def fmt_datetime(ts):
    return i18n.format_datetime(ts)


def fmt_size(n):
    if n < 1024:
        return _("%d bytes") % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    if n < 1024 ** 3:
        return "%.1f MB" % (n / 1024 / 1024)
    return "%.2f GB" % (n / 1024 ** 3)


def make_groups(items, sort_by, min_per_group=12):
    """Groups (already sorted) items by day, merging neighbouring days into ranges like the Windows Photos app.
    Returns a list of (title, [indices])."""
    if sort_by == "name" or not items:
        return [(None, list(range(len(items))))]
    groups = []
    cur = []
    cur_days = []
    last_day = None
    for i, it in enumerate(items):
        day = datetime.date.fromtimestamp(it.date_for(sort_by))
        if cur and day != last_day and len(cur) >= min_per_group:
            groups.append((cur_days, cur))
            cur, cur_days = [], []
        cur.append(i)
        cur_days.append(day)
        last_day = day
    if cur:
        groups.append((cur_days, cur))
    out = []
    for days, idxs in groups:
        a, b = min(days), max(days)
        fa, fb = i18n.format_date(a), i18n.format_date(b)
        out.append((fa if a == b else "%s - %s" % (fa, fb), idxs))
    return out


def mark_duplicates(items):
    """Flags files with identical file size and dimensions (cheap duplicate heuristic)."""
    seen = {}
    for it in items:
        it.dup = False
        if it.size > 0 and it.w and it.h:
            seen.setdefault((it.size, it.w, it.h), []).append(it)
    for group in seen.values():
        if len(group) > 1:
            for it in group:
                it.dup = True

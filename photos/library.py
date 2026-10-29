# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Library: folder scanning, lightweight metadata, sorting and filters."""
import datetime
import os
import sqlite3
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, GdkPixbuf  # noqa: E402

from . import i18n, settings  # noqa: E402
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
    __slots__ = ("path", "name", "folder", "size", "mtime", "ctime", "taken", "w", "h", "kind", "ext", "dup", "meta")

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
        self.meta = False            # True once w/h/taken were read (or restored from the cache)
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


# One buffered read covers the JPEG header and its EXIF block; on a network share the default 8 KB
# reads would cost several round trips per image.
_META_BUFFER = 128 * 1024


def read_meta(item):
    """Fills width/height (EXIF orientation applied) and the capture date."""
    item.meta = True
    if item.kind == "video":
        return
    done = False
    if Image is not None and item.ext not in (".svg", ".heic", ".heif", ".avif", ".jxl"):
        try:
            with open(item.path, "rb", buffering=_META_BUFFER) as fh, Image.open(fh) as im:
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


MAX_DEPTH = 40
STAT_WORKERS = 8
STAT_PARALLEL_FROM = 24      # below this many files a thread pool costs more than it saves


def _stat_entries(entries):
    """os.stat results for scandir entries, None where the file vanished. Over a network share each stat is
    a round trip, so large listings are done by several threads at once."""
    def one(e):
        try:
            return e.stat()
        except OSError:
            return None
    if len(entries) < STAT_PARALLEL_FROM:
        return [one(e) for e in entries]
    with ThreadPoolExecutor(max_workers=STAT_WORKERS, thread_name_prefix="photos-stat") as pool:
        return list(pool.map(one, entries))


def list_folder(folder, recursive=True, limit=200000):
    """Media files in `folder` (and below). Only the directory listing and one stat per file are needed."""
    out = []
    stack = [(folder, 0)]
    while stack and len(out) < limit:
        d, depth = stack.pop()
        found = []
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.startswith("."):
                        continue
                    try:
                        # directories reached through symlinks are never followed, so no loop is possible
                        if e.is_dir(follow_symlinks=False):
                            if recursive and e.name not in SKIP_DIRS and depth < MAX_DEPTH:
                                stack.append((e.path, depth + 1))
                        elif e.is_file() and is_media(e.name):
                            found.append(e)
                    except OSError:
                        continue
        except OSError:
            continue
        for e, st in zip(found, _stat_entries(found)):
            if st is not None:
                out.append(Item(e.path, st))
    return out


def list_siblings(path):
    """(items, index): the media next to `path` sorted by name and the position of `path` in that list.

    No image is opened and no file is stat'ed twice: the file is located by its path. A file that is not
    part of the listing (hidden, temporary name...) is returned alone."""
    sibs = sort_items(list_folder(os.path.dirname(path), recursive=False), "name", False)
    idx = next((k for k, i in enumerate(sibs) if i.path == path), -1)
    if idx < 0:
        return [Item(path, os.stat(path))], 0
    return sibs, idx


class MetaCache:
    """Persistent (path, size, mtime) -> (width, height, capture date).

    Opening every image just to learn its size is what makes a big or remote folder slow, and the answer
    does not change until the file does. The cache lives in the user's cache directory and is only a
    speed-up: any database problem silently falls back to reading the files."""

    SCHEMA = ("CREATE TABLE IF NOT EXISTS meta (path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, "
              "w INTEGER, h INTEGER, taken REAL) WITHOUT ROWID")

    def __init__(self, path=None):
        self.path = path
        self._db = None
        self._dead = False
        self._failures = 0
        self._lock = threading.RLock()

    def _file(self):
        return self.path or os.path.join(settings.CACHE_DIR, "meta.sqlite3")

    def _open(self):
        os.makedirs(os.path.dirname(self._file()), exist_ok=True)
        db = sqlite3.connect(self._file(), timeout=5, check_same_thread=False)
        try:
            # no WAL: it needs shared memory and is unsafe when the home/cache directory is on NFS
            db.execute("PRAGMA synchronous=OFF")
            db.execute(self.SCHEMA)
            db.commit()
        except sqlite3.Error:
            db.close()
            raise
        return db

    def _conn(self):
        if self._dead:
            return None
        if self._db is None:
            try:
                self._db = self._open()
            except (sqlite3.Error, OSError):
                # damaged file: start over once, then give up quietly
                for suffix in ("", "-wal", "-shm"):
                    try:
                        os.remove(self._file() + suffix)
                    except OSError:
                        pass
                try:
                    self._db = self._open()
                except (sqlite3.Error, OSError):
                    self._dead = True
        return self._db

    def _run(self, fn, default=None):
        with self._lock:
            db = self._conn()
            if db is None:
                return default
            try:
                return fn(db)
            except sqlite3.Error:
                # e.g. file locking not supported on this filesystem: retry a couple of times, then stop trying
                self._failures += 1
                self.close()
                if self._failures >= 3:
                    self._dead = True
                return default

    def lookup(self, folders):
        """{path: (size, mtime, w, h, taken)} for every cached file below the given folders."""
        def go(db):
            out = {}
            for f in folders:
                lo = f.rstrip("/") + "/"
                hi = lo[:-1] + "0"      # "0" sorts right after "/": the range is "everything below the folder"
                for row in db.execute("SELECT path, size, mtime, w, h, taken FROM meta WHERE path >= ? AND path < ?",
                                      (lo, hi)):
                    out[row[0]] = row[1:]
            return out
        return self._run(go, {})

    def store(self, items):
        rows = [(i.path, i.size, int(i.mtime), i.w, i.h, i.taken) for i in items]
        if rows:
            def go(db):
                db.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?, ?, ?, ?, ?)", rows)
                db.commit()
            self._run(go)

    def forget(self, paths):
        paths = list(paths)

        def go(db):
            for k in range(0, len(paths), 400):
                chunk = paths[k:k + 400]
                db.execute("DELETE FROM meta WHERE path IN (%s)" % ",".join("?" * len(chunk)), chunk)
            db.commit()
        if paths:
            self._run(go)

    def clear(self):
        def go(db):
            db.execute("DELETE FROM meta")
            db.commit()
        self._run(go)

    def close(self):
        with self._lock:
            if self._db is not None:
                try:
                    self._db.close()
                except sqlite3.Error:
                    pass
                self._db = None


_META = None
_META_LOCK = threading.Lock()


def meta_cache():
    global _META
    with _META_LOCK:
        if _META is None:
            _META = MetaCache()
        return _META


class Scanner:
    """Scans folders on a worker thread and hands the items to the main thread in batches.

    Sizes and dates come from the metadata cache when the file is unchanged; the rest is read by a small
    pool of threads, so the latency of a network share overlaps instead of adding up."""

    BATCH = 60
    WORKERS = min(8, max(4, (os.cpu_count() or 2) * 2))

    def __init__(self, folders, on_batch, on_done, recursive=True):
        self.folders = list(folders)
        self.on_batch = on_batch
        self.on_done = on_done
        self.recursive = recursive
        self.cancelled = False
        threading.Thread(target=self._run, daemon=True, name="photos-scan").start()

    def cancel(self):
        self.cancelled = True

    def _run(self):
        try:
            self._scan()
        except Exception as exc:  # noqa: BLE001
            print("scan error:", exc)      # keep what was delivered, but never leave the Gallery "loading" forever
        finally:
            GLib.idle_add(self._finish)

    def _scan(self):
        seen = set()
        items = []
        listed = []
        for f in self.folders:
            found = list_folder(f, self.recursive)
            if self.cancelled:
                return
            if found:
                listed.append(f)
            for it in found:
                if it.path not in seen:
                    seen.add(it.path)
                    items.append(it)
        cache = meta_cache()
        rows = cache.lookup(self.folders) if items else {}
        ready, todo = [], []
        for it in items:
            row = rows.get(it.path)
            if it.kind == "video":
                it.meta = True
                ready.append(it)
            elif row and row[0] == it.size and row[1] == int(it.mtime):
                it.w, it.h, it.taken = row[2], row[3], row[4]
                it.meta = True
                ready.append(it)
            else:
                todo.append(it)
        batch = []

        def push(it):
            batch.append(it)
            if len(batch) >= self.BATCH:
                flush()

        def flush():
            if batch:
                self._emit(list(batch))
                del batch[:]

        for it in ready:
            push(it)
        if todo:
            pool = ThreadPoolExecutor(max_workers=self.WORKERS, thread_name_prefix="photos-meta")
            try:
                futures = [pool.submit(read_meta, it) for it in todo]
                fresh = []
                for fut, it in zip(futures, todo):
                    try:
                        fut.result()
                    except Exception:  # noqa: BLE001
                        it.meta = True
                    if self.cancelled:
                        return
                    push(it)
                    fresh.append(it)
                    if len(fresh) >= 200:
                        cache.store(fresh)
                        fresh = []
                cache.store(fresh)
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
        flush()
        # drop cache rows of files that are gone, but only below folders that were actually listed
        prefixes = tuple(f.rstrip("/") + "/" for f in listed)
        stale = [p for p in rows if p.startswith(prefixes) and p not in seen] if prefixes else []
        cache.forget(stale)

    def _emit(self, batch):
        GLib.idle_add(lambda b=batch: (None if self.cancelled else self.on_batch(b)) and False)

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

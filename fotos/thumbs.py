# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Thumbnails: memory (LRU) + disk cache, decoded in worker threads."""
import hashlib
import os
import queue
import subprocess
import threading
from collections import OrderedDict

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, GdkPixbuf  # noqa: E402

from . import settings

BUCKETS = (192, 320, 512, 768)
_DIR = os.path.join(settings.CACHE_DIR, "thumbs")


def bucket_for(edge):
    for b in BUCKETS:
        if edge <= b:
            return b
    return BUCKETS[-1]


def _disk_path(item, bucket):
    h = hashlib.sha1(("%s|%d|%d" % (item.path, int(item.mtime), bucket)).encode("utf-8", "replace")).hexdigest()
    return os.path.join(_DIR, h[:2], h + ".png")


def _load(item, bucket):
    dp = _disk_path(item, bucket)
    try:
        if os.path.exists(dp):
            return GdkPixbuf.Pixbuf.new_from_file(dp)
    except GLib.Error:
        pass
    pb = None
    if item.kind == "video":
        tmp = dp + ".tmp.png"
        try:
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            subprocess.run(["ffmpegthumbnailer", "-i", item.path, "-o", tmp, "-s", str(bucket), "-q", "6"],
                           capture_output=True, timeout=20)
            if os.path.exists(tmp):
                pb = GdkPixbuf.Pixbuf.new_from_file(tmp)
                os.replace(tmp, dp)
                return pb
        except Exception:  # noqa: BLE001
            return None
        return None
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(item.path, bucket, bucket, True)
        pb = pb.apply_embedded_orientation() or pb
    except GLib.Error:
        return None
    try:
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        pb.savev(dp + ".tmp", "png", [], [])
        os.replace(dp + ".tmp", dp)
    except Exception:  # noqa: BLE001
        pass
    return pb


class ThumbCache:
    def __init__(self, capacity=700, workers=3):
        self.mem = OrderedDict()
        self.capacity = capacity
        self.pending = set()
        self.failed = set()
        self.q = queue.LifoQueue()
        self.lock = threading.Lock()
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def peek(self, item, bucket):
        key = (item.path, bucket)
        pb = self.mem.get(key)
        if pb is not None:
            self.mem.move_to_end(key)
        return pb

    def best(self, item):
        """Any thumbnail already in memory (for use as a placeholder), largest first."""
        for b in reversed(BUCKETS):
            pb = self.mem.get((item.path, b))
            if pb is not None:
                return pb
        return None

    def request(self, item, bucket, callback):
        key = (item.path, bucket)
        if key in self.mem or key in self.failed:
            return
        with self.lock:
            if key in self.pending:
                return
            self.pending.add(key)
        self.q.put((item, bucket, callback))

    def _worker(self):
        while True:
            item, bucket, callback = self.q.get()
            pb = None
            try:
                pb = _load(item, bucket)
            except Exception:  # noqa: BLE001
                pb = None
            GLib.idle_add(self._done, item, bucket, pb, callback)

    def _done(self, item, bucket, pb, callback):
        key = (item.path, bucket)
        with self.lock:
            self.pending.discard(key)
        if pb is None:
            self.failed.add(key)
        else:
            self.mem[key] = pb
            while len(self.mem) > self.capacity:
                self.mem.popitem(last=False)
            try:
                callback(item, bucket)
            except Exception:  # noqa: BLE001
                pass
        return False

    def invalidate(self, path):
        for k in [k for k in self.mem if k[0] == path]:
            self.mem.pop(k, None)
        self.failed = {k for k in self.failed if k[0] != path}


cache = ThumbCache()

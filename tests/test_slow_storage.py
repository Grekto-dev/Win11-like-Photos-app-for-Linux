# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for slow storage (network shares, old disks).

The app must never do per-file I/O on the UI thread, must not read every neighbour
image just to open one file, and must remember image metadata between runs.
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ISOLATED = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = str(Path(_ISOLATED.name) / "config")
os.environ["XDG_CACHE_HOME"] = str(Path(_ISOLATED.name) / "cache")

from PIL import Image  # noqa: E402
from gi.repository import GLib  # noqa: E402
from photos import library, settings  # noqa: E402


def make_folder(n, size=(64, 48)):
    d = tempfile.mkdtemp(dir=_ISOLATED.name)
    for i in range(n):
        Image.new("RGB", size, (i * 5 % 255, 40, 90)).save(os.path.join(d, "img_%03d.jpg" % i))
    return d


def pump(done, timeout=20):
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while not done and time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        time.sleep(0.002)
    assert done, "scan did not finish"


def run_scan(folders):
    """Runs a library.Scanner to completion, pumping the GLib main loop like the app does."""
    got, done = [], []
    library.Scanner(folders, lambda b: got.extend(b), lambda: done.append(1))
    pump(done)
    return got


class Counter:
    """Wraps library.read_meta and counts (optionally slowing) the calls."""

    def __init__(self, delay=0.0):
        self.calls, self.delay, self.lock = 0, delay, threading.Lock()
        self.orig = library.read_meta

    def __enter__(self):
        def wrapped(item):
            with self.lock:
                self.calls += 1
            if self.delay:
                time.sleep(self.delay)
            return self.orig(item)
        library.read_meta = wrapped
        return self

    def __exit__(self, *exc):
        library.read_meta = self.orig


class MetadataCacheTests(unittest.TestCase):
    def test_second_scan_does_not_reopen_images(self):
        folder = make_folder(25)
        with Counter() as c:
            first = run_scan([folder])
        self.assertEqual(c.calls, 25)
        with Counter() as c:
            second = run_scan([folder])
        self.assertEqual(c.calls, 0, "unchanged files must be served from the metadata cache")
        by_path = {i.path: (i.w, i.h, i.taken) for i in first}
        self.assertEqual({i.path: (i.w, i.h, i.taken) for i in second}, by_path)
        self.assertTrue(all((i.w, i.h) == (64, 48) for i in second))

    def test_changed_file_is_read_again(self):
        folder = make_folder(5)
        run_scan([folder])
        victim = os.path.join(folder, "img_002.jpg")
        Image.new("RGB", (120, 80), "red").save(victim)
        with Counter() as c:
            items = run_scan([folder])
        self.assertEqual(c.calls, 1)
        self.assertEqual({(i.w, i.h) for i in items if i.path == victim}, {(120, 80)})

    def test_deleted_files_leave_the_cache(self):
        folder = make_folder(6)
        run_scan([folder])
        gone = os.path.join(folder, "img_000.jpg")
        os.remove(gone)
        run_scan([folder])
        rows = library.meta_cache().lookup([folder])
        self.assertNotIn(gone, rows)
        self.assertEqual(len(rows), 5)

    def test_a_broken_cache_file_does_not_break_the_scan(self):
        folder = make_folder(3)
        library.meta_cache().close()
        Path(settings.CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(settings.CACHE_DIR, "meta.sqlite3").write_bytes(b"this is not a database" * 100)
        self.assertEqual(len(run_scan([folder])), 3)


    def test_cache_gives_up_after_repeated_database_errors(self):
        import sqlite3
        cache = library.MetaCache(os.path.join(_ISOLATED.name, "flaky.sqlite3"))
        opens = []
        orig_open = cache._open
        cache._open = lambda: opens.append(1) or orig_open()

        def boom(db):
            raise sqlite3.OperationalError("database is locked")
        for _ in range(5):
            self.assertEqual(cache._run(boom, "fallback"), "fallback")
        self.assertEqual(len(opens), 3, "after three failures the cache must stop retrying")
        self.assertEqual(cache.lookup(["/x"]), {})
        self.assertEqual(len(opens), 3)


class ScannerRobustnessTests(unittest.TestCase):
    def test_scan_always_finishes_even_if_something_unexpected_fails(self):
        folder = make_folder(6)
        orig = library.meta_cache
        library.meta_cache = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            done = []
            library.Scanner([folder], lambda b: None, lambda: done.append(1))
            pump(done)
        finally:
            library.meta_cache = orig
        self.assertEqual(done, [1], "on_done must run so the Gallery does not stay in the loading state")

    def test_cancelling_a_scan_in_flight_is_quiet_and_never_calls_back(self):
        folder = make_folder(60)
        library.meta_cache().clear()
        batches, done = [], []
        with Counter(delay=0.02):
            sc = library.Scanner([folder], lambda b: batches.append(b), lambda: done.append(1))
            time.sleep(0.1)
            sc.cancel()
            end = time.monotonic() + 1.0
            ctx = GLib.MainContext.default()
            while time.monotonic() < end:
                while ctx.pending():
                    ctx.iteration(False)
                time.sleep(0.01)
        self.assertEqual(done, [])
        seen = sum(len(b) for b in batches)
        self.assertLess(seen, 60, "cancelled scans must stop delivering")


class ParallelScanTests(unittest.TestCase):
    def test_metadata_is_read_concurrently(self):
        folder = make_folder(40)
        library.meta_cache().clear()
        start = time.monotonic()
        with Counter(delay=0.03) as c:
            items = run_scan([folder])
        elapsed = time.monotonic() - start
        self.assertEqual((len(items), c.calls), (40, 40))
        serial = 40 * 0.03
        self.assertLess(elapsed, serial * 0.5, "serial reading would take %.2fs, took %.2fs" % (serial, elapsed))

    def test_items_are_delivered_in_batches(self):
        folder = make_folder(150)
        library.meta_cache().clear()
        sizes, done = [], []
        library.Scanner([folder], lambda b: sizes.append(len(b)), lambda: done.append(1))
        pump(done)
        self.assertEqual(sum(sizes), 150)
        self.assertGreater(len(sizes), 1, "items must be delivered in several batches")
        self.assertTrue(all(n <= 60 for n in sizes))


class OpenSingleFileTests(unittest.TestCase):
    def test_list_siblings_finds_the_file_by_path_without_extra_stats(self):
        folder = make_folder(30)
        target = os.path.join(folder, "img_017.jpg")
        calls = []
        orig = os.path.samefile
        os.path.samefile = lambda *a: calls.append(a) or orig(*a)
        try:
            items, idx = library.list_siblings(target)
        finally:
            os.path.samefile = orig
        self.assertEqual(len(items), 30)
        self.assertEqual(items[idx].path, target)
        self.assertEqual([i.name for i in items], sorted(i.name for i in items))
        self.assertEqual(calls, [], "locating the file must not stat every sibling")

    def test_list_siblings_does_not_read_image_contents(self):
        folder = make_folder(12)
        with Counter() as c:
            library.list_siblings(os.path.join(folder, "img_003.jpg"))
        self.assertEqual(c.calls, 0)

    def test_list_siblings_for_a_file_outside_the_listing(self):
        folder = make_folder(4)
        hidden = os.path.join(folder, ".xdp-photo.png.tmp-abc")
        Image.new("RGB", (10, 10)).save(hidden, format="PNG")
        items, idx = library.list_siblings(hidden)
        self.assertEqual((len(items), idx), (1, 0))
        self.assertEqual(items[0].path, hidden)


class MainThreadIoTests(unittest.TestCase):
    def test_gallery_sources_do_not_touch_the_disk(self):
        """A dead network share in the settings must not freeze the window while it is built."""
        from photos.gallery import MainWindow
        settings.set("folders", ["/mnt/definitely-not-mounted/photos"])
        orig_isdir, orig_scandir = os.path.isdir, os.scandir
        hits = []
        os.path.isdir = lambda *a: hits.append(("isdir", a)) or orig_isdir(*a)
        os.scandir = lambda *a, **k: hits.append(("scandir", a)) or orig_scandir(*a, **k)
        try:
            folders = MainWindow.sources(None)
        finally:
            os.path.isdir, os.scandir = orig_isdir, orig_scandir
            settings.set("folders", [])
        self.assertIn("/mnt/definitely-not-mounted/photos", folders)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Opening a file must show the viewer at once; the folder's other images arrive afterwards.

Needs a display: xvfb-run -a /usr/bin/python3 tests/test_viewer_siblings.py
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ISOLATED = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = str(Path(_ISOLATED.name) / "config")
os.environ["XDG_CACHE_HOME"] = str(Path(_ISOLATED.name) / "cache")

from PIL import Image  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402
from photos import i18n, library, settings, theme  # noqa: E402
from photos.app import PhotosApp  # noqa: E402
from photos.viewer import ViewerWindow  # noqa: E402


def drain(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.005)


def make_folder(n):
    d = tempfile.mkdtemp(dir=_ISOLATED.name)
    for i in range(n):
        Image.new("RGB", (80, 60), (i * 9 % 255, 90, 30)).save(os.path.join(d, "p_%02d.jpg" % i))
    return d


class Recorder:
    """Stands in for PhotosApp: records what _open_paths decided without opening windows."""

    def __init__(self):
        self.gallery_opened = False
        self.viewer = None
        self.viewer_kwargs = {}
        self.siblings_for = None
        self.holds = 0

    def open_gallery(self):
        self.gallery_opened = True

    def open_viewer(self, items, index, **kw):
        self.viewer, self.viewer_kwargs = (items, index), kw
        return "WINDOW"

    def _adopt_siblings_async(self, win, item):
        self.siblings_for = (win, item)

    def _open_when_listed(self, folder_or_file, opener):
        self.deferred = (folder_or_file, opener)


class OpenPathsTests(unittest.TestCase):
    def test_single_file_opens_instantly_with_only_itself(self):
        folder = make_folder(25)
        target = os.path.join(folder, "p_10.jpg")
        calls = []
        orig_read, orig_list = library.read_meta, library.list_folder
        library.read_meta = lambda *a: calls.append("read_meta")
        library.list_folder = lambda *a, **k: calls.append("list_folder") or orig_list(*a, **k)
        rec: Any = Recorder()
        try:
            PhotosApp._open_paths(rec, [target], {})
        finally:
            library.read_meta, library.list_folder = orig_read, orig_list
        self.assertEqual(calls, [], "nothing may touch the sibling files before the window exists")
        self.assertFalse(rec.gallery_opened)
        items, index = rec.viewer
        self.assertEqual([i.path for i in items], [target])
        self.assertEqual(index, 0)
        self.assertEqual(rec.siblings_for, ("WINDOW", items[0]))

    def test_slideshow_of_one_file_waits_for_the_folder_listing(self):
        folder = make_folder(5)
        rec: Any = Recorder()
        PhotosApp._open_paths(rec, [os.path.join(folder, "p_01.jpg")], {"slideshow": True})
        self.assertIsNone(rec.viewer)
        self.assertTrue(hasattr(rec, "deferred"))

    def test_not_an_image_still_falls_back_to_the_gallery(self):
        folder = make_folder(1)
        txt = os.path.join(folder, "notes.tmp")
        Path(txt).write_text("no image here")
        rec: Any = Recorder()
        PhotosApp._open_paths(rec, [txt], {})
        self.assertTrue(rec.gallery_opened)
        self.assertIsNone(rec.viewer)


class AdoptSiblingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.set("viewer_maximized", False)
        i18n.set_language("en")
        theme.apply()

    def open_single(self, folder, name):
        path = os.path.join(folder, name)
        item = library.Item(path, os.stat(path))
        win = ViewerWindow(None, [item], 0)
        win.resize(900, 600)
        drain()
        return win, item

    def test_siblings_replace_the_single_item_and_keep_the_current_one(self):
        folder = make_folder(12)
        win, item = self.open_single(folder, "p_07.jpg")
        try:
            sibs, _ = library.list_siblings(item.path)
            win.adopt_siblings(sibs)
            self.assertEqual(len(win.items), 12)
            self.assertIs(win.item, item, "the item instance (size, metadata) must be kept")
            self.assertEqual(win.index, 7)
            self.assertEqual(win.film.index, 7)
            self.assertEqual(len(win.film.items), 12)
            win.goto(8)
            drain(0.4)
            self.assertEqual(win.item.name, "p_08.jpg")
        finally:
            win.destroy()
            drain()

    def test_adopting_a_list_without_the_current_file_changes_nothing(self):
        folder = make_folder(4)
        win, item = self.open_single(folder, "p_01.jpg")
        try:
            other = make_folder(3)
            sibs, _ = library.list_siblings(os.path.join(other, "p_00.jpg"))
            win.adopt_siblings(sibs)
            self.assertEqual([i.path for i in win.items], [item.path])
        finally:
            win.destroy()
            drain()

    def test_metadata_is_read_off_the_ui_thread_when_an_image_is_loaded(self):
        folder = make_folder(3)
        path = os.path.join(folder, "p_02.jpg")
        item = library.Item(path, os.stat(path))
        self.assertFalse(item.meta)
        threads = []
        import threading
        orig = library.read_meta

        def spy(it):
            threads.append(threading.current_thread() is threading.main_thread())
            return orig(it)
        library.read_meta = spy
        win = ViewerWindow(None, [item], 0)
        try:
            deadline = time.monotonic() + 5
            while not item.meta and time.monotonic() < deadline:
                drain(0.05)
        finally:
            library.read_meta = orig
            win.destroy()
            drain()
        self.assertTrue(item.meta)
        self.assertEqual(threads, [False], "read_meta must run on the loader thread, not the UI thread")


class SidebarTreeTests(unittest.TestCase):
    """The folder tree is built and expanded off the UI thread; the rows must still appear."""

    @classmethod
    def setUpClass(cls):
        # only one registered Gtk.Application per process: a second register() fails on the exported D-Bus object
        cls.app = PhotosApp()
        cls.app.register(None)      # emits "startup": windows may only be added after it

    def test_roots_and_children_appear_and_unreadable_roots_are_left_out(self):
        from photos.gallery import MainWindow
        root = tempfile.mkdtemp(dir=_ISOLATED.name)
        for sub in ("alpha/deep/deeper", "beta"):
            os.makedirs(os.path.join(root, sub))
        Image.new("RGB", (20, 20)).save(os.path.join(root, "alpha", "deep", "x.jpg"))
        orig_pictures = library.pictures_dir
        library.pictures_dir = lambda: root
        settings.set("folders", ["/mnt/rede-que-nao-existe/fotos"])
        app = self.app
        win = None

        def expander_of(side_item):
            found = []

            def walk(w):
                if isinstance(w, Gtk.Button) and w.get_style_context().has_class("side-expander"):
                    found.append(w)
                if isinstance(w, Gtk.Container):
                    for c in w.get_children():
                        walk(c)
            walk(side_item)
            return found[0] if found else None
        try:
            win = MainWindow(app)
            deadline = time.monotonic() + 5
            while ("folder", root) not in win.side_items and time.monotonic() < deadline:
                drain(0.05)
            self.assertIn(("folder", root), win.side_items, "the root folder row must show up")
            self.assertNotIn(("folder", "/mnt/rede-que-nao-existe/fotos"), win.side_items,
                             "an unreachable folder must not get a row")
            # expand root -> children are listed in the background and added when ready
            root_item = win.side_items[("folder", root)]
            self.assertIsNotNone(expander_of(root_item), "a folder with sub-folders gets an expander")
            expander_of(root_item).clicked()
            alpha = ("folder", os.path.join(root, "alpha"))
            deadline = time.monotonic() + 5
            while alpha not in win.side_items and time.monotonic() < deadline:
                drain(0.05)
            self.assertIn(alpha, win.side_items)
            self.assertIn(("folder", os.path.join(root, "beta")), win.side_items)
            self.assertIsNotNone(expander_of(win.side_items[alpha]), "alpha has a sub-folder, so it gets an expander")
            self.assertIsNone(expander_of(win.side_items[("folder", os.path.join(root, "beta"))]), "beta is a leaf")
        finally:
            library.pictures_dir = orig_pictures
            settings.set("folders", [])
            if win is not None:
                win.destroy()
                drain()


    def test_closing_the_window_stops_the_scan_and_pending_work(self):
        from photos.gallery import MainWindow
        root = tempfile.mkdtemp(dir=_ISOLATED.name)
        for i in range(30):
            Image.new("RGB", (30, 30)).save(os.path.join(root, "i%02d.jpg" % i))
        orig_pictures = library.pictures_dir
        library.pictures_dir = lambda: root
        app = self.app
        try:
            win = MainWindow(app)
            win._schedule_refresh()
            win.destroy()
            self.assertTrue(win._closed)
            self.assertTrue(win.scanner.cancelled)
            self.assertEqual(win.refresh_timer, 0)
            warnings = []
            handler = GLib.log_set_writer_func(lambda level, fields, n, data: (
                warnings.append(level) or GLib.LogWriterOutput.HANDLED), None)
            drain(0.8)       # late scan batches / listings arrive here and must be ignored quietly
            self.assertEqual(warnings, [], "a destroyed window must not be touched by late callbacks")
            del handler
        finally:
            library.pictures_dir = orig_pictures


class InfoPanelTests(unittest.TestCase):
    def test_info_panel_does_not_open_the_file_on_the_ui_thread(self):
        import threading
        from photos import actions
        from photos.viewer_widgets import InfoPanel
        folder = make_folder(1)
        path = os.path.join(folder, "p_00.jpg")
        item = library.Item(path, os.stat(path))
        library.read_meta(item)
        threads = []
        orig_exif, orig_dpi = actions.exif_fields, actions.image_dpi_depth
        actions.exif_fields = lambda p: threads.append(threading.current_thread() is threading.main_thread()) or orig_exif(p)
        actions.image_dpi_depth = lambda p: threads.append(threading.current_thread() is threading.main_thread()) or orig_dpi(p)
        noop = lambda *_: None  # noqa: E731
        panel = InfoPanel(noop, noop, noop, noop, noop)
        try:
            panel.update(item, item.w, item.h)
            self.assertNotIn(True, threads, "file access must never happen on the UI thread")
            deadline = time.monotonic() + 5
            while len(threads) < 2 and time.monotonic() < deadline:
                drain(0.05)
            drain(0.1)
            self.assertEqual(threads, [False, False], "both lookups must run, on the worker")
            labels = [w.get_text() for box in panel.fields.get_children() for w in box.get_children()[-1:]
                      if isinstance(w, Gtk.Label)]
            self.assertTrue(any("dpi" in t for t in labels), "details must appear once they are read: %r" % labels)
        finally:
            actions.exif_fields, actions.image_dpi_depth = orig_exif, orig_dpi

    def test_a_late_answer_for_a_previous_item_is_ignored(self):
        from photos.viewer_widgets import InfoPanel
        folder = make_folder(2)
        items = []
        for name in ("p_00.jpg", "p_01.jpg"):
            it = library.Item(os.path.join(folder, name), os.stat(os.path.join(folder, name)))
            library.read_meta(it)
            items.append(it)
        noop = lambda *_: None  # noqa: E731
        panel = InfoPanel(noop, noop, noop, noop, noop)
        panel.update(items[0], 80, 60)
        panel.update(items[1], 80, 60)
        drain(0.6)
        texts = []

        def walk(w):
            if isinstance(w, Gtk.Label):
                texts.append(w.get_text())
            if isinstance(w, Gtk.Container):
                for c in w.get_children():
                    walk(c)
        walk(panel.fields)
        self.assertIn("p_01.jpg", texts)
        self.assertNotIn("p_00.jpg", texts)


if __name__ == "__main__":
    unittest.main(verbosity=2)

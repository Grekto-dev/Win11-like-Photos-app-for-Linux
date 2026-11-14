# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""The order of the previous/next arrows: natural numbering for names, configurable in Settings.

Needs a display for the window tests: xvfb-run -a /usr/bin/python3 tests/test_viewer_order.py
"""
import os
import random
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

import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402
from PIL import Image  # noqa: E402
from photos import i18n, library, settings, theme  # noqa: E402
from photos.app import PhotosApp  # noqa: E402


def drain(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.005)


def names(items):
    return [i.name for i in items]


def make_files(file_names, folder=None):
    d = folder or tempfile.mkdtemp(dir=_ISOLATED.name)
    for n in file_names:
        Image.new("RGB", (16, 12), (len(n) * 7 % 255, 60, 90)).save(os.path.join(d, n), format="JPEG")
    return d


def fake_item(name, mtime=0.0, ctime=0.0):
    it = library.Item(os.path.join(_ISOLATED.name, name), os.stat(_ISOLATED.name))
    it.name, it.mtime, it.ctime = name, mtime, ctime
    return it


_APP = []


def shared_app():
    """Only one Gtk.Application may be registered per process (a second register() fails on the D-Bus object)."""
    if not _APP:
        app = PhotosApp()
        app.register(None)          # emits "startup": windows may only be added after it
        _APP.append(app)
    return _APP[0]


def reset_order():
    settings.set("viewer_sort_by", "name")
    settings.set("viewer_sort_desc", False)


class NaturalNameOrderTests(unittest.TestCase):
    def test_the_example_from_the_request_0_to_32(self):
        files = ["%d.jpg" % n for n in range(33)]
        shuffled = files[:]
        random.Random(7).shuffle(shuffled)
        # plain alphabetical order is what we do NOT want: 0, 1, 10, 11 ... 19, 2, 20 ...
        plain = sorted(files)
        self.assertEqual(plain[:4], ["0.jpg", "1.jpg", "10.jpg", "11.jpg"])
        got = sorted(shuffled, key=library.natural_key)
        self.assertEqual(got, files, "numbers in names must count by value: 2 before 10")
        self.assertEqual(got[:12], ["0.jpg", "1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg", "6.jpg", "7.jpg", "8.jpg",
                                    "9.jpg", "10.jpg", "11.jpg"])
        self.assertEqual(got[-1], "32.jpg")

    def test_sort_items_by_name_is_natural_in_both_directions(self):
        items = [fake_item("%d.jpg" % n) for n in random.Random(3).sample(range(33), 33)]
        asc = names(library.sort_items(items, "name", False))
        self.assertEqual(asc, ["%d.jpg" % n for n in range(33)])
        self.assertEqual(names(library.sort_items(items, "name", True)), asc[::-1])

    def test_camera_style_names(self):
        for expected in (
            ["IMG_2.jpg", "IMG_10.jpg", "IMG_100.jpg"],
            ["IMG_0009.jpg", "IMG_0010.jpg", "IMG_0100.jpg", "IMG_1000.jpg"],
            ["DSC9.jpg", "DSC10.jpg"],
            ["a1b2.jpg", "a1b10.jpg", "a2b1.jpg"],
            ["Trip 2 day 9.jpg", "Trip 2 day 10.jpg", "Trip 10 day 1.jpg"],
        ):
            with self.subTest(expected=expected):
                shuffled = expected[:]
                random.Random(1).shuffle(shuffled)
                self.assertEqual(sorted(shuffled, key=library.natural_key), expected)

    def test_copies_come_right_after_the_original(self):
        expected = ["foto.jpg", "foto (1).jpg", "foto (2).jpg", "foto (10).jpg"]
        shuffled = expected[:]
        random.Random(5).shuffle(shuffled)
        self.assertEqual(sorted(shuffled, key=library.natural_key), expected)
        # the extension never decides before the name: "foto.png" stays with "foto", not after "foto (1).jpg"
        self.assertEqual(sorted(["foto (1).jpg", "foto.png", "foto.jpg"], key=library.natural_key),
                         ["foto.jpg", "foto.png", "foto (1).jpg"])

    def test_case_and_accents_do_not_split_the_order(self):
        got = sorted(["b 2.jpg", "B 10.jpg", "\u00e1 1.jpg", "Z.jpg"], key=library.natural_key)
        self.assertEqual(got, ["\u00e1 1.jpg", "b 2.jpg", "B 10.jpg", "Z.jpg"])

    def test_equal_numbers_with_different_padding_are_deterministic(self):
        a = sorted(["img 01.jpg", "img 1.jpg", "img 001.jpg"], key=lambda n: (library.natural_key(n), n))
        b = sorted(["img 001.jpg", "img 1.jpg", "img 01.jpg"], key=lambda n: (library.natural_key(n), n))
        self.assertEqual(a, b)
        items = [fake_item(n) for n in ("img 01.jpg", "img 1.jpg", "img 001.jpg")]
        self.assertEqual(names(library.sort_items(items, "name", False)),
                         names(library.sort_items(items[::-1], "name", False)))

    def test_absurdly_long_numbers_do_not_crash(self):
        longest = "x" + "9" * 6000 + ".jpg"
        got = sorted([longest, "x1.jpg", "x" + "9" * 5000 + ".jpg"], key=library.natural_key)
        self.assertEqual(got[0], "x1.jpg")
        self.assertEqual(got[-1], longest)

    def test_non_ascii_digits_and_empty_stems(self):
        sorted([".jpg", "\u0663.jpg", "3.jpg", "\u0661\u0660.jpg", "a.jpg"], key=library.natural_key)

    def test_time_orders_break_ties_by_natural_name(self):
        items = [fake_item("p10.jpg", mtime=5), fake_item("p2.jpg", mtime=5), fake_item("p1.jpg", mtime=9),
                 fake_item("p3.jpg", mtime=1)]
        self.assertEqual(names(library.sort_items(items, "modified", False)), ["p3.jpg", "p2.jpg", "p10.jpg", "p1.jpg"])
        items = [fake_item("p10.jpg", ctime=5), fake_item("p2.jpg", ctime=5), fake_item("p1.jpg", ctime=9),
                 fake_item("p3.jpg", ctime=1)]
        self.assertEqual(names(library.sort_items(items, "created", False)), ["p3.jpg", "p2.jpg", "p10.jpg", "p1.jpg"])
        self.assertEqual(names(library.sort_items(items, "created", True)), ["p1.jpg", "p10.jpg", "p2.jpg", "p3.jpg"])


class ViewerOrderSettingTests(unittest.TestCase):
    def setUp(self):
        reset_order()

    def tearDown(self):
        reset_order()

    def test_defaults_are_name_ascending(self):
        self.assertEqual(settings.DEFAULTS["viewer_sort_by"], "name")
        self.assertIs(settings.DEFAULTS["viewer_sort_desc"], False)
        self.assertEqual(library.viewer_order(), ("name", False))

    def test_invalid_values_fall_back_instead_of_breaking_the_viewer(self):
        settings.set("viewer_sort_by", "taken")          # not offered for the arrows: needs reading every image
        settings.set("viewer_sort_desc", "yes")
        self.assertEqual(library.viewer_order(), ("name", False))
        settings.set("viewer_sort_by", 42)
        self.assertEqual(library.viewer_order()[0], "name")

    def test_list_siblings_follows_the_setting(self):
        folder = make_files(["%d.jpg" % n for n in range(1, 13)])
        for k, n in enumerate(range(1, 13)):             # modification times: 12 is the oldest, 1 the newest
            os.utime(os.path.join(folder, "%d.jpg" % n), (1_700_000_000 + (12 - k) * 100,) * 2)
        target = os.path.join(folder, "5.jpg")

        items, idx = library.list_siblings(target)
        self.assertEqual(names(items), ["%d.jpg" % n for n in range(1, 13)], "default: natural name order")
        self.assertEqual(items[idx].name, "5.jpg")

        settings.set("viewer_sort_desc", True)
        items, idx = library.list_siblings(target)
        self.assertEqual(names(items), ["%d.jpg" % n for n in range(12, 0, -1)])
        self.assertEqual(items[idx].name, "5.jpg")

        settings.set("viewer_sort_by", "modified")
        settings.set("viewer_sort_desc", False)
        items, idx = library.list_siblings(target)
        self.assertEqual(names(items), ["%d.jpg" % n for n in range(12, 0, -1)], "oldest first")
        settings.set("viewer_sort_desc", True)
        items, idx = library.list_siblings(target)
        self.assertEqual(names(items), ["%d.jpg" % n for n in range(1, 13)], "newest first")
        self.assertEqual(items[idx].name, "5.jpg")

    def test_list_siblings_does_not_read_images_for_any_order(self):
        folder = make_files(["a%d.jpg" % n for n in range(8)])
        calls = []
        orig = library.read_meta
        library.read_meta = lambda it: calls.append(it.name) or orig(it)
        try:
            for by in ("name", "created", "modified"):
                settings.set("viewer_sort_by", by)
                library.list_siblings(os.path.join(folder, "a3.jpg"))
        finally:
            library.read_meta = orig
        self.assertEqual(calls, [], "ordering must come from the directory listing, never from opening images")

    def test_order_for_viewer_keeps_the_chosen_photo(self):
        items = [fake_item("%d.jpg" % n) for n in (10, 2, 33, 1, 7)]
        chosen = items[2]                                # 33.jpg
        ordered, idx = library.order_for_viewer(items, 2)
        self.assertEqual(names(ordered), ["1.jpg", "2.jpg", "7.jpg", "10.jpg", "33.jpg"])
        self.assertIs(ordered[idx], chosen)
        settings.set("viewer_sort_desc", True)
        ordered, idx = library.order_for_viewer(items, 2)
        self.assertEqual(names(ordered), ["33.jpg", "10.jpg", "7.jpg", "2.jpg", "1.jpg"])
        self.assertIs(ordered[idx], chosen)
        self.assertEqual(names(items), ["10.jpg", "2.jpg", "33.jpg", "1.jpg", "7.jpg"], "the caller's list is untouched")


class OpenPathsOrderTests(unittest.TestCase):
    class Recorder:
        def __init__(self):
            self.kw = None

        def open_gallery(self):
            pass

        def open_viewer(self, items, index, **kw):
            self.items, self.index, self.kw = items, index, kw
            return "WINDOW"

        def _adopt_siblings_async(self, win, item):
            pass

    def test_files_given_on_the_command_line_keep_the_order_they_were_typed(self):
        folder = make_files(["b.jpg", "a.jpg", "c.jpg"])
        rec: Any = self.Recorder()
        PhotosApp._open_paths(rec, [os.path.join(folder, n) for n in ("c.jpg", "a.jpg", "b.jpg")], {})
        self.assertEqual(names(rec.items), ["c.jpg", "a.jpg", "b.jpg"])
        self.assertIs(rec.kw.get("resort"), False)


class ViewerWindowOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.set("viewer_maximized", False)
        i18n.set_language("en")
        theme.apply()
        cls.app = shared_app()

    def setUp(self):
        reset_order()
        self.wins = []

    def tearDown(self):
        for w in self.wins:
            w.destroy()
        drain()
        reset_order()

    def items_of(self, folder):
        return library.sort_items(library.list_folder(folder, recursive=False), "name", False)

    def open_from(self, folder, name, **kw):
        items = self.items_of(folder)
        idx = next(k for k, i in enumerate(items) if i.name == name)
        win = self.app.open_viewer(list(items), idx, **kw)
        self.wins.append(win)
        drain()
        return win

    def test_gallery_style_open_uses_the_viewer_order_and_the_clicked_photo(self):
        folder = make_files(["%d.jpg" % n for n in range(1, 13)])
        gallery_order = list(reversed(self.items_of(folder)))        # e.g. the Gallery sorted otherwise
        clicked = next(k for k, i in enumerate(gallery_order) if i.name == "4.jpg")
        win = self.app.open_viewer(gallery_order, clicked)
        self.wins.append(win)
        drain()
        self.assertEqual(names(win.items), ["%d.jpg" % n for n in range(1, 13)])
        self.assertEqual(win.item.name, "4.jpg")
        win.go(1)
        drain(0.4)
        self.assertEqual(win.item.name, "5.jpg", "the arrow moves to the next number, not the next alphabetical name")

    def test_arrows_walk_the_numbers_in_both_directions(self):
        folder = make_files(["%d.jpg" % n for n in range(0, 21)])
        win = self.open_from(folder, "9.jpg")
        seen = []
        for _i in range(3):
            win.go(1)
            drain(0.35)
            seen.append(win.item.name)
        self.assertEqual(seen, ["10.jpg", "11.jpg", "12.jpg"], "9 -> 10 -> 11 -> 12, never 9 -> 1 or 10 -> 2")
        for _i in range(4):
            win.go(-1)
            drain(0.35)
        self.assertEqual(win.item.name, "8.jpg")

    def test_descending_order_reverses_the_arrows(self):
        settings.set("viewer_sort_desc", True)
        folder = make_files(["%d.jpg" % n for n in range(1, 8)])
        win = self.open_from(folder, "4.jpg")
        self.assertEqual(names(win.items), ["%d.jpg" % n for n in range(7, 0, -1)])
        win.go(1)
        drain(0.4)
        self.assertEqual(win.item.name, "3.jpg")

    def test_changing_the_setting_reorders_open_viewers_and_keeps_the_photo(self):
        folder = make_files(["%d.jpg" % n for n in range(1, 13)])
        win = self.open_from(folder, "6.jpg")
        current = win.item
        self.assertEqual(names(win.items)[:3], ["1.jpg", "2.jpg", "3.jpg"])
        settings.set("viewer_sort_desc", True)
        drain(0.3)
        self.assertEqual(names(win.items), ["%d.jpg" % n for n in range(12, 0, -1)])
        self.assertIs(win.item, current)
        self.assertEqual(win.index, 6)
        self.assertEqual(win.film.index, 6)
        self.assertEqual(names(win.film.items), names(win.items))
        win.go(1)
        drain(0.4)
        self.assertEqual(win.item.name, "5.jpg")

    def test_viewer_opened_with_explicit_files_is_not_reordered(self):
        folder = make_files(["b.jpg", "a.jpg", "c.jpg"])
        items = [library.Item(os.path.join(folder, n), os.stat(os.path.join(folder, n))) for n in ("c.jpg", "a.jpg", "b.jpg")]
        win = self.app.open_viewer(items, 0, resort=False)
        self.wins.append(win)
        drain()
        settings.set("viewer_sort_by", "modified")
        drain(0.3)
        self.assertEqual(names(win.items), ["c.jpg", "a.jpg", "b.jpg"])

    def test_siblings_added_after_opening_follow_the_current_order(self):
        folder = make_files(["%d.jpg" % n for n in range(1, 13)])
        path = os.path.join(folder, "3.jpg")
        item = library.Item(path, os.stat(path))
        from photos.viewer import ViewerWindow
        win = ViewerWindow(None, [item], 0)
        self.wins.append(win)
        drain()
        settings.set("viewer_sort_desc", True)
        sibs, _idx = library.list_siblings(path)
        settings.set("viewer_sort_desc", False)          # the setting flips while the listing was in flight
        win.adopt_siblings(sibs)
        self.assertEqual(names(win.items), ["%d.jpg" % n for n in range(1, 13)])
        self.assertIs(win.item, item)


class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.set("viewer_maximized", False)
        i18n.set_language("en")
        theme.apply()
        cls.app = shared_app()

    def setUp(self):
        reset_order()

    def tearDown(self):
        reset_order()

    @staticmethod
    def texts(widget):
        out = []

        def walk(w):
            if isinstance(w, Gtk.Label):
                out.append(w.get_text())
            if isinstance(w, Gtk.Container):
                for c in w.get_children():
                    walk(c)
        walk(widget)
        return out

    def test_the_page_offers_the_order_and_the_direction_with_the_current_values(self):
        from photos.gallery import MainWindow
        win = MainWindow(self.app)
        try:
            drain(0.3)
            page = win.settings_page
            page.rebuild()
            texts = self.texts(page)
            self.assertIn("Browsing order", texts)
            self.assertIn("Browsing direction", texts)
            self.assertIn("Name", texts, "the current choice is shown on the button")
            self.assertIn("Ascending", texts)
            settings.set("viewer_sort_by", "modified")
            settings.set("viewer_sort_desc", True)
            page.rebuild()
            texts = self.texts(page)
            self.assertIn("Date modified", texts)
            self.assertIn("Descending", texts)
        finally:
            win.destroy()
            drain()

    def test_the_page_lists_exactly_the_three_orders_that_need_no_image_reading(self):
        from photos import settingspage
        self.assertEqual([k for k, _t in settingspage.viewer_order_options()], ["name", "created", "modified"])
        self.assertEqual([k for k, _t in settingspage.viewer_direction_options()], [False, True])

    def test_the_choice_is_saved_to_the_settings_file(self):
        import json
        settings.set("viewer_sort_by", "created")
        settings.set("viewer_sort_desc", True)
        data = json.load(open(settings.PATH, encoding="utf-8"))
        self.assertEqual((data["viewer_sort_by"], data["viewer_sort_desc"]), ("created", True))


if __name__ == "__main__":
    unittest.main(verbosity=2)

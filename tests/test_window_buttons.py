# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Window buttons (minimize, maximize, close) must show up whatever the desktop GTK/icon theme does.

Regression: with the Mint-Y-Dark-Aqua-Win11 theme the stock GTK title buttons were invisible, because that theme hides
their GtkImage (opacity 0) and draws the glyphs as a background-image, which the app's own CSS then cleared. The app now
draws its own buttons. The hostile CSS below is what that theme does (and a "no icons" icon theme is simulated by the
fact that the glyphs here never come from the icon theme).

Needs a display, e.g. xvfb-run -a /usr/bin/python3 tests/test_window_buttons.py.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ISOLATED = tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME'] = str(Path(_ISOLATED.name) / 'config')
os.environ['XDG_CACHE_HOME'] = str(Path(_ISOLATED.name) / 'cache')

import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk  # noqa: E402
from PIL import Image  # noqa: E402
from photos import i18n, library, settings, theme  # noqa: E402
from photos.viewer import ViewerWindow  # noqa: E402

# what Mint-Y-Dark-Aqua-Win11 does to GTK title buttons
HOSTILE_THEME = b"""
headerbar button.titlebutton { color: transparent; background-color: transparent; background-image: none;
    min-width: 46px; min-height: 46px; border: 0; }
headerbar button.titlebutton > image { opacity: 0; color: transparent; }
headerbar button.titlebutton.close { background-image: -gtk-gradient(linear, left top, left bottom, from(#f00), to(#f00)); }
"""


def drain(seconds=0.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.005)


def snapshot(widget):
    """Renders `widget` (as GTK draws it, CSS included) and returns a PIL image."""
    a = widget.get_allocation()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, a.width, a.height)
    cr = cairo.Context(surf)
    cr.set_source_rgb(*[int(theme.color('bg')[i:i + 2], 16) / 255 for i in (1, 3, 5)])      # the header bar behind it
    cr.paint()
    widget.draw(cr)
    surf.flush()
    return Image.frombuffer('RGBA', (a.width, a.height), bytes(surf.get_data()), 'raw', 'BGRA', surf.get_stride(), 1).convert('RGB')


def distinct_pixels(img):
    return len(set(img.getdata()))


class WindowButtonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.set('viewer_maximized', False)
        settings.set('theme', 'dark')
        i18n.set_language('en')
        cls.hostile = Gtk.CssProvider()
        cls.hostile.load_from_data(HOSTILE_THEME)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), cls.hostile, Gtk.STYLE_PROVIDER_PRIORITY_THEME)
        theme.apply()
        path = Path(_ISOLATED.name) / 'image.png'
        Image.new('RGB', (800, 450), '#204963').save(path)
        item = library.Item(str(path), path.stat())
        library.read_meta(item)
        cls.win = ViewerWindow(None, [item], 0)
        cls.win.resize(1100, 700)
        cls.win.show_all()
        drain(0.5)
        cls.hb = cls.win.hb

    @classmethod
    def tearDownClass(cls):
        Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), cls.hostile)
        cls.win.destroy()
        drain()

    def buttons(self):
        box = self.win.window_buttons
        return dict(zip(('minimize', 'maximize', 'close'), box.get_children()))

    def test_the_header_bar_does_not_use_the_stock_gtk_title_buttons(self):
        self.assertFalse(self.hb.get_show_close_button())
        found = []

        def walk(w):
            if 'titlebutton' in w.get_style_context().list_classes():
                found.append(w)
            if isinstance(w, Gtk.Container):
                w.forall(walk)
        walk(self.hb)
        self.assertEqual(found, [])

    def test_three_buttons_at_the_right_edge_in_order(self):
        b = self.buttons()
        self.assertEqual(list(b), ['minimize', 'maximize', 'close'])
        xs = []
        for name, btn in b.items():
            self.assertTrue(btn.get_visible(), name)
            a = btn.get_allocation()
            self.assertEqual((a.width, a.height), (46, 48), name)
            xs.append(btn.translate_coordinates(self.win, 0, 0)[0])
        self.assertEqual(xs[1] - xs[0], 46)
        self.assertEqual(xs[2] - xs[1], 46)
        hb_right = self.hb.translate_coordinates(self.win, 0, 0)[0] + self.hb.get_allocated_width()
        self.assertLessEqual(abs(xs[2] + 46 - hb_right), 1)                 # flush with the header bar's right edge (GTK rounds by 1 px)
        # and the other header bar buttons are to the left of them
        other = self.win.btn_open_with.translate_coordinates(self.win, 0, 0)[0] + self.win.btn_open_with.get_allocated_width()
        self.assertLessEqual(other, xs[0])

    def test_each_button_draws_a_visible_glyph_even_with_a_hostile_theme(self):
        for dark in (True, False):
            theme.apply(force_dark=dark)
            drain(0.2)
            for name, btn in self.buttons().items():
                img = snapshot(btn)
                self.assertGreater(distinct_pixels(img), 1, '%s is blank (dark=%s)' % (name, dark))
                bg = img.getpixel((2, 2))
                lit = sum(1 for p in img.getdata() if sum(abs(a - b) for a, b in zip(p, bg)) > 120)
                self.assertGreater(lit, 8, '%s glyph too faint (dark=%s)' % (name, dark))
        theme.apply(force_dark=True)
        drain(0.2)

    def test_the_glyphs_are_different_from_each_other(self):
        theme.apply(force_dark=True)
        drain(0.2)
        shots = {n: list(snapshot(b).getdata()) for n, b in self.buttons().items()}
        self.assertNotEqual(shots['minimize'], shots['maximize'])
        self.assertNotEqual(shots['maximize'], shots['close'])
        self.assertNotEqual(shots['minimize'], shots['close'])

    def test_close_turns_red_under_the_pointer(self):
        theme.apply(force_dark=True)
        drain(0.2)
        close = self.buttons()['close']
        close.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        drain(0.15)
        img = snapshot(close)
        close.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        r, g, b = img.getpixel((2, 2))
        self.assertEqual((r, g, b), (0xc4, 0x2b, 0x1c))
        light = sum(1 for p in img.getdata() if p[1] > 120)          # the white X on the red background (anti-aliased diagonals)
        self.assertGreater(light, 8)

    def test_other_buttons_get_the_grey_hover(self):
        theme.apply(force_dark=True)
        drain(0.2)
        mini = self.buttons()['minimize']
        idle = snapshot(mini).getpixel((2, 2))
        mini.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        drain(0.15)
        hover = snapshot(mini).getpixel((2, 2))
        mini.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        self.assertNotEqual(idle, hover)
        self.assertNotEqual(hover, (0xc4, 0x2b, 0x1c))

    def test_minimize_maximize_and_close_act_on_the_window(self):
        calls = []
        win = self.win
        win.window_buttons.actions = {n: (lambda n=n: calls.append(n)) for n in ('iconify', 'maximize', 'unmaximize', 'close')}
        try:
            b = self.buttons()
            b['minimize'].clicked()
            b['maximize'].clicked()
            b['close'].clicked()
            self.assertEqual(calls, ['iconify', 'maximize', 'close'])
            calls.clear()
            win.window_buttons.maximized = True            # what the window-state handler records
            b['maximize'].clicked()
            self.assertEqual(calls, ['unmaximize'])
        finally:
            win.window_buttons.actions = None
            win.window_buttons.maximized = False
            win.window_buttons.refresh()

    def test_the_maximize_button_becomes_restore_when_maximized(self):
        i18n.set_language('en')
        win = self.win
        win.window_buttons.refresh()
        before = (self.buttons()['maximize'].get_tooltip_text(), list(snapshot(self.buttons()['maximize']).getdata()))
        self.assertEqual(before[0], 'Maximize')
        win.maximize()
        deadline = time.monotonic() + 4
        while not win.is_maximized() and time.monotonic() < deadline:
            drain(0.1)
        if not win.is_maximized():
            self.skipTest('the window manager did not maximise the window')
        drain(0.4)
        after = (self.buttons()['maximize'].get_tooltip_text(), list(snapshot(self.buttons()['maximize']).getdata()))
        self.assertEqual(after[0], 'Restore')
        self.assertNotEqual(before[1], after[1])
        win.unmaximize()
        deadline = time.monotonic() + 4
        while win.is_maximized() and time.monotonic() < deadline:
            drain(0.1)
        drain(0.4)
        self.assertEqual(self.buttons()['maximize'].get_tooltip_text(), 'Maximize')

    def test_tooltips_follow_the_language(self):
        try:
            i18n.set_language('pt_BR')
            self.win.window_buttons.refresh()
            tips = {n: b.get_tooltip_text() for n, b in self.buttons().items()}
            self.assertEqual(tips, {'minimize': 'Minimizar', 'maximize': 'Maximizar', 'close': 'Fechar'})
        finally:
            i18n.set_language('en')
            self.win.window_buttons.refresh()

    def test_the_gallery_window_has_them_too(self):
        from photos.app import PhotosApp
        from photos.gallery import MainWindow
        app = PhotosApp()
        app.register(None)
        g = MainWindow(app)
        g.show_all()
        drain(0.5)
        try:
            self.assertFalse(g.hb.get_show_close_button())
            names = [b.get_tooltip_text() for b in g.window_buttons.get_children()]
            self.assertEqual(names, ['Minimize', 'Maximize', 'Close'])
            for b in g.window_buttons.get_children():
                self.assertGreater(distinct_pixels(snapshot(b)), 1)
            right = g.window_buttons.get_children()[-1]
            hb_right = g.hb.translate_coordinates(g, 0, 0)[0] + g.hb.get_allocated_width()
            self.assertLessEqual(abs(right.translate_coordinates(g, 0, 0)[0] + 46 - hb_right), 1)
        finally:
            g.destroy()
            drain(0.2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

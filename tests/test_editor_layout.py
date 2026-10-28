# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""GTK regression tests: crop aspect-ratio scrolling must not cover labels.

Run with a display, e.g. xvfb-run -a /usr/bin/python3 tests/test_editor_layout.py.
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

from PIL import Image  # noqa: E402
from photos import i18n, library, settings, theme  # noqa: E402
from photos.viewer import ViewerWindow  # noqa: E402
from gi.repository import Gtk  # noqa: E402


def drain(seconds=0.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.005)


class CropLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.set('viewer_maximized', False)
        settings.set('theme', 'dark')
        i18n.set_language('pt_BR')
        theme.apply()
        path = Path(_ISOLATED.name) / 'image.png'
        Image.new('RGB', (800, 450), '#204963').save(path)
        item = library.Item(str(path), path.stat())
        library.read_meta(item)
        cls.win = ViewerWindow(None, [item], 0)
        cls.win.resize(1200, 800)
        drain()
        cls.win.open_editor()
        drain()
        if cls.win.editor is None:
            raise AssertionError('open_editor() did not create cls.win.editor')
        cls.editor = cls.win.editor
        cls.editor.aspect_btn.clicked()
        drain()
        # Widget tree (photos/editor.py _build_aspect_row): bottom stack page 'aspect' is a
        # VERTICAL box whose child 0 is the ScrolledWindow (children[1] is the Done button);
        # the scroller's child is the Gtk.Viewport, whose child is the button row box.
        # Each aspect button's child is a column: child 0 = icon DrawingArea, child 1 = label.
        cls.scroller = cls.editor.bottom.get_child_by_name('aspect').get_children()[0]

    @classmethod
    def tearDownClass(cls):
        cls.win.destroy()
        drain()

    def test_horizontal_scrollbar_stays_thin_when_revealed(self):
        for dark in (True, False):
            with self.subTest(dark=dark):
                theme.apply(force_dark=dark)
                self.scroller.get_hadjustment().set_value(10)
                drain()
                hadj = self.scroller.get_hadjustment()
                self.assertGreater(hadj.get_upper(), hadj.get_page_size(),
                                   'Row must overflow horizontally so the scrollbar is revealed')
                self.assertTrue(self.scroller.get_hscrollbar().get_visible(),
                                'Horizontal scrollbar must be visible before measuring its thickness')
                minimum = self.scroller.get_hscrollbar().get_preferred_height()[0]
                self.assertLessEqual(minimum, 12,
                                     'Horizontal scrollbar must not inherit the 40 px vertical thumb height')
                vertical_width = self.scroller.get_vscrollbar().get_preferred_width()[0]
                self.assertLessEqual(vertical_width, 12)

    def test_aspect_labels_stay_above_the_scrollbar(self):
        """Reserve the overlay scrollbar's preferred thickness at the bottom as a worst case.

        Overlay scrollbars fade out when idle, but the layout must keep labels clear of the
        track even while the bar is faded or fully visible, so the full preferred thickness
        is subtracted from the allocation regardless of current opacity.
        """
        theme.apply(force_dark=True)
        drain()
        thickness = self.scroller.get_hscrollbar().get_preferred_height()[0]
        track_top = self.scroller.get_allocated_height() - thickness
        row = self.scroller.get_child().get_child()
        for button in row.get_children():
            label = button.get_child().get_children()[1]
            _, y = label.translate_coordinates(self.scroller, 0, 0)
            self.assertLessEqual(y + label.get_allocated_height(), track_top,
                                 'The scrollbar must not cover aspect ratio labels: ' + label.get_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)

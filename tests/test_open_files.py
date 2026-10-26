# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for explicitly opened images with nonstandard file names."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ISOLATED = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = str(Path(_ISOLATED.name) / "config")
os.environ["XDG_CACHE_HOME"] = str(Path(_ISOLATED.name) / "cache")

from photos.app import PhotosApp  # noqa: E402


class OpenRecorder:
    """Record the routing decision; exercise the real file and metadata pipeline."""
    def __init__(self):
        self.gallery_opened = False
        self.viewer = None

    def open_gallery(self):
        self.gallery_opened = True

    def open_viewer(self, items, index, **options):
        self.viewer = (items, index, options)


class ExplicitFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)

    def test_portal_temporary_png_opens_in_viewer(self):
        image = self.folder / '.xdp-.photo.png.2-4.pcsave.tmp-example'
        Image.new('RGB', (42, 31), '#bc531c').save(image, format='PNG')
        routed: Any = OpenRecorder()
        PhotosApp._open_paths(routed, [str(image)], {})
        self.assertFalse(routed.gallery_opened, 'A PNG with a temporary suffix must not fall back to Gallery')
        self.assertIsNotNone(routed.viewer)
        items, index, _ = routed.viewer
        self.assertEqual(items[index].path, str(image))
        self.assertEqual((items[index].w, items[index].h), (42, 31))


    def test_header_detection_preserves_scan_filters(self):
        from photos import library
        for name, fmt in [('no extension', 'JPEG'), ('wrong.dat', 'PNG'), ('.hidden-image', 'GIF')]:
            with self.subTest(name=name):
                image = self.folder / name
                Image.new('RGB', (42, 31)).save(image, format=fmt)
                self.assertFalse(library.is_media(str(image)))
                self.assertTrue(library.is_media(str(image), sniff=True))
                routed: Any = OpenRecorder()
                PhotosApp._open_paths(routed, [str(image)], {})
                self.assertFalse(routed.gallery_opened)
                self.assertEqual(routed.viewer[0][routed.viewer[1]].path, str(image))

    def test_non_image_and_missing_files_are_not_opened(self):
        for name in ['notes.tmp', 'missing']:
            with self.subTest(name=name):
                path = self.folder / name
                if name == 'notes.tmp':
                    path.write_text('This is not an image.')
                routed: Any = OpenRecorder()
                PhotosApp._open_paths(routed, [str(path)], {})
                self.assertTrue(routed.gallery_opened)
                self.assertIsNone(routed.viewer)

    def test_standard_image_still_selects_itself_among_siblings(self):
        first, selected = self.folder / 'a.jpg', self.folder / 'b.jpg'
        for path in (first, selected):
            Image.new('RGB', (42, 31)).save(path)
        routed: Any = OpenRecorder()
        PhotosApp._open_paths(routed, [str(selected)], {})
        self.assertFalse(routed.gallery_opened)
        self.assertEqual(len(routed.viewer[0]), 2)
        self.assertEqual(routed.viewer[0][routed.viewer[1]].path, str(selected))


if __name__ == '__main__':
    unittest.main(verbosity=2)

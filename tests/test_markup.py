# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Markup tools (pen, second pen, highlighter): sizes, colours, line modes and arrows.

The numbers below were measured on the Windows Photos app (see docs/DESIGN-NOTES.md): stroke widths are fixed in
screen pixels and converted to image pixels by the zoom, the highlighter is a 50 % alpha with flat ends, arrow heads
are two arms at 45 degrees about 3.8 times the stroke width long.

The first two classes need no display; the last one opens the editor and needs one, e.g.
xvfb-run -a /usr/bin/python3 tests/test_markup.py.
"""
import json
import math
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_ISOLATED = tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME'] = str(Path(_ISOLATED.name) / 'config')
os.environ['XDG_CACHE_HOME'] = str(Path(_ISOLATED.name) / 'cache')

from PIL import Image  # noqa: E402
from photos import i18n, imgops, library, markup, settings, theme  # noqa: E402

BLUE = '#0078d7'
YELLOW = '#fed430'
REFERENCE_PALETTE = [
    '#fed430', '#fbae17', '#f36323', '#e3182d', '#5b318d', '#914bb8', '#cf1278', '#c10051',
    '#3eccfd', '#0078d7', '#0051ba', '#7ec400', '#00b44b', '#ebebeb', '#b6b6b6', '#1f1f1f',
]


def rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class MarkupModelTests(unittest.TestCase):
    def setUp(self):
        settings.set('markup_tools', json.loads(json.dumps(settings.DEFAULTS['markup_tools'])))

    def test_widths_are_the_measured_screen_pixels(self):
        self.assertEqual(markup.WIDTHS['pen'], (1, 2, 4, 6, 8, 12))
        self.assertEqual(markup.WIDTHS['highlighter'], (8, 12, 16, 24, 28, 32))
        self.assertEqual(markup.LEVELS, 6)

    def test_default_level_is_three(self):
        self.assertEqual(markup.DEFAULT_LEVEL, 3)
        for tool in markup.TOOLS:
            self.assertEqual(markup.load_cfg(tool)['size'], 3)
        self.assertEqual(markup.width_ui('pen', 3), 4)
        self.assertEqual(markup.width_ui('highlighter', 3), 16)

    def test_both_pens_share_the_widths_and_the_highlighter_has_its_own(self):
        self.assertEqual(markup.kind_of('pen'), 'pen')
        self.assertEqual(markup.kind_of('pen2'), 'pen')
        self.assertEqual(markup.kind_of('highlighter'), 'highlighter')
        self.assertEqual([markup.width_ui('pen2', n) for n in range(1, 7)], list(markup.WIDTHS['pen']))

    def test_palette_is_the_reference_one_in_two_rows_of_eight(self):
        self.assertEqual([c for c, _n in markup.PALETTE], REFERENCE_PALETTE)
        self.assertEqual(len(markup.PALETTE), 16)
        names = [n for _c, n in markup.PALETTE]
        self.assertEqual(len(set(names)), 16)
        self.assertEqual(names[0], 'Dark yellow')
        self.assertEqual(names[9], 'Blue')
        self.assertEqual(names[15], 'Black')

    def test_default_tools(self):
        self.assertEqual(markup.TOOLS, ('pen', 'pen2', 'highlighter'))
        self.assertEqual(markup.load_cfg('pen'), {'color': BLUE, 'size': 3, 'mode': 0})
        self.assertEqual(markup.load_cfg('pen2'), {'color': '#1f1f1f', 'size': 3, 'mode': 0})
        self.assertEqual(markup.load_cfg('highlighter'), {'color': YELLOW, 'size': 3, 'mode': 0})

    def test_line_modes(self):
        self.assertEqual(markup.modes_for('pen'), [(False, 0), (False, 1), (False, 2), (True, 0), (True, 1), (True, 2)])
        self.assertEqual(markup.modes_for('pen2'), markup.modes_for('pen'))
        self.assertEqual(markup.modes_for('highlighter'), [(False, 0), (True, 0)])

    def test_each_tool_keeps_its_own_values_and_they_persist(self):
        markup.save_cfg('pen', {'color': '#e3182d', 'size': 6, 'mode': 4})
        markup.save_cfg('pen2', {'color': '#00b44b', 'size': 1, 'mode': 2})
        markup.save_cfg('highlighter', {'color': '#f36323', 'size': 5, 'mode': 1})
        stored = json.loads(Path(settings.PATH).read_text(encoding='utf-8'))['markup_tools']
        self.assertEqual(stored['pen'], {'color': '#e3182d', 'size': 6, 'mode': 4})
        self.assertEqual(markup.load_cfg('pen2'), {'color': '#00b44b', 'size': 1, 'mode': 2})
        self.assertEqual(markup.load_cfg('highlighter'), {'color': '#f36323', 'size': 5, 'mode': 1})
        self.assertEqual(markup.load_cfg('pen')['color'], '#e3182d')

    def test_garbage_in_the_settings_file_falls_back_per_field(self):
        settings.set('markup_tools', {
            'pen': {'color': 'red', 'size': 99, 'mode': 17},
            'pen2': {'color': '#E3182D', 'size': '4', 'mode': True},
            'highlighter': {'color': '#00b44b', 'size': 0, 'mode': 5},
            'unknown': {'color': '#000000'},
        })
        self.assertEqual(markup.load_cfg('pen'), {'color': BLUE, 'size': 3, 'mode': 0})
        self.assertEqual(markup.load_cfg('pen2'), {'color': '#e3182d', 'size': 3, 'mode': 0})
        self.assertEqual(markup.load_cfg('highlighter'), {'color': '#00b44b', 'size': 3, 'mode': 0})
        settings.set('markup_tools', 'broken')
        self.assertEqual(markup.load_cfg('pen'), {'color': BLUE, 'size': 3, 'mode': 0})

    def test_saved_value_is_a_copy(self):
        cfg = markup.load_cfg('pen')
        cfg['size'] = 6
        self.assertEqual(markup.load_cfg('pen')['size'], 3)

    def test_arrow_arms_are_at_45_degrees_and_3_8_widths_long(self):
        a, b = markup.arrow_arms((100.0, 50.0), (1.0, 0.0), 4.0)
        length = 3.8 * 4.0
        self.assertAlmostEqual(math.hypot(a[0] - 100, a[1] - 50), length, places=6)
        self.assertAlmostEqual(math.hypot(b[0] - 100, b[1] - 50), length, places=6)
        self.assertAlmostEqual(a[0], 100 - length * math.cos(math.pi / 4), places=6)
        self.assertAlmostEqual(abs(a[1] - 50), length * math.sin(math.pi / 4), places=6)
        self.assertAlmostEqual(a[1] - 50, -(b[1] - 50), places=6)

    def test_arrow_arms_follow_the_direction(self):
        a, b = markup.arrow_arms((0.0, 0.0), (0.0, 1.0), 4.0)      # moving down: the arms go up and out
        self.assertLess(a[1], 0)
        self.assertLess(b[1], 0)
        self.assertAlmostEqual(a[0], -b[0], places=6)

    def test_arrow_length_is_proportional_to_the_width(self):
        a, _b = markup.arrow_arms((0.0, 0.0), (1.0, 0.0), 1.0)
        self.assertAlmostEqual(math.hypot(*a), 3.8, places=6)
        self.assertEqual(markup.arrow_length(12.0), 12.0 * 3.8)
        self.assertEqual(markup.arrow_length(0.5), 0.5 * 3.8)

    def test_arrow_direction_on_a_small_loop_is_not_backwards(self):
        # a circle of radius 10 drawn with a 12 px pen: no point is 4 x width (48 px) away from the end
        pts = [(10 * math.cos(t / 20 * 2 * math.pi) + 50, 10 * math.sin(t / 20 * 2 * math.pi) + 50) for t in range(0, 19)]
        end, before = pts[-1], pts[-2]
        tangent = (end[0] - before[0], end[1] - before[1])
        n = math.hypot(*tangent)
        d = markup.end_direction(pts, 48.0)
        self.assertIsNotNone(d)
        self.assertGreater(d[0] * tangent[0] / n + d[1] * tangent[1] / n, 0.8)

    def test_arrow_direction_on_a_loop_that_closes_exactly(self):
        pts = [(10 * math.cos(t / 20 * 2 * math.pi) + 50, 10 * math.sin(t / 20 * 2 * math.pi) + 50) for t in range(0, 21)]
        self.assertEqual(pts[0][0], pts[-1][0])
        self.assertIsNotNone(markup.end_direction(pts, 48.0))

    def test_no_direction_when_the_stroke_has_no_extent(self):
        self.assertIsNone(markup.end_direction([(5.0, 5.0), (5.01, 5.0)], 8.0))

    def test_a_hex_colour_with_a_trailing_newline_is_rejected(self):
        settings.set('markup_tools', {'pen': {'color': '#e3182d\n', 'size': 3, 'mode': 0}})
        self.assertEqual(markup.load_cfg('pen')['color'], BLUE)

    def test_eraser_reach_covers_arrow_arms_and_wide_strokes(self):
        self.assertGreaterEqual(markup.hit_radius({'kind': 'highlighter', 'w': 32.0, 'arrows': 0}, 1.0), 16.0)
        self.assertGreaterEqual(markup.hit_radius({'kind': 'pen', 'w': 12.0, 'arrows': 1}, 1.0), 12 * 3.8 * 0.7)
        self.assertEqual(markup.hit_radius({'kind': 'pen', 'w': 1.0, 'arrows': 0}, 1.0), 12.0)      # never below 12 px
        self.assertAlmostEqual(markup.hit_radius({'kind': 'highlighter', 'w': 32.0, 'arrows': 0}, 0.5), 12.0)

    def test_end_direction_of_a_curve_uses_the_last_stretch(self):
        pts = [(float(x), 10 * math.sin(x / 8)) for x in range(0, 120)]
        dx, dy = markup.end_direction(pts, 8.0)
        self.assertAlmostEqual(math.hypot(dx, dy), 1.0, places=6)
        self.assertGreater(dx, 0.9)
        self.assertEqual(markup.end_direction([(5.0, 5.0)], 8.0), None)
        self.assertEqual(markup.end_direction([(5.0, 5.0), (5.0, 5.0)], 8.0), None)
        dx, dy = markup.end_direction([(0.0, 0.0), (3.0, 4.0)], 8.0)        # shorter than the look-back distance
        self.assertAlmostEqual(dx, 0.6)
        self.assertAlmostEqual(dy, 0.8)

    def test_image_width_is_the_screen_width_divided_by_the_zoom(self):
        self.assertAlmostEqual(markup.image_width('pen', 6, 1.0), 12.0)
        self.assertAlmostEqual(markup.image_width('pen', 6, 2.0), 6.0)
        self.assertAlmostEqual(markup.image_width('pen', 6, 0.6063), 12 / 0.6063, places=6)
        self.assertAlmostEqual(markup.image_width('highlighter', 1, 0.5), 16.0)
        self.assertEqual(markup.image_width('pen', 3, 0), 4.0)        # a zero zoom must not divide by zero

    def test_tooltips_describe_the_tool(self):
        i18n.set_language('en')
        self.assertEqual(markup.tool_tooltip('pen', markup.load_cfg('pen')),
                         'Pen: Blue, Thickness: 3, Freehand line without arrow')
        self.assertEqual(markup.tool_tooltip('pen2', markup.load_cfg('pen2')),
                         'Pen: Black, Thickness: 3, Freehand line without arrow')
        self.assertEqual(markup.tool_tooltip('highlighter', markup.load_cfg('highlighter')),
                         'Highlighter: Dark yellow, Thickness: 3, Freehand line')
        cfg = {'color': '#e3182d', 'size': 6, 'mode': 4}
        self.assertEqual(markup.tool_tooltip('pen', cfg), 'Pen: Red, Thickness: 6, Straight line with an arrow at the end')
        self.assertEqual(markup.tool_tooltip('pen', cfg, selected=True),
                         'Pen: Red, Thickness: 6, Straight line with an arrow at the end\n'
                         'Select again to change the ink properties.')

    def test_tooltips_are_translated(self):
        i18n.set_language('pt_BR')
        try:
            text = markup.tool_tooltip('pen', markup.load_cfg('pen'))
        finally:
            i18n.set_language('en')
        self.assertNotIn('Thickness', text)
        self.assertTrue(text.startswith('Caneta: Azul, Espessura: 3'))


def render(strokes, size=(100, 60)):
    """Burns the strokes (normalised points) on a white image of `size` and returns it."""
    im = Image.new('RGB', size, (255, 255, 255))
    return imgops.burn_strokes(im, strokes, (0.0, 0.0, 1.0, 1.0))


def stroke(kind, color, w, pts, size=(100, 60), arrows=0, straight=False):
    W, H = size
    return {'kind': kind, 'color': color, 'w': w, 'pts': [(x / W, y / H) for x, y in pts],
            'arrows': arrows, 'straight': straight}


class RenderTests(unittest.TestCase):
    def test_pen_has_the_requested_width_and_round_ends(self):
        im = render([stroke('pen', BLUE, 4, [(10, 30), (90, 30)], straight=True)])
        px = im.load()
        self.assertEqual([px[50, y] == rgb(BLUE) for y in range(26, 34)],
                         [False, False, True, True, True, True, False, False])
        self.assertEqual(px[50, 27], (255, 255, 255))
        self.assertEqual(px[9, 30], rgb(BLUE))        # the round cap reaches half a width past the start
        self.assertNotEqual(px[8, 30], (255, 255, 255))
        self.assertEqual(px[7, 30], (255, 255, 255))

    def test_a_one_pixel_pen_is_one_pixel(self):
        im = render([stroke('pen', BLUE, 1, [(10, 30.5), (90, 30.5)], straight=True)])
        rows = [y for y in range(60) if im.getpixel((50, y)) != (255, 255, 255)]
        self.assertEqual(rows, [30])

    def test_highlighter_is_half_transparent_with_flat_ends(self):
        im = render([stroke('highlighter', YELLOW, 8, [(10, 30), (90, 30)], straight=True)])
        px = im.load()
        want = tuple(round((a + 255) / 2) for a in rgb(YELLOW))
        self.assertTrue(close(px[50, 30], want, 1), (px[50, 30], want))
        self.assertEqual(px[9, 30], (255, 255, 255))      # butt cap: nothing before the first point
        self.assertTrue(close(px[10, 30], want, 1))
        self.assertEqual(px[50, 25], (255, 255, 255))
        self.assertTrue(close(px[50, 26], want, 1))

    def test_highlighter_over_a_colour_blends_each_channel_by_half(self):
        im = Image.new('RGB', (100, 60), (90, 138, 209))
        out = imgops.burn_strokes(im, [stroke('highlighter', YELLOW, 8, [(10, 30), (90, 30)], straight=True)],
                                  (0.0, 0.0, 1.0, 1.0))
        want = tuple(round((b + y) / 2) for b, y in zip((90, 138, 209), rgb(YELLOW)))
        self.assertTrue(close(out.getpixel((50, 30)), want, 1), out.getpixel((50, 30)))

    def test_a_highlighter_crossing_itself_does_not_get_darker(self):
        def dense(a, b, n=40):
            return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
        pts = dense((20, 20), (80, 20)) + dense((80, 20), (80, 40)) + dense((80, 40), (50, 40)) + dense((50, 40), (50, 10))
        im = render([stroke('highlighter', YELLOW, 8, pts)])       # the last leg crosses the first at (50, 20)
        single = im.getpixel((30, 20))
        crossing = im.getpixel((50, 20))
        self.assertTrue(close(crossing, single, 1), (crossing, single))

    def test_two_highlighter_strokes_do_add_up(self):
        a = stroke('highlighter', YELLOW, 8, [(10, 30), (90, 30)], straight=True)
        im = render([a, dict(a)])
        once = tuple(round((c + 255) / 2) for c in rgb(YELLOW))
        twice = tuple(round((c + o) / 2) for c, o in zip(rgb(YELLOW), once))
        self.assertTrue(close(im.getpixel((50, 30)), twice, 3), (im.getpixel((50, 30)), twice))   # 8-bit alpha, twice

    def test_arrow_at_the_end(self):
        w = 4
        base = stroke('pen', BLUE, w, [(10, 30), (90, 30)], straight=True)
        plain = render([base])
        with_arrow = render([dict(base, arrows=1)])
        arm = markup.arrow_length(w) * math.cos(math.pi / 4)
        mid = (round(90 - arm / 2), round(30 - arm / 2))                # middle of the upper arm
        self.assertEqual(plain.getpixel(mid), (255, 255, 255))
        self.assertEqual(with_arrow.getpixel(mid), rgb(BLUE))
        self.assertEqual(with_arrow.getpixel((mid[0], 60 - mid[1])), rgb(BLUE))     # the lower arm, mirrored
        self.assertEqual(with_arrow.getpixel((20, 15)), (255, 255, 255))
        # nothing is added at the other end
        self.assertEqual(with_arrow.getpixel((10 + round(arm / 2), mid[1])), (255, 255, 255))

    def test_arrows_at_both_ends(self):
        w = 4
        base = stroke('pen', BLUE, w, [(10, 30), (90, 30)], straight=True)
        both = render([dict(base, arrows=2)])
        arm = markup.arrow_length(w) * math.cos(math.pi / 4)
        self.assertEqual(both.getpixel((round(10 + arm / 2), round(30 - arm / 2))), rgb(BLUE))
        self.assertEqual(both.getpixel((round(90 - arm / 2), round(30 + arm / 2))), rgb(BLUE))

    def test_arrow_head_scales_with_the_width(self):
        size = (200, 120)
        thin = render([stroke('pen', BLUE, 2, [(20, 60), (180, 60)], size, arrows=1, straight=True)], size)
        thick = render([stroke('pen', BLUE, 12, [(20, 60), (180, 60)], size, arrows=1, straight=True)], size)

        def head_height(im):
            ys = [y for y in range(120) if im.getpixel((172, y)) != (255, 255, 255)]
            return ys[-1] - ys[0] + 1
        self.assertLess(head_height(thin), 12)
        self.assertGreater(head_height(thick), 28)

    def test_freehand_arrow_follows_the_end_of_the_curve(self):
        size = (200, 120)
        pts = [(20 + 6 * i, 60 - 30 * math.sin(i / 6.0)) for i in range(0, 28)]
        plain = render([stroke('pen', BLUE, 4, pts, size)], size)
        arrow = render([stroke('pen', BLUE, 4, pts, size, arrows=1)], size)

        def painted(im):
            return sum(1 for x in range(150, 200) for y in range(120) if im.getpixel((x, y)) != (255, 255, 255))
        self.assertGreater(painted(arrow), painted(plain) + 40)

    def test_highlighter_with_arrows_in_the_data_ignores_them(self):
        base = stroke('highlighter', YELLOW, 8, [(10, 30), (90, 30)], straight=True)
        self.assertEqual(list(render([dict(base, arrows=2)]).getdata()), list(render([base]).getdata()))

    def test_a_single_point_makes_a_dot(self):
        im = render([stroke('pen', BLUE, 6, [(50, 30)])])
        self.assertEqual(im.getpixel((50, 30)), rgb(BLUE))
        self.assertEqual(im.getpixel((60, 30)), (255, 255, 255))

    def test_a_single_click_with_an_arrow_mode_is_still_a_dot(self):
        for arrows in (0, 1, 2):
            im = render([stroke('pen', BLUE, 6, [(50, 30)], arrows=arrows)])
            painted = [(x, y) for x in range(100) for y in range(60) if im.getpixel((x, y)) != (255, 255, 255)]
            xs = [p[0] for p in painted]
            ys = [p[1] for p in painted]
            self.assertLessEqual(max(xs) - min(xs), 7, arrows)
            self.assertLessEqual(max(ys) - min(ys), 7, arrows)

    def test_a_tap_that_barely_moves_with_an_arrow_mode_is_still_a_dot(self):
        im = render([stroke('pen', BLUE, 6, [(50, 30), (50.3, 30)], arrows=2)])
        xs = [x for x in range(100) for y in range(60) if im.getpixel((x, y)) != (255, 255, 255)]
        self.assertLessEqual(max(xs) - min(xs), 7)

    def test_the_crop_does_not_scale_the_width(self):
        full = Image.new('RGB', (200, 120), (255, 255, 255))
        s = {'kind': 'pen', 'color': BLUE, 'w': 6, 'pts': [(0.3, 0.5), (0.7, 0.5)], 'arrows': 0, 'straight': True}
        out = imgops.burn_strokes(full.crop((50, 0, 150, 120)), [s], (0.25, 0.0, 0.75, 1.0))
        rows = [y for y in range(120) if out.getpixel((50, y)) != (255, 255, 255)]
        self.assertEqual(len(rows), 6)

    def test_strokes_from_before_the_width_change_still_render(self):
        old = {'kind': 'pen', 'color': '#ff0000', 'size': 5, 'pts': [(0.2, 0.2), (0.8, 0.8)]}
        out = render([old])
        self.assertNotEqual(out.getpixel((50, 30)), (255, 255, 255))


# ───────────────────────── editor window ─────────────────────────

def _editor_imports():
    global Gdk, Gtk, ViewerWindow
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gdk, Gtk  # noqa: F811
    from photos.viewer import ViewerWindow  # noqa: F811


def drain(seconds=0.15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.005)


def ev(x, y, state=0):
    return types.SimpleNamespace(type=None, button=1, x=x, y=y, state=state)


class EditorMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _editor_imports()
        settings.set('viewer_maximized', False)
        settings.set('theme', 'dark')
        i18n.set_language('en')
        theme.apply()
        path = Path(_ISOLATED.name) / 'image.png'
        Image.new('RGB', (800, 450), '#204963').save(path)
        item = library.Item(str(path), path.stat())
        library.read_meta(item)
        cls.win = ViewerWindow(None, [item], 0)
        cls.win.resize(1200, 800)
        cls.win.show()
        drain()
        cls.win.open_editor()
        drain()
        if cls.win.editor is None:
            raise AssertionError('open_editor() did not create the editor')
        cls.ed = cls.win.editor
        cls.canvas = cls.ed.canvas

    @classmethod
    def tearDownClass(cls):
        cls.win.destroy()
        drain()

    def setUp(self):
        settings.set('markup_tools', json.loads(json.dumps(settings.DEFAULTS['markup_tools'])))
        self.ed.reload_tool_cfg()
        self.ed.set_tab('markup')
        self.ed.state.strokes = []
        self.ed.undo = [self.ed.state.snapshot()]            # a fresh history for every test
        self.ed.redo = []
        self.ed._pick_tool('pen')
        self.canvas.fit()
        drain(0.1)

    def at(self, u, v):
        ox, oy = self.canvas.origin()
        s = self.canvas.scale()
        return ox + u * self.canvas.pw * s, oy + v * self.canvas.ph * s

    def draw(self, pts, state=0, steps=1):
        """Real press / motion / release through the canvas handlers, `pts` are normalised."""
        xy = [self.at(u, v) for u, v in pts]
        self.canvas._press(self.canvas, ev(*xy[0], state))
        for x, y in xy[1:]:
            self.canvas._motion(self.canvas, ev(x, y, state))
        self.canvas._release(self.canvas, ev(*xy[-1], state))
        drain(0.05)
        return self.ed.state.strokes[-1]

    # ── the bar ──
    def test_bar_has_two_pens_the_highlighter_the_eraser_and_clear_all(self):
        self.assertEqual(list(self.ed.tool_btns), ['pen', 'pen2', 'highlighter', 'eraser'])
        self.assertEqual(self.ed.tool_btns['eraser'].get_tooltip_text(), 'Remove markup')
        self.assertEqual(self.ed.clear_btn.get_tooltip_text(), 'Clear all markup')

    def test_the_tooltips_describe_each_tool(self):
        self.assertEqual(self.ed.tool_btns['pen'].get_tooltip_text(),
                         'Pen: Blue, Thickness: 3, Freehand line without arrow\nSelect again to change the ink properties.')
        self.assertEqual(self.ed.tool_btns['pen2'].get_tooltip_text(),
                         'Pen: Black, Thickness: 3, Freehand line without arrow')
        self.assertEqual(self.ed.tool_btns['highlighter'].get_tooltip_text(),
                         'Highlighter: Dark yellow, Thickness: 3, Freehand line')
        self.ed._pick_tool('pen2')
        self.assertIn('Select again', self.ed.tool_btns['pen2'].get_tooltip_text())
        self.assertNotIn('Select again', self.ed.tool_btns['pen'].get_tooltip_text())

    def test_the_icon_shows_the_colour_the_selection_and_the_arrow(self):
        glyph = self.ed.tool_btns['pen'].glyph
        self.assertEqual(glyph.color, BLUE)
        self.assertTrue(glyph.selected)
        self.assertEqual(glyph.arrows, 0)
        self.assertFalse(self.ed.tool_btns['pen2'].glyph.selected)
        self.ed.set_tool_color('pen', '#e3182d')
        self.ed.set_tool_mode('pen', 4)
        self.assertEqual(glyph.color, '#e3182d')
        self.assertEqual(glyph.arrows, 1)
        self.ed._pick_tool('highlighter')
        self.assertFalse(glyph.selected)
        self.assertTrue(self.ed.tool_btns['highlighter'].glyph.selected)

    def test_the_pointer_over_the_picture_is_the_normal_arrow(self):
        self.canvas._motion(self.canvas, ev(*self.at(0.5, 0.5)))
        self.assertIsNone(self.canvas.get_window().get_cursor())

    # ── drawing ──
    def test_the_width_is_fixed_on_the_screen_so_it_changes_with_the_zoom(self):
        self.ed.set_tool_size('pen', 3)                                # 4 screen pixels
        self.canvas.set_percent(1.0)
        drain(0.05)
        at_100 = self.draw([(0.45, 0.50), (0.55, 0.50)])['w']
        self.canvas.set_percent(0.5)
        drain(0.05)
        at_50 = self.draw([(0.45, 0.50), (0.55, 0.50)])['w']
        self.assertAlmostEqual(at_100, 4.0, places=2)
        self.assertAlmostEqual(at_50, 8.0, places=2)

    def test_every_level_stores_its_measured_width(self):
        self.canvas.set_percent(1.0)
        for level, want in enumerate(markup.WIDTHS['pen'], start=1):
            self.ed.set_tool_size('pen', level)
            self.assertAlmostEqual(self.draw([(0.4, 0.5), (0.6, 0.5)])['w'], want, places=2)
        self.ed._pick_tool('highlighter')
        for level, want in enumerate(markup.WIDTHS['highlighter'], start=1):
            self.ed.set_tool_size('highlighter', level)
            self.assertAlmostEqual(self.draw([(0.4, 0.5), (0.6, 0.5)])['w'], want, places=2)

    def test_the_stroke_carries_the_kind_colour_and_mode_of_its_tool(self):
        a = self.draw([(0.2, 0.2), (0.4, 0.3), (0.6, 0.2)])
        self.assertEqual((a['kind'], a['color'], a['arrows'], a['straight']), ('pen', BLUE, 0, False))
        self.ed._pick_tool('pen2')
        b = self.draw([(0.2, 0.4), (0.4, 0.5), (0.6, 0.4)])
        self.assertEqual((b['kind'], b['color']), ('pen', '#1f1f1f'))
        self.ed._pick_tool('highlighter')
        c = self.draw([(0.2, 0.6), (0.4, 0.7), (0.6, 0.6)])
        self.assertEqual((c['kind'], c['color']), ('highlighter', YELLOW))

    def test_a_straight_mode_keeps_only_the_two_ends(self):
        self.ed.set_tool_mode('pen', 3)
        s = self.draw([(0.2, 0.2), (0.3, 0.25), (0.4, 0.5), (0.7, 0.4)])
        self.assertTrue(s['straight'])
        self.assertEqual(s['arrows'], 0)
        self.assertEqual(len(s['pts']), 2)
        self.assertAlmostEqual(s['pts'][0][0], 0.2, places=3)
        self.assertAlmostEqual(s['pts'][1][0], 0.7, places=3)
        self.assertAlmostEqual(s['pts'][1][1], 0.4, places=3)

    def test_holding_shift_draws_a_straight_line_in_a_freehand_mode(self):
        s = self.draw([(0.2, 0.2), (0.3, 0.45), (0.7, 0.3)], state=Gdk.ModifierType.SHIFT_MASK)
        self.assertTrue(s['straight'])
        self.assertEqual(len(s['pts']), 2)
        free = self.draw([(0.2, 0.2), (0.3, 0.45), (0.7, 0.3)])
        self.assertFalse(free['straight'])
        self.assertGreater(len(free['pts']), 2)

    def test_the_arrow_modes(self):
        for mode, (straight, arrows) in enumerate(markup.modes_for('pen')):
            self.ed.set_tool_mode('pen', mode)
            s = self.draw([(0.2, 0.2), (0.4, 0.3), (0.7, 0.25)])
            self.assertEqual((s['straight'], s['arrows']), (straight, arrows), mode)

    def test_the_highlighter_straight_mode_has_no_arrows(self):
        self.ed._pick_tool('highlighter')
        self.ed.set_tool_mode('highlighter', 1)
        s = self.draw([(0.2, 0.2), (0.4, 0.3), (0.7, 0.25)])
        self.assertEqual((s['straight'], s['arrows']), (True, 0))

    def test_a_tap_leaves_a_dot_and_gets_undone(self):
        n = len(self.ed.state.strokes)
        x, y = self.at(0.5, 0.5)
        self.canvas._press(self.canvas, ev(x, y))
        self.canvas._release(self.canvas, ev(x, y))
        drain(0.05)
        self.assertEqual(len(self.ed.state.strokes), n + 1)
        self.ed.do_undo()
        self.assertEqual(len(self.ed.state.strokes), n)
        self.ed.do_redo()
        self.assertEqual(len(self.ed.state.strokes), n + 1)

    def test_the_eraser_removes_the_whole_stroke_it_touches(self):
        self.draw([(0.2, 0.2), (0.8, 0.2)])
        self.draw([(0.2, 0.7), (0.8, 0.7)])
        self.ed._pick_tool('eraser')
        x, y = self.at(0.5, 0.2)
        self.canvas._press(self.canvas, ev(x, y))
        self.canvas._release(self.canvas, ev(x, y))
        self.assertEqual(len(self.ed.state.strokes), 1)
        self.assertAlmostEqual(self.ed.state.strokes[0]['pts'][0][1], 0.7, places=3)

    def test_clear_all_removes_every_stroke(self):
        self.draw([(0.2, 0.2), (0.8, 0.2)])
        self.draw([(0.2, 0.7), (0.8, 0.7)])
        self.ed.clear_btn.clicked()
        self.assertEqual(self.ed.state.strokes, [])

    def test_the_pan_cursor_does_not_stay_on_grabbing_after_a_drag(self):
        calls = []
        original = self.canvas._set_cursor
        self.canvas._set_cursor = lambda name: (calls.append(name), original(name))[1]
        try:
            for tab in ('adjust', 'filters'):
                self.ed.set_tab(tab)
                calls.clear()
                x, y = self.at(0.5, 0.5)
                self.canvas._press(self.canvas, ev(x, y))
                self.assertEqual(calls[-1], 'grabbing')
                self.canvas._release(self.canvas, ev(x, y))
                self.assertIsNone(calls[-1], tab)
        finally:
            self.canvas._set_cursor = original
            self.ed.set_tab('markup')

    def test_nothing_is_drawn_before_the_picture_is_ready(self):
        pb = self.canvas.pb
        self.canvas.pb = None
        try:
            x, y = self.at(0.5, 0.5)
            self.canvas._press(self.canvas, ev(x, y))
            self.assertIsNone(self.canvas.cur)
        finally:
            self.canvas.pb = pb

    def test_the_eraser_reaches_the_arms_of_an_arrow(self):
        self.canvas.set_percent(1.0)
        self.ed.set_tool_size('pen', 6)
        self.ed.set_tool_mode('pen', 4)
        s = self.draw([(0.2, 0.5), (0.7, 0.5)])
        self.assertEqual(s['arrows'], 1)
        tip = self.at(0.7, 0.5)
        arm_len = markup.arrow_length(s['w']) * math.cos(math.pi / 4)
        self.ed._pick_tool('eraser')
        x, y = tip[0] - arm_len * 0.9, tip[1] - arm_len * 0.9      # near the end of the upper arm, far from the line
        self.canvas._press(self.canvas, ev(x, y))
        self.canvas._release(self.canvas, ev(x, y))
        self.assertEqual(self.ed.state.strokes, [])

    def test_the_eraser_reaches_the_edge_of_a_wide_highlighter(self):
        self.canvas.set_percent(1.0)
        self.ed._pick_tool('highlighter')
        self.ed.set_tool_size('highlighter', 6)              # 32 px wide
        self.draw([(0.2, 0.5), (0.7, 0.5)])
        self.ed._pick_tool('eraser')
        x, y = self.at(0.45, 0.5)
        y += 15                                              # inside the 16 px half width, outside the old 12 px reach
        self.canvas._press(self.canvas, ev(x, y))
        self.canvas._release(self.canvas, ev(x, y))
        self.assertEqual(self.ed.state.strokes, [])

    def test_the_flyout_is_destroyed_when_it_closes(self):
        parts = self.open_flyout('pen')
        pop = parts['popover']
        pop.popdown()
        drain(0.4)
        self.assertIsNone(pop.get_parent() if hasattr(pop, 'get_parent') else None)
        self.assertIsNone(pop.get_relative_to())

    # ── choices are remembered ──
    def test_the_choices_are_saved_per_tool_and_read_by_the_next_editor(self):
        self.ed.set_tool_color('pen', '#e3182d')
        self.ed.set_tool_size('pen', 6)
        self.ed.set_tool_mode('pen', 5)
        self.ed.set_tool_color('pen2', '#00b44b')
        stored = json.loads(Path(settings.PATH).read_text(encoding='utf-8'))['markup_tools']
        self.assertEqual(stored['pen'], {'color': '#e3182d', 'size': 6, 'mode': 5})
        self.assertEqual(stored['pen2']['color'], '#00b44b')
        self.assertEqual(stored['highlighter']['color'], YELLOW)
        self.ed.reload_tool_cfg()
        self.assertEqual(self.ed.tool_cfg['pen'], {'color': '#e3182d', 'size': 6, 'mode': 5})

    # ── the flyout ──
    def open_flyout(self, tool):
        self.ed._pick_tool(tool)
        self.ed._pick_tool(tool)           # the second click on the selected tool opens the flyout
        drain(0.2)
        return self.ed.flyout_parts

    def tearDown(self):
        parts = getattr(self.ed, 'flyout_parts', None)
        if parts and parts['popover'].get_visible():
            parts['popover'].popdown()
            drain(0.1)

    def test_flyout_of_a_pen_has_the_slider_sixteen_colours_and_six_modes(self):
        parts = self.open_flyout('pen')
        scale = parts['scale']
        adj = scale.get_adjustment()
        self.assertEqual((adj.get_lower(), adj.get_upper(), adj.get_step_increment()), (1, 6, 1))
        self.assertEqual(int(scale.get_value()), 3)
        self.assertEqual(parts['value_label'].get_text(), '3')
        self.assertEqual(len(parts['swatches']), 16)
        self.assertEqual([b.get_tooltip_text() for b in parts['swatches']], [n for _c, n in markup.PALETTE])
        self.assertEqual(len(parts['modes']), 6)

    def test_flyout_of_the_highlighter_has_only_two_modes(self):
        parts = self.open_flyout('highlighter')
        self.assertEqual(len(parts['modes']), 2)
        self.assertEqual(len(parts['swatches']), 16)

    def test_choosing_a_colour_keeps_the_flyout_open_and_saves_it(self):
        parts = self.open_flyout('pen')
        parts['swatches'][3].clicked()
        drain(0.05)
        self.assertTrue(parts['popover'].get_visible())
        self.assertEqual(self.ed.tool_cfg['pen']['color'], '#e3182d')
        self.assertEqual(json.loads(Path(settings.PATH).read_text(encoding='utf-8'))['markup_tools']['pen']['color'], '#e3182d')
        self.assertEqual(self.ed.tool_btns['pen'].glyph.color, '#e3182d')

    def test_the_slider_changes_the_level_and_the_number(self):
        parts = self.open_flyout('pen')
        parts['scale'].set_value(6)
        drain(0.05)
        self.assertEqual(self.ed.tool_cfg['pen']['size'], 6)
        self.assertEqual(parts['value_label'].get_text(), '6')
        self.assertIn('Thickness: 6', self.ed.tool_btns['pen'].get_tooltip_text())

    def test_the_slider_only_stops_on_whole_levels(self):
        parts = self.open_flyout('pen')
        parts['scale'].set_value(3.6)
        drain(0.05)
        self.assertEqual(self.ed.tool_cfg['pen']['size'], 4)
        self.assertEqual(parts['scale'].get_value(), 4)

    def test_choosing_a_mode(self):
        parts = self.open_flyout('pen')
        parts['modes'][4].clicked()
        drain(0.05)
        self.assertEqual(self.ed.tool_cfg['pen']['mode'], 4)
        self.assertEqual(self.ed.tool_btns['pen'].glyph.arrows, 1)
        self.assertTrue(parts['popover'].get_visible())
        self.assertTrue(parts['modes'][4].get_style_context().has_class('sel-on'))
        self.assertFalse(parts['modes'][0].get_style_context().has_class('sel-on'))

    def test_the_straight_line_mode_explains_the_shift_key(self):
        parts = self.open_flyout('pen')
        self.assertIn('Shift', parts['modes'][3].get_tooltip_text())
        self.assertNotIn('Shift', parts['modes'][0].get_tooltip_text())

    def test_the_selected_colour_has_the_ring(self):
        parts = self.open_flyout('pen')
        selected = [i for i, b in enumerate(parts['swatches']) if b.get_style_context().has_class('sw-on')]
        self.assertEqual(selected, [9])
        parts['swatches'][0].clicked()
        drain(0.05)
        selected = [i for i, b in enumerate(parts['swatches']) if b.get_style_context().has_class('sw-on')]
        self.assertEqual(selected, [0])

    def test_the_preview_is_a_wedge_that_grows_with_the_level(self):
        parts = self.open_flyout('pen')
        sizes = []
        for level in (1, 3, 6):
            parts['scale'].set_value(level)
            drain(0.05)
            sizes.append(parts['preview'].tip_width())
        self.assertEqual(sizes, sorted(sizes))
        self.assertEqual(sizes[0], markup.PREVIEW_TIP['pen'][0])
        self.assertEqual(sizes[2], markup.PREVIEW_TIP['pen'][5])


if __name__ == '__main__':
    unittest.main(verbosity=2)

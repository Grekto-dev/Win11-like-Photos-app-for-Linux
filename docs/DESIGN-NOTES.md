# Design notes

Observations used to re-create the look and behaviour of the Windows 11 Photos app (package
`Microsoft.Windows.Photos` 2026.11090.22001.0, Windows 11 24H2, 1440x900). They were taken by
inspecting the running app (screenshots, UI Automation tree, pixel sampling). No Microsoft code,
icons, fonts or other assets were copied; everything in this repository is original.

## Palette (dark theme, sampled)
| Role | Value |
|---|---|
| Title bar / sidebar / viewer background | `#202020` |
| Gallery content panel, bottom bar, info panel | `#272727` |
| Cards, menus | `#2b2b2b` |
| Search box, subtle buttons | `#2d2d2d` |
| Selected sidebar item | `#292929` (+ 3 px accent bar `#4cc2ff`) |
| Accent | `#4cc2ff` (text on accent: black) |
| Link | `#99ebff`; destructive text `#ff99a4` |

## Viewer
- Top bar 48 px: Edit (labelled), Rotate, Delete, Print, Share, More; file name centred; Open with ▾ on the right
  (narrow windows fold Print/Share/Open with into the More menu).
- Bottom bar 32 px: filmstrip toggle, slideshow, type/dimensions/size; centre: Information; right: fit/actual toggle,
  editable zoom combo, zoom out/slider/in, full screen.
- Zoom limits 1–800 %. Step buttons: 5 % below 50 %, 10 % up to 200 %, 25 % up to 600 %, then 50 %.
- Previous/Next arrows (≈20×48 px) appear only when the pointer is near the window edges.
- Information panel (Alt+Enter): 336 px card on the right, quick actions grid, then file name, date/time, size info,
  folder location.
- Filmstrip (F): thumbnails ≈ 48 px under the canvas, selected one outlined.

### Window buttons
Minimize / maximize (restore) / close are drawn by the app (`ui.WindowButtons`), 46 x 48 px, Windows 11 glyphs (10 px, 1 px lines;
two squares when maximized), grey hover, red `#c42b1c` with a white glyph for close. The stock GTK title buttons are not used: a
desktop GTK theme may hide them (a Windows 11 theme sets their image to `opacity: 0` and paints the glyphs as a background image),
and the icon theme may not match. Buttons touch the window edge (header padding is 0 on that side); in right-to-left languages
they move to the left with close at the edge.

## Gallery
- Left navigation (320 px, collapsible, draggable): Gallery, Favorites, This computer tree.
- Header: title + count, then Select, Slideshow, Sort, Filter, Layout types/sizes, More.
- Justified rows ("Cascade") with 14 px gaps, or square tiles; date-range group headers.
- Hover: white 2 px outline + checkbox; selection: accent outline + checked box; header becomes a card with the count.

## Editor
- Tabs: Crop, Adjust, Filters, Markup (the AI-based Erase and Background tabs are intentionally not re-created).
- Crop: handles, aspect presets, ±45° rotation ruler, rotate/flip. Adjust: Light (brightness, exposure, contrast,
  highlights, shadows, vignette) and Color (saturation, warmth, tint, sharpness). Filters: 14 presets + auto enhance.
  Markup: two pens, highlighter, eraser (removes the whole stroke), clear all (details below).
- Save options: save as copy, save, copy to clipboard.

### Markup tools (measured on the original)
Everything below was measured on the Windows Photos app: strokes drawn with real mouse input, then read back from screenshots
and from the clipboard image.

- **Width is fixed on the screen**, not in the picture. Pen levels 1-6 are 1, 2, 4, 6, 8, 12 px; highlighter levels are
  8, 12, 16, 24, 28, 32 px. A level-6 pen is 9.25 px wide in the saved picture at 128 % zoom and 20.0 px at 61 %. The width
  is converted when the stroke is created and stored as `w` (image pixels).
- Default level 3 for all tools. The slider has six stops and shows the level number.
- **Pens**: opaque, round ends. The first is blue (`#0078d7`), the second black (`#1f1f1f`, not pure black); they behave the same.
- **Highlighter**: the colour at 50 % opacity (plain alpha, not multiply), flat ends, no arrows. One stroke crossing itself does
  not get darker; two strokes add up.
- **Line modes** (pens): freehand / straight x no arrow / arrow at the end / arrows at both ends. Highlighter: freehand, straight.
  Shift while pressing makes a straight line in any mode.
- **Arrow head**: two arms at 45 degrees, 3.8 x the stroke width long, same width as the line, round joins.
- **Palette** (two rows of eight): `#fed430 #fbae17 #f36323 #e3182d #5b318d #914bb8 #cf1278 #c10051` /
  `#3eccfd #0078d7 #0051ba #7ec400 #00b44b #ebebeb #b6b6b6 #1f1f1f`; each swatch has its name as a tooltip, the selected one a
  white ring, a grey halo under the pointer.
- **Flyout**: wedge preview (thin on the left, as thick as the level on the right: pen 2, 4, 7, 10, 12, 14 px; round end for pens,
  flat for the highlighter), slider + number, palette, a divider, then the mode icons (the selected one on a tile). Choosing a
  colour or a mode keeps it open; Esc closes it.
- **Tool icon**: underline in the ink colour, a blue chevron on the selected tool, a small arrow when the mode has arrow heads.
  Tooltip: `Pen: Blue, Thickness: 3, Freehand line without arrow` (+ "Select again to change the ink properties." on the selected tool).
- Each tool remembers colour, level and mode between sessions. The eraser has no options; the pointer stays the normal arrow.
- Strokes are not accepted on the strip just above the floating bar (an invisible overlay in the original); not re-created.

## Settings
Theme, language (added in this project), tile attributes (duplicate badge), delete confirmation, mouse wheel
behaviour, zoom preference, slideshow duration, gallery folders, about.

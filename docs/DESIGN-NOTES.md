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

## Gallery
- Left navigation (320 px, collapsible, draggable): Gallery, Favorites, This computer tree.
- Header: title + count, then Select, Slideshow, Sort, Filter, Layout types/sizes, More.
- Justified rows ("Cascade") with 14 px gaps, or square tiles; date-range group headers.
- Hover: white 2 px outline + checkbox; selection: accent outline + checked box; header becomes a card with the count.

## Editor
- Tabs: Crop, Adjust, Filters, Markup (the AI-based Erase and Background tabs are intentionally not re-created).
- Crop: handles, aspect presets, ±45° rotation ruler, rotate/flip. Adjust: Light (brightness, exposure, contrast,
  highlights, shadows, vignette) and Color (saturation, warmth, tint, sharpness). Filters: 14 presets + auto enhance.
  Markup: pen, pencil, highlighter (multiply blending), eraser (removes the whole stroke), clear all.
- Save options: save as copy, save, copy to clipboard.

## Settings
Theme, language (added in this project), tile attributes (duplicate badge), delete confirmation, mouse wheel
behaviour, zoom preference, slideshow duration, gallery folders, about.

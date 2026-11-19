# Photos 0.1.5

Feature release of **Win11-like Photos app for Linux**: the markup tools of the editor now have the controls of the Windows Photos app.

## New

- **Tool options.** Click a markup tool again to open its panel: a preview, a six-level size slider, the 16-colour palette (each colour has its name as a tooltip) and the line modes. Colour, size and mode are remembered per tool.
- **Line modes.** Freehand or straight, each without an arrow, with an arrow at the end or with arrows at both ends. The highlighter has freehand and straight. Hold **Shift** while dragging to draw a straight line in any mode.
- **Two pens and a highlighter.** Blue and black pens plus the highlighter. The tool icons show the ink colour, the selected tool, and when the mode has arrows. Tooltips describe each tool, for example `Pen: Blue, Thickness: 3, Freehand line without arrow`.
- All new texts are translated into the seven interface languages.

## Fidelity

Measured on the Windows Photos app with real mouse input and the image it saves:

- Stroke width is fixed on the screen, as in the original (pens 1, 2, 4, 6, 8, 12 px; highlighter 8, 12, 16, 24, 28, 32 px). A stroke drawn while zoomed out is therefore thicker in the saved picture.
- The highlighter is the colour at 50 % opacity with flat ends; one stroke crossing itself does not get darker.
- Arrow heads are two arms at 45 degrees, 3.8 times the stroke width long.

## Fixes

- The eraser now reaches arrow heads and the edges of wide highlighter strokes.
- A single click with an arrow mode leaves a dot instead of a stray arrow; arrows on small loops point along the line.
- The "grabbing" pointer no longer stays stuck in the Adjust and Filters tabs.
- Option panels are released when they close.

## Notes

- The separate pencil tool is gone (the original has none); the second pen replaces it.
- The old pen and highlighter colour settings are not migrated: the tools start with blue, black and yellow at size 3.

## Install or update

```bash
sudo apt install ./photos_0.1.5_all.deb
```

Verify the download with `sha256sum -c photos_0.1.5_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.

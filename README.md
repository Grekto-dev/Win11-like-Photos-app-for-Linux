# Fotos for Linux

An independent re-creation of the **Photos** app from Windows 11, written in Python + GTK 3 for Linux
(developed and tested on Linux Mint / Cinnamon). Its look and behaviour were studied on the running Windows app;
**no Microsoft code, icons or other assets are used** — all code and SVG icons are original.

License: [Apache-2.0](LICENSE).

## Features

- **Gallery** — justified ("cascade") or square grid, grouped by date, search, sorting (date taken / created /
  modified / name), media filter, selection mode, favorites, folder tree, resizable/collapsible sidebar, duplicate badge,
  copy / move / rename / delete (to the trash), import from a folder, extra gallery folders, context menu,
  cached thumbnails (photos and videos).
- **Viewer** — smooth zoom (wheel, Ctrl+wheel, buttons, combo, slider), drag to pan, double-click to toggle fit,
  previous/next arrows, filmstrip, Information panel with EXIF, full screen, animated GIF, rotate, print, copy,
  save as, resize (px/%, quality, file type), set as desktop background, "open with…".
- **Slideshow** — full screen, cross-fade, pause, shuffle.
- **Editor** — Crop (handles, aspect presets, ±45° straighten, rotate/flip), Adjust (10 controls), Filters (14 presets,
  auto enhance, intensity), Markup (pen, pencil, highlighter, eraser), undo/redo/reset, save / save as copy / copy.
- **Settings** — theme (light / dark / system), **language**, delete confirmation, mouse-wheel behaviour,
  zoom preference, slideshow duration, gallery folders.
- **Languages** — English (default), Português (Brasil), Español, Français, 简体中文, हिन्दी and العربية
  (right-to-left layout included). The choice is saved and applied after a restart that the app offers to do for you.

Deliberately not re-created: AI features (generative erase, background tools), OneDrive/iCloud integration,
Clipchamp, visual search / OCR and the lock-screen option.

## Install

### From the `.deb` (Debian, Ubuntu, Linux Mint)

Download `fotos_<version>_all.deb` from the [Releases](../../releases) page, then:

```bash
sudo apt install ./fotos_0.1.0_all.deb
```

### From source

Requirements: Python ≥ 3.10, PyGObject, GTK 3, Pillow, librsvg (SVG loader); optional `ffmpegthumbnailer` for video thumbnails.

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil librsvg2-common ffmpegthumbnailer
git clone https://github.com/Grekto-dev/fotos-linux.git
cd fotos-linux
./install.sh              # symlink in ~/.local/bin, desktop entry and icon (./install.sh --uninstall to remove)
```

## Usage

```bash
fotos                        # open the Gallery
fotos photo.jpg              # open a file in the viewer (siblings are browsable)
fotos --slideshow ~/Pictures # start a slideshow
fotos --edit photo.jpg       # open straight in the editor
fotos --settings             # open the settings page
```

Shortcuts: `Ctrl+E` edit · `Ctrl+R` rotate · `Del` delete · `Ctrl+P` print · `Ctrl+S` save as · `Ctrl+C` copy ·
`Ctrl+0` fit · `Ctrl+1` actual size · `Ctrl +/-` zoom · `F` filmstrip · `Alt+Enter` information · `F2` rename ·
`F5` slideshow · `F11` full screen · `Ctrl+B` set as desktop background.

Settings are stored in `~/.config/fotos/settings.json`; thumbnails in `~/.cache/fotos`.

## Translations

Catalogs live in `fotos/locales/<code>.json`. Source strings are the English messages used in the code with `_("…")`,
`N_("…")` and `ngettext("singular", "plural", n)`; a value is a string, or `["singular", "plural"]` for plural messages.
To add a language: create the catalog, add it to `LANGUAGES` (and `MONTHS`/`DATE_PATTERNS`) in `fotos/i18n.py`, and run
`python3 tests/test_i18n.py`, which checks that every message is translated and that `%s`/`%d` placeholders match.

## Development

```bash
python3 tests/test_library.py   # library, actions, zoom steps, editing pipeline
python3 tests/test_i18n.py      # catalogs, plurals, dates, persistence
scripts/build-deb.sh            # builds dist/fotos_<version>_all.deb
```

Notes about the observed original behaviour are in [`docs/DESIGN-NOTES.md`](docs/DESIGN-NOTES.md).

## Releases

Pushing a tag such as `v0.1.0` runs `.github/workflows/release.yml`: it runs the tests, builds the `.deb`
and publishes it (with a SHA-256 file) as a GitHub Release. The tag must match `fotos/__init__.py` (`__version__`).

## Trademarks

"Windows" and "Photos" are trademarks of Microsoft Corporation. This project is not affiliated with or endorsed by Microsoft.

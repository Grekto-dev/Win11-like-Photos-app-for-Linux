# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Own SVG icons (20x20 grid, line style) rendered with the palette colour.

No third-party assets: every drawing below was written for this project."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402


def _gear():
    pts = []
    n = 8
    ro, ri = 8.2, 6.0
    for i in range(n):
        a = 2 * math.pi * i / n
        for da, r in ((-0.20, ri), (-0.13, ro), (0.13, ro), (0.20, ri)):
            pts.append((10 + r * math.cos(a + da), 10 + r * math.sin(a + da)))
    d = "M" + " L".join("%.2f %.2f" % p for p in pts) + "Z"
    return '<path d="%s" stroke-linejoin="round"/><circle cx="10" cy="10" r="2.6"/>' % d


def _sun():
    rays = []
    for i in range(8):
        a = math.pi * i / 4
        rays.append("M%.2f %.2fL%.2f %.2f" % (10 + 5.6 * math.cos(a), 10 + 5.6 * math.sin(a),
                                              10 + 7.6 * math.cos(a), 10 + 7.6 * math.sin(a)))
    return '<circle cx="10" cy="10" r="3.2"/><path d="%s"/>' % "".join(rays)


ICONS = {
    "edit": '<path d="M9.5 3.5H5.5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-4"/>'
            '<path d="M16 3.2a1.6 1.6 0 0 1 2.3 2.3l-7 7-3.1.8.8-3.1z"/>',
    "rotate": '<path d="M16.2 10a6.2 6.2 0 1 1-1.9-4.5"/><path d="M16.4 3.4v3.6h-3.6"/>',
    "rotate-left": '<path d="M3.8 10a6.2 6.2 0 1 0 1.9-4.5"/><path d="M3.6 3.4v3.6h3.6"/>',
    "rotate-right": '<path d="M16.2 10a6.2 6.2 0 1 1-1.9-4.5"/><path d="M16.4 3.4v3.6h-3.6"/>',
    "trash": '<path d="M3.5 5.5h13"/><path d="M7.8 5.5V4a1 1 0 0 1 1-1h2.4a1 1 0 0 1 1 1v1.5"/>'
             '<path d="M5 5.5l.8 9.8a1.6 1.6 0 0 0 1.6 1.5h5.2a1.6 1.6 0 0 0 1.6-1.5l.8-9.8"/>'
             '<path d="M8.4 9v5M11.6 9v5"/>',
    "print": '<path d="M6 7V3.5h8V7"/><path d="M6 14H4.5A1.5 1.5 0 0 1 3 12.5v-4A1.5 1.5 0 0 1 4.5 7h11A1.5 1.5 0 0 1 17 8.5v4a1.5 1.5 0 0 1-1.5 1.5H14"/>'
             '<rect x="6" y="11" width="8" height="5.8" rx="1"/>',
    "share": '<path d="M10 12.2V3.6"/><path d="M6.8 6.6L10 3.4l3.2 3.2"/>'
             '<path d="M6.8 8.6H5.5A1.5 1.5 0 0 0 4 10.1v5.4A1.5 1.5 0 0 0 5.5 17h9a1.5 1.5 0 0 0 1.5-1.5v-5.4a1.5 1.5 0 0 0-1.5-1.5h-1.3"/>',
    "more": '<circle cx="4.5" cy="10" r="1.1" fill="currentColor"/><circle cx="10" cy="10" r="1.1" fill="currentColor"/>'
            '<circle cx="15.5" cy="10" r="1.1" fill="currentColor"/>',
    "info": '<circle cx="10" cy="10" r="7.3"/><path d="M10 9.2v4.6"/><circle cx="10" cy="6.6" r=".5" fill="currentColor"/>',
    "filmstrip": '<rect x="2.8" y="3.5" width="14.4" height="10" rx="2"/><path d="M6 16.5h8"/>',
    "slideshow": '<rect x="2.8" y="3" width="14.4" height="14" rx="2.6"/><path d="M8.4 7.2v5.6l4.6-2.8z" stroke-linejoin="round"/>',
    "play": '<path d="M6.5 4.2v11.6l9-5.8z" fill="currentColor" stroke-linejoin="round"/>',
    "pause": '<rect x="5.2" y="4" width="3.2" height="12" rx=".8" fill="currentColor"/><rect x="11.6" y="4" width="3.2" height="12" rx=".8" fill="currentColor"/>',
    "skip-back": '<path d="M5 4.5v11"/><path d="M15 4.8v10.4L7.4 10z" stroke-linejoin="round"/>',
    "shuffle": '<path d="M3 6h2.5c3 0 4.5 8 7.5 8H17"/><path d="M3 14h2.5c1 0 1.8-.8 2.6-2M10.3 8.4C11 7.2 11.8 6 13 6H17"/><path d="M15 3.8L17.2 6 15 8.2M15 11.8l2.2 2.2L15 16.2"/>',
    "volume": '<path d="M3.5 8v4h3l4 3.3V4.7L6.5 8z" stroke-linejoin="round"/><path d="M13.4 7.4a3.6 3.6 0 0 1 0 5.2M15.5 5.4a6.5 6.5 0 0 1 0 9.2"/>',
    "zoom-in": '<circle cx="8.6" cy="8.6" r="5.4"/><path d="M12.6 12.6L17 17M8.6 6.2v4.8M6.2 8.6h4.8"/>',
    "zoom-out": '<circle cx="8.6" cy="8.6" r="5.4"/><path d="M12.6 12.6L17 17M6.2 8.6h4.8"/>',
    "fit": '<path d="M3.5 7V5.5A1.5 1.5 0 0 1 5 4h2M13 4h2a1.5 1.5 0 0 1 1.5 1.5V7M16.5 13v1.5A1.5 1.5 0 0 1 15 16h-2M7 16H5a1.5 1.5 0 0 1-1.5-1.5V13"/><rect x="7.4" y="7.4" width="5.2" height="5.2" rx=".8"/>',
    "actual": '<path d="M3.5 7V5.5A1.5 1.5 0 0 1 5 4h2M13 4h2a1.5 1.5 0 0 1 1.5 1.5V7M16.5 13v1.5A1.5 1.5 0 0 1 15 16h-2M7 16H5a1.5 1.5 0 0 1-1.5-1.5V13"/><path d="M8.4 8.2L10 7v6" stroke-linejoin="round"/>',
    "fullscreen": '<path d="M12 3.5h4.5V8M16.5 3.5L11.3 8.7M8 16.5H3.5V12M3.5 16.5l5.2-5.2"/>',
    "unfullscreen": '<path d="M16.5 8H12V3.5M12 8l5-5M3.5 12H8v4.5M8 12l-5 5"/>',
    "chev-down": '<path d="M5.5 8l4.5 4.5L14.5 8"/>',
    "chev-up": '<path d="M5.5 12l4.5-4.5 4.5 4.5"/>',
    "chev-left": '<path d="M12 5.5L7.5 10l4.5 4.5"/>',
    "chev-right": '<path d="M8 5.5l4.5 4.5L8 14.5"/>',
    "back": '<path d="M16 10H4.5M9.5 4.8L4.3 10l5.2 5.2"/>',
    "tri-left": '<path d="M12.6 5.4v9.2L6.6 10z" fill="currentColor" stroke-linejoin="round"/>',
    "tri-right": '<path d="M7.4 5.4v9.2l6-4.6z" fill="currentColor" stroke-linejoin="round"/>',
    "close": '<path d="M5 5l10 10M15 5L5 15"/>',
    "check": '<path d="M4.6 10.4l3.5 3.5 7.3-7.6"/>',
    "search": '<circle cx="8.6" cy="8.6" r="5.2"/><path d="M12.5 12.5L17 17"/>',
    "settings": _gear(),
    "photo": '<rect x="3" y="3.5" width="14" height="13" rx="2.4"/><circle cx="7.6" cy="8" r="1.3"/><path d="M3.4 14l4.2-4 3.2 3 2.2-2 3.6 3.4"/>',
    "import": '<rect x="3" y="3.5" width="14" height="13" rx="2.4"/><path d="M10 6.8v6.2M7.4 10.6l2.6 2.6 2.6-2.6"/>',
    "heart": '<path d="M10 16.4S3.4 12.4 3.4 7.8A3.4 3.4 0 0 1 10 6.4a3.4 3.4 0 0 1 6.6 1.4c0 4.6-6.6 8.6-6.6 8.6z" stroke-linejoin="round"/>',
    "heart-fill": '<path d="M10 16.4S3.4 12.4 3.4 7.8A3.4 3.4 0 0 1 10 6.4a3.4 3.4 0 0 1 6.6 1.4c0 4.6-6.6 8.6-6.6 8.6z" fill="currentColor" stroke-linejoin="round"/>',
    "folder": '<path d="M3 6a1.6 1.6 0 0 1 1.6-1.6h3.2l1.6 1.9h5.6A1.6 1.6 0 0 1 16.6 7.9v6.5A1.6 1.6 0 0 1 15 16H4.6A1.6 1.6 0 0 1 3 14.4z" stroke-linejoin="round"/>',
    "folder-plus": '<path d="M9.5 15.6H4.6A1.6 1.6 0 0 1 3 14V6a1.6 1.6 0 0 1 1.6-1.6h3.2l1.6 1.9h5.6A1.6 1.6 0 0 1 16.6 7.9v1.5"/><path d="M14.5 12v5M12 14.5h5"/>',
    "computer": '<rect x="3" y="3.6" width="14" height="9.6" rx="1.8"/><path d="M7 16.6h6M10 13.4v3.2"/>',
    "cloud": '<path d="M6.2 15.6a3.6 3.6 0 0 1-.4-7.2 4.6 4.6 0 0 1 8.8 1 3.1 3.1 0 0 1-.4 6.2z" stroke-linejoin="round"/>',
    "menu": '<path d="M3.5 6h13M3.5 10h13M3.5 14h13"/>',
    "select": '<rect x="3.4" y="3.4" width="13.2" height="13.2" rx="2.4"/><path d="M6.8 10.2l2.2 2.2 4.4-4.6"/>',
    "sort": '<path d="M6.6 16V4M3.6 7l3-3 3 3M13.4 4v12M10.4 13l3 3 3-3"/>',
    "filter": '<path d="M3.5 4.5h13l-5 6.3v4.4l-3 1.6v-6z" stroke-linejoin="round"/>',
    "layout": '<rect x="3.2" y="3.2" width="6" height="6" rx="1.2"/><rect x="10.8" y="3.2" width="6" height="6" rx="1.2"/><rect x="3.2" y="10.8" width="6" height="6" rx="1.2"/><rect x="10.8" y="10.8" width="6" height="6" rx="1.2"/>',
    "crop": '<path d="M6 2.8v10.7a.5.5 0 0 0 .5.5h10.7M2.8 6H13.5a.5.5 0 0 1 .5.5v10.7"/>',
    "brightness": _sun(),
    "wand": '<path d="M3.8 16.2l8.4-8.4"/><path d="M5.5 14.5l1.8 1.8M12.8 4l.8-2 .8 2 2 .8-2 .8-.8 2-.8-2-2-.8zM15.6 11.6l.5-1.2.5 1.2 1.2.5-1.2.5-.5 1.2-.5-1.2-1.2-.5z" stroke-linejoin="round"/>',
    "pen": '<path d="M3.4 16.6l.9-3.4 9-9a1.7 1.7 0 0 1 2.4 0l.1.1a1.7 1.7 0 0 1 0 2.4l-9 9z" stroke-linejoin="round"/><path d="M11.8 5.9l2.4 2.4"/>',
    "pencil": '<path d="M4 16l1-3.2L14 3.8a1.6 1.6 0 0 1 2.2 0 1.6 1.6 0 0 1 0 2.2L7.2 15z" stroke-linejoin="round"/><path d="M12.4 5.4l2.2 2.2M3.6 16.8h6"/>',
    "highlighter": '<path d="M7.6 4.8l5.6 5.6-4 4H6.2L4.6 12.8l-.2-1.6zM12.6 3.8l3.6 3.6-2.6 2.6" stroke-linejoin="round"/><path d="M3 17.2h7"/>',
    "eraser": '<path d="M8.4 16.6H17M4.2 12.6l7-7.4a1.6 1.6 0 0 1 2.3 0l2.7 2.7a1.6 1.6 0 0 1 0 2.2l-5.6 5.9H8.2a1.6 1.6 0 0 1-1.1-.5l-2.9-2.9a1.6 1.6 0 0 1 0-2z" stroke-linejoin="round"/><path d="M7.4 8.8l4.6 4.6"/>',
    "clear-all": '<rect x="4.2" y="4.2" width="11.6" height="11.6" rx="2.2" stroke-dasharray="2 2"/><path d="M8 8l4 4M12 8l-4 4"/>',
    "undo": '<path d="M7.2 4L3.6 7.6l3.6 3.6M4 7.6h7a4.4 4.4 0 0 1 0 8.8H7.4"/>',
    "redo": '<path d="M12.8 4l3.6 3.6-3.6 3.6M16 7.6H9a4.4 4.4 0 0 0 0 8.8h3.6"/>',
    "flip-h": '<path d="M3.4 7h13.2M13.6 4l3 3-3 3M16.6 13H3.4M6.4 10l-3 3 3 3"/>',
    "flip-v": '<path d="M7 3.4v13.2M4 6.4l3-3 3 3M13 16.6V3.4M10 13.6l3 3 3-3"/>',
    "aspect": '<rect x="3" y="4.4" width="14" height="11.2" rx="2.2"/><circle cx="7.4" cy="8.4" r="1.1"/><path d="M3.6 13.8l3.8-3.4 3 2.6 2.4-2 3.2 2.8"/>',
    "link": '<path d="M8.6 11.4a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-.8.8"/><path d="M11.4 8.6a3 3 0 0 0-4.2 0L4.6 11.2a3 3 0 0 0 4.2 4.2l.8-.8"/>',
    "copy": '<rect x="7" y="7" width="9.6" height="9.6" rx="1.8"/><path d="M13 7V5.4A1.8 1.8 0 0 0 11.2 3.6H5.4A1.8 1.8 0 0 0 3.6 5.4v5.8A1.8 1.8 0 0 0 5.4 13H7"/>',
    "save": '<path d="M4.6 3.4h8.2L16.6 7.2v8.2a1.2 1.2 0 0 1-1.2 1.2H4.6a1.2 1.2 0 0 1-1.2-1.2V4.6a1.2 1.2 0 0 1 1.2-1.2z" stroke-linejoin="round"/><path d="M6.6 3.6v4h5.2v-4M6.6 16.4v-5h6.8v5"/>',
    "open-with": '<path d="M8 4.6H5.4A1.8 1.8 0 0 0 3.6 6.4v8.2a1.8 1.8 0 0 0 1.8 1.8h8.2a1.8 1.8 0 0 0 1.8-1.8V12"/><path d="M11.4 3.6h5v5M16.2 3.8L9.4 10.6"/>',
    "folder-open": '<path d="M3 6.4A1.6 1.6 0 0 1 4.6 4.8h3.2l1.6 1.9h5A1.6 1.6 0 0 1 16 8.3V9"/><path d="M3 6.4v8a1.6 1.6 0 0 0 1.6 1.6h9.5a1.6 1.6 0 0 0 1.5-1.1l1.6-4.4A1 1 0 0 0 16.3 9H6.6a1.6 1.6 0 0 0-1.5 1z" stroke-linejoin="round"/>',
    "wallpaper": '<rect x="2.8" y="3.4" width="14.4" height="10.2" rx="1.8"/><path d="M7 16.6h6M3.2 11l3.6-3.2 3 2.6 2.2-1.8 4 3"/>',
    "mail": '<rect x="3" y="4.6" width="14" height="10.8" rx="2"/><path d="M3.6 6l6.4 4.8L16.4 6"/>',
    "cursor": '<path d="M5 3.5l10 5-4.2 1.4L9.4 14.2z" stroke-linejoin="round"/>',
    "sparkle": '<path d="M10 3l1.5 4.5L16 9l-4.5 1.5L10 15l-1.5-4.5L4 9l4.5-1.5z" stroke-linejoin="round"/>',
    "rename": '<path d="M4 16.4h12M6.4 13.2l.8-2.8 6.2-6.2a1.5 1.5 0 0 1 2.1 2.1L9.3 12.5z" stroke-linejoin="round"/>',
    "image-size": '<rect x="3" y="3.4" width="10.6" height="10.6" rx="1.8"/><path d="M11 16.8h3.8a2.2 2.2 0 0 0 2.2-2.2V10.8M13.6 8.4l3.2-3.2M14 5.2h2.8V8"/>',
    "disk": '<ellipse cx="10" cy="5.4" rx="6" ry="2.2"/><path d="M4 5.4v9.2c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2V5.4M4 10c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2"/>',
    "dimensions": '<rect x="3.2" y="3.2" width="13.6" height="13.6" rx="2"/><path d="M3.2 8h4.8V3.2M16.8 12H12v4.8"/>',
    "calendar": '<rect x="3.2" y="4.4" width="13.6" height="12.2" rx="2"/><path d="M3.4 8.4h13.2M7 2.8v3M13 2.8v3"/>',
    "star": '<path d="M10 3l2.1 4.5 4.9.6-3.6 3.4.9 4.9L10 14l-4.3 2.4.9-4.9L3 8.1l4.9-.6z" stroke-linejoin="round"/>',
}

_cache = {}
_registry = set()


# Icons that point in a reading direction are mirrored in right-to-left languages.
MIRROR_IN_RTL = {"chev-left", "chev-right", "tri-left", "tri-right", "back", "skip-back", "undo", "redo"}


def pixbuf(name, size, color):
    from . import i18n
    flip = i18n.is_rtl() and name in MIRROR_IN_RTL
    key = (name, size, color, flip)
    pb = _cache.get(key)
    if pb is not None:
        return pb
    body = ICONS[name].replace("currentColor", color)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 20 20" '
        'fill="none" stroke="%s" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
        % (size, size, color, body)
    )
    loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
    loader.write(svg.encode("utf-8"))
    loader.close()
    pb = loader.get_pixbuf()
    if flip:
        pb = pb.flip(True)
    _cache[key] = pb
    return pb


class Icon(Gtk.Image):
    """Image that follows the palette: role = colour key ('fg', 'muted', 'accent', 'danger', 'onaccent')."""

    def __init__(self, name, size=20, role="fg"):
        super().__init__()
        self.icon_name_ = name
        self.icon_size_ = size
        self.role_ = role
        self.disabled_ = False
        _registry.add(self)
        self.connect("destroy", lambda w: _registry.discard(w))
        self.refresh()

    def set_icon(self, name):
        if name != self.icon_name_:
            self.icon_name_ = name
            self.refresh()

    def set_role(self, role):
        if role != self.role_:
            self.role_ = role
            self.refresh()

    def refresh(self):
        from . import theme
        color = theme.color(self.role_)
        self.set_from_pixbuf(pixbuf(self.icon_name_, self.icon_size_, color))
        self.set_opacity(0.4 if self.disabled_ else 1.0)


def refresh_all():
    for img in list(_registry):
        try:
            img.refresh()
        except Exception:  # noqa: BLE001
            _registry.discard(img)

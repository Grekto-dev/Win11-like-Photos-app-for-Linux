# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Paletas (escuro/claro/sistema) e CSS global, medidos no Fotos do Windows 11."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from . import settings

DARK = {
    "bg": "#202020",            # title bar, sidebar, viewer
    "content": "#272727",       # Gallery content panel / bottom bar
    "card": "#2b2b2b",          # cards, menus
    "field": "#2d2d2d",         # search box, subtle buttons
    "hover": "#343434",
    "pressed": "#2b2b2b",
    "selected": "#292929",      # selected sidebar item
    "border": "#3a3a3a",
    "divider": "#323232",
    "fg": "#ffffff",
    "muted": "#c5c5c5",
    "faint": "#9d9d9d",
    "accent": "#4cc2ff",
    "accent_hover": "#47b1e8",
    "accent_pressed": "#42a1d2",
    "onaccent": "#000000",
    "link": "#99ebff",
    "danger": "#ff99a4",
    "scrim": "rgba(0,0,0,0.5)",
    "tooltip": "#2b2b2b",
    "arrow": "rgba(43,43,43,0.92)",
    "trough": "#8a8a8a",
    "tile": "#2b2b2b",
}

LIGHT = {
    "bg": "#f3f3f3",
    "content": "#fbfbfb",
    "card": "#fdfdfd",
    "field": "#ffffff",
    "hover": "#e9e9e9",
    "pressed": "#e1e1e1",
    "selected": "#ebebeb",
    "border": "#e0e0e0",
    "divider": "#e5e5e5",
    "fg": "#1a1a1a",
    "muted": "#505050",
    "faint": "#6b6b6b",
    "accent": "#005fb8",
    "accent_hover": "#1a6fbf",
    "accent_pressed": "#2f7cc5",
    "onaccent": "#ffffff",
    "link": "#005fb8",
    "danger": "#c42b1c",
    "scrim": "rgba(0,0,0,0.3)",
    "tooltip": "#ffffff",
    "arrow": "rgba(255,255,255,0.92)",
    "trough": "#8a8a8a",
    "tile": "#ebebeb",
}

_current = {"dark": True, "pal": DARK}
_provider = None


def system_is_dark():
    s = Gtk.Settings.get_default()
    if s.get_property("gtk-application-prefer-dark-theme"):
        return True
    name = (s.get_property("gtk-theme-name") or "").lower()
    return "dark" in name


def is_dark():
    return _current["dark"]


def pal():
    return _current["pal"]


def color(role):
    p = _current["pal"]
    if role in p:
        return p[role]
    return role  # already a hex colour


def rgba(role, alpha=None):
    c = Gdk.RGBA()
    c.parse(color(role))
    if alpha is not None:
        c.alpha = alpha
    return c


def set_source(cr, role, alpha=None):
    c = rgba(role, alpha)
    cr.set_source_rgba(c.red, c.green, c.blue, c.alpha)


FONT = '"Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans", "Ubuntu Sans", "Cantarell", sans-serif'


def build_css(p):
    return """
* { -gtk-icon-style: symbolic; }
window.photos, .photos-window, .photos-root { background-color: %(bg)s; color: %(fg)s; font-family: %(font)s; font-size: 13px; }
.photos label { color: %(fg)s; font-family: %(font)s; }
.photos .muted, .photos label.muted { color: %(muted)s; }
.photos .faint, .photos label.faint { color: %(faint)s; }
.photos .link, .photos label.link { color: %(link)s; }
.photos .danger, .photos label.danger { color: %(danger)s; }

headerbar.photos-hb, .photos-hb { background: %(bg)s; background-image: none; border: none; box-shadow: none; min-height: 48px; padding: 0 4px; color: %(fg)s; }
headerbar.photos-hb:backdrop { background: %(bg)s; }
headerbar.photos-hb button.titlebutton { color: %(fg)s; background: transparent; background-image: none; border: none; box-shadow: none; border-radius: 0; min-width: 46px; min-height: 48px; padding: 0; margin: 0; -gtk-icon-shadow: none; }
headerbar.photos-hb button.titlebutton:hover { background-color: %(hover)s; }
headerbar.photos-hb button.titlebutton.close:hover { background-color: #c42b1c; color: #ffffff; }
headerbar.photos-hb .title, headerbar.photos-hb label { color: %(fg)s; font-size: 12px; }
.photos-hb-title { font-size: 12px; }

button.fbtn, menubutton.fbtn > button, .fbtn { background: transparent; background-image: none; border: 1px solid transparent; box-shadow: none; border-radius: 4px; padding: 0 8px; min-height: 32px; min-width: 32px; color: %(fg)s; font-size: 13px; -gtk-icon-shadow: none; text-shadow: none; outline-width: 0; }
button.fbtn:hover, menubutton.fbtn > button:hover { background-color: %(hover)s; }
button.fbtn:active, button.fbtn:checked, menubutton.fbtn > button:checked { background-color: %(pressed)s; }
button.fbtn:disabled, menubutton.fbtn > button:disabled { opacity: 0.4; }
button.fbtn:focus { box-shadow: none; }
button.fbtn.subtle, menubutton.fbtn.subtle > button { background-color: %(field)s; border-color: %(divider)s; }
button.fbtn.subtle:hover, menubutton.fbtn.subtle > button:hover { background-color: %(hover)s; }
button.fbtn.accent, menubutton.fbtn.accent > button { background-color: %(accent)s; color: %(onaccent)s; border-color: transparent; }
button.fbtn.accent label, button.fbtn.accent { color: %(onaccent)s; }
button.fbtn.accent:hover { background-color: %(accent_hover)s; }
button.fbtn.accent:active { background-color: %(accent_pressed)s; }
button.fbtn.accent:disabled { opacity: 0.45; }
button.fbtn.bar { min-height: 32px; padding: 0 6px; }
button.fbtn.tool { min-width: 40px; min-height: 40px; padding: 0 8px; }
button.fbtn.round { border-radius: 16px; }
button.fbtn.flat-icon { min-width: 32px; padding: 0; }
button.fbtn.sel-on { background-color: %(hover)s; }

entry.fsearch { background-color: %(field)s; background-image: none; color: %(fg)s; border: 1px solid %(divider)s; border-bottom-color: %(faint)s; border-radius: 4px; min-height: 32px; padding: 0 10px; box-shadow: none; caret-color: %(fg)s; font-size: 13px; }
entry.fsearch:focus { border-bottom: 2px solid %(accent)s; background-color: %(field)s; }
entry.fsearch selection { background-color: %(accent)s; color: %(onaccent)s; }
entry.fsearch placeholder, entry.fsearch .placeholder { color: %(muted)s; }
entry.fnum { background-color: %(field)s; background-image: none; color: %(fg)s; border: 1px solid %(divider)s; border-bottom-color: %(faint)s; border-radius: 4px; min-height: 30px; padding: 0 8px; box-shadow: none; }
entry.fnum:focus { border-bottom: 2px solid %(accent)s; }
entry.fnum selection, entry.fzoom selection { background-color: %(accent)s; color: %(onaccent)s; }
entry.fzoom { background: transparent; border: none; box-shadow: none; color: %(fg)s; min-height: 24px; padding: 0 2px; font-size: 12px; }

.sidebar { background-color: %(bg)s; }
.side-item { border-radius: 4px; min-height: 36px; padding: 0 12px; margin: 2px 4px; background: transparent; }
.side-item:hover { background-color: %(hover)s; }
.side-item.selected { background-color: %(selected)s; }
.side-item.selected:hover { background-color: %(hover)s; }
.side-bar { background-color: %(accent)s; border-radius: 2px; min-width: 3px; min-height: 16px; margin: 0; }
.side-sep { background-color: %(divider)s; min-height: 1px; margin: 4px 0; }
.side-expander { min-width: 24px; min-height: 24px; padding: 0; border-radius: 4px; }
.tree-item { min-height: 32px; border-radius: 4px; margin: 1px 4px; background: transparent; padding: 0 8px; }
.tree-item:hover { background-color: %(hover)s; }
.tree-item.selected { background-color: %(selected)s; }

.fpaned > separator { background-color: transparent; min-width: 4px; background-image: none; }
.fpaned > separator:hover { background-color: %(accent)s; }
.content-panel { background-color: %(content)s; border-top-left-radius: 8px; border-top: 1px solid %(divider)s; border-left: 1px solid %(divider)s; }
.page-title { font-size: 20px; font-weight: 600; }
.page-sub { font-size: 13px; color: %(muted)s; }
.group-header { font-size: 14px; font-weight: 600; }
.empty-title { font-size: 20px; font-weight: 600; }

.selection-card { background-color: %(card)s; border: 1px solid %(divider)s; border-radius: 8px; padding: 6px 10px; }

.bottombar { background-color: %(content)s; min-height: 32px; border-top: 1px solid transparent; }
.bottombar label { font-size: 12px; }
.bottombar .sep { background-color: %(divider)s; min-width: 1px; min-height: 16px; margin: 0 6px; }
.topbar { background-color: %(bg)s; min-height: 48px; }
.viewer-bg { background-color: %(bg)s; }

.navarrow { background-color: %(arrow)s; border: 1px solid %(divider)s; border-radius: 4px; min-width: 20px; min-height: 48px; padding: 0; }
.navarrow:hover { background-color: %(hover)s; }

.info-panel { background-color: %(content)s; border: 1px solid %(divider)s; border-radius: 8px; }
.info-title { font-size: 18px; font-weight: 600; }
.info-label { font-size: 13px; font-weight: 600; }
.info-value { font-size: 13px; color: %(muted)s; }
.info-sep { background-color: %(divider)s; min-height: 1px; }
button.info-btn { background-color: %(field)s; border: 1px solid %(divider)s; border-radius: 4px; min-height: 32px; box-shadow: none; background-image: none; padding: 0 8px; color: %(fg)s; font-size: 13px; }
button.info-btn:hover { background-color: %(hover)s; }

popover.fmenu, popover.fmenu.background { background-color: %(card)s; background-image: none; border: 1px solid %(border)s; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.28); padding: 4px; margin: 6px; color: %(fg)s; }
popover.fmenu > box, popover.fmenu box { background: transparent; }
popover.fmenu modelbutton, popover.fmenu button.mitem { background: transparent; background-image: none; border: none; box-shadow: none; border-radius: 4px; min-height: 32px; padding: 0 10px; margin: 1px 0; color: %(fg)s; font-size: 13px; text-shadow: none; outline-width: 0; }
popover.fmenu button.mitem:hover { background-color: %(hover)s; }
popover.fmenu button.mitem:active { background-color: %(pressed)s; }
popover.fmenu button.mitem:disabled label, popover.fmenu button.mitem:disabled { opacity: 0.45; }
popover.fmenu button.mitem.danger label { color: %(danger)s; }
popover.fmenu .msep { background-color: %(divider)s; min-height: 1px; margin: 4px 2px; }
popover.fmenu .mhead { color: %(muted)s; font-size: 12px; margin: 6px 10px 2px 10px; }
popover.fmenu .mshort { color: %(faint)s; font-size: 12px; }
popover.fmenu .msub { color: %(faint)s; font-size: 12px; }
popover.fmenu .mmark { background-color: %(accent)s; border-radius: 2px; min-width: 3px; min-height: 16px; }

tooltip, tooltip.background { background-color: %(tooltip)s; background-image: none; border: 1px solid %(border)s; border-radius: 4px; color: %(fg)s; box-shadow: 0 2px 8px rgba(0,0,0,0.3); padding: 0; }
tooltip label { color: %(fg)s; font-size: 12px; padding: 4px 8px; }
tooltip * { background: transparent; }

scale.fscale trough { background-color: %(trough)s; min-height: 4px; border-radius: 2px; border: none; }
scale.fscale highlight { background-color: %(accent)s; border-radius: 2px; border: none; min-height: 4px; }
scale.fscale slider { background-color: %(accent)s; background-image: none; border: 3px solid %(content)s; border-radius: 10px; min-width: 10px; min-height: 10px; box-shadow: 0 0 0 1px %(accent)s; margin: -8px; }
scale.fscale slider:hover { background-color: %(accent_hover)s; }
scale.fscale.on-bg slider { border-color: %(bg)s; }
scale.fscale.on-card slider { border-color: %(content)s; }
scale.fscale.disabled trough { opacity: 0.4; }

switch.fswitch { background-color: transparent; background-image: none; border: 1px solid %(faint)s; border-radius: 10px; min-height: 20px; min-width: 40px; box-shadow: none; color: %(fg)s; }
switch.fswitch slider { background-color: %(faint)s; background-image: none; border: none; border-radius: 7px; min-width: 14px; min-height: 14px; margin: 2px; box-shadow: none; }
switch.fswitch:checked { background-color: %(accent)s; border-color: %(accent)s; }
switch.fswitch:checked slider { background-color: %(onaccent)s; }
switch.fswitch label { color: transparent; font-size: 0; }

check.fcheck, checkbutton.fcheck check { background-color: transparent; background-image: none; border: 1px solid %(faint)s; border-radius: 4px; min-width: 18px; min-height: 18px; box-shadow: none; color: %(onaccent)s; -gtk-icon-source: none; }
checkbutton.fcheck check:checked { background-color: %(accent)s; border-color: %(accent)s; }
radiobutton.fradio radio { background-color: transparent; background-image: none; border: 1px solid %(faint)s; border-radius: 50%%; min-width: 18px; min-height: 18px; box-shadow: none; color: transparent; -gtk-icon-source: none; outline-style: none; }
radiobutton.fradio radio:checked { border-color: %(accent)s; background-color: %(card)s; background-image: radial-gradient(circle, %(accent)s 0, %(accent)s 4px, transparent 5px); }
radiobutton.fradio:focus radio, radiobutton.fradio { outline-style: none; }
radiobutton.fradio label, checkbutton.fcheck label { margin-left: 4px; }

scrollbar { background: transparent; border: none; }
scrollbar slider { background-color: %(faint)s; border-radius: 3px; min-width: 4px; min-height: 40px; border: 2px solid transparent; }
scrollbar.vertical slider { min-width: 4px; }
scrollbar:hover slider { background-color: %(muted)s; }
scrolledwindow.fscroll, scrolledwindow.fscroll viewport { background: transparent; border: none; }
scrolledwindow undershoot.top, scrolledwindow undershoot.bottom, scrolledwindow undershoot.left, scrolledwindow undershoot.right, scrolledwindow overshoot { background: none; background-image: none; border: none; }

.scrim { background-color: %(scrim)s; }
.dialog-card { background-color: %(bg)s; border: 1px solid %(border)s; border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,0.35); }
.dialog-title { font-size: 20px; font-weight: 600; }
.dialog-body { font-size: 14px; }
.dialog-footer { background-color: %(content)s; border-top: 1px solid %(divider)s; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; }

.settings-card { background-color: %(card)s; border: 1px solid %(divider)s; border-radius: 4px; padding: 12px 14px; margin: 1px 0; }
.settings-head { font-size: 14px; font-weight: 600; margin-top: 16px; margin-bottom: 4px; }
.settings-title { font-size: 20px; font-weight: 600; }
.settings-sub { font-size: 12px; color: %(muted)s; }
.combo-btn { background-color: %(field)s; border: 1px solid %(divider)s; border-radius: 4px; min-width: 150px; min-height: 30px; padding: 0 10px; box-shadow: none; background-image: none; color: %(fg)s; }
.combo-btn:hover { background-color: %(hover)s; }

.editor-card { background-color: %(content)s; border: 1px solid %(divider)s; border-radius: 4px; }
.editor-panel { background-color: %(content)s; border: 1px solid %(divider)s; border-radius: 8px; }
.editor-tab { background: transparent; border: none; border-radius: 4px; min-width: 40px; min-height: 36px; padding: 0; box-shadow: none; background-image: none; }
.editor-tab:hover { background-color: %(hover)s; }
.editor-tab-bar { background-color: %(accent)s; border-radius: 2px; min-height: 3px; min-width: 16px; }
.slider-head label { font-size: 13px; }
.slider-val { font-size: 13px; }
.chip { background-color: %(card)s; border: 1px solid %(divider)s; border-radius: 4px; padding: 3px 8px; font-size: 12px; }
.pill { background-color: rgba(32,32,32,0.85); color: #ffffff; border-radius: 4px; padding: 2px 8px; }
.pill label { color: #ffffff; font-size: 12px; }
.section-title { font-size: 14px; font-weight: 600; margin: 12px 0 4px 0; }
.toast { background-color: %(card)s; border: 1px solid %(border)s; border-radius: 8px; padding: 10px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
.slide-top { background-image: linear-gradient(to bottom, rgba(0,0,0,0.6), rgba(0,0,0,0)); }
.slide-bar { background-color: rgba(32,32,32,0.92); border-radius: 4px; padding: 2px 4px; border: 1px solid #3a3a3a; }
.slide-bar button { color: #ffffff; }
.slide-bar label, .slide-top label { color: #ffffff; }
.sel-title { font-size: 14px; font-weight: 600; }
.slide-title { font-size: 16px; font-weight: 600; color: #ffffff; }
.zoombox { background-color: %(field)s; border: 1px solid %(divider)s; border-radius: 4px; padding: 0 2px; }
.zoombox:hover { background-color: %(hover)s; }
button.fbtn.filter-tile { padding: 4px; border-radius: 6px; }
.filter-name { font-size: 12px; }
.filter-name.on { font-weight: 600; }
""" % dict(p, font=FONT)


def apply(force_dark=None):
    """(Re)applies the palette according to the setting."""
    global _provider
    pref = settings.get("theme")
    if force_dark is not None:
        dark = force_dark
    elif pref == "dark":
        dark = True
    elif pref == "light":
        dark = False
    else:
        dark = system_is_dark()
    _current["dark"] = dark
    _current["pal"] = DARK if dark else LIGHT
    screen = Gdk.Screen.get_default()
    gs = Gtk.Settings.get_default()
    gs.set_property("gtk-application-prefer-dark-theme", dark)
    if _provider is not None:
        Gtk.StyleContext.remove_provider_for_screen(screen, _provider)
    _provider = Gtk.CssProvider()
    try:
        _provider.load_from_data(build_css(_current["pal"]).encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("CSS error:", exc)
    Gtk.StyleContext.add_provider_for_screen(screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    from . import icons
    icons.refresh_all()
    for cb in list(_listeners):
        cb()


_listeners = []


def on_change(cb):
    _listeners.append(cb)

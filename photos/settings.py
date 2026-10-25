# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Persistent settings (JSON in ~/.config/photos/settings.json)."""
import json
import os
import threading

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "photos")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "photos")
PATH = os.path.join(CONFIG_DIR, "settings.json")


def _migrate_legacy():
    """The app used to be called "fotos": move its settings/cache over once."""
    for new in (CONFIG_DIR, CACHE_DIR):
        old = os.path.join(os.path.dirname(new), "fotos")
        if not os.path.isdir(new) and os.path.isdir(old):
            try:
                os.rename(old, new)
            except OSError:
                pass


_migrate_legacy()

DEFAULTS = {
    "language": "en",           # en | zh_CN | hi | es | fr | ar | pt_BR
    "theme": "system",          # system | dark | light
    "sort_by": "taken",         # taken | created | modified | name
    "sort_desc": True,
    "media_filter": "all",      # all | photos | videos
    "layout": "cascade",        # cascade | square
    "tile_size": "medium",      # small | medium | large
    "folders": [],              # extra Gallery folders
    "favorites": [],            # favourite paths
    "wheel": "zoom",            # zoom | navigate
    "zoom_pref": "actual",      # actual | fit
    "confirm_delete": True,
    "show_tile_attrs": True,
    "sidebar_open": True,
    "sidebar_width": 320,
    "filmstrip": False,
    "info_open": False,
    "viewer_size": [1100, 720],
    "viewer_maximized": False,
    "main_size": [1280, 800],
    "main_maximized": False,
    "slideshow_interval": 5,
    "slideshow_shuffle": False,
    "pen_color": "#e61b1b",
    "pen_size": 3,
    "highlighter_color": "#ffd02f",
}

_lock = threading.Lock()
_data = None
_listeners = []


def _load():
    global _data
    if _data is None:
        _data = dict(DEFAULTS)
        try:
            with open(PATH, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                _data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
    return _data


def get(key):
    with _lock:
        return _load()[key]


def set(key, value):  # noqa: A001 - API intencional
    with _lock:
        data = _load()
        if data.get(key) == value:
            return
        data[key] = value
        _save_locked()
    for cb in list(_listeners):
        try:
            cb(key, value)
        except Exception:  # noqa: BLE001
            pass


def _save_locked():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, PATH)
    except OSError:
        pass


def connect(cb):
    """cb(key, value) is called on every change."""
    _listeners.append(cb)


def disconnect(cb):
    if cb in _listeners:
        _listeners.remove(cb)

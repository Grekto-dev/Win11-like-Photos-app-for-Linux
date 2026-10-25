# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""Internationalization: JSON catalogs keyed by the English message, with a persistent language setting.

English is the source language and the default. Other catalogs live in ``locales/<code>.json``;
a value is a string, or a ``[singular, plural]`` list for messages used with :func:`ngettext`.
"""
import datetime
import json
import os

from . import settings

# (code, name in its own language), ordered by number of speakers after English.
LANGUAGES = [
    ("en", "English"),
    ("zh_CN", "简体中文"),
    ("hi", "हिन्दी"),
    ("es", "Español"),
    ("fr", "Français"),
    ("ar", "العربية"),
    ("pt_BR", "Português (Brasil)"),
]
RTL_LANGUAGES = {"ar"}
DEFAULT = "en"
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "pt_BR": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर",
           "दिसंबर"],
    "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
           "ديسمبر"],
}
# Date patterns: {d} day, {m} month number, {M} month name, {y} year.
DATE_PATTERNS = {
    "en": "{M} {d}, {y}",
    "pt_BR": "{d} de {M} de {y}",
    "es": "{d} de {M} de {y}",
    "fr": "{d} {M} {y}",
    "zh_CN": "{y}年{m}月{d}日",
    "hi": "{d} {M} {y}",
    "ar": "{d} {M} {y}",
}

_lang = DEFAULT
_catalog = {}


def codes():
    return [c for c, _n in LANGUAGES]


def normalize(code):
    """Maps a code such as 'pt', 'pt_BR.UTF-8' or 'zh-CN' to a supported one (or the default)."""
    if not code:
        return DEFAULT
    code = str(code).split(".")[0].replace("-", "_")
    if code in codes():
        return code
    base = code.split("_")[0]
    for c in codes():
        if c.split("_")[0] == base:
            return c
    return DEFAULT


def _load(code):
    if code == DEFAULT:
        return {}
    try:
        with open(os.path.join(LOCALE_DIR, code + ".json"), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def set_language(code):
    """Activates a language for this process (does not persist it)."""
    global _lang, _catalog
    _lang = normalize(code)
    _catalog = _load(_lang)
    return _lang


def init():
    """Reads the persistent setting; call before the UI toolkit is imported."""
    code = set_language(settings.get("language"))
    # Makes GTK's own strings (stock dialogs, file chooser...) follow the chosen language.
    os.environ["LANGUAGE"] = code + (":en" if code != "en" else "")
    return code


def current():
    return _lang


def is_rtl():
    return _lang in RTL_LANGUAGES


def gettext(msgid):
    v = _catalog.get(msgid)
    if v is None:
        return msgid
    if isinstance(v, list):
        return v[0]
    return v


_ = gettext


def N_(msgid):
    """Marks a message for extraction without translating it now (translate with ``_`` when displaying)."""
    return msgid


def ngettext(singular, plural, n):
    """Returns the translated singular/plural form; ``%d`` in the result is replaced by *n*."""
    v = _catalog.get(singular)
    if isinstance(v, list) and len(v) == 2:
        txt = v[0] if n == 1 else v[1]
    elif _lang == DEFAULT or v is None:
        txt = singular if n == 1 else plural
    else:
        txt = v if isinstance(v, str) else singular
    return txt % n if "%d" in txt else txt


def month_name(m):
    return MONTHS.get(_lang, MONTHS[DEFAULT])[m - 1]


def format_date(d):
    pat = DATE_PATTERNS.get(_lang, DATE_PATTERNS[DEFAULT])
    return pat.format(d=d.day, m=d.month, M=month_name(d.month) if _lang in MONTHS else "", y=d.year)


def format_datetime(ts):
    d = datetime.datetime.fromtimestamp(ts)
    return "%s %02d:%02d" % (format_date(d), d.hour, d.minute)

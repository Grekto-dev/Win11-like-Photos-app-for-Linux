# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
"""i18n tests: catalog coverage, placeholders, plurals, dates and persistence."""
import ast
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from photos import i18n, settings  # noqa: E402

LANGS = [c for c in i18n.codes() if c != "en"]
PH = re.compile(r"%[sd%]|%\.\d[fd]")


def collect_msgids():
    """All literal arguments of _(), N_() and ngettext() across the package: {msgid: plural_or_None}."""
    out = {}
    for f in glob.glob(os.path.join(ROOT, "photos", "*.py")):
        if f.endswith("i18n.py"):
            continue
        for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("_", "N_", "ngettext") and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    plural = None
                    if n.func.id == "ngettext" and isinstance(n.args[1], ast.Constant):
                        plural = n.args[1].value
                    out[a.value] = plural
    return out


def catalog(code):
    return json.load(open(os.path.join(i18n.LOCALE_DIR, code + ".json"), encoding="utf-8"))


def test_every_message_is_translated_in_every_language():
    ids = collect_msgids()
    assert len(ids) > 200
    missing = []
    for code in LANGS:
        cat = catalog(code)
        for m, plural in ids.items():
            if not re.search(r"[A-Za-z]{2}", m) or m in ("Ctrl+A", "Esc", "Delete", "Ctrl+C", "Ctrl+E", "Ctrl+P",
                                                          "Ctrl+Shift+C", "Ctrl+S", "Ctrl+B", "Zoom", "Pixels"):
                continue
            if m not in cat:
                missing.append((code, m))
            elif plural is not None and not (isinstance(cat[m], list) and len(cat[m]) == 2):
                missing.append((code, m + " [plural]"))
    assert not missing, missing[:10]


def test_no_stale_messages_and_placeholders_match():
    ids = collect_msgids()
    for code in LANGS:
        cat = catalog(code)
        stale = [k for k in cat if k not in ids]
        assert not stale, (code, stale[:5])
        for k, v in cat.items():
            forms = v if isinstance(v, list) else [v]
            for form in forms:
                if isinstance(v, list):
                    continue
                assert sorted(PH.findall(form)) == sorted(PH.findall(k)), (code, k, form)


def test_languages_and_default():
    assert i18n.DEFAULT == "en" and settings.DEFAULTS["language"] == "en"
    names = dict(i18n.LANGUAGES)
    assert len(names) == 7 and {"en", "pt_BR"} <= set(names)
    assert i18n.normalize("pt") == "pt_BR" and i18n.normalize("zh-CN") == "zh_CN" and i18n.normalize("xx") == "en"
    assert i18n.normalize("fr_FR.UTF-8") == "fr"


def test_lookup_plurals_dates_and_rtl():
    import datetime
    i18n.set_language("en")
    assert i18n._("Gallery") == "Gallery" and i18n.ngettext("%d photo", "%d photos", 1) == "1 photo"
    assert i18n.ngettext("%d photo", "%d photos", 5) == "5 photos"
    d = datetime.date(2026, 10, 20)
    assert i18n.format_date(d) == "October 20, 2026"
    i18n.set_language("pt_BR")
    assert i18n._("Gallery") == "Galeria" and i18n.format_date(d) == "20 de outubro de 2026"
    assert i18n.ngettext("%d photo", "%d photos", 1) == "1 foto" and i18n.ngettext("%d photo", "%d photos", 3) == "3 fotos"
    assert i18n._("Delete this file?") == "Excluir este arquivo?"
    assert i18n.ngettext("Delete this file?", "Delete %d files?", 4) == "Excluir 4 arquivos?"
    i18n.set_language("zh_CN")
    assert i18n.format_date(d) == "2026年10月20日" and i18n._("Settings") == "设置"
    i18n.set_language("ar")
    assert i18n.is_rtl() and "أكتوبر" in i18n.format_date(d)
    i18n.set_language("hi"); assert not i18n.is_rtl() and i18n._("Settings") == "सेटिंग्स"
    i18n.set_language("es"); assert i18n._("Settings") == "Configuración"
    i18n.set_language("fr"); assert i18n._("Settings") == "Paramètres"
    i18n.set_language("en")
    assert i18n._("not a message") == "not a message"


def test_language_persists():
    cfg = os.environ["XDG_CONFIG_HOME"]
    settings.set("language", "fr")
    data = json.load(open(os.path.join(cfg, "photos", "settings.json")))
    assert data["language"] == "fr"
    # a fresh interpreter reads it back
    import subprocess
    code = ("import sys; sys.path.insert(0, %r); from photos import i18n; print(i18n.init(), i18n._('Gallery'))" % ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, XDG_CONFIG_HOME=cfg)).stdout.strip()
    assert out == "fr Galerie", out
    settings.set("language", "en")


def test_license_text_is_consistent_in_every_language():
    for code in LANGS:
        cat = json.load(open(os.path.join(ROOT, "photos", "locales", code + ".json"), encoding="utf-8"))
        for k, v in cat.items():
            if "License" in k or "Licen" in str(v):
                assert "GPL" not in str(v), (code, v)
        about = [v for k, v in cat.items() if k.startswith("Independent recreation")]
        assert about and all("Apache" in a for a in about), code


def test_app_title_follows_language():
    expected = {"en": "Photos", "pt_BR": "Fotos", "es": "Fotos", "fr": "Photos", "zh_CN": "照片", "hi": "फ़ोटो", "ar": "الصور"}
    for code, title in expected.items():
        i18n.set_language(code)
        assert i18n._("Photos") == title, (code, i18n._("Photos"))
    i18n.set_language("en")


def test_legacy_fotos_dirs_are_migrated():
    base = tempfile.mkdtemp()
    os.makedirs(os.path.join(base, "cfg", "fotos"))
    open(os.path.join(base, "cfg", "fotos", "settings.json"), "w").write('{"language": "fr"}')
    code = ("import sys; sys.path.insert(0, %r); from photos import settings; print(settings.PATH)" % ROOT)
    env = dict(os.environ, XDG_CONFIG_HOME=os.path.join(base, "cfg"), XDG_CACHE_HOME=os.path.join(base, "cache"))
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout.strip()
    assert out.endswith("cfg/photos/settings.json"), out
    assert json.load(open(out))["language"] == "fr"
    assert not os.path.exists(os.path.join(base, "cfg", "fotos"))


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)

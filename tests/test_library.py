# Copyright 2026 Grekto-dev
# SPDX-License-Identifier: Apache-2.0
import os, sys, datetime, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from photos import library, actions, imgops
from photos.canvas import next_zoom


def mk(tmp, name, size=(40, 20), when=None):
    p = os.path.join(tmp, name)
    Image.new("RGB", size, (10, 20, 30)).save(p)
    if when:
        os.utime(p, (when, when))
    return p


def test_scan_sort_filter_group():
    tmp = tempfile.mkdtemp()
    try:
        t0 = datetime.datetime(2026, 10, 1, 12).timestamp()
        for i, n in enumerate(["b.png", "a.png", "C.png"]):
            mk(tmp, n, when=t0 + i * 86400 * 5)
        os.makedirs(os.path.join(tmp, "sub"))
        mk(os.path.join(tmp, "sub"), "z.png", (20, 40))
        open(os.path.join(tmp, "nota.txt"), "w").write("x")
        items = library.list_folder(tmp)
        assert sorted(i.name for i in items) == ["C.png", "a.png", "b.png", "z.png"]
        for it in items:
            library.read_meta(it)
        z = [i for i in items if i.name == "z.png"][0]
        assert (z.w, z.h) == (20, 40)
        by_name = library.sort_items(items, "name", False)
        assert [i.name for i in by_name] == ["a.png", "b.png", "C.png", "z.png"]
        by_date = library.sort_items(items, "modified", True)
        assert by_date[0].name in ("z.png", "C.png")
        assert library.filter_items(items, "videos") == []
        assert len(library.filter_items(items, "photos", "A")) == 1
        assert len(library.filter_items(items, "all", "áÇ")) == 0
        groups = library.make_groups(by_date, "modified", min_per_group=2)
        assert sum(len(g[1]) for g in groups) == 4
        assert all(g[0] for g in groups)
    finally:
        shutil.rmtree(tmp)


def test_duplicates_and_actions():
    tmp = tempfile.mkdtemp()
    try:
        a = mk(tmp, "a.png"); b = mk(tmp, "b.png"); c = mk(tmp, "c.png", (30, 30))
        shutil.copy(a, os.path.join(tmp, "a2.png"))
        items = library.list_folder(tmp)
        for it in items:
            library.read_meta(it)
        library.mark_duplicates(items)
        assert sorted(i.name for i in items if i.dup) == ["a.png", "a2.png", "b.png"]
        d = actions.unique_path(a)
        assert d.endswith("a (2).png")
        new = actions.rename(c, "novo.png")
        assert os.path.exists(new) and not os.path.exists(c)
        try:
            actions.rename(new, "a.png")
            assert False
        except FileExistsError:
            pass
        sub = os.path.join(tmp, "dest"); os.makedirs(sub)
        out = actions.copy_to(a, sub, move=True)
        assert os.path.exists(out) and not os.path.exists(a)
        assert actions.copy_to(out, sub, move=True) == out  # same folder: does nothing
    finally:
        shutil.rmtree(tmp)


def test_zoom_steps():
    z = 0.25
    seq = []
    for _ in range(4):
        z = next_zoom(z, 1); seq.append(round(z * 100))
    assert seq == [30, 35, 40, 45]
    z = 1.0; seq = []
    for _ in range(3):
        z = next_zoom(z, 1); seq.append(round(z * 100))
    assert seq == [110, 120, 130]
    z = 6.0; assert round(next_zoom(z, 1) * 100) == 650
    assert next_zoom(8.0, 1) == 8.0
    assert round(next_zoom(0.01, -1) * 100) == 1


def test_imgops_pipeline():
    im = Image.new("RGB", (200, 100), (120, 130, 140))
    st = imgops.EditState()
    st.adjust["brightness"] = 50
    st.filter = "Dourado"
    st.ops = ["rot", "fh"]
    st.crop = (0.1, 0.1, 0.9, 0.9)
    st.strokes.append({"kind": "pen", "color": "#ff0000", "size": 5, "pts": [(0.2, 0.2), (0.8, 0.8)]})
    out = imgops.render_final(im, st)
    assert out.size == (round(100 * 0.8), round(200 * 0.8))
    assert imgops.EditState().is_default() and not st.is_default()


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)

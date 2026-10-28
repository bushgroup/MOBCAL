"""The user's guide as the Help viewer finds it (``mobcal.docs``): where the pages are, their order,
and where every link on them goes. No Qt; the viewer's own tests are in ``test_app.py``."""

import re
import sys
from pathlib import Path

import pytest

import mobcal
from mobcal import docs
from mobcal.methods import REPOSITORY

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def test_every_page_is_listed_the_window_first():
    pages = docs.pages()
    assert {p.name for p in pages} == {p.name for p in DOCS.glob("*.md")}
    assert pages[0].name == "window.md" and pages[0].title == "The window"
    known = [p.name for p in pages if p.name in docs.ORDER]
    assert known == [n for n in docs.ORDER if n in known]
    assert all(p.title and not p.title.startswith("#") for p in pages)


def test_a_new_page_comes_after_the_known_ones(tmp_path):
    for name, text in (("zeta.md", "# Zeta\n"), ("alpha.md", "No heading\n"),
                       ("window.md", "# The `window`\n"), ("methods.md", "# Methods\n")):
        (tmp_path / name).write_text(text, encoding="utf-8")
    pages = docs.pages(tmp_path)
    assert [p.name for p in pages] == ["window.md", "methods.md", "alpha.md", "zeta.md"]
    assert [p.title for p in pages] == ["The window", "Methods", "alpha", "Zeta"]
    assert docs.pages(tmp_path / "none") == []


def test_the_locator_in_a_source_tree_and_a_frozen_bundle(monkeypatch, tmp_path):
    assert docs.docs_dir() == mobcal.ROOT / "docs"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "mobcal.exe"))
    assert docs.docs_dir() == tmp_path / "_internal" / "docs"
    (tmp_path / "_internal" / "docs").mkdir(parents=True)
    (tmp_path / "_internal" / "docs" / "window.md").write_text("# The window\n",
                                                                encoding="utf-8")
    assert [p.name for p in docs.pages()] == ["window.md"]


def test_the_spec_ships_every_page():
    spec = (ROOT / "packaging" / "mobcal.spec").read_text(encoding="utf-8")
    assert '(os.path.join(ROOT, "docs", "*.md"), "docs")' in spec
    assert re.search(r"^if _pages != _want_pages:\n    raise RuntimeError", spec, re.M)


@pytest.mark.parametrize("heading, anchor", [
    ("How a batch uses the processors, and the estimate",
     "how-a-batch-uses-the-processors-and-the-estimate"),
    ("macOS (Apple silicon)", "macos-apple-silicon"),
    ("mobcal self-check", "mobcal-self-check"),
    ("The 2000 helium set", "the-2000-helium-set"),
    ("Split runs", "split-runs"),
])
def test_a_heading_has_githubs_anchor(heading, anchor):
    assert docs.slug(heading) == anchor


def test_a_repeated_heading_is_numbered_and_code_is_not_a_heading():
    text = "# T\n\n## Split runs\n\n```\n# not a heading\n```\n\n## Split `runs`\n"
    assert docs.anchors(text) == [(1, "T", "t"), (2, "Split runs", "split-runs"),
                                  (2, "Split runs", "split-runs-1")]


def test_every_link_between_pages_and_every_anchor_resolves():
    pages = {p.name: p for p in docs.pages()}
    anchors = {n: {a for *_, a in docs.anchors(p.path.read_text(encoding="utf-8"))}
               for n, p in pages.items()}
    inside = 0
    for name, p in pages.items():
        for href in docs.links(p.path.read_text(encoding="utf-8")):
            t = docs.target(href, name)
            if t.url is not None:
                continue
            inside += 1
            assert t.page in pages, f"{name}: {href} names no page"
            assert not t.anchor or t.anchor in anchors[t.page], f"{name}: {href} has no anchor"
    assert inside > 40


def test_every_link_outside_the_guide_goes_to_the_web_or_the_repository():
    for p in docs.pages():
        for href in docs.links(p.path.read_text(encoding="utf-8")):
            t = docs.target(href, p.name)
            if t.url is None:
                continue
            assert t.url.startswith("https://"), f"{p.name}: {href}"
            if t.url.startswith(f"{REPOSITORY}/blob/"):
                path = t.url.split("/blob/", 1)[1].split("/", 1)[1].split("#")[0]
                assert (ROOT / path).exists(), f"{p.name}: {href} names no file"


def test_a_repository_link_opens_at_the_versions_ref():
    assert docs.ref("2.0.0.dev0") == "main"
    assert docs.ref("2.0.0") == "v2.0.0" and docs.ref("2.0.0rc1") == "v2.0.0rc1"
    t = docs.target("../README.md#running-calculations", "install.md", "2.0.0")
    assert t == docs.Target(url=f"{REPOSITORY}/blob/v2.0.0/README.md#running-calculations")
    assert docs.target("../fortran/README.md", "mobcal-2012.md", "2.0.0.dev0").url == \
        f"{REPOSITORY}/blob/main/fortran/README.md"
    assert docs.target("https://example.org/a#b", "x.md").url == "https://example.org/a#b"
    assert docs.target("settings.md#the-bounds", "x.md") == docs.Target("settings.md",
                                                                         "the-bounds")
    assert docs.target("#the-file", "parameters.md") == docs.Target("parameters.md", "the-file")
    assert docs.target("../docs/methods.md", "x.md") == docs.Target("methods.md")

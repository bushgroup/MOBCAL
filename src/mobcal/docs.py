"""The user's guide: the Markdown pages of ``docs/``, where they are, their order, their links.

Qt-free, so the window's Help viewer (``mobcal.app.help``) and the tests share it. The pages are
``docs/`` in a source checkout and ``docs/`` under the bundle's own directory (``sys._MEIPASS``)
in an installed program, which ``packaging/mobcal.spec`` ships every page into. ``pages`` lists
whatever the directory holds: the known pages in ``ORDER``, the window first, then any other
page by name, so a new page needs no change here.

A link between pages is followed in the viewer; a link to anything else in the repository
(``../README.md``, ``../fortran/README.md``) is opened on GitHub at the installed version's ref
(``ref``), and a web address as it stands (``target``). A heading's anchor is the one GitHub
gives it (``slug``), so a ``page.md#section`` link works in both places.
"""

from __future__ import annotations

import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import mobcal
from mobcal import fortran
from mobcal.methods import REPOSITORY

# The window first; the command line as the same program from a terminal; then what a method
# is made of; then reproducing the two releases.
ORDER = ("window.md", "install.md", "command-line.md", "methods.md", "import.md", "qm.md",
         "parameters.md", "settings.md", "random-numbers.md", "mobcal-2012.md",
         "mobcal-2000.md")


@dataclass(frozen=True)
class Page:
    path: Path
    title: str  # the page's first-level heading

    @property
    def name(self) -> str:
        return self.path.name


def docs_dir() -> Path:
    """``docs/`` in this checkout, or the copy an installed program carries."""
    if fortran.frozen():
        return Path(getattr(sys, "_MEIPASS", fortran.install_dir())) / "docs"
    return mobcal.ROOT / "docs"


def title(text: str, fallback: str) -> str:
    m = re.search(r"^# +(.+?)\s*$", text, re.M)
    return plain(m.group(1)) if m else fallback


def pages(d: Path | None = None) -> list[Page]:
    """Every page in ``d`` (default ``docs_dir()``), the known ones in ``ORDER`` first."""
    d = docs_dir() if d is None else d
    found = sorted(d.glob("*.md")) if d.is_dir() else []
    rank = {name: i for i, name in enumerate(ORDER)}
    found.sort(key=lambda p: (rank.get(p.name, len(ORDER)), p.name))
    return [Page(p, title(p.read_text(encoding="utf-8"), p.stem)) for p in found]


def plain(md: str) -> str:
    """A heading's text as it reads: links to their text, code and emphasis marks dropped."""
    md = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", md)
    return re.sub(r"[`*]", "", md).strip()


def slug(text: str) -> str:
    """GitHub's anchor for a heading of this (rendered) text: lower case, punctuation other than
    ``-`` and ``_`` dropped, each space a hyphen."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def anchors(text: str) -> list[tuple[int, str, str]]:
    """Each heading of a Markdown page as (level, text, anchor), a repeated anchor numbered
    ``-1``, ``-2`` as GitHub numbers it. Headings inside fenced code are not headings."""
    out, seen, fenced = [], {}, False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else re.match(r"^(#{1,6}) +(.+?)\s*#*\s*$", line)
        if m:
            words = plain(m.group(2))
            out.append((len(m.group(1)), words, unique(slug(words), seen)))
    return out


def unique(anchor: str, seen: dict[str, int]) -> str:
    n = seen.get(anchor, 0)
    seen[anchor] = n + 1
    return f"{anchor}-{n}" if n else anchor


def ref(version: str = mobcal.__version__) -> str:
    """The GitHub ref a link outside ``docs/`` opens at: ``v<version>``, the release's tag, or
    ``main`` for a development version, which no tag names."""
    return "main" if ".dev" in version else f"v{version}"


@dataclass(frozen=True)
class Target:
    """Where a link goes: a page of the guide and an anchor in it (``page``, ``anchor``), or an
    address outside it (``url``)."""
    page: str | None = None
    anchor: str = ""
    url: str | None = None


def target(href: str, page: str, version: str = mobcal.__version__) -> Target:
    """Where a link on ``page`` (a file name in ``docs/``) goes. A link to another file in
    ``docs/`` that is not a page, or to anything above it, goes to the repository on GitHub."""
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return Target(url=href)
    if not parts.path:
        return Target(page=page, anchor=parts.fragment)
    path = posixpath.normpath(posixpath.join("docs", parts.path))
    if posixpath.dirname(path) == "docs" and path.endswith(".md"):
        return Target(page=posixpath.basename(path), anchor=parts.fragment)
    return Target(url=github(path, parts.fragment, version))


def github(path: str, anchor: str = "", version: str = mobcal.__version__) -> str:
    """A file of the repository, by its path from the root, on GitHub at the version's ref."""
    return f"{REPOSITORY}/blob/{ref(version)}/{path}" + (f"#{anchor}" if anchor else "")


def links(text: str) -> list[str]:
    """Every inline link's address on a Markdown page, outside fenced and inline code; a
    link's text may run over a line break."""
    prose = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    prose = re.sub(r"`[^`]*`", "", prose)
    return re.findall(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)", prose)

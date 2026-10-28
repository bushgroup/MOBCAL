"""Help ▸ MOBCAL Help: every page of the user's guide (``mobcal.docs``), offline, in the window.

Left, the contents: each page by its title, the window's page first, with its sections under
it; above them a search across every page, whose hits replace the contents while it holds text,
listed under their page and the section they are in. Right, the page, as Qt renders Markdown
(GitHub's dialect: tables and fenced code). A link to another page, or to a section of one, is
followed here; any other link opens in the system's browser, a file of the repository on GitHub
at the installed version (``mobcal.docs.target``). One viewer per window, non-modal; a second
F1 brings it forward on the page it was left at.

Qt's Markdown reader gives headings no anchors, so each heading is given GitHub's
(``mobcal.docs.slug``) after the page is read, and ``page.md#section`` works here as it does on
GitHub. Code is set in the platform's fixed font (Consolas where Windows has it, rather than the
Courier New it names) on a faint band of the text colour; the pages are read again when the
palette changes, since the reader fixes link colours as it reads.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPalette,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mobcal import docs

PAGE, ANCHOR, HIT = Qt.ItemDataRole.UserRole, Qt.ItemDataRole.UserRole + 1, \
    Qt.ItemDataRole.UserRole + 2
MIN_TERM = 2  # characters before a search runs
BEFORE, AFTER = 12, 60  # characters of context shown before and after a hit


def fixed_family() -> str:
    if sys.platform == "win32" and QFontDatabase.hasFamily("Consolas"):
        return "Consolas"
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


def mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(*(round(u + (v - u) * t) for u, v in zip(a.getRgb()[:3], b.getRgb()[:3],
                                                           strict=True)))


class Page:
    """One page read into a document: its anchors put on its headings, its code set, and the
    section each block falls in."""

    def __init__(self, page: docs.Page, font: QFont, palette: QPalette, parent) -> None:
        self.page = page
        self.doc = QTextDocument(parent)
        self.doc.setDefaultFont(font)
        self.doc.setMarkdown(page.path.read_text(encoding="utf-8"),
                             QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        self.sections: list[tuple[int, int, str, str]] = []  # (block, level, text, anchor)
        seen: dict[str, int] = {}
        family = fixed_family()
        band = mix(palette.color(QPalette.ColorRole.Base), palette.color(QPalette.ColorRole.Text),
                   0.07)
        cur = QTextCursor(self.doc)
        cur.beginEditBlock()
        b = self.doc.begin()
        while b.isValid():
            level = b.blockFormat().headingLevel()
            if level:
                anchor = docs.unique(docs.slug(b.text()), seen)
                self.sections.append((b.blockNumber(), level, b.text(), anchor))
                cur.setPosition(b.position())
                cur.setPosition(b.position() + b.length() - 1, QTextCursor.MoveMode.KeepAnchor)
                f = QTextCharFormat()
                f.setAnchor(True)
                f.setAnchorNames([anchor])
                cur.mergeCharFormat(f)
            code = b.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence)
            if code:
                cur.setPosition(b.position())
                bf = QTextBlockFormat()
                bf.setBackground(band)
                if not b.next().blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence):
                    bf.setBottomMargin(font.pointSizeF() * 0.8)  # a heading may follow at once
                cur.mergeBlockFormat(bf)
            it = b.begin()
            while not it.atEnd():
                frag = it.fragment()
                if code or frag.charFormat().fontFixedPitch():
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(),
                                    QTextCursor.MoveMode.KeepAnchor)
                    f = QTextCharFormat()
                    f.setFontFamilies([family])
                    f.setFontFixedPitch(True)
                    cur.mergeCharFormat(f)
                it += 1
            b = b.next()
        cur.endEditBlock()
        self.doc.setModified(False)

    def section_of(self, block: int) -> tuple[str, str]:
        """The heading a block falls under, and its anchor: the nearest above it, or the page's
        title and none."""
        found = (self.page.title, "")
        for n, _, text, anchor in self.sections:
            if n > block:
                break
            found = (text, anchor)
        return found


class HelpWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("MOBCAL Help")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search all pages")
        self.search.setClearButtonEnabled(True)
        self.contents = QTreeWidget()
        self.results = QTreeWidget()
        self.results.setIndentation(12)
        for tree in (self.contents, self.results):
            tree.setHeaderHidden(True)
            tree.itemActivated.connect(self._go)
            tree.itemClicked.connect(self._go)
        self.lists = QStackedWidget()
        self.lists.addWidget(self.contents)
        self.lists.addWidget(self.results)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.search)
        lay.addWidget(self.lists, 1)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self.follow)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 760])
        outer = QVBoxLayout(self)
        outer.addWidget(split)
        self.resize(1080, 760)
        self.typing = QTimer(self)
        self.typing.setSingleShot(True)
        self.typing.setInterval(200)
        self.typing.timeout.connect(self.find)
        self.search.textChanged.connect(lambda _: self.typing.start())
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search)
        self.current: str | None = None
        self.pages: dict[str, Page] = {}
        self.read()
        self.show_first()

    # --- reading the pages ----------------------------------------------------------------

    def read(self) -> None:
        """Read every page into a document and list it, with its sections, in the contents."""
        self.pages = {p.name: Page(p, self.view.font(), self.view.palette(), self)
                      for p in docs.pages()}
        self.contents.clear()
        for name, p in self.pages.items():
            item = QTreeWidgetItem([p.page.title])
            item.setData(0, PAGE, name)
            item.setData(0, ANCHOR, "")
            for _, level, text, anchor in p.sections:
                if level == 2:
                    sub = QTreeWidgetItem([text])
                    sub.setData(0, PAGE, name)
                    sub.setData(0, ANCHOR, anchor)
                    item.addChild(sub)
            self.contents.addTopLevelItem(item)

    def changeEvent(self, event) -> None:  # noqa: N802 -- Qt's name
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.pages:
            old, current = self.pages, self.current
            at = self.view.verticalScrollBar().value()
            self.read()
            self.current = None  # the view still holds the old document until open() replaces it
            if not self.show_first(current):
                at = 0
            self.view.verticalScrollBar().setValue(at)
            for p in old.values():
                p.doc.deleteLater()
            self.find()

    # --- moving about ---------------------------------------------------------------------

    def show_first(self, name: str | None = None) -> bool:
        """Open ``name`` if there is such a page; otherwise the first page, or say there are
        none. True when ``name`` was opened."""
        if name and self.open(name):
            return True
        if self.pages:
            self.open(next(iter(self.pages)))
        else:
            self.view.setDocument(QTextDocument(self))
            self.view.setPlainText(f"The help pages are not in {docs.docs_dir()}.")
        return False

    def open(self, name: str, anchor: str = "") -> bool:
        """Show a page, at a section when given one. False when there is no such page."""
        p = self.pages.get(name)
        if p is None:
            return False
        if name != self.current:
            self.view.setDocument(p.doc)
            self.current = name
            self.setWindowTitle(f"{p.page.title} - MOBCAL Help")
            for i in range(self.contents.topLevelItemCount()):
                item = self.contents.topLevelItem(i)
                item.setExpanded(item.data(0, PAGE) == name)
        if anchor:
            self.view.scrollToAnchor(anchor)
        else:
            self.view.verticalScrollBar().setValue(0)
        self._mark(name, anchor)
        return True

    def _mark(self, name: str, anchor: str) -> None:
        for i in range(self.contents.topLevelItemCount()):
            top = self.contents.topLevelItem(i)
            if top.data(0, PAGE) != name:
                continue
            item = top
            for j in range(top.childCount()):
                if anchor and top.child(j).data(0, ANCHOR) == anchor:
                    item = top.child(j)
            self.contents.blockSignals(True)
            self.contents.setCurrentItem(item)
            self.contents.blockSignals(False)

    def follow(self, url: QUrl) -> None:
        """A link clicked on the current page: to a page or section here, or out to the
        browser."""
        t = docs.target(url.toString(), self.current or "")
        if t.page is None:
            QDesktopServices.openUrl(QUrl(t.url))
        elif not self.open(t.page, t.anchor):  # a page this copy does not carry
            QDesktopServices.openUrl(QUrl(docs.github(f"docs/{t.page}", t.anchor)))

    def _go(self, item: QTreeWidgetItem) -> None:
        hit = item.data(0, HIT)
        if hit is None:
            self.open(item.data(0, PAGE), item.data(0, ANCHOR) or "")
            return
        self.open(item.data(0, PAGE))
        start, length = hit
        cur = self.view.textCursor()
        cur.setPosition(start)
        cur.setPosition(start + length, QTextCursor.MoveMode.KeepAnchor)
        self.view.setTextCursor(cur)
        bar = self.view.verticalScrollBar()  # the hit a third of the way down, not at an edge
        bar.setValue(bar.value() + self.view.cursorRect(cur).top()
                     - self.view.viewport().height() // 3)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # --- searching ------------------------------------------------------------------------

    def find(self) -> None:
        """List every place each page holds the search text, under the page, by section."""
        term = self.search.text().strip()
        if len(term) < MIN_TERM:
            self.lists.setCurrentWidget(self.contents)
            return
        self.results.clear()
        total = 0
        for name, p in self.pages.items():
            hits, cur = [], p.doc.find(term)
            while not cur.isNull():
                hits.append(cur)
                cur = p.doc.find(term, cur)
            if not hits:
                continue
            top = QTreeWidgetItem([f"{p.page.title} ({len(hits)})"])
            top.setData(0, PAGE, name)
            top.setData(0, ANCHOR, "")
            under: dict[str, QTreeWidgetItem] = {}
            for c in hits:
                block = c.block()
                heading, anchor = p.section_of(block.blockNumber())
                if (anchor or heading) not in under:
                    sec = QTreeWidgetItem([heading])
                    sec.setData(0, PAGE, name)
                    sec.setData(0, ANCHOR, anchor)
                    top.addChild(sec)
                    under[anchor or heading] = sec
                text, at = block.text(), c.selectionStart() - block.position()
                lo, hi = max(0, at - BEFORE), min(len(text), at + len(term) + AFTER)
                snippet = (("…" if lo else "") + text[lo:hi].strip()
                           + ("…" if hi < len(text) else ""))
                hit = QTreeWidgetItem([snippet])
                hit.setToolTip(0, snippet)
                hit.setData(0, PAGE, name)
                hit.setData(0, HIT, (c.selectionStart(), c.selectionEnd() - c.selectionStart()))
                under[anchor or heading].addChild(hit)
            self.results.addTopLevelItem(top)
            top.setExpanded(True)
            for sec in under.values():
                sec.setExpanded(True)
            total += len(hits)
        if not total:
            self.results.addTopLevelItem(QTreeWidgetItem([f"No page holds “{term}”."]))
        self.lists.setCurrentWidget(self.results)

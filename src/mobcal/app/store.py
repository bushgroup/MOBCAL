"""What the window remembers between launches: the results folder, the method, the method files
in the Method list (by path and SHA-256), the geometry, and the queue file's place.

``QSettings`` under an explicit organisation and application name, so the key does not move
when the executable is renamed. Everything here is a convenience: a window that has forgotten
it still runs. The queue itself is a file of ``mobcal.batch`` descriptions, not settings, so
that the command line could read it too.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QStandardPaths

from mobcal.app import APPLICATION, ORGANISATION

QUEUE_FILE = "queue.json"


class Store:
    def __init__(self, backing: QSettings | None = None, data_dir: Path | None = None) -> None:
        self._s = backing or QSettings(ORGANISATION, APPLICATION)
        self._data_dir = data_dir

    @property
    def out_dir(self) -> str:
        return str(self._s.value("out_dir", "") or "")

    @out_dir.setter
    def out_dir(self, value: str) -> None:
        self._s.setValue("out_dir", value)

    @property
    def method(self) -> str:
        return str(self._s.value("method", "") or "")

    @method.setter
    def method(self, value: str) -> None:
        self._s.setValue("method", value)

    @property
    def methods(self) -> list[tuple[str, str]]:
        """The method files in the Method list, as (path, SHA-256) when each was added."""
        try:
            doc = json.loads(str(self._s.value("methods", "") or "[]"))
            return [(str(p), str(s)) for p, s in doc]
        except (ValueError, TypeError):
            return []

    @methods.setter
    def methods(self, value: list[tuple[str, str]]) -> None:
        self._s.setValue("methods", json.dumps([list(v) for v in value]))

    @property
    def input_dir(self) -> str:
        return str(self._s.value("input_dir", "") or "")

    @input_dir.setter
    def input_dir(self, value: str) -> None:
        self._s.setValue("input_dir", value)

    @property
    def geometry(self) -> QByteArray | None:
        v = self._s.value("geometry")
        return v if isinstance(v, QByteArray) else None

    @geometry.setter
    def geometry(self, value: QByteArray) -> None:
        self._s.setValue("geometry", value)

    @property
    def queue_path(self) -> Path:
        d = self._data_dir or Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation))
        return d / QUEUE_FILE

    def default_out_dir(self) -> str:
        if self.out_dir:
            return self.out_dir
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        return str(Path(docs) / "MOBCAL results")

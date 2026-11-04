"""``mobcal clean``: a finished split run's scratch removed after the run, for folders on disk.

A split run (``mobcal.run``, ``Job.split``) leaves, besides its inputs, its output and
``record.json``, three kinds of scratch: a folder per worker (``w01`` to ``wW``), a claim file
per block under the claimed dealing, and a copy in the run directory of every block file the
combining run read. A run of this version removes them itself once its combining run succeeds
(``Job.scratch``); this module does the same for runs already on disk, written before it did,
run under ``keep``, or whose own removal left a file Windows held open.

It acts only on a run directory whose ``record.json`` says ``ok`` and names a split. A run in
flight has no record (the driver removes it before starting), and a failed, stopped or serial
run is left as it is. Before removing anything it adds to the record what the worker folders
alone hold (``mobcal.run.harvest_split``) when the record has no ``split`` block yet, and it
appends to ``cleaned`` what it removed; no field already in the record changes. ``plan`` lists
what would go, ``apply`` removes it, and a second pass finds nothing.

No Qt here.

    from mobcal import clean
    for c in clean.plan([Path("results")]):
        print(c)
        clean.apply(c, "zip")
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mobcal.io.block import block_of_claim
from mobcal.run import (
    RECORD_JSON,
    clear_scratch,
    dump_record,
    harvest_split,
    owners_on_disk,
    scratch_files,
)

MODES = ("delete", "zip")


@dataclass(frozen=True)
class Cleanup:
    """One run directory's scratch as it stands."""
    run_dir: Path
    record: dict
    worker_folders: int
    claim_files: int
    block_files: int
    files: int  # every file that would go, the worker folders' contents counted
    bytes: int

    @property
    def total(self) -> int:
        return int(self.record["mobcal_in"]["split"])

    def __str__(self) -> str:
        return (f"{self.run_dir.name}: {self.worker_folders} worker folders, "
                f"{self.claim_files} claim files, {self.block_files} block files "
                f"({self.files} files, {self.bytes:,} bytes)")


def run_dirs(paths: Iterable[Path]) -> list[Path]:
    """The run directories named: each path that holds a ``record.json``, and each folder of
    them, one level down."""
    found: list[Path] = []
    for p in map(Path, paths):
        if (p / RECORD_JSON).is_file():
            found.append(p)
        elif p.is_dir():
            found += sorted(r.parent for r in p.glob(f"*/{RECORD_JSON}"))
    return found


def _read(run_dir: Path) -> dict | None:
    """The record of a finished split run that succeeded, else None."""
    try:
        doc = json.loads((run_dir / RECORD_JSON).read_text(encoding="utf-8"))
        split = doc["mobcal_in"]["split"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if doc.get("status") != "ok" or not split:
        return None
    return doc


def _size(paths: Iterable[Path]) -> tuple[int, int]:
    n = b = 0
    for p in paths:
        for f in (p.rglob("*") if p.is_dir() else [p]):
            if f.is_file():
                n += 1
                try:
                    b += f.stat().st_size
                except OSError:
                    pass
    return n, b


def plan(paths: Iterable[Path]) -> list[Cleanup]:
    """Every run directory under ``paths`` with scratch to remove: an ``ok`` split run holding
    a worker folder, a claim file or a block file. A run with none is left out."""
    out = []
    for d in run_dirs(paths):
        doc = _read(d)
        if doc is None:
            continue
        found = scratch_files(d, int(doc["mobcal_in"]["split"]))
        n = {k: len(v) for k, v in found.items()}
        if not any(n.values()):
            continue
        files, size = _size(p for v in found.values() for p in v)
        out.append(Cleanup(d, doc, n["worker_folders"], n["claim_files"], n["block_files"],
                           files, size))
    return out


def _owners(run_dir: Path, total: int) -> dict[str, int]:
    """Who integrated each block: the worker folder holding it, else the claim file's word."""
    owners = owners_on_disk(run_dir, total)
    for p in run_dir.glob("claim-*"):
        name = block_of_claim(p.name)
        if name not in owners:
            try:
                owners[name] = int(p.read_text(encoding="ascii").split()[0])
            except (OSError, ValueError, IndexError):
                pass
    return owners


def apply(c: Cleanup, mode: str = "delete") -> dict:
    """Remove one run's scratch under ``mode`` (``delete`` or ``zip``, as ``mobcal run
    --scratch``), harvesting the worker folders into the record first when it has no ``split``
    block, and append what went to the record's ``cleaned`` list. Returns that entry."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    doc, d, total = dict(c.record), c.run_dir, c.total
    if "split" not in doc:
        st = doc.get("settings") or {}
        doc["split"] = harvest_split(
            d, total, doc["mobcal_in"].get("dealing") or "static",
            int(doc.get("input", {}).get("coordinate_sets", 1)),
            int(st.get("itn", 10)) * int(st.get("inp", 40)),
            dt.datetime.fromisoformat(doc["started"]), _owners(d, total))
        dump_record(doc, d / RECORD_JSON)  # the harvest is on disk before anything is removed
    entry = {"date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
             **clear_scratch(d, total, mode)}
    doc["cleaned"] = [*doc.get("cleaned", []), entry]
    dump_record(doc, d / RECORD_JSON)
    return entry

"""mobcal: the 2012 MOBCAL trajectory-method Fortran with a Python driver around it.

The package has one seam. ``mobcal.fortran`` (locate, verify and build the 2012 sources),
``mobcal.io`` (the ``.mfj``, ``mobcal.in`` and ``.out`` formats) and ``mobcal.run`` (the
process-fanout driver) never import Qt; ``mobcal.app`` is the PySide6 window on top of them.
Only ``mobcal.fortran`` exists at founding.
"""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "2.0.0rc2.dev0"

ROOT = Path(__file__).resolve().parent.parent.parent


def lab_dir() -> Path | None:
    """The private lab repository, if this checkout has one beside it.

    Resolution order: ``$MOBCAL_LAB``, then a ``MOBCAL-lab`` directory at this repo's root, then
    the sibling ``../MOBCAL-lab``. Returns None in a public clone, and nothing in this package
    needs it to be otherwise.
    """
    env = os.environ.get("MOBCAL_LAB")
    candidates = [Path(env)] if env else []
    candidates += [ROOT / "MOBCAL-lab", ROOT.parent / "MOBCAL-lab"]
    for c in candidates:
        if (c / "CLAUDE.md").is_file():
            return c
    return None

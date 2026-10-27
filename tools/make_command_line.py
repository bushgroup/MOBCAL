"""Write ``docs/command-line.md``, the command-line reference, from the argument parser.

    uv run tools/make_command_line.py

The page is ``mobcal.cli.reference()``: every subcommand's usage and arguments, with the help
strings ``mobcal.cli`` gives them, which for the settings the window also sets are the
descriptions in ``mobcal.options``, the window's tooltips. ``tests/test_options.py``
fails while the committed page differs from what this writes, so a change to an option or a
description is followed by a run of this tool in the same commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mobcal import cli  # noqa: E402


def main() -> int:
    out = ROOT / cli.REFERENCE
    out.write_bytes(cli.reference().encode("utf-8"))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

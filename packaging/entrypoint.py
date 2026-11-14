"""PyInstaller's entry script for the console executables.

PyInstaller freezes a script, not a console-script name from ``pyproject.toml``, so each
executable needs a real file that calls its command: this one, named by ``mobcal.spec`` for
``mobcal``, ``ccs-ion`` and ``ccs-result`` alike. One script and one Analysis make all three;
each executable runs the command of its own name (``mobcal.cli.COMMANDS``), and a name that is
none of them runs ``mobcal``.
"""

import os
import sys

from mobcal.cli import COMMANDS, main

if __name__ == "__main__":
    name = os.path.splitext(os.path.basename(sys.executable))[0].lower()
    sys.exit(COMMANDS.get(name, main)())

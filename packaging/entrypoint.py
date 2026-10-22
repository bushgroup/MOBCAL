"""PyInstaller's entry script.

PyInstaller freezes a script, not a console-script name from ``pyproject.toml``, so the
executable needs a real file that calls ``mobcal.cli.main``: this one, named by ``mobcal.spec``.
"""

import sys

from mobcal.cli import main

if __name__ == "__main__":
    sys.exit(main())

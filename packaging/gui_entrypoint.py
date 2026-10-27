"""PyInstaller's entry script for the window's executable.

The windowed executable (``mobcal-gui``: no console on Windows, the ``MOBCAL.app`` on macOS)
opens the window and nothing else; the console executable beside it is the command line, whose
``mobcal gui`` opens the same window.
"""

import sys

from mobcal.app import main

if __name__ == "__main__":
    sys.exit(main())

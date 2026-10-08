# Starts Vocet without any terminal window. Used by the Start menu shortcut (install.ps1) and "Start with Windows".
#
# Why this file does its own setup: the virtual environment's pythonw.exe (made by uv)
# is a *console* program, so starting Vocet through it opened a terminal window, and
# closing that window killed Vocet. The shortcut therefore runs Python's real, windowless
# pythonw.exe, and this file points it at the project's installed packages (.venv).
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PACKAGES = ROOT / ".venv" / "Lib" / "site-packages"
if VENV_PACKAGES.is_dir() and str(VENV_PACKAGES) not in sys.path:
    site.addsitedir(str(VENV_PACKAGES))
sys.path.insert(0, str(ROOT))

from vocet.app import main  # noqa: E402

main()

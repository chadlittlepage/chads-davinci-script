"""Standalone app entry point for py2app.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

import sys

# Add src to path so chads_davinci imports work in the bundle
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from chads_davinci.build_main import main

if __name__ == "__main__":
    sys.exit(main())

"""PyInstaller entry point for Colima Desktop.

PyInstaller runs this file as a top-level script, so we use absolute imports
and make sure the project root is on sys.path.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Augment PATH early (packaged apps inherit a minimal PATH).
from colima_desk._paths import augment_path

augment_path()

from colima_desk.__main__ import main

raise SystemExit(main())
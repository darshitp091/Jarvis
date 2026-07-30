"""Pytest configuration.

Its presence at the repository root puts the project directory on sys.path, so
tests can `import services...` the same way main.py does.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

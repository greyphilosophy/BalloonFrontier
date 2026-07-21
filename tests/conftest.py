import os
import sys

# Ensure the project root (which contains the balloon_frontier package)
# is importable for all tests.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

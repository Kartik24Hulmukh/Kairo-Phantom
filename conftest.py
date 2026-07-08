"""Root conftest — ensures repo root is on sys.path for all test workers.

When pytest-xdist spawns worker processes, they don't inherit sys.path
modifications made at import time in test modules. This conftest ensures
the repo root is on sys.path so that `bench.*`, `kernel.*`, `packs.*`,
and `kairo.*` are importable from all workers.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

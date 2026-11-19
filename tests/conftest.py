"""
tests/conftest.py
=================
Pytest and Unittest configuration and shared environment setup.
Ensures root workspace is on sys.path and configures logging for test suites.
"""

import os
import sys
import logging

# Ensure project root is first on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

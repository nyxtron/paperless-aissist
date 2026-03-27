"""Pytest configuration — set DATA_DIR before any app modules are imported."""
import os
import tempfile

# database.py reads DATA_DIR at import time and tries to mkdir it;
# point it at a temp directory so tests work without a running environment.
if "DATA_DIR" not in os.environ:
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="paperless_aissist_test_")

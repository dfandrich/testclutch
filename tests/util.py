"""Utility functions used in multiple tests."""

import os
from typing import TextIO
from unittest.mock import patch


# Directory holding test data files
DATADIR = 'data'


def data_file(fn: str) -> str:
    """Return the path to a given test data file."""
    return os.path.join(os.path.dirname(__file__), DATADIR, fn)


def open_data(fn: str) -> TextIO:
    """Return an open file object for the given test data file."""
    return open(data_file(fn))


def patch_config_get(key: str, value):
    """Mock config.get() to return a specific value for a given key.

    All other values return None, so this should only be used when a single config.get() is
    expected.
    """
    return patch('testclutch.config.get', side_effect=lambda k: value if k == key else None)

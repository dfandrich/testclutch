"""Utility functions used in multiple tests."""

import os
from typing import TextIO
from unittest.mock import patch

from testclutch import config


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

    All other keys return the originally-configured value. Multiple items can be overridden by
    calling this more than once, but it cannot be used as a decorator in that case; it must
    be called within the test (for example as a context manager) because each patch must have access
    to the mock installed by the previous call, which isn't the case when called as a decorator.
    """
    def side_effect(k: str):
        return value if k == key else orig_get(k)

    # Use the original (or the previously-patched) get() for unmatched keys
    orig_get = config.get
    return patch('testclutch.config.get', side_effect=side_effect)

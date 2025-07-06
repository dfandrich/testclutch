"""Test case data."""

from enum import IntEnum


# These are stored directly in the database
class TestResult(IntEnum):
    """Enumeration of all possible results of a test."""
    __test__ = False

    UNKNOWN = 0     # test result is not known
    PASS = 1        # test succeeded
    FAIL = 2        # test failed
    SKIP = 3        # test was skipped
    TIMEOUT = 4     # test timed out
    FAILIGNORE = 5  # test failed, but the result was ignored
    ABORT = 6       # test was stopped prematurely by the framework
    ERROR = 7       # a framework error occurred while running the test
    LAST = ERROR

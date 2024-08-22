"""Structures to hold PR data during analysis
"""

import contextlib
import fcntl
import logging
import pickle
from dataclasses import dataclass

from testclutch import config


@dataclass
class FailedTest:
    """Data about a failed test in a PR"""
    uniquejob: str  # unique job name
    testname: str   # test name
    url: str        # URL to test logs


@dataclass
class FailingTest:
    """Data about a flaky test in a CI job"""
    uniquejob: str   # unique job name
    testname: str    # test name
    rate: float      # ratio of failed to attempted runs (for flaky tests)


@dataclass
class PRAnalysis:
    """Analysis data for a PR

    This is persisted between invocations so individual job runs can be
    performed to obtain data for each origin.
    """
    num: int                                 # PR number
    checkrepo: str                           # source repository on which the PR is made
    start: int                               # epoch time when analysis started
    failed: dict[str, list[FailedTest]]      # all tests that failed in this PR per origin
    flaky: dict[str, list[FailingTest]]      # flaky test information per origin
    permafail: dict[str, list[FailingTest]]  # permafail test information per origin
    commit: dict[str, str]                   # commit being tested per origin
    commented: int                           # epoch time of PR comment


class PRAnalysisState:

    def __init__(self):
        self.statefile = None

    def read_state(self, wrlock: bool) -> dict[str, dict[int, PRAnalysis]]:
        """Reads the persistent state of PRs being analyzed

        Args:
            wrlock: True to obtain an exclusive lock on the state file, which must be later cleared
            with a call to write_state(). The call will block until a lock can be obtained,
            either a write lock or a read lock. Use True when the read data will be written out
            again later to ensure it won't be changed in the meantime.

        Returns:
            dict by checkrepo of dict by PR of analysis objects
        """
        assert not self.statefile
        filename = config.expand('pr_gather_path')
        pranalyses = {}

        # Open the file and obtain an appropriate lock
        try:
            f = open(filename, 'r+b' if wrlock else 'rb')
            if wrlock:
                fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
                # keep file handle around to hold the lock
                self.statefile = f
            else:
                fcntl.lockf(f.fileno(), fcntl.LOCK_SH)

        except FileNotFoundError:
            logging.error('pr_gather_path file not found; creating an empty one')

            # We need a file lock so we need a file. Create an empty one.
            # If there was a race condition and another program tried to create a file at the same
            # time there will be an exception, but the goal is to create an empty file without
            # overwriting any existing one, which will have been accomplished, so ignore that and
            # continue.
            with contextlib.suppress(FileExistsError):
                open(filename, 'xb').close()

            # Recursively call this function again in order to obtain the lock. Since the file now
            # exists, we will not enter this same exception path again, limiting recursion.
            return self.read_state(wrlock)

        # File is open here and holding an appropriate lock
        try:
            pranalyses = pickle.load(f)

        except EOFError:
            # This will happen when reading an empty file, such as is created on the first run.
            logging.error('Empty pr_gather_path file; starting fresh')
        except AttributeError:
            # This can happen when reading a file written with an older program using an older,
            # incompatible schema. THIS WILL CAUSE DATA LOSS!
            logging.error('Incompatible pr_gather_path found; starting fresh')
        except pickle.UnpicklingError:
            # This can happen with an invalid file or possibly a truncated one
            # THIS WILL CAUSE DATA LOSS!
            logging.error('Incompatible pr_gather_path file found; starting fresh')

        # Release a read lock here, but keep a write lock
        if not wrlock:
            # lock is released when file is closed
            f.close()

        return pranalyses

    def write_state(self, pranalyses: dict[str, dict[int, PRAnalysis]]):
        assert self.statefile  # read_state() must have been called with wrlock=True
        filename = config.expand('pr_gather_path')
        # The file is overwritten here, which will corrupt it if this program crashes while writing.
        # Since this is really only a cache file, it can just be deleted and the analysis process
        # restarted.
        with open(filename, 'wb') as f:
            # protocol=5 was introduced with Python 3.8, and we don't support any Python
            # version earlier than that, anyway.
            pickle.dump(pranalyses, f, protocol=5)

        if self.statefile:
            # lock is released when file is closed
            self.statefile.close()
            self.statefile = None


def upgrade_state():
    "Debugging tool to upgrade a PRAnalysis to a newer version"
    state = PRAnalysisState()
    pranalyses = state.read_state(True)
    for repo in pranalyses.values():
        for pr in repo.values():
            # Add code here to add any new PRAnalysis fields to an older pr
            pr.commit = {}
    state.write_state(pranalyses)


if __name__ == '__main__':
    # Debugging
    # upgrade_state()
    state = PRAnalysisState()
    pranalyses = state.read_state(False)
    import pprint
    pprint.pprint(pranalyses)

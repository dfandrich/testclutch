"""Parses pytest test log files

The test is expected to have been run with the "-r ap" (or "-r A") option to get the test summary
at the end.

pytest also supports writing a junit format output file, which has the advantage of providing
test run times.
"""

import logging
import re
from typing import TextIO

from testclutch.logdef import ParsedLog, TestCases, TestMeta  # noqa: F401
from testclutch.testcasedef import TestResult


# pytest -r A format
SUMMARY_START_RE = re.compile(r'^={5,} short test summary info =+$')
# uses SESSION_END_RE to end
RESULT_RE = re.compile(r'^(\w+) (.*::\S*) *(- )?(.*)$')
SKIPPED_RE = re.compile(r'^(\w+) \[\S*\] (\S*): (.*)$')
NONVERBOSE_SENTINAL_RE = re.compile(r'^collected ([0-9]+) items$')
SUMMARY_PLATFORM_RE = re.compile(r'^platform (\w+)( -- (.*))?')

# pytest -v format
SESSION_END_RE = re.compile(r'^={3,} (\d+) (\w+).* in ([0-9.]+)s ([()\d:]+)? *=')
RESULTV_RE = re.compile(r'^(\S+::\S+) (\w+) +(\(.*\) +)?\[[ \d]+%\]$')
VERBOSE_SENTINAL_RE = re.compile(r'^collecting \.\.\. collected ([0-9]+) items$')
PLATFORM_RE = re.compile(r'^platform (\w+)( -- (.*) --)?')

# common lines
SESSION_START_RE = re.compile(r'^={5,} test session starts =+$')


def parse_log_file_summary(f: TextIO) -> ParsedLog:
    """Parses pytest's test summary output.

    This is output with the "-r ap" or "-r A" flag.
    Disadvantage: skipped test names are not available
    Advantage: reason for skipping a test is available

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    while l := f.readline():
        if SESSION_START_RE.search(l):
            logging.debug("Found the start of a pytest log")
            meta = {
                'testformat': 'pytest',
                'testresult': 'truncated',  # will be overwritten if the real end is found
            }
            while l := f.readline():
                l = l.rstrip()
                if r := SUMMARY_PLATFORM_RE.search(l):
                    meta['os'] = r.group(1)
                    meta['testdeps'] = r.group(3)
                elif VERBOSE_SENTINAL_RE .search(l):
                    # If this is found, this is a verbose log so clear data and give up
                    logging.debug("Acutally, it's a verbose log; give up")
                    meta = {}
                    break
                elif SUMMARY_START_RE.search(l):
                    logging.debug("Found the start of a pytest short log")
                    while l := f.readline():
                        l = l.rstrip()
                        if r := SESSION_END_RE.search(l):
                            if r.group(2) == 'failed':
                                meta['testresult'] = 'failure'
                            else:
                                meta['testresult'] = 'success'
                            meta['runtestsduration'] = str(int(float(r.group(3)) * 1000000))
                            break
                        elif r := RESULT_RE.search(l):
                            if r.group(1) == 'PASSED':
                                testcases.append((r.group(2), TestResult.PASS, r.group(4), 0))
                            elif r.group(1) == 'FAILED':
                                testcases.append((r.group(2), TestResult.FAIL, r.group(4), 0))
                            elif r.group(1) == 'XPASS':
                                # Treat this as a normal pass (it was expected to fail)
                                testcases.append((r.group(2), TestResult.PASS, r.group(4), 0))
                            elif r.group(1) == 'XFAIL':
                                testcases.append((r.group(2), TestResult.FAILIGNORE, r.group(4), 0))
                            else:
                                logging.error("Unknown pytest result: %s", r.group(1))
                        elif r := SKIPPED_RE.search(l):
                            if r.group(1) == 'SKIPPED':
                                # The actual test name being skipped is not available here. The
                                # name used here is an approximation that is good enough to
                                # identify the test but won't match the actual test name if it
                                # were not skipped.
                                testcases.append((r.group(2), TestResult.SKIP, r.group(3), 0))
                            else:
                                logging.debug("Ignoring not SKIPPED type: %s", r.group(1))

    if not testcases:
        logging.debug('No pytest test summary could be found in the file')
    return meta, testcases


def parse_log_file(f: TextIO) -> ParsedLog:
    """Parses pytest's verbose output.

    This is output with the "-v" flag.
    Disadvantage: reason for skipping a test is not available
    Advantage: slightly higher chance of misidentifying a log lines as a test

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    while l := f.readline():
        if SESSION_START_RE.search(l):
            logging.debug("Found the start of a pytest log")
            meta = {
                'testformat': 'pytest',
                'testresult': 'truncated',  # will be overwritten if the real end is found
            }
            while l := f.readline():
                l = l.rstrip()
                if r := SESSION_END_RE.search(l):
                    if r.group(2) == 'failed':
                        meta['testresult'] = 'failure'
                    else:
                        meta['testresult'] = 'success'
                    meta['runtestsduration'] = str(int(float(r.group(3)) * 1000000))
                    break
                elif r := PLATFORM_RE.search(l):
                    meta['os'] = r.group(1)
                    meta['testdeps'] = r.group(3)
                elif NONVERBOSE_SENTINAL_RE .search(l):
                    # If this is found, this is not a verbose log so clear data and give up
                    logging.debug("Acutally, it's not a verbose log at all; give up")
                    meta = {}
                    break
                elif r := RESULTV_RE.search(l):
                    if r.group(2) == 'PASSED':
                        testcases.append((r.group(1), TestResult.PASS, '', 0))
                    elif r.group(2) == 'FAILED':
                        testcases.append((r.group(1), TestResult.FAIL, '', 0))
                    elif r.group(2) == 'SKIPPED':
                        testcases.append((r.group(1), TestResult.SKIP, '', 0))
                    elif r.group(2) == 'XPASS':
                        # Treat this as a normal pass (it was expected to fail)
                        testcases.append((r.group(1), TestResult.PASS, '', 0))
                    elif r.group(2) == 'XFAIL':
                        testcases.append((r.group(1), TestResult.FAILIGNORE, '', 0))
                    else:
                        logging.error("Unknown pytest result: %s", r.group(2))

    if not testcases:
        logging.info('No pytest verbose logs could be found in the file')
    return meta, testcases

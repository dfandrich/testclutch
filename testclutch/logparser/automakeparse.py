"""Parses automake test logs files

This is a simple format that is probably prone to false positives.

If more than one test series is found in the log, they are concatenated and treated as a single one.
"""

import logging
import re

from testclutch.filedef import TextIOReadline
from testclutch.logdef import ParsedLog, SingleTestFinding, TestCases, TestMeta  # noqa: F401
from testclutch.testcasedef import TestResult


# Pass/fail status for a test
RESULT_RE = re.compile(r'^(PASS|FAIL|SKIP|XFAIL|XPASS|ERROR):\s(.+?)(( - )(.*))?$')

# Start/end of summary log at end
SUMMARY_START_RE = re.compile(r'^Testsuite summary for (.*)$')
SUMMARY_END_RE = re.compile(r'^# ERROR:\s+(\d+)$')

# Summary failure line
SUMMARY_FAIL_RE = re.compile(r'^# FAIL:\s+(\d+)$')


def result_code(result: str) -> TestResult:
    if result == 'PASS':
        return TestResult.PASS
    if result == 'FAIL':
        return TestResult.FAIL
    if result == 'SKIP':
        return TestResult.SKIP
    if result == 'XFAIL':
        return TestResult.FAILIGNORE
    if result == 'XPASS':
        return TestResult.PASS  # no way to specify "unexpected pass"
    if result == 'ERROR':
        return TestResult.ERROR
    return TestResult.UNKNOWN


def parse_log_file(f: TextIOReadline) -> ParsedLog:
    """Parses automake's test output."""
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    while l := f.readline():
        if r := RESULT_RE.search(l):
            # Found a test result
            if m := r.group(5):
                info = m.strip()
            else:
                info = ''
            if code := result_code(r.group(1)):
                testcases.append(SingleTestFinding(r.group(2), code, info, 0))
            else:
                testcases.append(SingleTestFinding(r.group(2), TestResult.UNKNOWN, info, 0))
            if meta.get('testresult') == 'success':
                # This is the second (or more) test suite result in the log file, so delete
                # a previous success result so this one's result will prevail.
                del meta['testresult']

        elif r := SUMMARY_START_RE.search(l):
            desc = r.group(1)
            if desc.endswith(' -'):
                desc = desc[:-2]
            meta['testtarget'] = desc

            # Summary section
            while l := f.readline():
                if r := SUMMARY_FAIL_RE.search(l):
                    if r.group(1) == '0':
                        # If more than one test log is found in the file, we don't want to
                        # replace a failure result with success.
                        if 'testresult' not in meta:
                            meta['testresult'] = 'success'
                    else:
                        meta['testresult'] = 'failure'
                elif r := SUMMARY_END_RE.search(l):
                    break

    if testcases:
        logging.debug('Found an automake test log')
        meta['testformat'] = 'automake'
        if 'testresult' not in meta:
            meta['testresult'] = 'truncated'
    else:
        logging.debug('No automake test log could be found in the file')
        # In case we found something that looks like a summary, but no actual test results
        meta = {}
    return meta, testcases

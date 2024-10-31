"""Parses Python unittest test log files.

The test is expected to have been run with the "-v" and "-b" options.
"""

import contextlib
import logging
import re

from testclutch.filedef import TextIOReadline
from testclutch.logdef import ParsedLog, SingleTestFinding, TestCases, TestMeta, TestMetaStr  # noqa: F401
from testclutch.testcasedef import TestResult


# Test result line
# This can sometimes be split into two lines, such as for a FunctionTestCase that has a description,
# which is continued with TEST_CONT_RE
TEST_RE = re.compile(r'^(?P<method>[a-zA-Z_][\w._]*) \((?P<module>[a-zA-Z_][\w._]*)\)( \.\.\. (?P<result>.+))?$')

# Subtest result line
# Unfortunately, unittest doesn't list all subtests on success and only the subtests that failed
# on a failure, so just track the main test name instead of each subtest individually.
SUBTEST_RE = re.compile(r'^ +(?P<method>[a-zA-Z_][\w._]*) \((?P<module>[a-zA-Z_][\w._]*)\) \((?P<subtest>[^)]+)\) \.\.\. (?P<result>.+)?$')

# If the test line is split into two
TEST_CONT_RE = re.compile(r'^.* \.\.\. (?P<result>.+)$')

# Final count line near end
COUNT_RE = re.compile(r'^Ran (\d+) test(?:s)? in ([-\d.]+)s$')

# Final line and end giving overall result
FINAL_RE = re.compile(r'^(OK|FAILED|NO TESTS RAN)( \(.*\))?$')

# Parses the "result" part of TEST_RE or SUBTEST_RE
RESULT_RE = re.compile(r"^(?P<result>[\w _]+)(?: '?(?P<text>.*?)'?)?$")

# Mapping from text results to the appropriate enum
RESULT_CODES = {
    'ok': TestResult.PASS,
    'FAIL': TestResult.FAIL,
    'skipped': TestResult.SKIP,
    'ERROR': TestResult.FAIL,  # Failure running the test; treat this as a normal failure
    'expected failure': TestResult.FAILIGNORE,
    'unexpected success': TestResult.FAIL,  # Treat this "success" as a normal failure (it was
                                            # expected to fail, not succeed)
}


def make_testname(module: str, method: str) -> str:
    """Turn the module and method strings into a single test identifier."""
    if module.endswith(f'.{method}'):
        # This is probably Python >= 3.11 that already includes the method in the module string
        # This is a bit dangerous as it could remove a legitimate part of a name on Python <3.11
        return module
    # This is actually backwards for FunctionTestCase, but there doesn't seem to be any way
    # to detect that.
    return f'{module}.{method}'


class LogEndExit(Exception):
    """Raised when the end of the log file is reached to avoid continued parsing."""


def parse_log_file(f: TextIOReadline) -> ParsedLog:
    """Parses unittest's verbose output.

    This is output with the "-v" flag, with "-b" also sometimes necessary to avoid mangled text.

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    with contextlib.suppress(LogEndExit):
        # Outer loop searching for the actual unittest log
        while l := f.readline():
            l = l.rstrip()
            # There is no standard line to indicate the start of a test log, so look for a test
            # result or the time that's logged even if no tests are available.
            if not TEST_RE.search(l) and not COUNT_RE.search(l):
                continue

            logging.debug('Found the start of a unittest log')
            meta = {
                'testformat': 'unittest',
                'testresult': 'truncated',  # will be overwritten if the real end is found
            }

            # Inner loop around the actual unittest log
            # Start by processing the line just read since it's probably a test result.
            while l:
                l = l.rstrip()
                if r := FINAL_RE.search(l):
                    if r.group(1) == 'FAILED':
                        meta['testresult'] = 'failure'
                    elif r.group(1) in {'OK', 'NO TESTS RAN'}:
                        meta['testresult'] = 'success'
                    else:
                        logging.warning('Unexpected end result of unittest: %s', r.group(1))
                    # End of test log.
                    # This exception causes an exit from both nested while statements, ensuring that
                    # no more log parsing is performed.
                    raise LogEndExit

                if r := COUNT_RE.search(l):
                    meta['runtestsduration'] = str(int(float(r.group(2)) * 1000000))
                elif (r := TEST_RE.search(l)) or (r := SUBTEST_RE.search(l)):
                    if r.group('result') and (rr := RESULT_RE.search(r.group('result'))):
                        if not (reason := rr.group('text')):
                            reason = ''
                        if result_code := RESULT_CODES.get(rr.group('result')):
                            # There can be several subtests for one test, so this may be appending
                            # identical tests to the list. We remove any duplicates later.
                            testcases.append(
                                SingleTestFinding(
                                    make_testname(r.group('module'), r.group('method')),
                                    result_code, reason, 0))
                        else:
                            logging.error('Unknown unittest test result: %s',
                                          rr.group('result'))
                    else:
                        # We have a split test line; get the second half
                        if not (l := f.readline()):
                            # EOF; there is no second half
                            raise LogEndExit
                        l = l.rstrip()
                        if ((rr := TEST_CONT_RE.search(l))
                                and (rr := RESULT_RE.search(rr.group('result')))):
                            if not (reason := rr.group('text')):
                                reason = ''
                            if result_code := RESULT_CODES.get(rr.group('result')):
                                testcases.append(
                                    SingleTestFinding(
                                        make_testname(r.group('module'), r.group('method')),
                                        result_code, reason, 0))
                            else:
                                logging.warning(f"Unknown result code {rr.group('result')}")

                        else:
                            logging.warning(
                                'Missing continuation line for '
                                f"{make_testname(r.group('module'), r.group('method'))}")
                            # Process the current line in case it's for a new test
                            continue

                l = f.readline()

    if not testcases:
        logging.debug('No unittest verbose logs could be found in the file')

    # Remove duplicate tests in the list
    # This can happen for subtests, where we treat all subtests as one test case
    alltests = set()
    uniquetests = []
    for test in testcases:
        if test.name in alltests:
            logging.debug(f'Test {test.name} appears more than once')
            continue
        alltests.add(test.name)
        uniquetests.append(test)

    return meta, uniquetests

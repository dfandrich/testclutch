"""Parses pytest test log files.

The test is expected to have been run with the "-r ap" (or "-r A") option to get the test summary
at the end.

pytest also supports writing a junit format output file, which has the advantage of providing
test run times.
"""

import logging
import re
from typing import Optional

from testclutch import pyplatform
from testclutch.filedef import TextIOReadline
from testclutch.logdef import ParsedLog, SingleTestFinding, TestCases, TestMeta  # noqa: F401
from testclutch.logparser import curlparse
from testclutch.testcasedef import TestResult


# pytest -r A format
SUMMARY_START_RE = re.compile(r'^={5,} short test summary info =+$')
# uses SESSION_END_RE to end
RESULT_RE = re.compile(r'^(\w+) (.+?::.*?\S) +(- )?(.*?)$')
SKIPPED_RE = re.compile(r'^(\w+) \[.+\] (.+?): (.*)$')
NONVERBOSE_SENTINEL_RE = re.compile(r'^collected ([0-9]+) items$')
# This is for xdist since NONVERBOSE_SENTINEL_RE doesn't appear
NONVERBOSE_SENTINEL2_RE = re.compile(r'^[a-zA-Z.]* +\[100%\]$')
SUMMARY_PLATFORM_RE = re.compile(r'^platform (\w+)( -- (.*))?$')

# pytest -v format
SESSION_END_RE = re.compile(r'^={3,} (\d+) (\w+).* in ([0-9.]+)s ([()\d:]+)? *=')
RESULTV_RE = re.compile(r'^(?P<name>\S+::\S+(\[.+?\])?) (?P<result>\w+) +(\(.*\) +)?\[[ \d]+%\]$')
VERBOSE_SENTINEL_RE = re.compile(r'^collecting \.\.\. collected ([0-9]+) items$')
# This is for xdist since VERBOSE_SENTINEL_RE doesn't appear
VERBOSE_SENTINEL2_RE = re.compile(r'^cachedir: ')
PLATFORM_RE = re.compile(r'^platform (\w+)( -- (.*) --)')

# pytest -v format with xdist
# This one shows up in the short output format as well
XDIST_WORKERS_RE = re.compile(r'^([0-9]+) workers \[([0-9]+) items\]$')
RESULTV_XDIST_RE = re.compile(r'^\[\w+\] \[ *\d+%\] (?P<result>\w+) (?P<name>.+?::.*)$')

# pytest-astropy-header --astropy-header option
ASTROPY_PLATFORM_RE = re.compile(r'Platform: (.*)$')

# curl-specific test headers
# This provides the same information as ASTROPY_PLATFORM_RE
CURL_PLATFORM_RE = re.compile(r'^ *platform: ([^ ]+)$')
CURL_VERSION_RE = re.compile(r'^ *curl: Version: curl (?P<ver>[^ ]+) \([^)]+\)( (?P<deps>.*))?$')
CURL_FEATURES_RE = re.compile(r'^ *curl: Features: (.*)$')
CURL_PROTOCOLS_RE = re.compile(r'^ *curl: Protocols: (.*)$')

# common lines
SESSION_START_RE = re.compile(r'^={5,} test session starts =+$')

# capture ANSI X3.64 escape sequences added with --color=yes
STRIP_ANSI_RE = re.compile(
    '\x1b[- #%()*+./]|'
    '(?:\x1b\\[|\x9b)[ -?]*[@-~]|'  # CSI ... Cmd
    '(?:\x1b\\]|\x9d).*?(?:\x1b\\|[\x07\x9c])|'  # OSC ... (ST|BEL)
    '(?:\x1b[P^_]|[\x90\x9e\x9f]).*?(?:\x1b\\|\x9c)|'  # (DCS|PM|APC) ... ST
    '\x1b.|[\x80-\x9f]'
)


def strip_ansi(s: Optional[str]) -> Optional[str]:
    """Strip ANSI X3.64 escape sequences from string.

    A None input is passed straight to the output.
    """
    if not s:
        return s
    return STRIP_ANSI_RE.sub('', s)


def parse_log_file_summary(f: TextIOReadline) -> ParsedLog:
    """Parses pytest's test summary output.

    This is output with the "-r ap" or "-r A" flag.
    Disadvantage: skipped test names are not available
    Advantage: reason for skipping a test is available

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    while l := strip_ansi(f.readline()):
        if SESSION_START_RE.search(l):
            logging.debug('Found the start of a pytest log')
            meta = {
                'testformat': 'pytest',
                'testresult': 'truncated',  # will be overwritten if the real end is found
            }
            while l := strip_ansi(f.readline()):
                l = l.rstrip()
                if r := SUMMARY_PLATFORM_RE.search(l):
                    meta['os'] = r.group(1)
                    meta['testdeps'] = r.group(3)
                elif r := XDIST_WORKERS_RE.search(l):
                    # This shows up in short logs as well with xdist
                    meta['paralleljobs'] = r.group(1)
                elif (r := ASTROPY_PLATFORM_RE.search(l)) or (r := CURL_PLATFORM_RE.search(l)):
                    meta['pyplatform'] = r.group(1)
                    platmeta = pyplatform.parse_platform(r.group(1))
                    meta = {**meta, **platmeta}
                elif r := CURL_VERSION_RE.search(l):
                    meta['testingver'] = r.group('ver')
                    meta['curldeps'] = r.group('deps')
                elif r := CURL_FEATURES_RE.search(l):
                    meta['features'] = r.group(1)
                elif r := CURL_PROTOCOLS_RE.search(l):
                    meta['curlprotocols'] = r.group(1)
                elif bimeta := curlparse.parse_buildinfo(l):
                    # curl-specific buildinfo lines
                    meta = {**meta, **bimeta}
                elif VERBOSE_SENTINEL_RE.search(l) or VERBOSE_SENTINEL2_RE.search(l):  # noqa: R508
                    # If this is found, this is a verbose log so clear data and give up
                    logging.debug("Actually, it's a verbose log; give up")
                    meta = {}
                    break
                elif SUMMARY_START_RE.search(l):
                    logging.debug('Found a pytest short log')
                    while l := strip_ansi(f.readline()):
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
                                testcases.append(SingleTestFinding(
                                    r.group(2), TestResult.PASS, r.group(4), 0))
                            elif r.group(1) == 'FAILED':
                                testcases.append(SingleTestFinding(
                                    r.group(2), TestResult.FAIL, r.group(4), 0))
                            elif r.group(1) == 'XPASS':
                                # Treat this as a normal pass (it was expected to fail)
                                testcases.append(SingleTestFinding(
                                    r.group(2), TestResult.PASS, r.group(4), 0))
                            elif r.group(1) == 'XFAIL':
                                testcases.append(SingleTestFinding(
                                    r.group(2), TestResult.FAILIGNORE, r.group(4), 0))
                            else:
                                logging.error('Unknown pytest result: %s', r.group(1))
                        elif r := SKIPPED_RE.search(l):
                            if r.group(1) == 'SKIPPED':
                                # The actual test name being skipped is not available here. The
                                # name used here is an approximation that is good enough to
                                # identify the test but won't match the actual test name if it
                                # were not skipped.
                                testcases.append(SingleTestFinding(
                                    r.group(2), TestResult.SKIP, r.group(3), 0))
                            else:
                                logging.debug('Ignoring not SKIPPED type: %s', r.group(1))

    if not testcases:
        logging.debug('No pytest test summary could be found in the file')
    return meta, testcases


def parse_log_file(f: TextIOReadline) -> ParsedLog:
    """Parses pytest's verbose output.

    This is output with the "-v" flag.
    Disadvantage: reason for skipping a test is not available
    Advantage: slightly higher chance of misidentifying a log lines as a test

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}       # type: TestMeta
    testcases = []  # type: TestCases
    while l := strip_ansi(f.readline()):
        if SESSION_START_RE.search(l):
            logging.debug('Found the start of a pytest log')
            meta = {
                'testformat': 'pytest',
                'testresult': 'truncated',  # will be overwritten if the real end is found
            }
            while l := strip_ansi(f.readline()):
                l = l.rstrip()
                if r := SESSION_END_RE.search(l):
                    if r.group(2) == 'failed':
                        meta['testresult'] = 'failure'
                    else:
                        meta['testresult'] = 'success'
                    meta['runtestsduration'] = str(int(float(r.group(3)) * 1000000))
                    break
                if r := PLATFORM_RE.search(l):
                    meta['os'] = r.group(1)
                    meta['testdeps'] = r.group(3)
                elif r := XDIST_WORKERS_RE.search(l):
                    meta['paralleljobs'] = r.group(1)
                elif (r := ASTROPY_PLATFORM_RE.search(l)) or (r := CURL_PLATFORM_RE.search(l)):
                    meta['pyplatform'] = r.group(1)
                    platmeta = pyplatform.parse_platform(r.group(1))
                    meta = {**meta, **platmeta}
                elif r := CURL_VERSION_RE.search(l):
                    meta['testingver'] = r.group('ver')
                    meta['curldeps'] = r.group('deps')
                elif r := CURL_FEATURES_RE.search(l):
                    meta['features'] = r.group(1)
                elif r := CURL_PROTOCOLS_RE.search(l):
                    meta['curlprotocols'] = r.group(1)
                elif bimeta := curlparse.parse_buildinfo(l):
                    # curl-specific buildinfo lines
                    meta = {**meta, **bimeta}
                elif (NONVERBOSE_SENTINEL_RE.search(l)  # noqa: R508
                      or NONVERBOSE_SENTINEL2_RE.search(l)):
                    # If this is found, this is not a verbose log so clear data and give up
                    # Note that this does not appear with xdist
                    logging.debug("Actually, it's not a verbose log at all; give up")
                    meta = {}
                    break
                elif (r := RESULTV_RE.search(l)) or (r := RESULTV_XDIST_RE.search(l)):
                    if r.group('result') == 'PASSED':
                        testcases.append(SingleTestFinding(r.group('name'), TestResult.PASS, '', 0))
                    elif r.group('result') == 'FAILED':
                        testcases.append(SingleTestFinding(r.group('name'), TestResult.FAIL, '', 0))
                    elif r.group('result') == 'SKIPPED':
                        testcases.append(SingleTestFinding(r.group('name'), TestResult.SKIP, '', 0))
                    elif r.group('result') == 'XPASS':
                        # Treat this as a normal pass (it was expected to fail)
                        testcases.append(SingleTestFinding(r.group('name'), TestResult.PASS, '', 0))
                    elif r.group('result') == 'XFAIL':
                        testcases.append(SingleTestFinding(
                            r.group('name'), TestResult.FAILIGNORE, '', 0))
                    else:
                        logging.error('Unknown pytest result: %s', r.group('result'))

    if not testcases:
        logging.debug('No pytest verbose logs could be found in the file')
    return meta, testcases

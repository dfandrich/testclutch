"""Parses curl test log files."""

import datetime
import logging
import re
import zlib

from testclutch import uname
from testclutch.filedef import TextIOReadline
from testclutch.logdef import ParsedLog, SingleTestFinding, TestCases, TestMeta, TestMetaStr  # noqa: F401
from testclutch.testcasedef import TestResult


# TODO: obsolete after 2024-09-10
# NOTE: if lines are added below that match spaces at the start of a line,
# update ingest/curlauto.py at the same time

# Early headers
# TODO: this is obsolete after 2024-09-20 which added Args:
RE_RUNTESTS = re.compile(r'perl.*/runtests\.pl (.*)$')
# If a log is truncated, this line won't be found; use a different one (that may not be as reliable)
# RE_USINGAUTOMAKE = re.compile(r'make +all-am')
RE_USINGAUTOMAKE = re.compile(r'^Making all in ')
# It's easier to figure out the compiler path on a libtool invocation, so restrict checking to that
RE_COMPILERPATHAC = re.compile(r"""libtool .*--mode=compile (\S+) """)

# configure headers
# These won't be available in most logs because they show up before a compile,
# not before a test run, so jobs where those are separated won't see them.
RE_COMPILERAC = re.compile(r"compiler version\.\.\. ([^']+) '([^']*)'(?: \(raw: '([^']*)'\))?")
RE_COMPILERCMAKE = re.compile(r'^-- The C compiler identification is (\S+) (\S+)')
RE_USINGCMAKE = re.compile(r'^-- Using CMake version')
RE_USINGCMAKEMSBUILD = re.compile(r'^(\d+>)?Checking Build System')
RE_USINGCMAKEMAKE = re.compile(r'^\[ *\d+%] (Building C object|Built target)')
RE_USINGCMAKENINJA = re.compile(r'^\[\d+/\d+\] (Building C object|Built target)')
RE_USINGCMAKERUNMAKE = re.compile(r'make  *-f CMakeFiles')  # used if we missed the configure stage

# Test log header
RE_START = re.compile(r'^\*{9} System characteristics \*')
RE_CURLVER = re.compile(r'^\* curl (\S+) \(([^)]+)\)')
RE_DEPS = re.compile(r'^\* (.+)$')
RE_HOST = re.compile(r'^\* Host: (\S+)')
RE_FEATURES = re.compile(r'^\* Features: (.*)$')
RE_PROTOCOLS = re.compile(r'^\* Protocols: (.*)$')
RE_OS = re.compile(r'^\* OS: (\S+)')
RE_PERL = re.compile(r'^\* Perl: v([\d.]+\d)')
RE_JOBS = re.compile(r'^\* Jobs: (\d+)')
RE_ARGS = re.compile(r'^\* Args: (.+)')
RE_SYSTEM = re.compile(r'^\* System: (\S+ \S* \S+.*)$')
RE_SEED = re.compile(r'^\* Seed: (\d+)')
# These could all match on the same line
RE_VALGRIND = re.compile(r'^\* Env:.*\bValgrind\b')
RE_EVENT = re.compile(r'^\* Env:.*\bevent-based\b')
RE_DUPHANDLE = re.compile(r'^\* Env:.*\btest-duphandle\b')

# Buildinfo fields in header, starting 2024-09-06
# Some are duplicated by other runtests.pl lines, namely:
#   buildinfo.target (same as RE_CURLVER[1])
#   buildinfo.target.vendor (same as RE_CURLVER[1][-1])
#   buildinfo.host.os (same as RE_OS)
#   buildinfo.host.cpu (same as RE_BI_HOSTTRIPLET[0])
#   buildinfo.host.vendor (same as RE_BI_HOSTTRIPLET[-1])
# but since these can be used in non-runtests.pl contexts, some are parsed anyway.
# TODO: Add the remaining fields:
#   buildinfo.configure.command
#   buildinfo.configure.make
#   buildinfo.target.flags
# Some duplicate information obtained earlier during the compile, but since the compile logs are
# not always available, it's better to rely on these.
# Note that these regexes expect no prefix (which on runtests.pl logs will be "* ") before being
# matched.
# TODO: after a suitable period, remove the duplicate data fields that come from compile logs.
RE_BI_COMPILER = re.compile(r'^buildinfo\.compiler: (.+)$')
RE_BI_COMPILERVER = re.compile(r'^buildinfo\.compiler\.version: (\S+)')
RE_BI_GENERATOR = re.compile(r'^buildinfo\.configure\.generator: (.+)$')
RE_BI_CONFIGURETOOL = re.compile(r'^buildinfo\.configure\.tool: (.+)$')
RE_BI_CONFIGUREARGS = re.compile(r'^buildinfo\.configure\.args: (.+)$')
RE_BI_CONFIGUREVER = re.compile(r'^buildinfo\.configure\.version: (\S+)')
RE_BI_TARGETTRIPLET = re.compile(r'^buildinfo\.target: (\S+)$')
RE_BI_TARGETCPU = re.compile(r'^buildinfo\.target\.cpu: (\S+)')
RE_BI_TARGETOS = re.compile(r'^buildinfo\.target\.os: (.+)')
RE_BI_HOSTTRIPLET = re.compile(r'^buildinfo\.host: (\S+)$')
RE_BI_HOSTOS = re.compile(r'^buildinfo\.host\.os: (.+)$')
RE_BI_HOSTCPU = re.compile(r'^buildinfo\.host\.cpu: (\S+)$')

# Test log results
RE_STARTRESULTS = re.compile(r'^\*{41}')
RE_TOIGNORE = re.compile(r'^Warning: test(\d{1,5}) result is ignored')
RE_SKIPPED = re.compile(r'^test (\d{4,5}) SKIPPED: (.*)$')
RE_FAILED = re.compile(r'^ (\d{1,5}): ((\w+)( \(.*\))?) FAILED')
RE_VALGRINDFAILED = re.compile(r'^ (valgrind) ERROR')
RE_IGNORED = re.compile(r'^ (\d{1,5}): IGNORED: (.*)$')
# Obsolete after 2023-06-21
RE_EXITFAILED = re.compile(r'^ (exit) FAILED$')
RE_TESTSTART = re.compile(r'^test (\d{4,5})\.\.\.\[')
RE_SKIPAFTERSTART = re.compile(r'^CMD |^RUN: |^Warning: |^postcheck |^curl returned |^Killed'
                               r'|(\d+) functions to make fail'
                               r'|(^\*\* [A-Z ]+$)'
                               r'|functions found, but only fail'
                               r'|allocation(s)? allowed, did'
                               r'|did \d+ allocations, \d+ allowed'
                               r'|allocated \d+ maximum, \d+ allowed'
                               r'|At [\da-fA-F]+, there is '
                               r'|^ allocated by '
                               r'|Leak detected:'
                               r"|Found '[^']+' confirmed to not exist"
                               r'|received SIG[A-Z]+, exiting'
                               r'|(^\s?$)'
                               r'|( log/(\d+/)?std)'
                               r'|(^\S+ returned .* expecting (\d)+$)')
RE_ABORTED = re.compile(r'Aborting tests$')
# Should be just {11} after 2023-06-21
RE_TESTRESULTOK = re.compile(r'^.{10,11} OK \(.*, took (-?\d+\.\d+)s')
RE_TORTUREOK = re.compile(r'^torture OK$')
RE_TORTURESKIPPED = re.compile(r'^ found (no functions to make fail)$')
RE_TOTALTIME = re.compile(r'tests were considered during (\d+) seconds')
RE_OKSUMMARY = re.compile(r'^TESTDONE: (\d+) tests out of (\d+) reported OK')
RE_FAILSUMMARY = re.compile(r'^TESTFAIL: These test cases failed: ')

# Test log results with -s option
RE_TESTSTARTSHORT = re.compile(r'^test (\d{4,5})\.\.\.$')
RE_TESTRESULTSHORT = re.compile(r'^test (\d{4,5})\.\.\.(\w+) \(.*, took (-?\d+\.\d+)s')
RE_TESTFAILEDSHORT = re.compile(r'^test (\d{4,5})\.\.\.FAILED$')

# testcurl headers
RE_TESTCURLCOMMITSTART = re.compile(r'^testcurl: The most recent curl git commits:')
RE_TESTCURLCOMMIT = re.compile(r'^testcurl:( ){1,3}'
                               r'(((?P<shash>[0-9a-f]{7,11})(?: ))|(?P<lhash>[0-9a-f]{40}$))')
RE_TESTCURLDAILY = re.compile(r'^testcurl: curl-([\d.]+)-(\d{8})/? is verified to be '
                              r'a fine daily source dir')
RE_TESTCURLDATE = re.compile(r'^testcurl: date = (.*)$')
RE_TESTCURLENDDATE = re.compile(r'^testcurl: enddate = (.*)$')
RE_TESTCURLVER = re.compile(r'^testcurl: version = (.*)$')
RE_TESTCURLNAME = re.compile(r'testcurl: NAME = (.*)$')
RE_TESTCURLDESC = re.compile(r'testcurl: DESC = (.*)$')
RE_TESTCURLBUILDCODE = re.compile(r'testcurl: (\w+) = ')
TESTCURLBUILDCODEIGNORED = frozenset(('NOTES', 'version', 'date', 'timestamp'))
# TODO: lots more testcurl headers that could be added here

# autoconf target (or host) triplet (sometimes quadruplet)
RE_TARGETTRIPLET = re.compile(r'([\w.]+)-([\w.]+)-([-\w.]+)')


def escs(s: str) -> str:
    """Escape non-ascii characters in a string.

    This makes it safer to display by avoiding invalid UTF-8 and ANSI escape sequences.
    """
    return s.encode('utf-8').decode('us-ascii', errors='backslashreplace')


def strip0(n: str) -> str:
    """Strip leading zeros in a string integer."""
    return str(int(n))


def check_found_result(testcases: TestCases):
    """Check if a missing test result was found.

    It can happen that an expected test result line is not found, usually due to an unexpected
    line appearing instead (like a verbose log output line, or postcheck failure or similar.
    In such a case, a TestResult.UNKNOWN result will be entered. However, subsequent parsing
    can find the actual test result and that will be added to the list. That makes two results
    for the same test which is not desired.

    This function looks at the last two test entries and deletes an UNKNOWN entry if the next
    one contains the correct result.
    """
    if len(testcases) < 2:
        return
    if testcases[-1].name == testcases[-2].name and testcases[-2].result == TestResult.UNKNOWN:
        del testcases[-2]
    return


def parse_buildinfo(l: str) -> TestMetaStr:
    """Parse a buildinfo line if found.

    The input strings are expected to start with "buildinfo..." without another prefix.
    """
    meta = {}
    if r := RE_BI_GENERATOR.search(l):
        if r.group(1) in {'Unix Makefiles', 'MSYS Makefiles'}:
            meta['buildsystem'] = 'cmake/make'
        elif r.group(1) == 'Ninja':
            meta['buildsystem'] = 'cmake/ninja'
        elif r.group(1) == 'Ninja Multi-Config':
            meta['buildsystem'] = 'cmake/ninja-multiconfig'
        elif r.group(1).startswith('Visual Studio'):
            meta['buildsystem'] = 'cmake/msbuild'
        else:
            logging.warning('Unknown cmake generator %s', r.group(1))
    elif r := RE_BI_CONFIGURETOOL.search(l):
        if r.group(1) == 'configure':
            meta['buildsystem'] = 'automake'
        elif r.group(1).endswith('cmake') or r.group(1).endswith('cmake.exe'):
            # This should be made more specific momentarily on the generator line
            meta['buildsystem'] = 'cmake'
        else:
            logging.warning('Unknown configure program %s', r.group(1))
    elif r := RE_BI_CONFIGUREARGS.search(l):
        meta['configureargs'] = r.group(1).strip()
    elif r := RE_BI_CONFIGUREVER.search(l):
        meta['buildsystemver'] = r.group(1)
    elif r := RE_BI_COMPILER.search(l):
        meta['compiler'] = r.group(1)
    elif r := RE_BI_COMPILERVER.search(l):
        # During a short transition period in 2024-09, this field could hold a
        # compilerversion or a compilerversioncode. Determine which it is by
        # looking at its contents. Once backward compatibility is no longer needed,
        # change this to unconditionally set compilerversion.
        # TODO: obsolete after 2024-09-10
        ver = r.group(1)
        if len(ver) < 3 or ver.find('.') > 0:
            meta['compilerversion'] = ver
        else:
            meta['compilerversioncode'] = ver
    elif r := RE_BI_TARGETTRIPLET.search(l):
        meta['targettriplet'] = r.group(1)
        if rr := RE_TARGETTRIPLET.search(r.group(1)):
            meta['targetarch'] = rr.group(1)
            meta['targetvendor'] = rr.group(2)
            # targetos will contain the "kernel" field when it exists (in a target
            # quadruplet) AND the "os" field. This ends up being more consistent
            # than trying to separate them into two fields when they exist, as
            # "kernel" and "os" aren't always unique descriptors.
            meta['targetos'] = rr.group(3)
        else:
            # Probably created by CMake, which doesn't use a triplet but just the OS
            meta['targetos'] = r.group(1)
    elif r := RE_BI_TARGETCPU.search(l):
        meta['targetarch'] = r.group(1)
    elif r := RE_BI_TARGETOS.search(l):
        meta['targetos'] = r.group(1)
    elif r := RE_BI_HOSTTRIPLET.search(l):
        meta['hosttriplet'] = r.group(1)
        if rr := RE_TARGETTRIPLET.search(r.group(1)):
            meta['hostarch'] = rr.group(1)
            meta['hostvendor'] = rr.group(2)
            # hostos will contain the "kernel" field when it exists (in a host
            # quadruplet) AND the "os" field. This ends up being more consistent
            # than trying to separate them into two fields when they exist, as
            # "kernel" and "os" aren't always unique descriptors.
            meta['hostos'] = rr.group(3)
        else:
            # Probably created by CMake, which doesn't use a triplet but just the OS
            meta['hostos'] = r.group(1)
    elif r := RE_BI_HOSTCPU.search(l):
        meta['hostarch'] = r.group(1)
    elif r := RE_BI_HOSTOS.search(l):
        meta['hostos'] = r.group(1)

    return meta


def parse_log_file(f: TextIOReadline) -> ParsedLog:  # noqa: C901
    """Parses curl's runtests.pl test log output.

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}         # type: TestMeta
    testcases = []    # type: TestCases
    toignore = set()  # type: set[str]
    got_first = False
    while l := f.readline():
        if not got_first:
            logging.debug('First log line: %s', escs(l))
            got_first = True
        if RE_START.search(l):
            logging.debug('Found the start of a curl test log')
            meta['testformat'] = 'curl'
            meta['testresult'] = 'truncated'  # will be overwritten if the real end is found
            meta['testmode'] = 'normal'       # will be overwritten if another mode is used
            meta['withduphandle'] = 'no'      # will be overwritten if test-duphandle is enabled
            meta['withevent'] = 'no'          # will be overwritten if event-based is enabled
            meta['withvalgrind'] = 'no'       # will be overwritten if Valgrind is enabled
            # ********* System characteristics ********
            if not (l := f.readline()):
                break
            l = l.rstrip()
            if r := RE_CURLVER.search(l):
                meta['testingver'] = r.group(1)
                meta['targettriplet'] = r.group(2)
                if rr := RE_TARGETTRIPLET.search(r.group(2)):
                    # Some of these may be overwritten later by buildinfo data
                    meta['targetarch'] = rr.group(1)
                    meta['targetvendor'] = rr.group(2)
                    # targetos will contain the "kernel" field when it exists (in a target
                    # quadruplet) AND the "os" field. This ends up being more consistent than trying
                    # to separate them into two fields when they exist, as "kernel" and "os" aren't
                    # always unique descriptors.
                    meta['targetos'] = rr.group(3)
                elif r.group(2):
                    # Probably created by CMake, which doesn't use a triplet but just the OS
                    meta['targetos'] = r.group(2)
            if not (l := f.readline()):
                break
            l = l.rstrip()
            if r := RE_DEPS.search(l):
                meta['curldeps'] = r.group(1)
                while l := f.readline():
                    l = l.rstrip()
                    # These checks could all match the same line
                    if r := RE_VALGRIND.search(l):
                        meta['withvalgrind'] = 'yes'
                    if r := RE_EVENT.search(l):
                        meta['withevent'] = 'yes'
                    if r := RE_DUPHANDLE.search(l):
                        meta['withduphandle'] = 'yes'
                    # These checks are all mutually exclusive
                    if r := RE_HOST.search(l):
                        meta['host'] = r.group(1)
                    elif r := RE_FEATURES.search(l):
                        meta['features'] = r.group(1)
                    elif r := RE_PROTOCOLS.search(l):
                        meta['curlprotocols'] = r.group(1)
                    elif r := RE_ARGS.search(l):
                        meta['runtestsopts'] = r.group(1)
                    elif r := RE_OS.search(l):
                        meta['os'] = r.group(1)
                    elif r := RE_PERL.search(l):
                        meta['perlver'] = r.group(1)
                    elif r := RE_JOBS.search(l):
                        meta['paralleljobs'] = r.group(1)
                    elif r := RE_SEED.search(l):
                        meta['randomseed'] = r.group(1)
                    elif r := RE_SYSTEM.search(l):
                        unamemeta = uname.parse_uname(r.group(1))
                        if unamemeta:
                            meta = {**meta, **unamemeta}
                        else:
                            logging.warning('Unexpected uname line: %s', escs(r.group(1)))
                    elif l.startswith('* ') and (bimeta := parse_buildinfo(l[2:])):
                        meta = {**meta, **bimeta}
                    elif RE_STARTRESULTS.search(l):
                        # *****************************************
                        while l := f.readline():
                            l = l.rstrip()
                            if r := RE_SKIPPED.search(l):
                                testcases.append(
                                    SingleTestFinding(strip0(r.group(1)), TestResult.SKIP,
                                                      r.group(2), 0))
                            elif r := RE_TESTSTART.search(l):
                                # In case verbose mode is on, skip the verbose lines
                                # (this doesn't always work properly)
                                # Also skip other test harness warning messages
                                # TODO: maybe just rely on RE_TESTRESULTOK matching properly
                                # and don't bother doing it this way. This way is less likely
                                # to correlate the wrong result with a test, though.
                                while l := f.readline():
                                    if not RE_SKIPAFTERSTART.search(l.rstrip()):
                                        break
                                if not l:
                                    # EOF
                                    break
                                l = l.rstrip()
                                if rr := RE_TESTRESULTOK.search(l):
                                    duration = int(float(rr.group(1)) * 1000000)
                                    if duration < 0:
                                        duration = 0  # bug in the test harness
                                    testno = strip0(r.group(1))
                                    testcases.append(
                                        SingleTestFinding(testno, TestResult.PASS, '', duration))
                                elif rr := RE_TORTUREOK.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(
                                        SingleTestFinding(testno, TestResult.PASS, '', 0))
                                    meta['testmode'] = 'torture'
                                elif rr := RE_FAILED.search(l):
                                    if rr.group(1) in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(
                                        SingleTestFinding(rr.group(1), result, rr.group(2), 0))
                                    if rr.group(2) == 'torture':
                                        meta['testmode'] = 'torture'
                                elif rr := RE_IGNORED.search(l):
                                    testcases.append(
                                        SingleTestFinding(rr.group(1), TestResult.SKIP, rr.group(2), 0))
                                elif rr := RE_EXITFAILED.search(l):
                                    testno = strip0(r.group(1))
                                    if testno in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(
                                        SingleTestFinding(testno, result, rr.group(1), 0))
                                elif rr := RE_ABORTED.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(
                                        SingleTestFinding(testno, TestResult.ABORT, rr.group(0), 0))
                                elif rr := RE_VALGRINDFAILED.search(l):
                                    testno = strip0(r.group(1))
                                    if testno in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(
                                        SingleTestFinding(testno, result, rr.group(1), 0))
                                elif rr := RE_TORTURESKIPPED.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(
                                        SingleTestFinding(testno, TestResult.SKIP, r.group(1), 0))
                                    meta['testmode'] = 'torture'
                                else:
                                    logging.warning('Expecting test status line, got: %s', escs(l))
                                    testno = strip0(r.group(1))
                                    testcases.append(SingleTestFinding(
                                        testno, TestResult.UNKNOWN, 'no test status line', 0))
                            elif r := RE_TESTSTARTSHORT.search(l):
                                # The next line will be a RE_FAILED, so just drop through and
                                # it will be handled on the next pass below
                                pass
                            elif r := RE_FAILED.search(l):
                                if r.group(1) in toignore:
                                    result = TestResult.FAILIGNORE
                                else:
                                    result = TestResult.FAIL
                                testcases.append(
                                    SingleTestFinding(r.group(1), result, r.group(2), 0))
                                if r.group(2) == 'torture':
                                    meta['testmode'] = 'torture'
                            elif r := RE_IGNORED.search(l):
                                testcases.append(
                                    SingleTestFinding(r.group(1), TestResult.SKIP, r.group(2), 0))
                            elif r := RE_ABORTED.search(l):
                                # We have no RE_TESTSTART here to attach this to a specific test
                                # number, so we can't do anything but ignore it
                                pass
                            elif r := RE_TESTRESULTSHORT.search(l):
                                assert r.group(2) == 'OK'  # I think this is true
                                duration = int(float(r.group(3)) * 1000000)
                                if duration < 0:
                                    duration = 0  # bug in the test harness
                                testno = str(int(r.group(1)))
                                testcases.append(
                                    SingleTestFinding(testno, TestResult.PASS, '', duration))
                            elif r := RE_TESTFAILEDSHORT.search(l):
                                if r.group(1) in toignore:
                                    result = TestResult.FAILIGNORE
                                else:
                                    result = TestResult.FAIL
                                testno = str(int(r.group(1)))
                                testcases.append(SingleTestFinding(testno, result, '', 0))
                            elif r := RE_TOTALTIME.search(l):
                                meta['runtestsduration'] = str(int(r.group(1)) * 1000000)
                            elif r := RE_OKSUMMARY.search(l):
                                # This may be overwritten by the following failure line. Tests
                                # can be considered to be successful even with a failing test,
                                # since a test result can be marked as ignored.
                                meta['testresult'] = 'success'
                            elif r := RE_FAILSUMMARY.search(l):
                                # This one will appear as well as the previous line, but this line
                                # will prevail
                                meta['testresult'] = 'failure'
                            elif r := RE_TOIGNORE.search(l):
                                toignore.add(r.group(1))
                            elif r := RE_TESTCURLENDDATE.search(l):
                                # Replace "UTC" with the numeric time zone, which strptime can
                                # deal with
                                datestr = r.group(1).replace(' UTC', '+0000')
                                timestamp = datetime.datetime.strptime(datestr,
                                                                       '%a %b %d %H:%M:%S %Y%z')
                                meta['runfinishtime'] = int(timestamp.timestamp())
                            check_found_result(testcases)

        elif RE_TESTCURLCOMMITSTART.search(l):
            meta['executor'] = 'testcurl'
            if not (l := f.readline()):
                break
            # TODO: it appears that this first displayed commit isn't necessarily the one
            # being used, since some logs show this being from a bagder/* branch instead.
            # Not sure what causes this, unless it's a weird way that the daily build has
            # been set up. It is likely related to buildbot being set up to send PR build
            # results to the daily build server, not just pushes to master.
            if r := RE_TESTCURLCOMMIT.search(l):
                meta['commit'] = r.group('shash') if r.group('shash') else r.group('lhash')
        elif r := RE_TESTCURLDAILY .search(l):
            meta['executor'] = 'testcurl'
            meta['dailybuild'] = r.group(2)
        elif r := RE_TESTCURLNAME.search(l):
            meta['ciname'] = r.group(1)
        elif r := RE_TESTCURLDESC.search(l):
            meta['cijob'] = r.group(1)
        elif r := RE_TESTCURLDATE.search(l):
            # Replace "UTC" with the numeric time zone, which strptime can deal with
            datestr = r.group(1).replace(' UTC', '+0000')
            timestamp = datetime.datetime.strptime(datestr, '%a %b %d %H:%M:%S %Y%z')
            meta['runstarttime'] = int(timestamp.timestamp())
        elif r := RE_TESTCURLVER.search(l):
            meta['executorver'] = r.group(1)
        elif r := RE_TESTCURLBUILDCODE.search(l):
            # buildcode is a hash of testcurl lines that make up a unique code for the
            # source of this log. It is identical to the buildcode used internally on the
            # page https://curl.se/dev/builds.html
            if r.group(1) not in TESTCURLBUILDCODEIGNORED:
                current_code = int(meta.get('buildcode', 0))
                # Use ISO 8859/1 to avoid any kind of encoding error; it hashes just as well
                # as anything else
                meta['buildcode'] = zlib.crc32(l.strip().encode('ISO-8859-1'), current_code)
        elif r := RE_RUNTESTS.search(l):
            # This may be overwritten later by RE_ARGS
            meta['runtestsopts'] = r.group(1)
        elif r := RE_COMPILERAC.search(l):
            meta['compiler'] = r.group(1)
            meta['compilerversioncode'] = r.group(2)
            if r.group(3):
                meta['compilerversion'] = r.group(3)
        elif r := RE_COMPILERCMAKE.search(l):
            meta['compiler'] = r.group(1)
            meta['compilerversion'] = r.group(2)
        elif r := RE_USINGCMAKE.search(l):
            # This could be overwritten by a more specific version below
            meta['buildsystem'] = 'cmake'
        elif r := RE_USINGCMAKEMSBUILD.search(l):
            meta['buildsystem'] = 'cmake/msbuild'
        elif (r := RE_USINGCMAKEMAKE.search(l)) or (r := RE_USINGCMAKERUNMAKE.search(l)):
            meta['buildsystem'] = 'cmake/make'
        elif r := RE_USINGCMAKENINJA.search(l):
            meta['buildsystem'] = 'cmake/ninja'
        elif r := RE_USINGAUTOMAKE.search(l):
            meta['buildsystem'] = 'automake'
        elif r := RE_COMPILERPATHAC.search(l):
            meta['compilerpath'] = r.group(1)

    # Log major problems in parsing
    if 'testingver' not in meta:
        logging.debug('The file does not appear to be a curl test log')

    if not testcases:
        logging.debug('No curl tests could be found in the file')

    # Look for duplicate tests in the list
    alltests = set()
    for test in testcases:
        if test.name in alltests:
            # If this happens, then the parser above may need to be fixed so that each test
            # result is extracted a single time.
            # It might simply be that --repeat=N was used to run tests multiple times.
            logging.info(f'Tests appear more than once ({test.name} is the first); '
                         'Was the test run multiple times? Is there a parser problem?')
            break
        alltests.add(test.name)

    return meta, testcases

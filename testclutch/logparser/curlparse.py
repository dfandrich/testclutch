"""Parses curl test log files

"""

import datetime
import logging
import re
import zlib
from typing import Set, TextIO  # noqa: F401

from testclutch.logdef import ParsedLog, SingleTestFinding, TestCases, TestMeta, TestMetaStr  # noqa: F401
from testclutch.testcasedef import TestResult


# NOTE: if lines are added below that match spaces at the start of a line,
# update ingest/curlauto.py at the same time

# Early headers
RE_RUNTESTS = re.compile(r'perl.*/runtests\.pl (.*)$')
# If a log is truncated, this line won't be found; use a different one (that may not be as reliable)
# RE_USINGAUTOMAKE = re.compile(r'make +all-am')
RE_USINGAUTOMAKE = re.compile(r'^Making all in ')
# It's easier to figure out the compiler path on a libtool invocation, so restrict checking to that
RE_COMPILERPATHAC = re.compile(r'''libtool .*--mode=compile (\S+) ''')

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
RE_FEATURES = re.compile(r'^\* Features: (.+)$')
RE_VALGRIND = re.compile(r'^\* Env:.*\bValgrind\b')
RE_EVENT = re.compile(r'^\* Env:.*\bevent-based\b')
RE_OS = re.compile(r'^\* OS: (\S+)')
RE_JOBS = re.compile(r'^\* Jobs: (\d+)')
RE_SYSTEM = re.compile(r'^\* System: (\S+ \S* \S+.*)$')
RE_SEED = re.compile(r'^\* Seed: (\d+)')

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
RE_SKIPAFTERSTART = re.compile(r'(^(CMD |RUN: |Warning: |postcheck |curl returned |Killed|'
                               r' (\d+) functions to make fail)|'
                               r'functions found, but only fail|received SIGINT, exiting)|'
                               r'(^\s?$)|( log/(\d+/)?std)|(^\S+ returned .* expecting (\d)+$)')
RE_ABORTED = re.compile(r'Aborting tests$')
# Should be just {11} after 2023-06-21
RE_TESTRESULTOK = re.compile(r'^.{10,11} OK \(.*, took (-?\d+\.\d+)s')
RE_TORTUREOK = re.compile(r'^torture OK$')
RE_TORTUREFAILED = re.compile(r'MEMORY FAILURE$')
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
RE_TESTCURLNAME = re.compile(r'testcurl: NAME = (.*)$')
RE_TESTCURLDESC = re.compile(r'testcurl: DESC = (.*)$')
RE_TESTCURLBUILDCODE = re.compile(r'testcurl: (\w+) = ')
TESTCURLBUILDCODEIGNORED = frozenset(('NOTES', 'version', 'date', 'timestamp'))
# TODO: lots more testcurl headers that could be added here

# autoconf target triplet (sometimes quadruplet)
RE_TARGETTRIPLET = re.compile(r'([\w.]+)-([\w.]+)-([-\w.]+)')

# Match a valid year since Linux was created, also 1970 in case of time issue
LINUX_YEAR_RE = re.compile(r'^(20\d\d)|(199\d)|(1970)$')


def escs(s: str) -> str:
    """Escape non-ascii characters in a string

    This makes it safer to display by avoiding invalid UTF-8 and ANSI escape sequences.
    """
    return s.encode('utf-8').decode('us-ascii', 'backslashreplace')


def strip0(n: str) -> str:
    """Strip leading zeros in a string integer"""
    return str(int(n))


def check_found_result(testcases: TestCases):
    """Check if a missing test result was found

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


def parse_uname(uname: str) -> TestMetaStr:
    "Parse the output of 'uname -a' from many OSes for relevant data"
    meta = {}

    # This one treats multiple spaces as one separator (needed on Linux, NetBSD
    # and Darwin because they can have an extra space before a date)
    sysparts = uname.split()
    # This one treats multiple spaces as separators of empty items (needed on
    # FreeBSD because its hostname can be empty)
    syspartsblanks = uname.split(sep=' ')

    meta['systemos'] = syspartsblanks[0]
    # hostname can be blank
    if syspartsblanks[1]:
        meta['systemhost'] = syspartsblanks[1]
    meta['systemosver'] = syspartsblanks[2]

    # We can get more info on some OSes
    if meta['systemos'] == 'Linux' and len(syspartsblanks) >= 12:
        for i in range(9, len(syspartsblanks) - 2):
            if LINUX_YEAR_RE.match(syspartsblanks[i]):
                # arch is found immediately after the kernel build year
                meta['arch'] = syspartsblanks[i + 1]
                break
    elif meta['systemos'] == 'Darwin' and len(sysparts) == 15:
        # macOS
        meta['arch'] = sysparts[14]
    elif meta['systemos'] == 'FreeBSD' and len(syspartsblanks) == 8:
        meta['arch'] = syspartsblanks[7]
    elif meta['systemos'] == 'FreeBSD' and len(sysparts) == 8:
        # one uname spotted in the wild had an extra space before the arch
        meta['arch'] = sysparts[7]
    elif meta['systemos'] == 'FreeBSD' and len(syspartsblanks) == 15:  # starting 14.0
        meta['arch'] = syspartsblanks[14]
    elif meta['systemos'] == 'FreeBSD' and len(sysparts) == 15:  # starting 14.0
        # one uname spotted in the wild had four extra spaces after the year
        meta['arch'] = sysparts[14]
    elif meta['systemos'] == 'NetBSD' and len(sysparts) == 15:
        meta['arch'] = sysparts[14]
    elif meta['systemos'] == 'NetBSD' and len(sysparts) == 14 and 'systemhost' not in meta:
        # If the host field is blank, it shifts all the other parts down
        # one. The other systems use syspartsblank to avoid this problem,
        # but NetBSD embeds a date in its uname -a which can likely
        # contain an extra space which would cause THAT workaround to
        # fail.
        meta['arch'] = sysparts[13]
    elif meta['systemos'] == 'OpenBSD' and len(syspartsblanks) == 5:
        meta['arch'] = syspartsblanks[4]
    elif meta['systemos'] == 'SunOS' and len(syspartsblanks) in (8, 7):  # Solaris, OmniOS
        meta['arch'] = syspartsblanks[5]
    elif (meta['systemos'].startswith('MSYS_NT')
          or meta['systemos'].startswith('MINGW32_NT')
          or meta['systemos'].startswith('MINGW64_NT')
          or meta['systemos'].startswith('CYGWIN_NT')) and len(sysparts) == 8:
        meta['arch'] = sysparts[6]
    elif (meta['systemos'].startswith('MSYS_NT')
          or meta['systemos'].startswith('MINGW32_NT')
          or meta['systemos'].startswith('MINGW64_NT')
          or meta['systemos'].startswith('CYGWIN_NT')) and len(sysparts) == 7:
        # This version is missing the time zone
        meta['arch'] = sysparts[5]
    elif meta['systemos'] == 'AIX' and len(sysparts) == 5:
        # systemosver as set above is just the minor release number
        meta['systemosver'] = f'{sysparts[3]}.{sysparts[2]}'
    elif meta['systemos'] == 'Haiku' and len(syspartsblanks) == 11:
        meta['arch'] = syspartsblanks[9]
        # TODO: OS revision is in syspartsblanks[3], which perhaps should be appended to
        # syspartsblanks[2] and go into meta['systemosver']. Take a look at how it presents
        # itself once it comes out of beta.
    elif meta['systemos'] == 'Minix' and len(syspartsblanks) == 7:
        meta['arch'] = syspartsblanks[6]
    else:
        logging.warning('Unexpected uname line: %s', escs(uname))

    return meta


def parse_log_file(f: TextIO) -> ParsedLog:  # noqa: C901
    """Parses curl's runtests.pl test log output.

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    meta = {}         # type: TestMeta
    testcases = []    # type: TestCases
    toignore = set()  # type: Set[str]
    got_first = False
    while l := f.readline():
        if not got_first:
            logging.debug("First log line: %s", escs(l))
            got_first = True
        if RE_START.search(l):
            logging.debug("Found the start of a curl test log")
            meta['testformat'] = 'curl'
            meta['testresult'] = 'truncated'  # will be overwritten if the real end is found
            meta['testmode'] = 'normal'       # will be overwritten if another mode is used
            meta['withvalgrind'] = 'no'       # will be overwritten if Valgrind is enabled
            meta['withevent'] = 'no'          # will be overwritten if event-based is enabled
            # ********* System characteristics ********
            if not (l := f.readline()):
                break
            l = l.rstrip()
            if r := RE_CURLVER.search(l):
                meta['testingver'] = r.group(1)
                meta['targettriplet'] = r.group(2)
                if rr := RE_TARGETTRIPLET.search(r.group(2)):
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
                    if r := RE_HOST.search(l):
                        meta['host'] = r.group(1)
                    elif r := RE_FEATURES.search(l):
                        meta['features'] = r.group(1)
                    elif r := RE_OS.search(l):
                        meta['os'] = r.group(1)
                    elif r := RE_VALGRIND.search(l):
                        meta['withvalgrind'] = 'yes'
                    elif r := RE_EVENT.search(l):
                        meta['withevent'] = 'yes'
                    elif r := RE_JOBS.search(l):
                        meta['paralleljobs'] = r.group(1)
                    elif r := RE_SEED.search(l):
                        meta['randomseed'] = r.group(1)
                    elif r := RE_SYSTEM.search(l):
                        unamemeta = parse_uname(r.group(1))
                        meta = {**meta, **unamemeta}

                    elif RE_STARTRESULTS.search(l):
                        # *****************************************
                        while l := f.readline():
                            l = l.rstrip()
                            if r := RE_SKIPPED.search(l):
                                testcases.append(SingleTestFinding(strip0(r.group(1)), TestResult.SKIP,
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
                                    testcases.append(SingleTestFinding(
                                        testno, TestResult.PASS, "", duration))
                                elif rr := RE_TORTUREOK.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(SingleTestFinding(
                                        testno, TestResult.PASS, "", 0))
                                    meta['testmode'] = 'torture'
                                elif rr := RE_FAILED.search(l):
                                    if rr.group(1) in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(SingleTestFinding(
                                        rr.group(1), result, rr.group(2), 0))
                                elif rr := RE_IGNORED.search(l):
                                    testcases.append(SingleTestFinding(
                                        rr.group(1), TestResult.SKIP, rr.group(2), 0))
                                elif rr := RE_EXITFAILED.search(l):
                                    testno = strip0(r.group(1))
                                    if testno in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(SingleTestFinding(
                                        testno, result, rr.group(1), 0))
                                elif rr := RE_ABORTED.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(SingleTestFinding(
                                        testno, TestResult.ABORT, rr.group(0), 0))
                                elif rr := RE_TORTUREFAILED.search(l):
                                    # The real error line is coming up...just ignore this and wait
                                    meta['testmode'] = 'torture'
                                elif rr := RE_VALGRINDFAILED.search(l):
                                    testno = strip0(r.group(1))
                                    if testno in toignore:
                                        result = TestResult.FAILIGNORE
                                    else:
                                        result = TestResult.FAIL
                                    testcases.append(SingleTestFinding(
                                        testno, result, rr.group(1), 0))
                                elif rr := RE_TORTURESKIPPED.search(l):
                                    testno = strip0(r.group(1))
                                    testcases.append(SingleTestFinding(
                                        testno, TestResult.SKIP, r.group(1), 0))
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
                                testcases.append(SingleTestFinding(
                                    r.group(1), result, r.group(2), 0))
                            elif r := RE_IGNORED.search(l):
                                testcases.append(SingleTestFinding(
                                    r.group(1), TestResult.SKIP, r.group(2), 0))
                            elif r := RE_ABORTED.search(l):
                                # We have no RE_TESTSTART here to attach this to a specific test
                                # number, so we can't do anything but ignore it
                                pass
                            elif r := RE_TESTRESULTSHORT.search(l):
                                assert r.group(2) == "OK"  # I think this is true
                                duration = int(float(r.group(3)) * 1000000)
                                if duration < 0:
                                    duration = 0  # bug in the test harness
                                testno = str(int(r.group(1)))
                                testcases.append(SingleTestFinding(
                                    testno, TestResult.PASS, "", duration))
                            elif r := RE_TESTFAILEDSHORT.search(l):
                                if r.group(1) in toignore:
                                    result = TestResult.FAILIGNORE
                                else:
                                    result = TestResult.FAIL
                                testno = str(int(r.group(1)))
                                testcases.append(SingleTestFinding(testno, result, "", 0))
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
                            check_found_result(testcases)

        elif RE_TESTCURLCOMMITSTART.search(l):
            meta['executor'] = 'testcurl'
            if not (l := f.readline()):
                break
            # TODO: it appears that this first displayed commit isn't necessarily the one
            # being used, since some logs show this being from a bagder/* branch instead.
            # Not sure what causes this, unless it's a weird way that the daily build has
            # been set up.
            if r := RE_TESTCURLCOMMIT.search(l):
                meta['commit'] = r.group('shash') if r.group('shash') else r.group('lhash')
        elif r := RE_TESTCURLDAILY .search(l):
            meta['executor'] = 'testcurl'
            meta['dailybuild'] = r.group(2)
        elif r := RE_TESTCURLNAME.search(l):
            meta['ciname'] = r.group(1)
        elif r := RE_TESTCURLDESC.search(l):
            meta['cijob'] = r.group(1)
        elif r := RE_TESTCURLDATE .search(l):
            # Replace "UTC" with the numeric time zone, which strptime can deal with
            datestr = r.group(1).replace(' UTC', '+0000')
            timestamp = datetime.datetime.strptime(datestr, "%a %b %d %H:%M:%S %Y%z")
            meta['runstarttime'] = int(timestamp.timestamp())
        elif r := RE_TESTCURLBUILDCODE.search(l):
            # buildcode is a hash of testcurl lines that make up a unique code for the
            # source of this log. It is identical to the buildcode used internally on the
            # page https://curl.se/dev/builds.html
            if r.group(1) not in TESTCURLBUILDCODEIGNORED:
                current_code = meta['buildcode'] if 'buildcode' in meta else 0
                # Use ISO 8859/1 to avoid any kind of encoding error; it hashes just as well
                # as anything else
                meta['buildcode'] = zlib.crc32(l.strip().encode('ISO-8859-1'), current_code)
        elif r := RE_RUNTESTS.search(l):
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
        elif r := RE_USINGCMAKEMAKE.search(l):
            meta['buildsystem'] = 'cmake/make'
        elif r := RE_USINGCMAKERUNMAKE.search(l):
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

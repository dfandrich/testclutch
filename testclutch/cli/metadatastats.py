"""Metadata statistics analysis
"""

import argparse
import contextlib
import datetime
import itertools
import logging
import math
import re
import textwrap
from dataclasses import dataclass
from html import escape
from typing import Callable, Iterable, List, Sequence, Tuple, Union

import testclutch
from testclutch import analysis
from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.logdef import TestMetaStr
from testclutch.testcasedef import TestResult


# Returns all unique name,value pairs since the given time
NAME_VALUES_SQL = r'SELECT name, value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? GROUP BY name, value;'

# Returns a count of the number of test runs since the given time
TEST_RUNS_COUNT_SQL = r'SELECT COUNT(1) FROM testruns WHERE time >= ? AND repo = ?;'

# Count of all test results by test and format
TEST_RESULTS_COUNT_BY_TEST_SQL = r'SELECT testid,result,COUNT(1) FROM testruns INNER JOIN testresults ON testruns.id = testresults.id WHERE time >= ? AND repo = ? GROUP BY testid, result;'

# Subquery to select all recent test run IDs for a project
RECENT_IDS_SQL = r'''SELECT id FROM testruns WHERE time >= ? AND repo = ?'''

# Returns a count of each kind of test result since the given time
TEST_RESULTS_COUNT_SQL = r'SELECT result, COUNT(1) FROM testruns INNER JOIN testresults ON testruns.id = testresults.id WHERE time >= ? AND repo = ? GROUP BY result;'
# Alternate formulation for memory efficiency testing
#  TEST_RESULTS_COUNT_SQL = r'SELECT result, COUNT(1) FROM testresults WHERE testresults.id in (SELECT id from testruns WHERE time >= ? AND repo = ?) GROUP BY result'

# Returns the sum of a time spent on each test since the given time
TEST_RUN_TIME_SQL = r'SELECT SUM(runtime) FROM testruns INNER JOIN testresults ON testruns.id = testresults.id WHERE time >= ? AND repo = ?;'

# Returns all metadata values for a given name since the given time
ONE_NAME_VALUES_SQL = r'SELECT DISTINCT value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ?;'

# Returns all unique job names run since the given time
JOB_NAMES_SQL = r"SELECT DISTINCT origin, account, value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND name = 'uniquejobname' AND repo = ?;"

# Returns largest & smallest values for a given name since the given time
MAX_MIN_VALUE_SQL = r'SELECT MAX(CAST(value AS INT)),MIN(CAST(value AS INT)) FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ?;'

# Returns largest & smallest values for a given name since the given time for runs matching a
# secondary metadata value
MAX_MIN_VALUE_SECONDARY_SQL = r'SELECT MAX(CAST(value AS INT)),MIN(CAST(value AS INT)) FROM testrunmeta WHERE id IN (SELECT testruns.id FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ? AND value = ?) AND name = ?;'

# Return count of matching name/value pairs since the given time
COUNT_NAME_VALUE_SQL = r'SELECT COUNT(1) FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ? AND value = ?;'

# Job with highest/lowest/avg number of tests run by test format, ignoring SKIP tests (result==3)
# and only counting distinct test IDs.
# {function} must be defined by the caller
FUNCTION_TESTS_BY_TYPE_SQL = f'''SELECT testformat, {{function}}(numtests) FROM (
    SELECT testresults.id, value AS testformat, COUNT(DISTINCT testresults.testid) AS numtests FROM testresults INNER JOIN testrunmeta ON testresults.id = testrunmeta.id WHERE testresults.id IN
        ({RECENT_IDS_SQL})
    AND name = 'testformat' AND testresults.result <> 3 GROUP BY testresults.id, testformat
    )
GROUP BY testformat ORDER BY testformat;'''

# Job with highest number of tests run by test format
MAX_TESTS_BY_TYPE_SQL = FUNCTION_TESTS_BY_TYPE_SQL.format(function='MAX')

# Average number of tests run by test format
AVG_TESTS_BY_TYPE_SQL = FUNCTION_TESTS_BY_TYPE_SQL.format(function='AVG')

# Retrieve a few metadata values for tests matching a testid and result
MOST_RECENT_TEST_STATUS_META_SQL = r'SELECT testrunmeta.value FROM testresults INNER JOIN testruns ON testruns.id = testresults.id INNER JOIN testrunmeta ON testrunmeta.id = testresults.id WHERE time >= ? AND repo = ? AND testid = ? AND result = ? AND testrunmeta.name = ? ORDER BY testruns.time DESC limit ?;'

IGNORED_NAMES = frozenset(('host', 'jobduration', 'jobfinishtime', 'jobid', 'jobstarttime',
                           'runduration', 'runfinishtime', 'runid', 'runprocesstime',
                           'runstarttime', 'runtestsduration', 'runtriggertime', 'runurl',
                           'stepfinishtime', 'steprunduration', 'stepstarttime', 'systemhost',
                           'url', 'workflowid'))

# Characters that are allowed in an HTML ID, except for " which is handled specially
ID_TOKEN_RE = re.compile(r'[^-A-Za-z0-9_:."]')

# strftime() format string including time zone
TIMEZ_FMT = '%a, %d %b %Y %H:%M:%S %z'

# Characters to use for 'enabled' and 'disabled' in the features matrix
YES = '✓'
NO = '⨯'
MAYBE = '?'


def _try_integer(val: str) -> Union[int, str]:
    """Try to convert the value to a low-value 0-prefixed integer in string form

    Returns raw string if it cannot. Use as a sort key function to sort numeric test names by
    numeric value and string test names alphabetically, allowing sorting mixed integers and strings.
    A more general alternative would be natsort.natsorted()
    """
    with contextlib.suppress(ValueError):
        return '%09d' % int(val)
    return val


class MetadataStats:
    def __init__(self, ds: db.Datastore, repo: str, since: datetime.datetime):
        assert ds.db  # satisfy pytype that this isn't None
        self.ds = ds
        self.repo = repo
        self.since = since

    def get_name_values(self) -> List[Tuple[str, str]]:
        nvstats = self.ds.db.cursor()
        oldest = int(self.since.timestamp())
        nvstats.execute(NAME_VALUES_SQL, (oldest, self.repo))
        return nvstats.fetchall()


class MetadataAdjuster:
    "Adjust metadata values by splitting them and/or transforming them with regular expressions"
    def __init__(self, splits: dict[str, str], transforms: dict[str, list[tuple[str, str]]]):
        # Compile regular expressions so they're ready for use
        self.splits = {k: re.compile(v) for k, v in splits.items()}
        self.transforms = {k: [(re.compile(pat), repl) for pat, repl in l]
                           for k, l in transforms.items()}

    def split(self, metaname: str, value: str) -> list[str]:
        """Transform a metadata value into multiple by splitting it on a regular expression

        Any blank values are removed.
        """
        if metaname in self.splits:
            splitvalues = self.splits[metaname].split(value)
        else:
            splitvalues = [value]
        return [value for value in splitvalues if value]

    def transform(self, metaname: str, value: str) -> str:
        """Transform a metadata value by passing it through one or more regular expressions

        The value may end up empty, depending on the transformation.
        """
        if metaname in self.transforms:
            # Tweak the value
            for pattern, repl in self.transforms[metaname]:
                value = pattern.sub(repl, value)
        return value

    def adjust(self, metaname: str, value: str) -> list[str]:
        """Adjust metadata value by performing any splitting and transforming that was requested

        Any blank entries are removed.

        Returns:
            list of values, which may contain zero or more entries depending on the transformations
        """
        values = (self.transform(metaname, v) for v in self.split(metaname, value))
        return [v for v in values if v]


class FeatureMatrix:
    def __init__(self, ds: db.Datastore, repo: str, since: datetime.datetime):
        assert ds.db  # satisfy pytype that this isn't None
        self.ds = ds
        self.repo = repo
        self.since = since
        self.from_time = int(since.timestamp())
        self.analyzer = analysis.ResultsOverTimeByUniqueJob(ds)
        self.all_meta = []  # type: list[TestMetaStr]

    def all_unique_jobs(self) -> list[str]:
        return self.analyzer.all_unique_jobs(self.repo, self.from_time)

    def get_uniquejob_meta(self, globaluniquejob: str) -> TestMetaStr:
        to_time = int(datetime.datetime.now().timestamp())
        # Using disabled_job_hours instead of analysis_hours because we want only the most current
        # job run, and anything older than that is irrelevant
        logging.info(f'Getting runs since {self.since.ctime()} '
                     f'of unique job {globaluniquejob}')
        self.analyzer.load_unique_job(globaluniquejob, self.from_time, to_time)
        if not self.analyzer.all_jobs_status:
            logging.info('Nothing to analyze for %s', globaluniquejob)
            return {}
        last_job_status = self.analyzer.all_jobs_status[0]
        testid = last_job_status.testid
        return self.ds.collect_meta(testid)

    def make_job_title(self, job: TestMetaStr) -> str:
        return self.analyzer.make_job_title(job)

    def load_all_meta(self):
        "Read metadata for all jobs"
        self.all_meta = []
        for job in self.all_unique_jobs():
            meta = self.get_uniquejob_meta(job)
            assert meta, "Each job must have metadata; edge condition on expiry?"
            self.all_meta.append(meta)
        logging.info(f'Loaded {len(self.all_meta)} unique jobs')

    def build_features(self, metas: Sequence[str], adjuster: MetadataAdjuster
                       ) -> list[tuple[str, str, Union[str, int]]]:
        """Build a list of convolved features available in the tests

        load_all_meta() must have been called first.

        Returns:
            list of tuples with feature title, metadata name and metadata value
        """
        features = {}  # type: dict[str, set[str]]
        for metaname in metas:
            for meta in self.all_meta:
                if metaname in meta:
                    values = adjuster.adjust(metaname, meta[metaname])
                    feature = features.setdefault(metaname, set())
                    feature.update(values)

        # Remove any metadata fields that were requested but not actually found
        foundmetas = [name for name in metas if name in features]
        return [(f'{name}: {value}', name, value) for name in foundmetas
                for value in sorted(features[name], key=str.casefold)]


def idify(s: str) -> str:
    """Make the given string valid as a double-quoted HTML id token

    Invalid characters are replaced with underscores, double quotes are replaced with an HTML entity
    and the whole string is prefixed with "test" to guarantee the first character is a letter.
    """
    filtered = ID_TOKEN_RE.sub('_', s)
    return 'test' + re.sub('"', '&quot;', filtered)


class TestRunStats:
    def __init__(self, ds: db.Datastore, repo: str, since: datetime.datetime):
        assert ds.db  # satisfy pytype that this isn't None
        self.ds = ds
        self.repo = repo
        self.since = since
        self.oldest = int(since.timestamp())

    def get_test_run_count(self) -> int:
        count = self.ds.db.cursor()
        count.execute(TEST_RUNS_COUNT_SQL, (self.oldest, self.repo))
        return count.fetchone()[0]

    def get_test_results_count(self) -> List[Tuple[int, int]]:
        count = self.ds.db.cursor()
        count.execute(TEST_RESULTS_COUNT_SQL, (self.oldest, self.repo))
        return count.fetchall()

    def get_test_run_time(self) -> int:
        count = self.ds.db.cursor()
        count.execute(TEST_RUN_TIME_SQL, (self.oldest, self.repo))
        return count.fetchone()[0]

    def get_job_names(self) -> List[str]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(JOB_NAMES_SQL, (self.oldest, self.repo))
        return nvalues.fetchall()

    def get_values_for_name(self, name: str) -> List[str]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(ONE_NAME_VALUES_SQL, (self.oldest, self.repo, name))
        return nvalues.fetchall()

    def get_max_min_for_name(self, name: str) -> Tuple[int, int]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(MAX_MIN_VALUE_SQL, (self.oldest, self.repo, name))
        return tuple(int(n) for n in nvalues.fetchone())

    def get_max_min_for_name_secondary(self, name: str, secondary: str, value: str,
                                       ) -> Tuple[int, int]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(MAX_MIN_VALUE_SECONDARY_SQL,
                        (self.oldest, self.repo, secondary, value, name))
        return tuple(int(n) for n in nvalues.fetchone())

    def get_count_for_name_value(self, name: str, value: str) -> int:
        nvalues = self.ds.db.cursor()
        nvalues.execute(COUNT_NAME_VALUE_SQL, (self.oldest, self.repo, name, value))
        return nvalues.fetchone()[0]

    def get_max_tests_by_type(self) -> List[Tuple[str, int]]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(MAX_TESTS_BY_TYPE_SQL, (self.oldest, self.repo))
        return nvalues.fetchall()

    def get_avg_tests_by_type(self) -> List[Tuple[str, int]]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(AVG_TESTS_BY_TYPE_SQL, (self.oldest, self.repo))
        return nvalues.fetchall()

    def get_test_results_count_by_test(self) -> List[Tuple[str, int, int]]:
        nvalues = self.ds.db.cursor()
        nvalues.execute(TEST_RESULTS_COUNT_BY_TEST_SQL, (self.oldest, self.repo))
        return nvalues.fetchall()

    def get_test_results_url(self, testname: str, status: int) -> List[Tuple[str]]:
        values = self.ds.db.cursor()
        values.execute(MOST_RECENT_TEST_STATUS_META_SQL,
                       (self.oldest, self.repo, testname, status, 'url',
                        int(config.get('test_results_count_num_recent_urls'))))
        return values.fetchall()


def output_nv_summary_text(nv: Iterable, full_list: bool):
    for n, v in itertools.groupby(nv, key=lambda x: x[0]):
        print(n)
        if not full_list and n in IGNORED_NAMES:
            print('  (redacted)')
        else:
            for val in v:
                print('  ', val[1])


def output_nv_summary_html(nv: Iterable, repo: str, hours: int, full_list: bool):
    now = datetime.datetime.now(datetime.timezone.utc)
    print(textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html><head><title>Metadata values</title>
        <meta name="generator" content="Test Clutch {testclutch.__version__}">
        </head>
        <body>
        <h1>Metadata for test runs on {escape(repo)}</h1>
        Report generated {escape(now.strftime(TIMEZ_FMT))}
        covering runs over the past {hours / 24:.0f} days.
        <p>
        Expand each name to see all its values among recent test runs.
        Note that not all test runs expose all metadata.
        <br>
        """))
    for n, v in itertools.groupby(nv, key=lambda x: x[0]):
        print(f'<details><summary id="{escape(n)}">{escape(n)}</summary><ul>')
        if not full_list and n in IGNORED_NAMES:
            print('<li>(redacted)</li>')
        else:
            for val in v:
                print(f'<li>{escape(val[1])}</li>')
        print('</ul></details>')
    print('</body></html>')


def output_test_run_stats_text(trstats: TestRunStats):
    def print_text(label, content='', indent: int = 0):
        if indent:
            print('  ', end='')
        print(label, content)
    output_test_run_stats(trstats, print_text)


def output_test_run_stats_html(trstats: TestRunStats):
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - trstats.since).days
    print(textwrap.dedent(f"""
        <!DOCTYPE html>
        <html><head><title>Test run statistics</title>
        <meta name="generator" content="Test Clutch {testclutch.__version__}">
        </head>
        <body>
        <h1>Test run statistics for test runs on {escape(trstats.repo)}</h1>
        Report generated {escape(now.strftime(TIMEZ_FMT))}
        covering runs over the past {days:.0f} days.
        <p>
        """))
    current_indent = 0

    def print_html(label, content='', indent: int = 0):
        nonlocal current_indent
        if indent and not current_indent:
            print('<ul>')
        if not indent and current_indent:
            print('</ul>')
        if indent:
            print('<li>', end='')
        elif not current_indent:
            print('<br>', end='')
        current_indent = indent
        print(f'{label} {content}')
        if current_indent:
            print('</li>', end='')

    output_test_run_stats(trstats, print_html)
    print('</body></html>')


def num_precision(n: float, p: int) -> int:
    """Returns the number of digits of precision

    Given the number of decimal points to print p of the number n, return the number of digits
    for the floating point format operator. The intent is to display very small numbers without
    scientific notation, yet showing the desired amount of precision.
    """
    return max(int(-math.log10(n) + p), 0) if n != 0 else p


def output_test_run_stats(trstats: TestRunStats, print_func: Callable):
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - trstats.since).total_seconds() / (24 * 3600)  # to handle fractional days
    print_func('Days of stats:', f'{days: 0.0f}')

    # Find the earliest and latest logs in the DB. Since no single one of these metadata values is
    # mandatory, check them all and take the extremes. This also means that we'll likely be showing
    # the start time in the oldest case but the finish time of the newest case.
    # TypeError is raised if there is no value in the database for that name
    newest, oldest = 0, 32503679999  # initialize to something in case the DB is empty
    with contextlib.suppress(TypeError):
        newer, older = trstats.get_max_min_for_name('runtriggertime')
        newest = max(newest, newer)
        oldest = min(oldest, older)
    with contextlib.suppress(TypeError):
        newer, older = trstats.get_max_min_for_name('runstarttime')
        newest = max(newest, newer)
        oldest = min(oldest, older)
    with contextlib.suppress(TypeError):
        newer, older = trstats.get_max_min_for_name('runfinishtime')
        newest = max(newest, newer)
        oldest = min(oldest, older)
    print_func(
        'Most recent run: '
        f'{datetime.datetime.fromtimestamp(newest, tz=datetime.timezone.utc).strftime(TIMEZ_FMT)}')
    print_func(
        'Oldest run used: '
        f'{datetime.datetime.fromtimestamp(oldest, tz=datetime.timezone.utc).strftime(TIMEZ_FMT)}')

    total_count = trstats.get_test_run_count()
    print_func('Total test runs:', f'{total_count}')
    print_func('Runs per day:', f'{total_count / days: 0.1f}')

    results_count = trstats.get_test_results_count()
    total_tests = 0
    total_tests_run = 0
    for result, count in results_count:
        total_tests += count
        total_tests_run += count if result != TestResult.SKIP else 0
    print_func('Total tests run:', f'{total_tests_run}')
    print_func('Tests run per day:', f'{total_tests_run / days:.1f}')

    print_func('TOTAL tests considered:', f'{total_tests} (100%)')
    # This sort key makes the results appear in a more logical progression
    for status, count in sorted(results_count, key=lambda x: x[0] if x[0] else 99):
        code = TestResult(status)
        pct = count / total_tests * 100
        print_func(f'{code.name}:', f'{count} ({pct:.{num_precision(pct, 2)}f}%)', indent=1)
    # Skip these on an empty DB
    if total_count:
        truncated = trstats.get_count_for_name_value('testresult', 'truncated')
        pct = truncated / total_count * 100
        print_func('Tests runs that were aborted:', f'{truncated} ({pct:.{num_precision(pct, 3)}f}%)')

        total_run_time = trstats.get_test_run_time()
        print_func('Total time spent running tests:', f'{total_run_time / 1000000:.0f} sec.')
        print_func('Time spent running tests per day:', f'{total_run_time / 1000000 / days:.0f} sec./day '
                   f'({total_run_time / 1000000 / days / 24 / 3600:.1f} days/day)')
        print_func('Time spent running per test:', f'{total_run_time / 1000000 / total_tests_run:.3f} sec./test')
    with contextlib.suppress(TypeError):
        # "runtestsduration" isn't mandatory and TypeError will be raised if missing
        # Store these data first, then display them like the ones below, prefixed
        # by test format, for consistency
        rundurations = []
        for formattup in trstats.get_values_for_name('testformat'):
            testformat = formattup[0]
            largest, smallest = trstats.get_max_min_for_name_secondary(
                'runtestsduration', 'testformat', testformat)
            rundurations.append((testformat, smallest, largest))
        print_func('Longest test runs:')
        for testformat, smallest, largest in rundurations:
            print_func(f'{testformat}:', f'{largest / 1000000: .0f} sec.', indent=1)
        print_func('Shortest test runs:')
        for testformat, smallest, largest in rundurations:
            print_func(f'{testformat}:', f'{smallest / 1000000: .0f} sec.', indent=1)

    print_func('Most number of unique tests attempted in one run by test format:')
    for testtype, maxtests in trstats.get_max_tests_by_type():
        print_func(f'{testtype}: {maxtests}', indent=1)
    print_func('Average number of tests attempted in one run by test format:')
    for testtype, avgtests in trstats.get_avg_tests_by_type():
        print_func(f'{testtype}: {avgtests:.1f}', indent=1)
    print_func('Number of git commits tested:', len(trstats.get_values_for_name('commit')))
    print_func('Number of unique CI systems:', len(trstats.get_values_for_name('origin')))
    print_func('Number of unique build systems:', len(trstats.get_values_for_name('buildsystem')))
    print_func('Number of kinds of test formats:', len(trstats.get_values_for_name('testformat')))
    print_func('Number of kinds of test modes:', len(trstats.get_values_for_name('testmode')))
    print_func('Number of unique operating systems:', len(trstats.get_values_for_name('os')))
    print_func('Number of unique configured test jobs:', len(trstats.get_job_names()))


def output_test_results_count(trstats: TestRunStats,
                              print_func: Callable):
    print_func('Test', 'Result', 'Count', ['Examples'], title=True)

    total_counts = trstats.get_test_results_count_by_test()
    logging.info('Found %d different tests+results', len(total_counts))
    # Sort by count descending, then by increasing test number
    total_counts.sort(key=lambda x: (-x[2], _try_integer(x[0])))
    num_shown = 0
    for test, status, count in total_counts:
        if status in frozenset((TestResult.PASS, TestResult.SKIP)):
            continue
        code = TestResult(status)
        num_shown = num_shown + 1
        if num_shown < int(config.get('test_results_count_max_urls')):
            urls = trstats.get_test_results_url(test, status)
        else:
            # Getting the URLs is a slow operation, so only get them for the top few tests
            urls = []
        print_func(test, code.name, count, [x[0] for x in urls])


def output_test_results_count_text(trstats: TestRunStats):
    def print_text(test: str, code: str, count: int, urls: Sequence[str], title: bool = False):
        items = (test, code, count, urls[0] if urls else [])  # only show 1 URL in text mode
        for i in items:
            print(i, end=' ')
        print()
        if title:
            print('------' * len(items))
    output_test_results_count(trstats, print_text)


def output_test_results_count_html(trstats: TestRunStats):
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - trstats.since).days
    print(textwrap.dedent("""\
        <!DOCTYPE html>
        <html><head><title>Test failure counts</title>
        <style type="text/css">
        tr:nth-child(even) {
          background-color: #D6EEEE;
        }
        </style>
        """ + f"""
        <meta name="generator" content="Test Clutch {testclutch.__version__}">
        </head>
        <body>
        <h1>Test failure counts for test runs on {escape(trstats.repo)}</h1>
        <p>
        Report generated {escape(now.strftime(TIMEZ_FMT))}
        covering runs over the past {days:.0f} days.
        </p>
        <table>
        """))
    anchors = set()  # keep track to avoid duplicates

    def print_html(test: str, code: str, count: int, urls: Sequence[str], title: bool = False):
        """Print a row of data

        urls[0] contains the title, not a URL, when title=True
        """
        tag = 'th' if title else 'td'
        anchorshorttext = ''
        anchor2text = ''
        if not title:
            # Create a short anchor direct to this test
            anchor = idify(test)
            # Avoid making a duplicate short anchor; just rely on the unambiguous one if so
            anchorshorttext = f' id="{anchor}"' if anchor not in anchors else ''
            anchors.add(anchor)
            # Create a second, unambiguous anchor, that incorporates the return code. Actually, it
            # might not be unambiguous if two different test names are the same except for one
            # or more invalid characters (that are replaced in both cases).
            # Unfortunately in HTML id, unlike class, can only have a single id so this must be
            # applied to a different tag.
            anchor2text = f' id="{idify(f"{test}_{code}")}"'
        items = [test, code, count]
        if title:
            items.append(urls[0])
        print(f'<tr{anchor2text}>')
        for i in items:
            print(f'<{tag}{anchorshorttext}>{escape(str(i))}</{tag}>', end='')
            anchorshorttext = ''  # only the first tag should get this
        print(f'<{tag}>')
        if not title:
            for i in urls:
                print(f'<a href="{escape(str(i))}">Log</a>', end=' ')
        print(f'</{tag}></tr>')

    output_test_results_count(trstats, print_html)
    print('</table></body></html>')


def output_feature_matrix_html(fm: FeatureMatrix):
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - fm.since).days
    print(textwrap.dedent("""\
        <!DOCTYPE html>
        <html><head><title>Test Job Feature Matrix</title>
        <style type="text/css">
        body {
          background-color: white;
        }
        td {
          outline: 1px solid;
          text-align: center;
        }
        .no {
          background-color: #FFAAAA;
        }
        .yes {
          background-color: #AAFFAA;
        }
        .maybe {
          background-color: #FFCC00;
        }
        thead {
          position: sticky;
          top: 0px;
          background-color: white;
        }
        </style>
        """ + f"""
        <meta name="generator" content="Test Clutch {testclutch.__version__}">
        </head>
        <body>
        <h1>Configured Test Job Features on {escape(fm.repo)}</h1>
        <p>
        Report generated {escape(now.strftime(TIMEZ_FMT))}
        covering jobs over the past {days:.0f} days.
        </p>
        <p>
        <span class="yes">{YES}</span> job has this feature
        <br>
        <span class="no">{NO}</span> job does not have this feature
        <br>
        <span class="maybe">{MAYBE}</span> unable to tell if job has this feature
        </p>
        <p>
        The job links to the results of the latest run.
        </p>
        <table>
        """))

    fm.load_all_meta()
    adjuster = MetadataAdjuster(config.get('matrix_meta_splits'),
                                config.get('matrix_meta_transforms'))
    features = fm.build_features(config.get('matrix_meta_fields'), adjuster)

    @dataclass
    class IntCounter:
        count: int = 0

    featurecounts = [IntCounter() for _ in features]
    print('<thead><tr><th>Job</th>')
    for title, _, _ in features:
        print(f'<th>{escape(title)}</th>')
    print('</tr></thead><tbody>')

    for meta in fm.all_meta:
        if 'url' in meta:
            print(f'<tr><td><a href="{escape(meta["url"])}">{escape(fm.make_job_title(meta))}'
                  '</a></td>')
        else:
            print(f'<tr><td>{escape(fm.make_job_title(meta))}</td>')
        for (_, name, value), counter in zip(features, featurecounts):
            jobvalue = adjuster.adjust(name, meta.get(name, ''))
            match = value in set(jobvalue)
            maybe = name not in meta
            print(f'<td class="{"maybe" if maybe else "yes" if match else "no"}">'
                  f'{MAYBE if maybe else YES if match else NO}</td>')
            if match:
                counter.count += 1
        print('</tr>')

    # Print totals of each feature
    print(f'<tr><td>TOTALS: {len(fm.all_meta)}</td>')
    for counter in featurecounts:
        print(f'<td>{counter.count}</td>')

    print('</tr></tbody></table></body></html>')


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Summarize test metadata')
    argparsing.arguments_logging(parser)
    parser.add_argument(
        '--html',
        action='store_true',
        help='Output summary in HTML')
    parser.add_argument(
        '--full',
        action='store_true',
        help='List all value instead of redacting unintersting ones')
    parser.add_argument(
        '--report',
        choices=['feature_matrix', 'metadata_values', 'test_run_stats', 'test_results_count'],
        required=True,
        help='Which type of report should be generated')
    parser.add_argument(
        '--howrecent',
        type=int,
        help='Amount of history to analyze, in hours')
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    hours = args.howrecent
    if not hours:
        hours = config.get('analysis_hours')
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

    ds = db.Datastore()
    ds.connect()
    logging.info(f'Creating report "{args.report}" since {since}')

    if args.report == 'metadata_values':
        mdstats = MetadataStats(ds, config.expand('check_repo'), since)
        nv = mdstats.get_name_values()
        if args.html:
            output_nv_summary_html(nv, repo=config.expand('check_repo'),
                                   hours=hours, full_list=args.full)
        else:
            output_nv_summary_text(nv, full_list=args.full)

    elif args.report == 'test_run_stats':
        trstats = TestRunStats(ds, config.expand('check_repo'), since)
        if args.html:
            output_test_run_stats_html(trstats)
        else:
            output_test_run_stats_text(trstats)

    elif args.report == 'test_results_count':
        trstats = TestRunStats(ds, config.expand('check_repo'), since)
        if args.html:
            output_test_results_count_html(trstats)
        else:
            output_test_results_count_text(trstats)

    elif args.report == 'feature_matrix':
        # The default hours is different for this job, so set it again from scratch here
        hours = args.howrecent
        if not hours:
            hours = config.get('disabled_job_hours')
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        featurematrix = FeatureMatrix(ds, config.expand('check_repo'), since)
        if args.html:
            output_feature_matrix_html(featurematrix)
        else:
            logging.error(f'--html must be used with {args.report}')

    else:
        logging.error(f'Unknown report "{args.report}"')


if __name__ == '__main__':
    main()

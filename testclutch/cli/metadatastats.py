"""Metadata statistics analysis
"""

import argparse
import datetime
import itertools
import math
import textwrap
from html import escape
from typing import Iterable, List, Tuple

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.testcasedef import TestResult


# Returns all unique name,value pairs since the given time
NAME_VALUES_SQL = r'SELECT name, value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? GROUP BY name, value;'

# Returns a count of the number of test runs since the given time
TEST_RUNS_COUNT_SQL = r'SELECT count(1) FROM testruns WHERE time >= ? AND repo = ?;'

# Returns a count of each kind fo test result since the given time
TEST_RESULTS_COUNT_SQL = r'SELECT result, COUNT(1) FROM testruns INNER JOIN testresults ON testruns.id = testresults.id WHERE time > ? AND repo = ? GROUP BY result;'

# Returns the sum of a time spent on each test since the given time
TEST_RUN_TIME_SQL = r'SELECT SUM(runtime) FROM testruns INNER JOIN testresults ON testruns.id = testresults.id WHERE time > ? AND repo = ?;'

# Returns all metadata values for a given name since the given time
ONE_NAME_VALUES_SQL = r'SELECT DISTINCT value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ?;'

# Returns all unique job names run since the given time
JOB_NAMES_SQL = r"SELECT DISTINCT origin, account, value FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND name = 'uniquejobname' AND repo = ?;"

# Returns largest values for a given name since the given time
MAX_MIN_VALUE_SQL = r'SELECT MAX(CAST(value AS INT)),MIN(CAST(value AS INT)) FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ?;'

# Return count of matching name/value pairs since the given time
COUNT_NAME_VALUE_SQL = r'SELECT COUNT(1) FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = ? and value = ?;'

IGNORED_NAMES = frozenset(('host', 'jobduration', 'jobfinishtime', 'jobid', 'jobstarttime',
                           'runduration', 'runfinishtime', 'runid', 'runprocesstime',
                           'runstarttime', 'runtestsduration', 'runtriggertime', 'runurl',
                           'stepfinishtime', 'steprunduration', 'stepstarttime', 'systemhost',
                           'url', 'workflowid'))


class MetadataStats:
    def __init__(self, ds: db.Datastore, repo: str, since: datetime.datetime):
        self.ds = ds
        self.repo = repo
        self.since = since

    def get_name_values(self) -> List[Tuple[str, str]]:
        assert self.ds.db  # satisfy pytype that this isn't None
        nvstats = self.ds.db.cursor()
        oldest = int(self.since.timestamp())
        nvstats.execute(NAME_VALUES_SQL, (oldest, self.repo))
        return nvstats.fetchall()


class TestRunStats:
    def __init__(self, ds: db.Datastore, repo: str, since: datetime.datetime):
        self.ds = ds
        self.repo = repo
        self.since = since
        self.oldest = int(since.timestamp())

    def get_test_run_count(self) -> int:
        assert self.ds.db  # satisfy pytype that this isn't None
        count = self.ds.db.cursor()
        count.execute(TEST_RUNS_COUNT_SQL, (self.oldest, self.repo))
        return count.fetchone()[0]

    def get_test_results_count(self):
        assert self.ds.db  # satisfy pytype that this isn't None
        count = self.ds.db.cursor()
        count.execute(TEST_RESULTS_COUNT_SQL, (self.oldest, self.repo))
        return count.fetchall()

    def get_test_run_time(self) -> int:
        assert self.ds.db  # satisfy pytype that this isn't None
        count = self.ds.db.cursor()
        count.execute(TEST_RUN_TIME_SQL, (self.oldest, self.repo))
        return count.fetchone()[0]

    def get_job_names(self) -> List[str]:
        assert self.ds.db  # satisfy pytype that this isn't None
        nvalues = self.ds.db.cursor()
        nvalues.execute(JOB_NAMES_SQL, (self.oldest, self.repo))
        return nvalues.fetchall()

    def get_values_for_name(self, name: str) -> List[str]:
        assert self.ds.db  # satisfy pytype that this isn't None
        nvalues = self.ds.db.cursor()
        nvalues.execute(ONE_NAME_VALUES_SQL, (self.oldest, self.repo, name))
        return nvalues.fetchall()

    def get_max_min_for_name(self, name: str) -> Tuple[int, int]:
        assert self.ds.db  # satisfy pytype that this isn't None
        nvalues = self.ds.db.cursor()
        nvalues.execute(MAX_MIN_VALUE_SQL, (self.oldest, self.repo, name))
        return tuple(int(n) for n in nvalues.fetchone())

    def get_count_for_name_value(self, name: str, value: str) -> int:
        assert self.ds.db  # satisfy pytype that this isn't None
        nvalues = self.ds.db.cursor()
        nvalues.execute(COUNT_NAME_VALUE_SQL, (self.oldest, self.repo, name, value))
        return nvalues.fetchone()[0]


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
    print(textwrap.dedent(f"""
        <!DOCTYPE html>
        <html><head><title>Metadata values</title></head><body>
        <h1>Metadata for test runs on {escape(repo)}</h1>
        Report generated {escape(now.strftime('%a, %d %b %Y %H:%M:%S %z'))}
        covering runs over the past {hours / 24:.0f} days.
        <p>
        Expand each name to see all its values among recent test runs.
        Note that not all test runs expose all metadata.
        <br>
        """))
    for n, v in itertools.groupby(nv, key=lambda x: x[0]):
        print(f'<details><summary>{escape(n)}</summary><ul>')
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
        <html><head><title>Test run statistics</title></head><body>
        <h1>Test run statistics for test runs on {escape(trstats.repo)}</h1>
        Report generated {escape(now.strftime('%a, %d %b %Y %H:%M:%S %z'))}
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


def output_test_run_stats(trstats: TestRunStats, print_func):
    now = datetime.datetime.now(datetime.timezone.utc)
    days = (now - trstats.since).days
    print_func('Days of stats:', f'{days}')
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
    truncated = trstats.get_count_for_name_value('testresult', 'truncated')
    pct = truncated / total_count * 100
    print_func('Tests runs that were aborted:', f'{truncated} ({pct:.{num_precision(pct, 3)}f}%)')

    total_run_time = trstats.get_test_run_time()
    print_func('Total time spent running tests:', f'{total_run_time / 1000000:.0f} sec.')
    print_func('Time spent running tests per day:', f'{total_run_time / 1000000 / days:.0f} sec./day '
               f'({total_run_time / 1000000 / days / 24 / 3600:.1f} days/day)')
    print_func('Time spent running per test:', f'{total_run_time / 1000000 / total_tests_run:.3f} sec./test')
    try:
        # This name isn't mandatory and an exception will be raised if there is nothing there
        largest, smallest = trstats.get_max_min_for_name('runtestsduration')
        print_func('Longest test run:', f'{largest / 1000000: .0f} sec.')
        print_func('Shortest test run:', f'{smallest / 1000000: .0f} sec.')
    except TypeError:
        # No durations were found
        pass
    print_func('Number of git commits tested:', len(trstats.get_values_for_name('commit')))
    print_func('Number of unique CI systems:', len(trstats.get_values_for_name('origin')))
    print_func('Number of unique build systems:', len(trstats.get_values_for_name('buildsystem')))
    print_func('Number of kinds of test formats:', len(trstats.get_values_for_name('testformat')))
    print_func('Number of kinds of test modes:', len(trstats.get_values_for_name('testmode')))
    print_func('Number of unique operating systems:', len(trstats.get_values_for_name('os')))
    print_func('Number of unique configured test jobs:', len(trstats.get_job_names()))


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
        choices=['metadata_values', 'test_run_stats'],
        default='metadata_values',
        help='Which type of report should be generated')
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    hours = int(config.get('analysis_hours'))
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

    ds = db.Datastore()
    ds.connect()

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


if __name__ == '__main__':
    main()

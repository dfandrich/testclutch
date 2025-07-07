"""Find test job runs where a particular test failed or succeeded."""

import argparse
import datetime
from contextlib import nullcontext
from typing import Collection

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.testcasedef import TestResult


# Test status considered failed
FAILED = frozenset((TestResult.FAIL, TestResult.TIMEOUT))

# Test status considered succeeded
SUCCEEDED = frozenset((TestResult.PASS,))


# Return data about test runs that contain a failed test
RUNS_BY_TEST_STATUS_SQL = r'SELECT testresults.id, testruns.time, resulttext FROM testresults INNER JOIN testruns ON testruns.id = testresults.id WHERE time >= ? AND repo = ? AND testid = ? AND result IN (?, ?);'


class FindFailedRuns:
    """Find test job runs where a particular test has a specific status."""

    def __init__(self, ds: db.Datastore):
        assert ds.db  # satisfy pytype that this isn't None
        self.ds = ds

    def find_status_run(self, repo: str, since: datetime.datetime, testname: str,
                        statuses: Collection[int]) -> list[tuple[int, int, str]]:
        jobruns = self.ds.db.cursor()
        if len(statuses) < 2:
            # Duplicate a single item
            statuses = (iter(statuses).__next__(), ) * 2
        assert len(statuses) == 2  # limitation for now due to simplification of the query
        oldest = int(since.timestamp())
        jobruns.execute(RUNS_BY_TEST_STATUS_SQL,
                        (oldest, repo, testname, *statuses))
        return jobruns.fetchall()

    def show_matches(self, testmatches: list[tuple[int, int, str]]):
        # Sort by descending date
        testmatches.sort(key=lambda x: x[1], reverse=True)
        for testid, runtime, failtext in testmatches:
            meta = self.ds.collect_meta(testid)
            name = meta.get('cijob', meta['uniquejobname'])
            print('Job:', f'{meta["origin"].capitalize()}: {name}')
            print('Time:',
                  datetime.datetime.fromtimestamp(
                      int(runtime), tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                  f'(run ID {meta["runid"]})')
            if failtext:
                print(f'Failure reason: {failtext}')
            if 'url' in meta:
                print('URL:', meta['url'])
            else:
                print('URL: (unknown)')
            print()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Find test runs matching specific tests')
    argparsing.arguments_logging(parser)
    argparsing.arguments_config(parser)
    with nullcontext(parser.add_argument_group(
                     'query arguments', 'Specifying test matches')) as query:
        query.add_argument(
            '--failed',
            nargs='*',
            default=[],
            help='Select runs where these tests failed')
        query.add_argument(
            '--succeeded',
            nargs='*',
            default=[],
            help='Select runs where these tests succeeded')
        query.add_argument(
            '--resultcode',
            choices=[code.name for code in TestResult],
            help='Specify test result code to match')
    # TODO: use this to catch arguments for --failed and --succeeded, too, except that means only
    # one query can be done in an invocation, which is probably fine.
    parser.add_argument(
        'tests',
        nargs='*',
        help='Tests to match against --resultcode')
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--since',
        help='Only look at logs created since this ISO date or number of hours')
    return parser.parse_args(args=args)


def main() -> int:
    args = parse_args()
    log.setup(args)

    if args.since:
        try:
            since = (datetime.datetime.now(tz=datetime.timezone.utc)
                     - datetime.timedelta(hours=int(args.since)))
        except ValueError:
            since = datetime.datetime.fromisoformat(args.since)
    else:
        # Default to same time as logfile analysis time since it's probably only
        # recent tests we would want to see
        since = (datetime.datetime.now(tz=datetime.timezone.utc)
                 - datetime.timedelta(hours=config.get('analysis_hours')))

    if not args.succeeded and not args.failed and not args.resultcode:
        print('Must specify at least one of --failed, --succeeded or --resultcode')
        return 1

    if not args.succeeded and not args.failed and not args.tests:
        print('Must specify tests with --failed, --succeeded or after --resultcode')
        return 1

    with db.Datastore() as ds:
        ffr = FindFailedRuns(ds)

        for testname in args.succeeded:
            print('------------------------------------')
            print(f'Looking for succeeded test {testname} runs')
            testmatches = ffr.find_status_run(args.checkrepo, since, testname, SUCCEEDED)
            ffr.show_matches(testmatches)

        for testname in args.failed:
            print('------------------------------------')
            print(f'Looking for failed test {testname} runs')
            testmatches = ffr.find_status_run(args.checkrepo, since, testname, FAILED)
            ffr.show_matches(testmatches)

        for testname in args.tests:
            print('------------------------------------')
            print(f'Looking for runs of test {testname} matching {args.resultcode}')
            testmatches = ffr.find_status_run(
                args.checkrepo, since, testname, (TestResult[args.resultcode],))
            ffr.show_matches(testmatches)

    return 0


if __name__ == '__main__':
    main()

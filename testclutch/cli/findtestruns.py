"""Find test job runs where a particular test failed or succeeded.
"""

import argparse
import datetime
from typing import Collection, List, Tuple

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.testcasedef import TestResult


# Test status considered failed
FAILED = frozenset((TestResult.FAIL, TestResult.TIMEOUT))

# Test status considered succeeded
# PASS is duplicated due to simplifications in the matching query
SUCCEEDED = [TestResult.PASS, TestResult.PASS]


# Return data about test runs that contain a failed test
RUNS_BY_TEST_STATUS_SQL = r'SELECT testresults.id, testruns.time, resulttext FROM testresults INNER JOIN testruns ON testruns.id = testresults.id WHERE time >= ? AND repo = ? AND testid = ? AND result IN (?, ?);'


class FindFailedRuns:
    def __init__(self, ds: db.Datastore):
        self.ds = ds

    def find_status_run(self, repo: str, since: datetime.datetime, testname: str,
                        status: Collection) -> List[Tuple[int, int, str]]:
        assert self.ds.db  # satisfy pytype that this isn't None
        jobruns = self.ds.db.cursor()
        statuses = list(status)
        assert len(statuses) == 2  # limitation for now
        oldest = int(since.timestamp())
        jobruns.execute(RUNS_BY_TEST_STATUS_SQL,
                        (oldest, repo, testname, statuses[0], statuses[1]))
        return jobruns.fetchall()

    def show_matches(self, testmatches: List[Tuple[int, int, str]]):
        # Sort by descending date
        testmatches.sort(key=lambda x: x[1], reverse=True)
        for testid, runtime, failtext in testmatches:
            meta = self.ds.collect_meta(testid)
            assert isinstance(meta['origin'], str)  # satisfy pytype that this isn't int
            if 'cijob' in meta:
                name = meta['cijob']
            else:
                name = meta['uniquejobname']
            print("Job:", f"{meta['origin'].capitalize()}: {name}")
            print("Time:", datetime.datetime.fromtimestamp(int(runtime)).strftime("%Y-%m-%d %H:%M:%S"),
                  f"(run ID {meta['runid']})")
            if failtext:
                print(f"Failure reason: {failtext}")
            if 'url' in meta:
                print('URL:', meta['url'])
            else:
                print('URL: (unknown)')
            print()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze test results in the database')
    argparsing.arguments_logging(parser)
    query = parser.add_argument_group('query arguments', 'Specifying test matches')
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
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--since',
        help='Only look at logs created since this ISO date or number of hours')
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    if args.since:
        try:
            since = datetime.datetime.now() - datetime.timedelta(hours=int(args.since))
        except ValueError:
            since = datetime.datetime.fromisoformat(args.since)
    else:
        since = datetime.datetime.fromtimestamp(0)

    if not args.succeeded and not args.failed:
        print('Must specify --failed or --succeeded')
        return

    ds = db.Datastore()
    ds.connect()

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

    ds.close()


if __name__ == '__main__':
    main()

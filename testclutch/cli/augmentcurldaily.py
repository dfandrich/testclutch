"""Augment build metadata with daily curl snapshot commit info

The git commit at which daily builds are snapshotted is not available from the build logs.
This extracts what information is available from a daily snapshot file and augmenst existing
ingested tests with the information about the last commit.
"""

import argparse
import datetime
import logging
from typing import Tuple

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.augment import curldailyinfo


# Number of git commits to look at to find the right one
NUM_COMMIT_CANDIDATES = 30

# Select records for curlauto builds
CURLAUTO_BUILDS_SQL = r"SELECT testrunmeta.id FROM testrunmeta WHERE name = 'origin' AND value = 'curlauto'"

# Select records from curlauto daily builds
DAILY_BUILDS_SQL = (
    f"SELECT testrunmeta.id, testrunmeta.value FROM ({CURLAUTO_BUILDS_SQL}) AS originmatch "
    r"INNER JOIN testrunmeta ON originmatch.id = testrunmeta.id WHERE name = 'dailybuild'")

# Select records from curlauto daily builds for a particular day
# Input is daily build value
DAILY_BUILDS_MATCHING_DATE_SQL = (
    f"SELECT testrunmeta.id FROM ({DAILY_BUILDS_SQL}) AS dailymatch "
    r"INNER JOIN testrunmeta ON dailymatch.id = testrunmeta.id WHERE testrunmeta.value = ?")

# Select records from curlauto daily builds that also have commit metadata
DAILY_BUILDS_WITH_COMMIT_SQL = (
    f"SELECT datematch.id FROM ({DAILY_BUILDS_MATCHING_DATE_SQL}) AS datematch "
    r"INNER JOIN testrunmeta ON datematch.id = testrunmeta.id WHERE name = 'commit'")


class CurlDailyAugmenter:
    def __init__(self, repo: str, ds: db.Datastore, dry_run: bool = False):
        self.repo = repo
        self.ds = ds
        self.dry_run = dry_run

    def get_all_daily_info(self, fn: str) -> Tuple[str, str, str]:
        day_code, daily_time, daily_title = curldailyinfo.get_daily_info(fn)

        if day_code != daily_time.astimezone(datetime.timezone.utc).strftime('%Y%m%d'):
            logging.error('Date mismatch: %s vs %s',
                          day_code, daily_time.astimezone(datetime.timezone.utc))
            return ('', '', '')

        # TODO: it may be better to walk the linked list of commits (prev_commit) to find the ones
        # behind the last one rather than looking purely by time. This is TBD.
        branch = config.expand('branch')
        candidates = self.ds.select_commit_before_time(
            self.repo, branch, int(daily_time.timestamp()), NUM_COMMIT_CANDIDATES)

        if not candidates:
            logging.error('No commits found since %s', daily_time)

        first = True
        for candidate in candidates:
            commithash, committime, title, committeremail, authoremail = candidate
            logging.debug(f'Found {commithash:.9} "{title}"')
            if daily_title == title:
                break
            if first:
                # This is an indication that there was more than one commit around this time and
                # the likelihood of choosing the wrong one increases
                logging.info('git commit from daily tarball was not the first guess: %s', title)
                first = False
        else:
            logging.error('Not able to find a matching commit in the previous %d: %s',
                          NUM_COMMIT_CANDIDATES, daily_title)
            return ('', '', '')

        return day_code, commithash, title

    def augment_daily(self, fn: str):
        # Get info from daily build tarball
        day_code, commithash, title = self.get_all_daily_info(fn)
        logging.info('File %s matches date %s hash %s title %s', fn, day_code, commithash, title)

        # Find daily build test logs
        # TODO: restrict by recent builds only
        assert self.ds.cur  # satisfy pytype that this isn't None
        res = self.ds.cur.execute(DAILY_BUILDS_MATCHING_DATE_SQL, (day_code, ))
        daily = res.fetchall()
        logging.info('%d jobs matching day %s', len(daily), day_code)

        # Find daily build test logs that already have commits
        res = self.ds.cur.execute(DAILY_BUILDS_WITH_COMMIT_SQL, (day_code, ))
        with_commit = set(x[0] for x in res.fetchall())
        if with_commit:
            logging.info('...but %d jobs already have a commit', len(with_commit))

        # Remove records that already have a commit
        recs_to_add_commits = [job[0] for job in daily if job[0] not in with_commit]
        logging.info('...leaving %d jobs to modify', len(recs_to_add_commits))

        # Add commit to daily build records that don't already have one
        if not self.dry_run:
            meta = {'commit': commithash,
                    'summary': title}
            for recid in recs_to_add_commits:
                self.ds.store_test_meta(recid, meta)


def augment_curl_daily(args):
    ds = db.Datastore()
    ds.connect()

    cda = CurlDailyAugmenter(args.checkrepo, ds, args.dry_run)
    for fn in args.filenames:
        cda.augment_daily(fn)

    ds.close()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Augment test run metadata from daily builds with git commits')
    argparsing.arguments_logging(parser)
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        'filenames',
        nargs='+',
        help="Path to one or more daily build tarball")

    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    if not args.checkrepo.startswith('https://github.com/'):
        logging.error('--checkrepo value seems wrong; using anyway')

    augment_curl_daily(args)


if __name__ == '__main__':
    main()

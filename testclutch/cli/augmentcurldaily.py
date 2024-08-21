"""Augment build metadata with daily curl snapshot commit info

The git commit at which daily builds are snapshotted is not available from the build logs.
This extracts what information is available from a daily snapshot file and augments existing
ingested tests with the information about the last commit.
"""

import argparse
import datetime
import logging

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.augment import curldailyinfo


# Select records for curlauto builds
CURLAUTO_BUILDS_SQL = r"SELECT testruns.id FROM testruns INNER JOIN testrunmeta ON testruns.id = testrunmeta.id WHERE time >= ? AND repo = ? AND name = 'origin' AND value = 'curlauto'"

# Select records for curlauto daily builds for a particular day
DAILY_BUILDS_MATCHING_DATE_SQL = (
    f"SELECT testrunmeta.id, testrunmeta.value FROM ({CURLAUTO_BUILDS_SQL}) AS originmatch "
    r"INNER JOIN testrunmeta ON originmatch.id = testrunmeta.id "
    r"WHERE name = 'dailybuild' AND value = ?")

# Select records from curlauto daily builds that also have commit metadata
DAILY_BUILDS_WITH_COMMIT_SQL = (
    f"SELECT datematch.id FROM ({DAILY_BUILDS_MATCHING_DATE_SQL}) AS datematch "
    r"INNER JOIN testrunmeta ON datematch.id = testrunmeta.id WHERE name = 'commit'")


class CurlDailyAugmenter:
    def __init__(self, repo: str, ds: db.Datastore, dry_run: bool = False):
        assert ds.cur  # satisfy pytype that this isn't None
        self.repo = repo
        self.ds = ds
        self.dry_run = dry_run

    def get_all_daily_info(self, fn: str) -> tuple[str, str, str]:
        day_code, daily_time, commithash = curldailyinfo.get_daily_info(fn)
        logging.debug(f'Daily snapshot from {day_code} at {daily_time.ctime()} '
                      f'with hash {commithash}')
        if day_code != daily_time.astimezone(datetime.timezone.utc).strftime('%Y%m%d'):
            logging.error('Date mismatch: %s vs %s',
                          day_code, daily_time.astimezone(datetime.timezone.utc))
            return '', '', ''

        if not commithash:
            logging.warning('No hash found in daily snapshot')
            return day_code, '', ''

        branch = config.expand('branch')
        # We only need one commit here, not all subsequent ones, but the list should be very short
        # and this function is already available.
        candidates = self.ds.select_all_commit_after_commit(self.repo, branch, commithash)

        if not candidates:
            logging.error(f'Commit {commithash} for {daily_time} snapshot not found in commit DB')
            return day_code, commithash, ''

        candidate = candidates[-1]
        logging.debug(f'Found commit {candidate.commit_hash:.9} "{candidate.title}"')
        if commithash != candidate.commit_hash:
            logging.error(f'Expecting hash {commithash}, got {candidate.commit_hash}')
            return day_code, commithash, ''

        return day_code, commithash, candidate.title

    def augment_daily(self, fn: str, howrecent: int):
        # Get info from daily build tarball
        day_code, commithash, title = self.get_all_daily_info(fn)
        logging.info('File %s matches date %s hash %s title %s', fn, day_code, commithash, title)

        if not commithash:
            logging.error('Could not find the commit hash; skipping augmentation')
            return

        # Find daily build test logs
        res = self.ds.cur.execute(DAILY_BUILDS_MATCHING_DATE_SQL,
                                  (howrecent, self.repo, day_code, ))
        daily = res.fetchall()
        logging.info('%d jobs matching day %s', len(daily), day_code)

        if daily:
            # Find daily build test logs that already have commits
            res = self.ds.cur.execute(DAILY_BUILDS_WITH_COMMIT_SQL,
                                      (howrecent, self.repo, day_code, ))
            with_commit = frozenset(x[0] for x in res.fetchall())
            if with_commit:
                logging.info('...but %d jobs already have a commit', len(with_commit))

            # Drop records from list that already have a commit
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
    if args.howrecent:
        since = int(datetime.datetime.now().timestamp()) - args.howrecent * 3600
    else:
        logging.warning("Use --howrecent to speed up augmentation")
        since = 0

    for fn in args.filenames:
        cda.augment_daily(fn, since)

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
    parser.add_argument(
        '--howrecent',
        type=int,
        help='Maximum age of logs to augment, in hours')
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    if not args.checkrepo.startswith('https://github.com/'):
        logging.error('--checkrepo value seems wrong; using anyway')

    augment_curl_daily(args)


if __name__ == '__main__':
    main()

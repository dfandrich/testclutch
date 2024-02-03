"""Augment short git hashes to make them full

This can currently happen for origin=curlauto builds, but the code doesn't discriminate.
"""

import argparse
import logging

from testclutch import config
from testclutch import db


# Select records with short hashes
SHORT_HASHES_SQL = r"SELECT testrunmeta.id, testrunmeta.value AS shorthash FROM testrunmeta WHERE name = 'commit' AND length(value) < 40"

# Select records with short hashes on the desired repo
SHORT_HASHES_REPO_SQL = (
    f"SELECT testrunmeta.id, shorthash FROM ({SHORT_HASHES_SQL}) AS hashmatch "
    r"INNER JOIN testrunmeta ON hashmatch.id = testrunmeta.id WHERE name = 'checkrepo' AND value = ?")

# Match a short hash in the commit database
SHORT_HASH_SQL = r"SELECT commithash FROM commitinfo WHERE SUBSTR(commithash, 1, ?) = ?"

# Update a commit hash
# Checking value is a fail-safe and shouldn't really be needed
UPDATE_HASH_SQL = r"UPDATE testrunmeta SET value = ? WHERE id = ? AND name = 'commit' AND value = ?"


class GitHashAugmenter:
    def __init__(self, repo: str, ds: db.Datastore, dry_run: bool = False):
        self.repo = repo
        self.ds = ds
        self.dry_run = dry_run

    def augment_short_hashes(self):
        # Find short hashes
        assert self.ds and self.ds.cur and self.ds.db  # satisfy pytype that these aren't None
        # TODO: optionally limit check to last X hours
        res = self.ds.cur.execute(SHORT_HASHES_REPO_SQL, (self.repo, ))
        shorts = res.fetchall()
        logging.info('%d records with short hashes', len(shorts))
        for recid, shorthash in shorts:
            logging.info('Looking up hash %s', shorthash)
            res = self.ds.cur.execute(SHORT_HASH_SQL, (len(shorthash), shorthash))
            long = res.fetchall()
            if len(long) > 1:
                logging.warning('More than one commit hash matches for %s; skipping', shorthash)
            if not long:
                logging.warning('Cannot find long hash for %s', shorthash)
            else:
                longhash = long[0][0]
                logging.debug('Replacing %s with %s', shorthash, longhash)
                if not self.dry_run:
                    res = self.ds.cur.execute(UPDATE_HASH_SQL, (longhash, recid, shorthash))
        self.ds.db.commit()


def augment_short_hashes(args):
    ds = db.Datastore()
    ds.connect()

    gitaugment = GitHashAugmenter(args.checkrepo, ds, args.dry_run)
    gitaugment.augment_short_hashes()

    ds.close()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Replace short git hashes in the database with long ones')
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        help="Parse file but don't store it in the database")
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_true',
        help="Show more logging")
    parser.add_argument(
        '--debug',
        action='store_true',
        help="Show debug level logging")
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")

    return parser.parse_args(args=args)


def main():
    args = parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(levelno)s %(filename)s: %(message)s',)
        args.verbose = True
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format='%(filename)s: %(message)s',)

    if not args.checkrepo.startswith('https://github.com/'):
        logging.error('--checkrepo value seems wrong; using anyway')

    augment_short_hashes(args)


if __name__ == '__main__':
    main()

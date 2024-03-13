"""Get commit information from a git repository
"""

import argparse
import logging
import subprocess
from typing import List, Optional

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch.gitdef import CommitInfo


class GitCommitIngestor:
    def __init__(self, repo: str, ds: Optional[db.Datastore]):
        self.repo = repo
        self.ds = ds
        self.dry_run = ds is None

    def extract_git_commit_info(self, repo: str, branch: str, since: str) -> List[CommitInfo]:
        "Returns information about git commits"
        try:
            # git nowadays has -C to select the repo to use, but this way works with
            # much older versions
            commands = ['env', f'GIT_DIR={repo}', 'git', 'log',
                        '--pretty=format:%ct%n%H%n%cn%n%ce%n%an%n%ae%n%s%n',
                        '--since', since, branch]
            logging.debug('Running: %s', ' '.join(commands))
            with subprocess.Popen(commands,
                                  stdout=subprocess.PIPE, text=True,
                                  encoding=config.get('git_comment_encoding')) as p:
                assert p.stdout  # satisfy pytype that this isn't None
                result = []
                while l := p.stdout.readline():
                    result.append(CommitInfo(
                        commit_time=int(l.strip()),
                        commit_hash=p.stdout.readline().strip(),
                        committer_name=p.stdout.readline().strip(),
                        committer_email=p.stdout.readline().strip(),
                        author_name=p.stdout.readline().strip(),
                        author_email=p.stdout.readline().strip(),
                        title=p.stdout.readline().strip()
                    ))
                    if not (l := p.stdout.readline()):
                        break
                    if l.strip():
                        logging.error('Inconsistency in git log output')
                        break
        except FileNotFoundError:
            logging.exception('Could not extract git commit info')
            return []

        # Now go through them all (except the last) to add the prev_hash field
        for i in range(len(result) - 1):
            result[i].prev_hash = result[i + 1].commit_hash

        # We don't want to store a commit without prev_hash, so just delete it
        if result:
            del result[-1]

        return result

    def ingest_commit_info(self, local_repo: str, branch: str, since: str):
        infolist = self.extract_git_commit_info(local_repo, branch, since)
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        logging.info('%d commits extracted', len(infolist))
        for info in infolist:
            if self.ds:
                try:
                    self.ds.store_commit_info(self.repo, branch, info)
                except db.IntegrityError:
                    logging.debug('Commit %s has already been ingested!', info.commit_hash[:8])


def ingest_commits(args):
    if not args.dry_run:
        ds = db.Datastore()
        ds.connect()
    else:
        ds = None

    gc = GitCommitIngestor(args.checkrepo, ds)
    gc.ingest_commit_info(args.localrepo, args.branch, args.since)

    if ds:
        ds.close()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Ingest git commits into the database')
    argparsing.arguments_logging(parser)
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--branch',
        default=config.expand('branch'),
        help="Branch whose commits will be read")
    parser.add_argument(
        'localrepo',
        help="Path to the local repository patching --checkrepo")
    parser.add_argument(
        'since',
        help="Date/time from which git commits will be read")
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    if not args.checkrepo.startswith('https://github.com/'):
        logging.error('--checkrepo value seems wrong; using anyway')

    ingest_commits(args)


if __name__ == '__main__':
    main()

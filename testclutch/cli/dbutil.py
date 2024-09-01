"""Test program to manipulate the database
"""

import datetime
import logging
import sys
from email import utils

from testclutch import config
from testclutch import db


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(levelno)s %(filename)s: %(message)s',)
    if len(sys.argv) < 2:
        print('Usage: dbutil [command [args...]]')
        print('Commands available: deleteid commitchain commitchainrev checkcommitchain')
        sys.exit(1)

    ds = db.Datastore()
    ds.connect()
    assert ds.db and ds.cur  # satisfy pytype that this isn't None

    if sys.argv[1] == 'deleteid':
        if len(sys.argv) < 3:
            print('Usage: dbutil deleteid <id>')
            sys.exit(1)
        rec_id = int(sys.argv[2])
        print('Deleting job record id %d' % rec_id)
        ds.delete_test_run(rec_id)

    elif sys.argv[1] == 'commitchain':
        if len(sys.argv) not in (3, 5):
            print('Usage: dbutil commitchain [<repo> <branch>] <commit>')
            sys.exit(1)
        if len(sys.argv) == 5:
            repo, branch, commit = sys.argv[2:6]
        else:
            repo = config.expand('check_repo')
            branch = config.expand('branch')
            commit = sys.argv[2]
        commits = ds.select_all_commit_after_commit(repo, branch, commit)
        for c in commits:
            print(f'commit {c.commit_hash}')
            print(f'prev {c.prev_hash}')
            print(f'Author: {c.author_name} <{c.author_email}>')
            print(f'Commit: {c.committer_name} <{c.committer_email}>')
            format_date = utils.format_datetime(datetime.datetime.fromtimestamp(
                c.commit_time).astimezone(datetime.timezone.utc))
            print(f'CommitDate: {format_date}')
            print()
            print(f'    {c.title}')
            print()

    elif sys.argv[1] == 'commitchainrev':
        if len(sys.argv) not in (3, 4, 5):
            print('Usage: dbutil commitchainrev [<repo> <branch> [<commit>]]')
            sys.exit(1)
        if len(sys.argv) == 5:
            repo, branch, commit = sys.argv[2:6]
        elif len(sys.argv) == 4:
            repo, branch = sys.argv[2:5]
            # Get the most recent commit
            commits = ds.select_commit_before_time(repo, branch,
                                                   int(datetime.datetime.now().timestamp()), 1)
            if not commits:
                print('Error: no matching commits found in db')
                sys.exit(1)
            commit = commits[0][0]
        else:  # len(sys.argv) == 3
            repo = config.expand('check_repo')
            branch = config.expand('branch')
            commit = sys.argv[2]
        commits = ds.select_all_commit_before_commit(repo, branch, commit)
        for c in commits:
            print(f'commit {c.commit_hash}')
            print(f'prev {c.prev_hash}')
            print(f'Author: {c.author_name} <{c.author_email}>')
            print(f'Commit: {c.committer_name} <{c.committer_email}>')
            format_date = utils.format_datetime(datetime.datetime.fromtimestamp(c.commit_time).astimezone(datetime.timezone.utc))
            print(f'CommitDate: {format_date}')
            print()
            print(f'    {c.title}')
            print()

    elif sys.argv[1] == 'checkcommitchain':
        if len(sys.argv) not in (3, 5):
            print('Usage: dbutil checkcommitchain [<repo> <branch>] <commit>')
            print('Checks that the commit chain is unbroken. <commit> must be the')
            print('oldest commit in the database.')
            sys.exit(1)
        if len(sys.argv) == 5:
            repo, branch, commit = sys.argv[2:6]
        else:
            repo = config.expand('check_repo')
            branch = config.expand('branch')
            commit = sys.argv[2]
        commits = ds.select_all_commit_after_commit(repo, branch, commit)
        branch = config.expand('branch')
        ds.cur.execute("SELECT count(1) FROM commitinfo WHERE repo=? AND branch=?", (repo, branch,))
        commits_in_db = ds.cur.fetchone()[0]
        if commits_in_db != len(commits):
            print('Error: commit chain in db is incomplete')
            print(f'database: {commits_in_db} chain length: {len(commits)}')
            sys.exit(2)
        else:
            print(f'Commit chain matches database (length {commits_in_db})')

    else:
        print(f'Unknown command {sys.argv[1]}')

    ds.close()


if __name__ == '__main__':
    main()

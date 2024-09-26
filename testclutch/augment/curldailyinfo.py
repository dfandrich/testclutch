"""Extract information from curl daily tar balls."""

import datetime
import io
import logging
import posixpath
import re
import tarfile


# Extract the date from the directory name
DIR_NAME_RE = re.compile(r'^.*-(\d{8})$')

# Extract the git commit message title out of the CHANGES file
CHANGES_TITLE_RE = re.compile(r'^- (.*)$')

# This is the first generated file in the tar ball which gives a close approximation of the time
# at which the git pull was performed
SENTINEL_FILE = 'm4/libtool.m4'

# This file provides the git commit after 2024-08-04
COMMIT_FILE = 'docs/tarball-commit.txt'

# Character maps used in the COMMIT_FILE
COMMIT_CHARMAP = 'UTF-8'

# The number of seconds to assume between the git pull and generation of the first file.
# Better to underestimate this than overestimate it to avoid missing a last-momment commit.
PULL_TIME_LAG = 4

# Time zone in which th daily tarball is built; this affects the date within the file name
BUILDER_TZ = '+0200'


def get_daily_info(fn: str) -> tuple[str, datetime.datetime, str]:
    """Get the exact time & commit when the daily tarball was generated.

    Also, the daily date is not (necessarily) the date of availability at GitHub, which can be
    much longer if the user takes his time to upload it. It is only an upper bound on the commit
    date.
    """
    tar = tarfile.open(fn)
    tar_files = tar.getmembers()

    # Get the directory name
    first = tar_files[0].name.split('/')[0]
    logging.debug('Reading %s: %s/%s', fn, first, COMMIT_FILE)
    # Extract the date from the directory name
    r = DIR_NAME_RE.search(first)
    if not r:
        raise RuntimeError('Daily build contents is unexpected')
    day_code = r.group(1)
    build_day = datetime.datetime.strptime(day_code + BUILDER_TZ, '%Y%m%d%z').date()
    # Get the date of the first generated file in the tarball
    sentinel = tar.getmember(posixpath.join(first, SENTINEL_FILE))
    generated_time = (datetime.datetime.fromtimestamp(sentinel.mtime, tz=datetime.timezone.utc)
                      - datetime.timedelta(seconds=-PULL_TIME_LAG))
    generated_date = generated_time.date()

    # Sanity check the dates
    if generated_date != build_day:
        logging.error('curl daily build date mismatch; %s is not %s', generated_date, build_day)
        raise RuntimeError('curl daily build date mismatch')

    # Read the commit hash
    try:
        with io.TextIOWrapper(tar.extractfile(posixpath.join(first, COMMIT_FILE)),
                              line_buffering=True, encoding=COMMIT_CHARMAP) as commitf:
            commit = commitf.readline().strip()
    except KeyError:
        # COMMIT_FILE is not in archive
        commit = ''

    return (day_code, generated_time, commit)


if __name__ == '__main__':
    import sys
    fn = sys.argv[1]
    print(f'File: {fn}')
    day_code, daily_time, commit = get_daily_info(fn)
    print(f'Date code: {day_code}')
    print(f'Daily time: {daily_time}')
    print(f'Daily commit: {commit}')

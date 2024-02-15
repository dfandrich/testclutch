"""Extract information from curl daily tar balls
"""

import datetime
import io
import logging
import posixpath
import re
import tarfile
from typing import Tuple


# Extract the date from the directory name
DIR_NAME_RE = re.compile(r'^.*-(\d{8})$')

# Extract the git commit message title out of the CHANGES file
CHANGES_TITLE_RE = re.compile(r'^- (.*)$')

# This is the first generated file in the tar ball which gives a close approximation of the time
# at which the git pull was performed
SENTINEL_FILE = 'm4/libtool.m4'

# This file provides the git commit messages
CHANGES_FILE = 'CHANGES'

# Character maps used in the CHANGES file. They are tried in order until the text
# decodes without an error.
CHANGES_CHARMAPS = ['UTF-8', 'CP1252', 'CP437']

# The number of seconds to assume between the git pull and generation of the first file.
# Better to underestimate this than overestimate it to avoid missing a last-momment commit.
PULL_TIME_LAG = 4

# Time zone in which th daily tarball is built; this affects the date within the file name
BUILDER_TZ = '+0200'


def get_daily_info(fn: str) -> Tuple[str, datetime.datetime, str]:
    """Get the exact time & commit message when the daily tarball was generated

    While the exact time is pretty close, there is still a chance that a git commit
    right at this time didn't make it into the tar ball. The git commit title is also
    returned to help disambiguate it.

    Also, the daily date is not (necessarily) the date of availability at GitHub, which can be
    much longer if the user takes his time to upload it. It is only an upper bound on the commit
    date.
    """
    tar = tarfile.open(fn)
    tar_files = tar.getmembers()

    # Get the directory name
    first = tar_files[0].name.split('/')[0]
    logging.debug('Reading %s: %s/%s', fn, first, CHANGES_FILE)
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

    class DecodeSuccess(Exception):
        pass

    commit_msg = ''
    encodings = iter(CHANGES_CHARMAPS)
    encoding = ''
    while True:
        try:
            encoding = next(encodings)
            logging.debug('Trying encoding %s', encoding)
            changes = io.TextIOWrapper(tar.extractfile(posixpath.join(first, CHANGES_FILE)),
                                       line_buffering=True, encoding=encoding)
            while l := changes.readline():
                if r := CHANGES_TITLE_RE.search(l):
                    commit_msg = r.group(1)
                    raise DecodeSuccess
        except UnicodeDecodeError:
            logging.warning('Decoding as %s failed. Trying next encoding.', encoding)
        except StopIteration:
            # IF this ever happens, make sure there's an encoding in CHANGES_CHARMAPS that can
            # map every 8 bit byte into a character.
            logging.fatal('Abort: Text could not be decoded with any of %d encodings',
                          len(CHANGES_CHARMAPS))
            raise RuntimeError('%s could not be decoded' % CHANGES_FILE)
        except DecodeSuccess:
            break

    return (day_code, generated_time, commit_msg)

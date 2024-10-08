"""Disk cache of log files.

Transparently compresses and decompresses logs, if desired.
"""

import io
import os
import shutil
import stat

from testclutch import config

import zstd


COMPRESS_EXT = '.zst'


def create_dirs(subdir: str):
    """Create any parent directories that don't exist."""
    os.makedirs(os.path.join(config.expand('log_cache_path'), subdir), exist_ok=True)


def in_cache(fn: str) -> bool:
    """Return true if file exists in cache.

    The file may optionally be compressed.
    """
    path = os.path.join(config.expand('log_cache_path'), fn)
    try:
        os.stat(path)
    except FileNotFoundError:
        path += COMPRESS_EXT
        try:
            os.stat(path)
        except FileNotFoundError:
            return False
    return True


# TODO: figure out return type; -> IO gives errors on callers
def open_cache_file(fn: str, mode: str = 'r'):
    if mode.find('r') < 0:
        raise RuntimeError(f'Must be read mode: {mode}')
    path = os.path.join(config.expand('log_cache_path'), fn)
    try:
        compress_path = path + COMPRESS_EXT
        with open(compress_path, 'rb') as compress_file:
            if mode.find('b') >= 0:
                # Could add this using io.BytesIO if we need to
                raise RuntimeError(f'Binary mode not supported: {mode}')
            # If any bad characters are encountered while decoding using this charset (such as if a
            # binary file was displayed in a log dump), they will automatically be replaced with
            # backslash escapes.
            return io.StringIO(zstd.decompress(compress_file.read()).decode(
                config.expand('log_charset'), errors='backslashreplace'))
    except FileNotFoundError:
        return open(path, mode)


def move_into_cache(from_file: str, to_file: str):
    """Move a file directly into the cache."""
    to_path = os.path.join(config.expand('log_cache_path'), to_file)
    shutil.move(from_file, to_path)


def move_into_cache_compressed(from_file: str, to_file: str):
    """Compress a file and move it into the cache.

    Don't compress it if it's too small.
    """
    if os.stat(from_file)[stat.ST_SIZE] <= config.get('compress_threshold_bytes'):
        # There is a bug where zstd writes a warning message
        # "PY_SSIZE_T_CLEAN will be required for '#' formats" into the file that corrupts it when
        # given a zero-length file. This threshold eliminates that problem, as well as the overhead
        # to compress and decompress an already-tiny file.
        move_into_cache(from_file, to_file)
        return

    compressed = zstd.compress(open(from_file, 'rb').read())
    to_path = os.path.join(config.expand('log_cache_path'), to_file + COMPRESS_EXT)
    with open(to_path, 'wb') as out_file:
        out_file.write(compressed)
    os.unlink(from_file)

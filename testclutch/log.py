"""Debug logging functions
"""

import argparse
import logging
import os
import shlex
import sys
from typing import Optional


def calling_program() -> str:
    "Return the name of the program that started us"
    return os.path.basename(sys.argv[0])


def logging_level_to_syslog(level: int) -> int:
    "Converts a logging level into a syslog-compatible one"
    if level <= logging.DEBUG:
        return 7  # KERN_DEBUG
    if level <= logging.INFO:
        return 6  # KERN_INFO
    # Nothing maps to syslog level 5 (KERN_NOTICE)
    if level <= logging.WARN:
        return 4  # KERN_WARNING
    if level <= logging.ERROR:
        return 3  # KERN_ERR
    if level <= logging.CRITICAL:
        return 2  # KERN_CRIT
    # Should never get here
    return 1      # KERN_ALERT


class SyslogFormatter(logging.Formatter):
    "Formats log messages with a syslog-style level prefix"

    def __init__(self, fmt: str):
        super().__init__()
        self.base_format = fmt

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        self._style._fmt = f'<{logging_level_to_syslog(record.levelno)}>' + self.base_format
        return super().format(record)


def setup(args: argparse.Namespace, program: Optional[str] = None, subprogram: str = ''):
    """Set up the logging subsystem in a consistent way.

    program defaults to the program invoking this run.
    subprogram is appended to the program (used to show operating mode)
    """
    if not program:
        program = shlex.quote(calling_program())
    if subprogram:
        program = f'{program}|{subprogram}'
    # Escape percents to pass through format()
    program = program.replace('%', '%%')
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format=program + ' %(levelno)s %(filename)s: %(message)s',)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format=program + ' %(filename)s: %(message)s',)
    else:
        logging.basicConfig(level=logging.WARNING, format='%(filename)s: %(message)s',)
    if args.level_prefix:
        for handler in logging.getLogger().handlers:
            handler.setFormatter(SyslogFormatter(handler.formatter._style._fmt))

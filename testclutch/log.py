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


def setup(args: argparse.Namespace, program: Optional[str] = None):
    """Set up the logging subsystem in a consistent way.

    program defaults to the program invoking this run.
    """
    if not program:
        program = shlex.quote(calling_program())
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format=program + ' %(levelno)s %(filename)s: %(message)s',)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format=program + ' %(filename)s: %(message)s',)
    else:
        logging.basicConfig(level=logging.WARNING, format='%(filename)s: %(message)s',)

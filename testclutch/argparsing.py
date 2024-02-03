"""Functions to set up common argument parsers
"""

import argparse
import os

from testclutch import config

KNOWN_ORIGINS = ['appveyor', 'autobuilds', 'azure', 'circle', 'cirrus', 'curlauto', 'gha',
                 'local']


class ExpandUserFileType(argparse.FileType):
    """argparse.FileType that expands user directories"""

    def __call__(self, string):
        return super().__call__(os.path.expanduser(string))


def arguments_logging(parser: argparse.ArgumentParser):
    "Add arguments needed for logging"
    parser.add_argument(
        '--dry-run',
        #dest='dry_run',
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


def arguments_ci(parser: argparse.ArgumentParser):
    "Add arguments needed for selecting and using a CI system"
    parser.add_argument(
        '--origin',
        required=True,
        choices=KNOWN_ORIGINS,
        help="Origin of the log file")
    parser.add_argument(
        '--authfile',
        type=ExpandUserFileType('r'),
        help="File holding authentication token if needed for this --origin")
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--account',
        help="account name in the CI service, if different from that in --checkrepo")
    parser.add_argument(
        '--project',
        help="project name in the CI service, if different from that in --checkrepo")

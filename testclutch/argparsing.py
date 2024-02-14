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


class StoreMultipleConstAction(argparse.Action):
    """Store the value of the const to multiple attributes.

    const holds the value to store (defaults to True) and attrs is an iterable
    of attribute names to store the value, in addition to dest.
    """
    def __init__(self,
                 option_strings,
                 dest,
                 const=True,
                 attrs='',
                 default=None,
                 required=False,
                 help=None,     # noqa: A002
                 metavar=None):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            const=const,
            default=default,
            required=required,
            help=help)
        self.attrs = attrs

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.const)
        for attr in self.attrs:
            setattr(namespace, attr, self.const)


def arguments_logging(parser: argparse.ArgumentParser):
    "Add arguments needed for logging"
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Go through the motions but don't make permanent changes")
    parser.add_argument(
        '-v', '--verbose',
        dest='verbose',
        action='store_true',
        help="Show more log messages")
    parser.add_argument(
        '--debug',
        action=StoreMultipleConstAction,
        attrs=['verbose'],
        help="Show debug level log messages")


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

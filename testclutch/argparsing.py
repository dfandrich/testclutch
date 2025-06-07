"""Functions to set up common argument parsers."""

import argparse
import ast
import os
from typing import Optional

from testclutch import config

KNOWN_ORIGINS = ['appveyor', 'azure', 'circle', 'cirrus', 'curlauto', 'gha', 'local']


class ExpandUserFileName:
    """argparsing type that checks if a file has the desired permisssions.

    User directories with tildes (e.g. ~user/foo) are expanded first.
    The file name is returned rather than an open file (unlike argparse.FileType) so that file
    nametimes is not an issue. This way (vs. argparse.FileType) introduces a race condition because
    the file permissions could change between the time we check them and the time the file is
    later opened, but this way at least lets us close the file when we're done with it when the
    file is used more than once.

    Future improvements:
    - check if the file is the correct type (e.g. directory vs file)
    - if the file is writable but it doesn't exist, it should check the write status of the
      containing directory to ensure that the file can be created
    """

    def __init__(self, mode: str = 'r'):
        self.mode = mode

    def __call__(self, filename: str):
        fn = os.path.expanduser(filename)
        modebits = ((os.R_OK if 'r' in self.mode or '+' in self.mode else 0)
                    | (os.W_OK if 'w' in self.mode or 'x' in self.mode or 'a' in self.mode
                       or '+' in self.mode else 0))
        if not os.access(fn, modebits):
            raise argparse.ArgumentTypeError(f'{fn} does not exist or have permission')
        return fn


class StoreMultipleConstAction(argparse.Action):
    """Store the value of the const to multiple attributes.

    const holds the value to store (defaults to True) and attrs is an iterable
    of attribute names to store the value, in addition to dest.
    """

    def __init__(self,
                 option_strings,
                 dest: str,
                 const: bool = True,
                 attrs: Optional[list[str]] = None,
                 default=None,
                 required: bool = False,
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
        self.attrs = attrs if attrs else []

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, self.const)
        for attr in self.attrs:
            setattr(namespace, attr, self.const)


class OverrideConfigAction(argparse.Action):
    """argparsing action that adds a configuration override."""
    def __init__(self,
                 option_strings,
                 dest: str,
                 default=None,
                 required: bool = False,
                 help=None):     # noqa: A002
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=1,
            default=default,
            required=required,
            metavar='NAME=VALUE',
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        for assignment in values:
            try:
                name, rawval = assignment.split('=', 1)
            except ValueError as e:
                raise argparse.ArgumentTypeError(f'Missing = in {assignment}') from e
            # Let any exceptions through here since they provide detail about the problem
            val = ast.literal_eval(rawval) if rawval else ''
            config.add_override(name, val)


def arguments_config(parser: argparse.ArgumentParser):
    """Add arguments needed for manipulating the configuration."""
    parser.add_argument(
        '--set',
        action=OverrideConfigAction,
        help='Override a config value')


def arguments_logging(parser: argparse.ArgumentParser):
    """Add arguments needed for logging."""
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Go through the motions but don't make permanent changes")
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show more log messages')
    parser.add_argument(
        '--debug',
        action=StoreMultipleConstAction,
        attrs=['verbose'],
        help='Show debug level log messages')
    parser.add_argument(
        '--level-prefix',
        action='store_true',
        help='Include syslog priority level in log message as <N> prefix')


def arguments_ci(parser: argparse.ArgumentParser, required: bool = True):
    """Add arguments needed for selecting and using a CI system."""
    parser.add_argument(
        '--origin',
        required=required,
        choices=KNOWN_ORIGINS,
        help='Origin of the log file')
    parser.add_argument(
        '--authfile',
        type=ExpandUserFileName('r'),
        help='File holding authentication token if needed for this --origin')
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--account',
        help='account name in the CI service, if different from that in --checkrepo')
    parser.add_argument(
        '--project',
        help='project name in the CI service, if different from that in --checkrepo')

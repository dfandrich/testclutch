"""Common URL manipulation functions

This contains functions relating to source repositories but not CI services.
"""

import argparse
import contextlib
import logging
import urllib.parse
from typing import Tuple, Union


def get_project_name(args: Union[str, argparse.Namespace]) -> Tuple[str, str]:
    """Returns the source code owner and project to use for a CI system

    This extracts them from the source repository URL, unless they are overridden by command-line
    arguments. This currently supports GitHub URLs and others with a similar format (like GitLab).

    Args:
        args: either the source code URL, or an object with the URL in checkrepo and the CI
        service's account and project in attributes with those names

    Returns:
        tuple of account, project
    """
    if hasattr(args, 'checkrepo'):
        # We got a argparse.Namespace
        checkrepo = args.checkrepo
        account = args.account
        project = args.project
    else:
        # We just got a string
        checkrepo = args
        account = ''
        project = ''
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(checkrepo)
    parts = path.split('/')
    # Sanity check URL
    if len(parts) != 3:
        logging.error('Unsupported repository URL: %s', checkrepo)
        raise RuntimeError(f'Unsupported repository URL {checkrepo}')
    if not account:
        account = path.split('/')[1]
    if not project:
        project = path.split('/')[2]
    return (account, project)


def url_host(url: str) -> str:
    "Return the host component of the URL"
    _, netloc, _, _, _ = urllib.parse.urlsplit(url)
    assert isinstance(netloc, str)  # pytype is confused about this
    return netloc.casefold()


def url_pr(url: str) -> int:
    """Extracts the PR number from a GitHub URL

    Returns 0 in case of invalid URL or one not containing a PR number
    """
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(url)
    if netloc != 'github.com':
        logging.error('Cannot extract PR from URL %s', url)
        return 0
    paths = path.split('/')
    if len(paths) < 5 or paths[3] != 'pull':
        logging.error('Cannot extract PR from URL %s', url)
        return 0
    pr = 0
    with contextlib.suppress(ValueError):
        pr = int(paths[3])
    return pr

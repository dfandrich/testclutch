"""Network API functions
"""

import functools
import logging
import os
import tempfile
import time
from typing import Callable, Optional, Type

import requests
from requests import adapters

import testclutch


HTTPError = requests.exceptions.HTTPError

# The User-Agent: header to use
USER_AGENT = f'testclutch/{testclutch.__version__}'

# Block size to download
CHUNK_SIZE = 0x10000


def get(url: str, headers: Optional[dict[str, str]] = None, **args) -> requests.Response:
    """Perform an HTTP request with standard request headers if none are supplied"""
    if not headers:
        headers = {'User-Agent': USER_AGENT}
    return requests.get(url=url, headers=headers, **args)


class Session(requests.Session):
    """Set up a requests session with a standard configuration"""

    def __init__(self, total: int = 4, backoff_factor: int = 10,
                 status_forcelist: Optional[list[int]] = None,
                 allowed_methods: Optional[list[str]] = None):
        super().__init__()
        if not status_forcelist:
            status_forcelist = [429, 500, 502, 503, 504]
        if not allowed_methods:
            allowed_methods = ['HEAD', 'GET', 'OPTIONS']

        # Experimental retry settings
        # This should delay a total of 10+20+40+80 seconds before aborting
        retry_strategy = adapters.Retry(
            total=total, backoff_factor=backoff_factor, status_forcelist=status_forcelist,
            allowed_methods=allowed_methods)
        adapter = adapters.HTTPAdapter(max_retries=retry_strategy)
        self.mount('https://', adapter)
        self.mount('http://', adapter)


# This could be replaced by the tenacity or backoff packages for more features
def retry_on_exception(func: Callable, exception: Type[Exception],
                       retries: int = 10, delay: float = 10):
    """Retry a function call on an exception, with fixed delay"""
    for attempt in range(retries):
        try:
            return func()
        except exception as e:
            exc = e
            logging.info(f'Download attempt {attempt} failed; retrying after delay')
            # TODO: This will sleep once too often at the end, unnecessarily delaying the caller
            time.sleep(delay)
            continue

    # all attempts raised an exception, so raise it now
    raise exc


def download_file_onetry(resp: requests.models.Response, url: str) -> tuple[str, str]:
    """Download the file at the link into a temporary file using the requests object

    This is done in a streamed manner to avoid having to load the entire file into RAM at once.
    """
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        try:
            # In case of download error, this can raise the exception:
            #   requests.exceptions.ChunkedEncodingError: Response ended prematurely
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                tmp.write(chunk)
        except:  # noqa: E722
            # Delete the temporary file on exception
            os.unlink(tmp.name)
            raise
    content_type = resp.headers.get('Content-Type', 'application/octet-stream')
    return (tmp.name, content_type)


def download_file(resp: requests.models.Response, url: str) -> tuple[str, str]:
    """Download a file, retrying a few times in case of errors, if necessary"""
    return retry_on_exception(functools.partial(download_file_onetry, resp, url),
                              requests.exceptions.ChunkedEncodingError)

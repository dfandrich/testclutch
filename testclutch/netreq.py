"""Network API functions
"""

from typing import Dict, List, Optional

import requests
from requests import adapters

import testclutch


HTTPError = requests.exceptions.HTTPError

# The User-Agent: header to use
USER_AGENT = f'testclutch/{testclutch.__version__}'


def get(url: str, headers: Optional[Dict[str, str]] = None, **args):
    "Perform an HTTP request with standard request headers if none are supplied"
    if not headers:
        headers = {'User-Agent': USER_AGENT}
    return requests.get(url=url, headers=headers, **args)


class Session(requests.Session):
    "Set up a requests session with a standard configuration"

    def __init__(self, total: int = 4, backoff_factor: int = 10,
                 status_forcelist: Optional[List[int]] = None,
                 allowed_methods: Optional[List[str]] = None):
        super().__init__()
        if not status_forcelist:
            status_forcelist = [429, 500, 502, 503, 504]
        if not allowed_methods:
            allowed_methods = ["HEAD", "GET", "OPTIONS"]

        # Experimental retry settings
        # This should delay a total of 10+20+40+80 seconds before aborting
        retry_strategy = adapters.Retry(
            total=total, backoff_factor=backoff_factor, status_forcelist=status_forcelist,
            allowed_methods=allowed_methods)
        adapter = adapters.HTTPAdapter(max_retries=retry_strategy)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

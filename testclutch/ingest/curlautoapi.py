"""API to access the curl autobuilds system
"""

import enum
import html
import html.parser
import logging
import re
import urllib

from testclutch import netreq


BASE_URL = 'https://curl.se/dev/inbox/'
DATA_TYPE = 'text/html,text/plain'

LOG_FILE_RE = re.compile(r'^build-.*\.log$')

CHUNK_SIZE = 0x10000


# Taken from spec-tree
class HTMLDirParser(html.parser.HTMLParser):
    """Parse the HTML resulting from an HTTP directory request.

    This works with the output from Apache, IIS, lighttpd and nginx. The first
    link in the links attribute is the parent directory.
    Some servers support returning directories in structured formats (e.g., XML
    or JSON) but it seems to be controlled server-side and the client doesn't
    appear to be able to influence it.
    """

    class TableState(enum.IntEnum):
        """States for the HTML parser."""
        NONE = enum.auto()
        TR = enum.auto()
        TH = enum.auto()

    def __init__(self):
        super().__init__()
        self.table_state = self.TableState.NONE
        self.links = []

    def error(self, message: str):
        logging.warning('%s', message)

    def handle_starttag(self, tag: str, attrs: list[tuple]):
        if tag == 'th':
            self.table_state = self.TableState.TH

        elif tag == 'tr':
            self.table_state = self.TableState.TR

        elif tag == 'a':
            if self.table_state == self.TableState.TH:
                # Ignore links in the table header
                return
            attrdict = dict(attrs)
            href = urllib.parse.unquote(html.unescape(attrdict['href']))
            # Remove Apache & IIS' special column sorting links
            if not href.startswith('?'):
                self.links.append(href)
        # ignore all other tags


class CurlAutoApi:

    def __init__(self):
        # This should delay a total of 5+10+20+40 seconds before aborting
        self.http = netreq.Session(backoff_factor=5)

    def _standard_headers(self) -> dict:
        return {'Accept': DATA_TYPE,
                'User-Agent': netreq.USER_AGENT
                }

    def get_runs(self) -> list[str]:
        """Returns info about all recent workflow runs"""
        url = BASE_URL
        logging.debug('Retrieving index from %s', url)
        with self.http.get(url, headers=self._standard_headers()) as resp:
            resp.raise_for_status()
            htmlp = HTMLDirParser()
            htmlp.feed(resp.text)
        htmlp.close()

        # Filter out all but log files
        return [link for link in htmlp.links if LOG_FILE_RE.search(link)]

    def get_logs(self, log_name: str) -> tuple[str, str]:
        url = BASE_URL + log_name
        logging.debug('Retrieving log from %s', url)
        with netreq.get(url, stream=True) as resp:
            return netreq.download_file(resp, url)

"""Retrieve logs from CircleCI runs
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from testclutch import netreq
from testclutch import urls

HTTPError = netreq.HTTPError

# See https://circleci.com/docs/api/v1/
BASE_URL = "https://circleci.com/api/v1.1"
RECENT_URL = BASE_URL + "/project/{vcs}/{user}/{project}"
RUN_URL = RECENT_URL + "/{build}"

DATA_TYPE = "application/json"

PAGINATION = 100      # Number to retrieve at once; maximum 100
MAX_RETRIEVED = 3000  # Don't ever retrieve more than this number

CHUNK_SIZE = 0x10000


class CircleApi:
    def __init__(self, checkurl: str):
        account, project = urls.get_project_name(checkurl)
        self.owner = account
        self.repo = project
        if urls.url_host(checkurl) != 'github.com':
            raise RuntimeError('Unsupported checkurl ' + checkurl)
        self.vcs = 'github'
        self.http = netreq.Session()

    def _standard_headers(self) -> Dict:
        return {"Accept": DATA_TYPE,
                "Content-Type": DATA_TYPE,
                "User-Agent": netreq.USER_AGENT
                }

    def get_runs(self) -> List[Dict[str, Any]]:
        """Returns info about all recent workflow runs on Cirrus CI"""
        # TODO: add date checking to break off pagination early
        combined_resp = []
        last_resp = None
        offset = 0
        while len(combined_resp) < MAX_RETRIEVED:
            url = RECENT_URL.format(vcs=self.vcs, user=self.owner, project=self.repo)
            params = {"limit": PAGINATION,
                      "offset": offset,
                      "shallow": "true",  # non-shallow doesn't give enough info; rely on get_run
                      }
            logging.debug('Retrieving runs from %s', url)
            with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
                if resp.status_code == 400:
                    # No more builds to download
                    break
                resp.raise_for_status()
                last_resp = json.loads(resp.text)
            combined_resp.extend(last_resp)
            offset += PAGINATION
        return combined_resp

    def get_run(self, build_id: int) -> Dict[str, Any]:
        """Returns info about a single run"""
        url = RUN_URL.format(vcs=self.vcs, user=self.owner, project=self.repo, build=build_id)
        with self.http.get(url, headers=self._standard_headers()) as resp:
            resp.raise_for_status()
            last_resp = json.loads(resp.text)
        return last_resp

    def get_logs(self, log_url: str) -> Tuple[str, Optional[str]]:
        logging.info('Retrieving log from %s', log_url)
        with self.http.get(log_url, stream=True) as resp:
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                try:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        tmp.write(chunk)
                except:  # noqa: E722
                    # Delete the temporary file on exception
                    os.unlink(tmp.name)
                    raise
            content_type = resp.headers.get('Content-Type', None)
        return (tmp.name, content_type)

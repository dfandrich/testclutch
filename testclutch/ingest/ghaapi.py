"""Retrieve logs from GitHub Actions runs

The token must be created from the GitHub personal settings "Developer Settings" menu as a
fine-grained personal access token. It can be set for only public repositories and does not need any
fine-grained repository permissions in order to read GitHub Actions logs.
"""

import datetime
import json
import logging
import tempfile
from typing import Any, Dict, Optional, Tuple

from testclutch import netreq


HTTPError = netreq.HTTPError

# See https://docs.github.com/en/rest?apiVersion=2022-11-28
BASE_URL = "https://api.github.com/repos/{owner}/{repo}/actions/{endpoint}"
RUN_URL = BASE_URL + "/{run_id}"
LOGS_URL = RUN_URL + "/logs"
JOBS_URL = RUN_URL + "/jobs"
PULL_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
API_VERSION = "2022-11-28"
DATA_TYPE = "application/vnd.github+json"

MAX_RETRIEVED = 1000  # Don't ever retrieve more than this number (max. 1000)
PAGINATION = 100      # Number to retrieve at once

# True to authenticate all API calls, not just log downloads. Needed to overcome low
# unauthenticated rate limits. See
# https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting
ALWAYS_AUTH = True


class GithubApi:
    def __init__(self, owner, repo, token):
        self.owner = owner
        self.repo = repo
        self.token = token

        # This should delay a total of 30+60+120+240+480 seconds before aborting
        # Oddly, GitHub uses 403 and not 429 for Client Error: rate limit exceeded
        # TODO: subclass Retry to override get_retry_after and support the
        # GitHub x-ratelimit-remaining and x-ratelimit-reset headers
        self.http = netreq.Session(total=5, backoff_factor=30,
                                   status_forcelist=[403, 429, 500, 502, 503, 504])

    def _standard_headers(self) -> Dict:
        headers = {"Accept": DATA_TYPE,
                   "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": netreq.USER_AGENT
                   }
        if ALWAYS_AUTH:
            headers['Authorization'] = 'Bearer ' + self.token
        return headers

    def _standard_auth_headers(self) -> Dict[str, str]:
        headers = self._standard_headers()
        if not ALWAYS_AUTH:
            headers['Authorization'] = 'Bearer ' + self.token
        return headers

    def _http_get_paged_json(self, url: str, headers: Dict[str, str],
                             params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Perform a paged HTTP get, combining all paged results in array

        The JSON response must have at least one array member, the last of which will be used as
        the signal for completed paging when it is empty.
        Raises an exception in case of error.

        Returns the Python equivalent of the JSON data structure (which will be a dict).
        """
        useparams = params.copy() if params else {}
        useparams["per_page"] = PAGINATION
        useparams["page"] = 1
        combined = {}

        done = False
        while not done and useparams["page"] <= MAX_RETRIEVED / PAGINATION:
            resp = self.http.get(url, headers=headers, params=useparams)
            resp.raise_for_status()

            j = json.loads(resp.text)
            done = True  # fail safe in case there is no array item
            # Copy or combine all returned items
            for k, v in j.items():
                if isinstance(v, list):
                    combined.setdefault(k, []).extend(v)
                    done = not v  # signal for pagination complete
                else:
                    if k in combined and combined[k] != v:
                        # If a item occurs in more than one page, it should have the same
                        # value each time. But, just in case a newer value is returned by the
                        # end, use that value in the response and continue.
                        logging.warn(f'Inconsistent static value over pages for {k}')
                    combined[k] = v

            useparams["page"] += 1

        return combined

    def get_runs(self, branch: Optional[str] = None, since: Optional[datetime.datetime] = None
                 ) -> Dict[str, Any]:
        """Returns info about all recent workflow runs on GitHub Actions"""
        url = BASE_URL.format(owner=self.owner, repo=self.repo, endpoint='runs')
        params = {"status": "completed"}
        if branch:
            params["branch"] = branch
            # Assume we don't want PRs if we supply a specific branch
            params["exclude_pull_requests"] = "true"
        if since:
            params["created"] = ">" + since.isoformat()

        return self._http_get_paged_json(url, headers=self._standard_headers(), params=params)

    def get_run(self, run_id: int) -> Dict[str, Any]:
        """Returns info about a single workflow run on GitHub Actions"""
        url = RUN_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_jobs(self, run_id: int) -> Dict[str, Any]:
        """Returns info about the jobs in a workflow run on GitHub Actions"""
        url = JOBS_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_logs(self, run_id: int) -> Tuple[str, Optional[str]]:
        url = LOGS_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        with self.http.get(url, headers=self._standard_auth_headers(), stream=True) as resp:
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                for chunk in resp.iter_content(chunk_size=0x10000):
                    tmp.write(chunk)
            if 'Content-Type' in resp.headers:
                content_type = resp.headers['Content-Type']
            else:
                content_type = None
        return (tmp.name, content_type)

    def get_pull(self, pr: int) -> Dict[str, Any]:
        """Returns info about a pull request on GitHub Actions"""
        url = PULL_URL.format(owner=self.owner, repo=self.repo, pull_number=pr)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

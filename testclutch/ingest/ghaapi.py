"""Retrieve logs from GitHub Actions runs

The token must be created from the GitHub personal settings "Developer Settings" menu as a
fine-grained personal access token. It can be set for only public repositories and does not need any
fine-grained repository permissions in order to read GitHub Actions logs.
"""

import datetime
import json
import logging
import os
import re
import tempfile
from typing import Any, Optional, Union

from testclutch import netreq


HTTPError = netreq.HTTPError

# See https://docs.github.com/en/rest?apiVersion=2022-11-28
API_URL = "https://api.github.com"
BASE_URL = API_URL + "/repos/{owner}/{repo}/actions/{endpoint}"
RUN_URL = BASE_URL + "/{run_id}"
LOGS_URL = RUN_URL + "/logs"
JOBS_URL = RUN_URL + "/jobs"
PULLS_URL = API_URL + "/repos/{owner}/{repo}/pulls"
PULL_URL = PULLS_URL + "/{pull_number}"
COMMITS_URL = API_URL + "/repos/{owner}/{repo}/commits/{commit_id}/status"
CHECKRUNS_URL = API_URL + "/repos/{owner}/{repo}/commits/{commit_id}/check-runs"
COMMENTS_URL = API_URL + "/repos/{owner}/{repo}/issues/{issue_number}/comments"
API_VERSION = "2022-11-28"
DATA_TYPE = "application/vnd.github+json"

MAX_RETRIEVED = 1000  # Don't ever retrieve more than this number (max. 1000)
PAGINATION = 100      # Number to retrieve at once

# True to authenticate all API calls, not just log downloads. Needed to overcome low
# unauthenticated rate limits. See
# https://docs.github.com/en/rest/overview/resources-in-the-rest-api?apiVersion=2022-11-28#rate-limiting
ALWAYS_AUTH = True

# Matches a time stamp that includes a time zone.
# Unfortunately, sometimes GHA includes one and sometimes it doesn't.
TIME_WITH_ZONE_RE = re.compile(r'^.{19}.*[-+]')


def convert_time(timestamp: str) -> datetime.datetime:
    """Converts a GitHub time into a datetime object.

    There seem to be three kinds of time formats used:
        2023-07-24T15:16:01.000-07:00
        2023-07-24T22:03:10Z
        2023-08-15T13:03:32.000Z
    """
    if not TIME_WITH_ZONE_RE.search(timestamp):
        if timestamp.find('.') > 0:
            # need to add this so the datetime object will be time zone aware, with sub-seconds
            return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%S.%fZ%z')
        else:
            # need to add this so the datetime object will be time zone aware
            return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%SZ%z')
    return datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f%z')


class GithubApi:
    def __init__(self, owner: str, repo: str, token: Optional[str]):
        self.owner = owner
        self.repo = repo
        self.token = token

        # This should delay a total of 30+60+120+240+480 seconds before aborting
        # Oddly, GitHub uses 403 and not 429 for Client Error: rate limit exceeded
        # TODO: subclass Retry to override get_retry_after and support the
        # GitHub x-ratelimit-remaining and x-ratelimit-reset headers
        self.http = netreq.Session(total=5, backoff_factor=30,
                                   status_forcelist=[403, 429, 500, 502, 503, 504])

    def _standard_headers(self) -> dict:
        headers = {"Accept": DATA_TYPE,
                   "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": netreq.USER_AGENT
                   }
        if ALWAYS_AUTH and self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        return headers

    def _standard_auth_headers(self) -> dict[str, str]:
        headers = self._standard_headers()
        if 'Authorization' not in headers:
            if self.token:
                headers['Authorization'] = 'Bearer ' + self.token
            else:
                logging.warning('Auth requested but no token available: %s', type(self.token))
        return headers

    def _http_get_paged_json(self, url: str, headers: dict[str, str],
                             params: Optional[dict[str, str]] = None
                             ) -> Union[dict[str, Any], list[Any]]:
        """Perform a paged HTTP get, combining all paged results in array

        The JSON response must have at least one array member if a dict, the last of which will be
        used as the signal for completed paging when it is empty. The JSON response may also be a
        single array.
        Raises an exception in case of network error.

        Returns the Python equivalent of the JSON data structure (which will be a dict).
        """
        useparams = params.copy() if params else {}
        useparams["per_page"] = PAGINATION
        useparams["page"] = 1
        combined = None

        done = False
        while not done and useparams["page"] <= MAX_RETRIEVED / PAGINATION:
            resp = self.http.get(url, headers=headers, params=useparams)
            resp.raise_for_status()

            j = json.loads(resp.text)
            if isinstance(j, dict):
                # Returned value is dict containing at least one array item
                done = True  # fail safe in case there is no array item
                if not combined:
                    combined = {}
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
                            logging.warning(f'Inconsistent value over pages for {k} '
                                            f'(was {combined[k]}, now {v})')
                        combined[k] = v

            elif isinstance(j, list):
                # Returned value is array
                if not combined:
                    combined = []
                done = not j  # signal for pagination complete
                combined.extend(j)

            else:
                assert False, f"Unexpected return type {type(j)} from API "

            useparams["page"] += 1

        assert combined is not None  # since it hasn't raised an exception this must be true
        return combined

    def get_runs(self, branch: Optional[str] = None, since: Optional[datetime.datetime] = None
                 ) -> dict[str, Any]:
        """Returns info about all recent workflow runs on GitHub Actions"""
        url = BASE_URL.format(owner=self.owner, repo=self.repo, endpoint='runs')
        params = {"status": "completed"}
        if branch:
            params["branch"] = branch
            # Assume we don't want PRs if we supply a specific branch
            params["exclude_pull_requests"] = "true"
        else:
            # Assume we only want PRs if we DON'T supply a specific branch
            params["event"] = "pull_request"
        if since:
            params["created"] = ">" + since.isoformat()

        result = self._http_get_paged_json(url, headers=self._standard_headers(), params=params)
        assert isinstance(result, dict)
        return result

    def get_run(self, run_id: int) -> dict[str, Any]:
        """Returns info about a single workflow run on GitHub Actions"""
        url = RUN_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_jobs(self, run_id: int) -> dict[str, Any]:
        """Returns info about the jobs in a workflow run on GitHub Actions"""
        url = JOBS_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_logs(self, run_id: int) -> tuple[str, Optional[str]]:
        url = LOGS_URL.format(owner=self.owner, repo=self.repo, endpoint='runs', run_id=run_id)
        with self.http.get(url, headers=self._standard_auth_headers(), stream=True) as resp:
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                try:
                    for chunk in resp.iter_content(chunk_size=0x10000):
                        tmp.write(chunk)
                except:  # noqa: E722
                    # Delete the temporary file on exception
                    os.unlink(tmp.name)
                    raise
            content_type = resp.headers.get('Content-Type', None)
        return (tmp.name, content_type)

    def get_pulls(self, state: str) -> list[Any]:
        """Returns info about pull requests"""
        url = PULLS_URL.format(owner=self.owner, repo=self.repo)
        params = {"state": state}
        result = self._http_get_paged_json(url, headers=self._standard_headers(), params=params)
        assert isinstance(result, list)
        return result

    def get_pull(self, pr: int) -> dict[str, Any]:
        """Returns info about a pull request on GitHub Actions"""
        url = PULL_URL.format(owner=self.owner, repo=self.repo, pull_number=pr)
        resp = self.http.get(url, headers=self._standard_headers())
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_commit_status(self, commit: str) -> dict[str, Any]:
        """Returns the status of checks on a commit"""
        url = COMMITS_URL.format(owner=self.owner, repo=self.repo, commit_id=commit)
        result = self._http_get_paged_json(url, headers=self._standard_headers())
        assert isinstance(result, dict)
        return result

    def get_check_runs(self, commit: str) -> dict[str, Any]:
        """Returns the check runs on a commit

        This requires one of the following fine-grained token permissions:
            "Checks" repository permissions (read)
        """
        url = CHECKRUNS_URL.format(owner=self.owner, repo=self.repo, commit_id=commit)
        result = self._http_get_paged_json(url, headers=self._standard_headers())
        assert isinstance(result, dict)
        return result

    def create_comment(self, issue_id: int, comment: str) -> dict[str, Any]:
        """Creates a comment on a GitHub issue or pull request

        This requires one of the following fine-grained token permissions:
            "Issues" repository permissions (write)
            "Pull requests" repository permissions (write)
        """
        url = COMMENTS_URL.format(owner=self.owner, repo=self.repo, issue_number=issue_id)
        data = {'body': comment}
        resp = self.http.post(url, headers=self._standard_auth_headers(), data=json.dumps(data))
        resp.raise_for_status()
        return json.loads(resp.text)

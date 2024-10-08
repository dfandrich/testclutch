"""Retrieve logs from Appveyor runs."""

import json
import logging
from typing import Any, Optional

from testclutch import netreq


# See https://www.appveyor.com/docs/api/
BASE_URL = 'https://ci.appveyor.com/api'
BASE_PROJECT_URL = BASE_URL + '/projects/{account}/{project}'
RUNS_URL = BASE_PROJECT_URL + '/history'
RUN_BY_VERSION_URL = BASE_PROJECT_URL + '/build/{build_ver}'
LOG_URL = 'https://ci.appveyor.com/api/buildjobs/{job_id}/log'

DATA_TYPE = 'application/json'

MAX_RETRIEVED = 1000  # Don't ever retrieve more than this number
PAGINATION = 20       # Number to retrieve at once; maximum 20
CHUNK_SIZE = 0x10000


class AppveyorApi:
    """Retrieve logs from Appveyor runs."""

    def __init__(self, account: str, project: str, token: Optional[str]):
        self.account = account
        self.project = project
        self.token = token
        self.http = netreq.Session()

    def _standard_headers(self) -> dict:
        return {'Accept': DATA_TYPE,
                'Content-Type': DATA_TYPE,
                'User-Agent': netreq.USER_AGENT
                }

    def get_runs(self, branch: str) -> dict[str, Any]:
        """Returns info about all recent workflow runs on Appveyor."""
        # TODO: add date checking to break off pagination early
        combined_resp = {'builds': []}
        last_resp = None
        # Keep getting more runs on: 1) the first time through the loop, 2) if some builds
        # were returned on the last call, and 3) only if we haven't reached the maximum
        while (not combined_resp['builds'] or last_resp['builds']
               ) and len(combined_resp['builds']) < MAX_RETRIEVED:
            url = RUNS_URL.format(account=self.account, project=self.project)
            params = {'branch': branch,
                      'recordsNumber': PAGINATION
                      }
            if 'project' in combined_resp:
                params['startBuildId'] = last_resp['builds'][-1]['buildId']
            logging.debug('Retrieving runs from %s', url)
            with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
                resp.raise_for_status()
                last_resp = json.loads(resp.text)
            if 'project' not in combined_resp:
                combined_resp['project'] = last_resp['project']
            combined_resp['builds'].extend(last_resp['builds'])
        return combined_resp

    def get_run(self, build_id: int) -> dict[str, Any]:
        """Returns info about a single run on Appveyor."""
        url = RUNS_URL.format(account=self.account, project=self.project)
        params = {
            # This API is intended for pagination, so it starts listing # builds EARLIER than
            # the startBuildId, so we must give a value larger than what we want.
            'startBuildId': build_id + 1,
            'recordsNumber': 1,
        }
        logging.debug('Retrieving run from %s', url)
        with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
            resp.raise_for_status()
            run_search = json.loads(resp.text)

        build = run_search['builds'][0]
        if build['buildId'] != build_id:
            raise RuntimeError(f'API error: wanted build_id {build_id}, got {build["buildId"]}')

        # Do another request by version to get the real info
        return self.get_run_by_buildver(build['version'])

    def get_run_by_buildver(self, build_ver: str) -> dict[str, Any]:
        """Returns info about a single run on Appveyor.

        This one is more efficient than get_run() but requires the build version which isn't as
        convenient to find as build_id.
        """
        url = RUN_BY_VERSION_URL.format(account=self.account, project=self.project,
                                        build_ver=build_ver)
        logging.debug('Retrieving run by version from %s', url)
        with self.http.get(url, headers=self._standard_headers()) as resp:
            resp.raise_for_status()
            return json.loads(resp.text)

    def get_logs(self, job_id: str) -> tuple[str, str]:
        """Retrieve log file for a job."""
        url = LOG_URL.format(job_id=job_id)
        params = {'fullLog': 'true'
                  }
        logging.debug('Retrieving log from %s', url)
        with self.http.get(url, headers=self._standard_headers(), params=params, stream=True
                           ) as resp:
            return netreq.download_file(resp, url)

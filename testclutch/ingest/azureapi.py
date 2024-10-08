"""Retrieve logs from Azure Devops runs."""

import datetime
import json
import logging
from typing import Any, Optional

from testclutch import netreq


# https://learn.microsoft.com/en-us/rest/api/azure/devops/?view=azure-devops-rest-7.1
API_VERSION_A = '7.1-preview.7'
API_VERSION_B = '7.1-preview.2'
BASE_URL = 'https://dev.azure.com/{organization}/{project}/_apis'

LIST_BUILDS_URL = BASE_URL + '/build/builds'
GET_BUILD_URL = BASE_URL + '/build/builds/{build_id}'
GET_BUILD_TIMELINES_URL = GET_BUILD_URL + '/timeline'
LOGS_URL = GET_BUILD_URL + '/logs/{log_id}'

# This doesn't seem to be part of any formalized API
VIEW_LOG_URL = 'https://dev.azure.com/{organization}/{project}/_build/results?buildId={build_id}&view=logs&j={job_uuid}&t={log_uuid}'

DATA_TYPE = 'application/json'

CHUNK_SIZE = 0x10000
MAX_RETRIEVED = 1000  # Don't ever retrieve more than this number


class AzureApi:
    """Retrieve logs from Azure Devops runs."""

    def __init__(self, organization: str, project: str):
        self.organization = organization
        self.project = project
        self.http = netreq.Session()

    def _standard_headers(self) -> dict:
        return {'Accept': DATA_TYPE,
                'Content-Type': DATA_TYPE,
                'User-Agent': netreq.USER_AGENT
                }

    def get_builds(self, branch: Optional[str], hours: int) -> dict[str, Any]:
        """Returns info about all recent builds."""
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        url = LIST_BUILDS_URL.format(organization=self.organization, project=self.project)
        logging.debug('Retrieving builds from %s', url)
        # TODO: there are a few more filters that are probably useful (e.g.
        # repositoryId, which seems to be a UUID), reasonFilter
        params = {'$top': MAX_RETRIEVED,
                  'repositoryType': 'git',
                  'statusFilter': 'completed',
                  'minTime': since.isoformat(),
                  'api-version': API_VERSION_A
                  }
        if branch:
            params['branchName'] = branch
        with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
            resp.raise_for_status()
            return json.loads(resp.text)

    def get_build(self, build_id: int) -> dict[str, Any]:
        """Returns info about a build."""
        url = GET_BUILD_URL.format(organization=self.organization, project=self.project,
                                   build_id=build_id)
        logging.debug('Retrieving build from %s', url)
        params = {'api-version': API_VERSION_A,
                  'propertyFilters': 'Build'
                  }
        with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
            # Note: this can return 203 (Non-Authoritative Information) in case of bad account name,
            # which is not one of the errors to be raised.
            # TODO: perhaps treat that one similarly here, but consider that 203 is not intended as
            # as an error code.
            resp.raise_for_status()
            return json.loads(resp.text)

    def get_build_timelines(self, build_id: int) -> dict[str, Any]:
        """Returns timeline for a build."""
        url = GET_BUILD_TIMELINES_URL.format(organization=self.organization, project=self.project,
                                             build_id=build_id)
        logging.debug('Retrieving build timeline from %s', url)
        params = {'api-version': API_VERSION_B,
                  'propertyFilters': 'Build'
                  }
        with self.http.get(url, headers=self._standard_headers(), params=params) as resp:
            resp.raise_for_status()
            return json.loads(resp.text)

    def get_logs(self, build_id: int, log_id: int) -> tuple[str, str]:
        url = LOGS_URL.format(organization=self.organization, project=self.project,
                              build_id=build_id, log_id=log_id)
        logging.info('Retrieving log from %s', url)
        with self.http.get(url, stream=True) as resp:
            return netreq.download_file(resp, url)

    def get_build_log_url(self, build_id: int, job_uuid: str, log_uuid: str) -> str:
        return VIEW_LOG_URL.format(project=self.project, organization=self.organization,
                                   build_id=build_id, log_uuid=log_uuid, job_uuid=job_uuid)

"""Retrieve logs from Cirrus CI runs
"""

import json
import logging
from typing import Any

from testclutch import netreq
from testclutch import urls


HTTPError = netreq.HTTPError

# See https://cirrus-ci.org/api/
GRAPHQL_URL = 'https://api.cirrus-ci.com/graphql'
LOGS_URL = 'https://api.cirrus-ci.com/v1/task/{task_id}/logs/{command_name}.log'
DATA_TYPE = 'application/json'

MAX_RETRIEVED = 1000  # Don't ever retrieve more than this number

# GraphQL schema is at https://github.com/cirruslabs/cirrus-ci-web/blob/master/schema.gql
# Retrieve a list of test runs
RUNS_GRAPHQL = r"""
query OwnerRepositoryQuery(
  $platform: String!
  $owner: String!
  $name: String!
  $branch: String
  $numbuilds: Int
) {
  ownerRepository(platform: $platform, owner: $owner, name: $name) {
    ...RepositoryBuildList_repository_SmLDq
    id
  }
}

fragment BuildBranchNameChipNew_build on Build {
  id
  branch
  tag
  repository {
    id
    owner
    name
  }
}

fragment BuildCard_build on Build {
  id
  status
  changeMessageTitle
  buildCreatedTimestamp
  clockDurationInSeconds
  changeIdInRepo
  pullRequest
  repository {
    ...RepositoryNameChipNew_repository
    ...RepositoryOwnerChipNew_repository
    id
  }
  ...BuildBranchNameChipNew_build
}

fragment CreateBuildDialog_repository on Repository {
  id
  owner
  name
  masterBranch
}

fragment RepositoryBuildList_repository_SmLDq on Repository {
  id
  platform
  owner
  name
  viewerPermission
  ...CreateBuildDialog_repository
  builds(last: $numbuilds, branch: $branch) {
    edges {
      node {
        ...BuildCard_build
      }
    }
  }
}

fragment RepositoryNameChipNew_repository on Repository {
  owner
  name
}

fragment RepositoryOwnerChipNew_repository on Repository {
  owner
}
"""

# Retrieve information about one test run
RUN_GRAPHQL = r"""
query BuildByIdQuery(
  $buildId: ID!
) {
  build(id: $buildId) {
    ...BuildDetails_build
    ...AppBreadcrumbs_build
    id
  }
  viewer {
    ...AppBreadcrumbs_viewer
    id
  }
}

fragment AccountSwitch_viewer on User {
  relatedOwners {
    platform
    name
  }
}

fragment AppBreadcrumbs_build on Build {
  id
  branch
  changeIdInRepo
  repository {
    id
    platform
    owner
    name
  }
}

fragment AppBreadcrumbs_viewer on User {
  ...AccountSwitch_viewer
}

fragment BuildCreatedChip_build on Build {
  id
  buildCreatedTimestamp
}

fragment BuildDebuggingInformation_build on Build {
  parsingResult {
    outputLogs
    environment
  }
}

fragment BuildDetails_build on Build {
  id
  branch
  status
  changeIdInRepo
  pullRequest
  changeMessageTitle
  ...BuildCreatedChip_build
  ...BuildStatusChip_build
  notifications {
    message
    ...Notification_notification
  }
  ...ConfigurationWithIssues_build
  ...BuildDebuggingInformation_build
  latestGroupTasks {
    id
    name
    status
    creationTimestamp
    executingTimestamp
    durationInSeconds
    requiredGroups
    instanceArchitecture
    instancePlatform
    artifacts {
      name
      type
      format
      files {
        path
      }
    }
    ...TaskList_tasks
  }
  repository {
    cloneUrl
    viewerPermission
    id
  }
  hooks {
    ...HookList_hooks
    id
  }
}

fragment BuildStatusChip_build on Build {
  id
  status
  durationInSeconds
  clockDurationInSeconds
}

fragment ConfigurationWithIssues_build on Build {
  parsingResult {
    issues {
      level
      message
      path
      line
      column
    }
  }
}

fragment HookCreatedChip_hook on Hook {
  id
  timestamp
}

fragment HookListRow_hook on Hook {
  id
  ...HookStatusChip_hook
  ...HookCreatedChip_hook
  ...HookNameChip_hook
}

fragment HookList_hooks on Hook {
  id
  timestamp
  ...HookListRow_hook
}

fragment HookNameChip_hook on Hook {
  id
  name
}

fragment HookStatusChip_hook on Hook {
  info {
    error
    durationNanos
  }
}

fragment Notification_notification on Notification {
  level
  message
  link
}

fragment TaskCreatedChip_task on Task {
  creationTimestamp
}

fragment TaskDurationChip_task on Task {
  id
  status
  creationTimestamp
  scheduledTimestamp
  executingTimestamp
  durationInSeconds
}

fragment TaskListRow_task on Task {
  id
  status
  executingTimestamp
  scheduledTimestamp
  finalStatusTimestamp
  commands {
    name
  }
  ...TaskDurationChip_task
  ...TaskNameChip_task
  ...TaskCreatedChip_task
  uniqueLabels
}

fragment TaskList_tasks on Task {
  id
  localGroupId
  requiredGroups
  executingTimestamp
  scheduledTimestamp
  finalStatusTimestamp
  ...TaskListRow_task
}

fragment TaskNameChip_task on Task {
  id
  name
}
"""


class CirrusApi:
    def __init__(self, checkurl: str, token: str):
        account, project = urls.get_project_name(checkurl)
        self.owner = account
        self.repo = project
        if urls.url_host(checkurl) != 'github.com':
            raise RuntimeError('Unsupported checkurl ' + checkurl)
        self.platform = 'github'
        self.token = token
        self.http = netreq.Session()

    def _standard_headers(self) -> dict:
        return {'Accept': DATA_TYPE,
                'User-Agent': netreq.USER_AGENT
                }

    def query_graphql(self, query: str, var: dict) -> dict:
        """Send a GraphQL query to the server and return the raw Python data response"""
        jsonreq = {'query': query,
                   'variables': var,
                   }
        resp = self.http.post(GRAPHQL_URL, headers=self._standard_headers(),
                              data=json.dumps(jsonreq))
        resp.raise_for_status()
        return json.loads(resp.text)

    def get_runs(self, branch: str) -> dict[str, Any]:
        """Returns info about all recent workflow runs on Cirrus CI

        If branch is an empty string, no branch matching is performed.
        """
        var = {'platform': self.platform,
               'owner': self.owner,
               'name': self.repo,
               'branch': branch,
               'numbuilds': MAX_RETRIEVED
               }
        return self.query_graphql(RUNS_GRAPHQL, var)

    def get_run(self, run_id: int) -> dict[str, Any]:
        var = {'buildId': run_id
               }
        return self.query_graphql(RUN_GRAPHQL, var)

    def get_logs(self, task_id: int, command_name: str) -> tuple[str, str]:
        url = LOGS_URL.format(task_id=task_id, command_name=command_name)
        logging.info('Retrieving log from %s', url)
        with self.http.get(url, headers=self._standard_headers(), stream=True) as resp:
            return netreq.download_file(resp, url)

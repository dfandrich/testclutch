"""Code to get GitHub pull request logs from results on Azure
"""

import logging
from typing import List, Tuple

from testclutch import config
from testclutch.ingest import azure
from testclutch.logdef import TestCases, TestMeta


class AzureAnalyzer(azure.AzureIngestor):
    """Azure log analyzer

    Based on AzureIngestor but with the store method replaced to store log data instead
    and methods to retrieve by PR.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.clear_test_results()

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        "Store test results in a list"
        self.test_results.append((meta, testcases))

    def clear_test_results(self):
        self.test_results = []  # type: List[Tuple[TestMeta, TestCases]]

    def _find_matching_runs(self, pr: int, hours: int) -> List[int]:
        matches = []
        # Don't specify the branch in order to pick up PRs
        # There is a parameter in build['parameters'], namely system.pullRequest.targetBranch that
        # could be compared to the branch we want, but 1) it seems to be JSON embedded in JSON, and
        # 2) we don't really care about the branch as long as the PR number matches.
        builds = self.azure.get_builds(None, hours)
        for build in builds['value']:
            if (build['status'] == 'completed'
                and 'pr.sourceSha' in build['triggerInfo']
                    and int(build['triggerInfo']['pr.number']) == pr):
                matches.append(build['id'])
        return matches

    def gather_pr(self, pr: int) -> List[Tuple[TestMeta, TestCases]]:
        self.clear_test_results()
        found = self._find_matching_runs(pr, config.get('pr_age_hours_default'))
        if not found:
            # Nothing found recently; expand the search much longer
            found = self._find_matching_runs(pr, config.get('pr_age_hours_max'))

        logging.debug(f'Found {len(found)} builds')
        for build in found:
            self.ingest_a_run(build)
            # Only look at the first build found
            break
        return self.test_results

"""Code to get GitHub pull request logs from results on Azure
"""

import logging

from testclutch import config
from testclutch.ingest import azure
from testclutch.logdef import ParsedLog, TestCases, TestMeta


class AzureAnalyzer(azure.AzureIngestor):
    """Azure PR log analyzer

    Based on AzureIngestor but with the store method replaced to store log data instead
    and methods to retrieve by PR.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.clear_test_results()

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        """Store test results in a list

        This overrides the method in the base class.
        """
        self.test_results.append((meta, testcases))

    def clear_test_results(self):
        self.test_results = []  # type: list[ParsedLog]

    def _find_matching_runs(self, pr: int, hours: int) -> list[int]:
        """Find runs for the given PR made within the given number of hours

        Returns runs for all commits on this PR (if there were runs for more than one) in reverse
        chronological order (most recent first).
        """
        matches = []
        # Don't specify the branch in order to pick up PR runs
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

    def gather_pr(self, pr: int) -> list[ParsedLog]:
        self.clear_test_results()
        found = self._find_matching_runs(pr, config.get('pr_age_hours_default'))
        if not found:
            # Nothing found recently; expand the search much longer
            found = self._find_matching_runs(pr, config.get('pr_age_hours_max'))

        logging.info(f'Found {len(found)} runs; only looking at the most recent one')
        if found:
            # Only look at the first (most recent) build found
            self.ingest_a_run(found[0])
        return self.test_results

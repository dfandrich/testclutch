"""Code to get GitHub pull request logs from results on Appveyor
"""

import logging

from testclutch import config
from testclutch.ingest import appveyor
from testclutch.logdef import ParsedLog, TestCases, TestMeta


class AppveyorAnalyzeJob(appveyor.AppveyorIngestor):
    """Appveyor PR log analyzer

    Based on AppveyorIngestor but with the store method replaced to store log data instead
    and methods to retrieve by PR.
    """
    def __init__(self, *args):
        super().__init__(*args)
        self.test_results = []  # type: list[ParsedLog]

    def store_test_run(self, logmeta: TestMeta, testcases: TestCases):
        """Store test results in a list

        This overrides the method in the base class.
        """
        self.test_results.append((logmeta, testcases))

    def find_for_pr(self, pr: int) -> list[str]:
        "Returns the build version for runs for this pr"
        # Start with a list of ALL recent completed runs
        branch = config.expand('branch')
        runs = self.av.get_runs(branch)
        results = []
        for job in runs['builds']:
            # Only look at completed runs
            if (job['status'] in frozenset(('success', 'failed', 'cancelled'))
                    and 'pullRequestId' in job and int(job['pullRequestId']) == pr):
                results.append(job['version'])
        return results

    def gather_pr(self, pr: int) -> list[ParsedLog]:
        # Clear any earlier results and start again
        self.test_results = []
        buildvers = self.find_for_pr(pr)
        if not buildvers:
            logging.error('No Appveyor run found for PR#%d', pr)
        logging.info(f'Found {len(buildvers)} runs; only looking at the most recent')
        if buildvers:
            self.ingest_a_run_by_buildver(buildvers[0])
        return self.test_results

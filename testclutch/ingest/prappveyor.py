"""Code to get GitHub pull request logs from results on Appveyor
"""

import logging
from typing import Optional

from testclutch import config
from testclutch import db
from testclutch.ingest import appveyor
from testclutch.ingest import appveyorapi
from testclutch.logdef import ParsedLog, TestCases, TestMeta


class AppveyorAnalyzeJob:
    def __init__(self, account: str, project: str, repo: str, ds: db.Datastore,
                 token: Optional[str]):
        self.account = account
        self.project = project
        self.repo = repo
        self.av = appveyorapi.AppveyorApi(account, project, token)
        self.avi = appveyor.AppveyorIngestor(account, project, repo, ds, token)
        self.ds = ds
        self.test_results = []  # type: list[ParsedLog]

    def gather_log(self, logmeta: TestMeta, testcases: TestCases):
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
            self.avi.process_a_run_by_buildver(buildvers[0], self.gather_log)
        return self.test_results

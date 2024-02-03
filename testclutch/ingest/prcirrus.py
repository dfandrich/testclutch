"""Code to get GitHub pull request logs from results on Cirrus CI
"""

import logging
from typing import List, Tuple

from testclutch.ingest import cirrus
from testclutch.logdef import TestCases, TestMeta


class CirrusAnalyzer(cirrus.CirrusIngestor):
    """Cirrus log analyzer

    Based on CirrusIngestor but with the store method replaced to store log data instead
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

    def _find_matching_runs(self, pr: int, branch: str) -> List[int]:
        matches = []
        rsp = self.cirrus.get_runs(branch)
        for run in rsp['data']['ownerRepository']['builds']['edges']:
            node = run['node']
            if (node['status'] in frozenset(('ABORTED', 'FAILED', 'COMPLETED')) and
                    node['pullRequest'] == pr):
                matches.append(int(node['id']))
        return matches

    def gather_pr(self, pr: int) -> List[Tuple[TestMeta, TestCases]]:
        self.clear_test_results()
        found = self._find_matching_runs(pr, '')
        logging.debug(f'Found {len(found)} builds')
        for build in found:
            self.ingest_a_run(build)
            # Only look at the first build found
            break
        return self.test_results

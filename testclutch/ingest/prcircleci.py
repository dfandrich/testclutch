"""Code to get GitHub pull request logs from results on Circle CI
"""

import logging

from testclutch import urls
from testclutch.ingest import circleci
from testclutch.logdef import ParsedLog, TestCases, TestMeta


class CircleAnalyzer(circleci.CircleIngestor):
    """Circle PR log analyzer

    Based on CircleIngestor but with the store method replaced to store log data instead
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

    def find_for_pr(self, pr: int) -> list[int]:
        "Returns the runs for this PR"
        # Start with a list of ALL recent completed runs
        builds = []
        runs = self.circle.get_runs()
        logging.debug('Search found %d runs', len(runs))
        for run in runs:
            if (run['lifecycle'] == 'finished'
                    and run['pull_requests']):
                url = run['pull_requests'][0]['url']
                build_pr = urls.url_pr(url)
                if pr == build_pr:
                    logging.debug('Found build %s on branch %s', run['build_num'], run['branch'])
                    builds.append(run['build_num'])

        logging.info('Found %d runs for PR#%d', len(builds), pr)
        return builds

    def gather_pr(self, pr: int) -> list[ParsedLog]:
        # Clear any earlier results and start again
        self.test_results = []
        builds = self.find_for_pr(pr)
        for build in builds:
            self.ingest_a_run(build)
        return self.test_results

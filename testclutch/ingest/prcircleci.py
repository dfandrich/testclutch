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

    def _find_for_pr(self, pr: int) -> list[int]:
        """Find runs for the given PR

        Only return runs for the most recent commit, if there were runs for more than one.
        """
        # Start with a list of ALL recent completed runs
        matchingpr = []
        runs = self.circle.get_runs()
        logging.debug('Search found %d runs', len(runs))
        for run in runs:
            if (run['lifecycle'] == 'finished'
                    and run['pull_requests']):
                url = run['pull_requests'][0]['url']
                build_pr = urls.url_pr(url)
                if pr == build_pr:
                    logging.debug('Found build %s on branch %s', run['build_num'], run['branch'])
                    matchingpr.append((run['build_num'], run['vcs_revision']))

        # matchingpr now contains all runs for this PR, which could cover more than one git commit
        # if the user pushed several that were run separately. Keep only the runs on the most recent
        # commit by sorting by build ID and filtering for the commit handled by the most recent one.
        builds = []
        if matchingpr:
            mostrecentcommit = max(matchingpr, key=lambda x: x[0])[1]
            logging.info(f'Only getting runs for the most recent commit {mostrecentcommit:.9}')
            builds = [match[0] for match in matchingpr if match[1] == mostrecentcommit]
        return builds

    def gather_pr(self, pr: int) -> list[ParsedLog]:
        # Clear any earlier results and start again
        self.test_results = []
        builds = self._find_for_pr(pr)
        logging.info('Found %d runs for PR#%d', len(builds), pr)
        for build in builds:
            self.ingest_a_run(build)
        return self.test_results

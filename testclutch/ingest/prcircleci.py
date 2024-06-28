"""Code to get GitHub pull request logs from results on Circle CI
"""

import logging
import urllib
from typing import List

from testclutch import db
from testclutch import urls
from testclutch.ingest import circleci
from testclutch.ingest import circleciapi
from testclutch.logdef import ParsedLog, TestCases, TestMeta


class CircleAnalyzer:
    def __init__(self, repo: str, ds: db.Datastore):
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(repo)
        safe_path = circleci.sanitize_path(path)
        self.repo = f'{netloc}{safe_path}'
        self.circle = circleciapi.CircleApi(repo)
        self.circlei = circleci.CircleIngestor(repo, ds)
        self.ds = ds
        self.test_results = []  # type: List[ParsedLog]

    def gather_log(self, logmeta: TestMeta, testcases: TestCases):
        self.test_results.append((logmeta, testcases))

    def find_for_pr(self, pr: int) -> List[int]:
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

    def gather_pr(self, pr: int) -> List[ParsedLog]:
        # Clear any earlier results and start again
        self.test_results = []
        builds = self.find_for_pr(pr)
        for build in builds:
            self.circlei.process_a_run(build, self.gather_log)
        return self.test_results

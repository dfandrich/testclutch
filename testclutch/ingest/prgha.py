"""Code to get GitHub pull request logs from results on GitHub Actions
"""

import datetime
import logging
from typing import List, Optional, Tuple

from testclutch import config
from testclutch import db
from testclutch.ingest import gha
from testclutch.ingest import ghaapi
from testclutch.logdef import TestCases, TestMeta


# We're only interested in pull requests here
PR_EVENT = 'pull_request'


class GithubAnalyzeJob:
    def __init__(self, owner: str, repo: str, token: str, ds: db.Datastore):
        self.owner = owner
        self.repo = repo
        self.ds = ds
        self.gh = ghaapi.GithubApi(owner, repo, token)
        self.ghi = gha.GithubIngestor(owner, repo, token, ds)
        self.test_results = []  # type: List[Tuple[TestMeta, TestCases]]
        self.prmeta = {}  # type: TestMeta

    def _is_matching_run(self, run: TestMeta, commit: str) -> bool:
        return (run['event'] == PR_EVENT and
                run['status'] == 'completed' and
                run['head_sha'] == commit)

    def _find_matching_runs(self, commit: str, since: Optional[datetime.datetime]) -> List[int]:
        "Find all runs on PRs for a particular commit"
        found = []
        for run in self.gh.get_runs(since=since)['workflow_runs']:
            if self._is_matching_run(run, commit):
                # Found a matching run
                found.append(run['id'])
                logging.debug('Found run %s from %s, %s', run['id'], run['created_at'], run['name'])
        return found

    def find_for_pr(self, pr: int) -> List[int]:
        pr_info = self.gh.get_pull(pr)
        commit = pr_info['head']['sha']
        logging.debug(f'PR#{pr} is about commit {commit:.9}')

        found = self._find_matching_runs(
            commit,
            since=datetime.datetime.now() - datetime.timedelta(
                hours=config.get('pr_age_hours_default'))
        )
        if not found:
            logging.info(f'No PR#{pr} runs found in the last {config.get("pr_age_hours_default")} '
                         f'hours; trying again for {config.get("pr_age_hours_max")} hours')
            found = self._find_matching_runs(
                commit,
                since=datetime.datetime.now() - datetime.timedelta(
                    hours=config.get('pr_age_hours_max'))
            )
        logging.debug('Found %d matching runs', len(found))
        return found

    def gather_log(self, logmeta: TestMeta, testcases: TestCases):
        meta = {**self.prmeta, **logmeta}
        if meta['trigger'] != 'pull_request':
            logging.info(f"Log is due to {meta['trigger']}, not a pull request; skipping")
            return

        self.test_results.append((meta, testcases))

    def gather_pr(self, pr: int) -> List[Tuple[TestMeta, TestCases]]:
        # Clear any earlier results and start again
        self.test_results = []
        self.prmeta = {}
        runs = self.find_for_pr(pr)
        if not runs:
            logging.error('No GHA run found for PR#%d', pr)
        # TODO: we really only want to look at the most recent run, not all of them
        # But, we want all jobs in that run, even when configured from different sources
        for run_id in runs:
            self.prmeta = {'pullrequest': pr}
            self.ghi.process_a_run(run_id, self.gather_log)
        return self.test_results

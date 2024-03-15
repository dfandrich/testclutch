"""Code to perform analysis of test data.
"""

import collections
import datetime
import logging
import textwrap
from dataclasses import dataclass
from html import escape
from typing import Dict, List, Optional, Set, Tuple, Union

import testclutch
from testclutch import config
from testclutch import db
from testclutch.gitdef import CommitInfo
from testclutch.logdef import TestMeta
from testclutch.testcasedef import TestResult

# TODO: python >= 3.9 allows collections.Counter instead of Dict
# record_id, jobtime, {test: count}
TestFailCount = Tuple[int, int, Dict[str, int]]

# Select a set of all the unique test jobs. The uniqueness is a single string which
# is the concatenation of: [account,]repo,origin,uniquejobname
# NOTE: THIS ISN'T FILTERED BY repo
# UNIQUE_JOBS = r"SELECT DISTINCT GROUP_CONCAT(value) uniquejob FROM testrunmeta WHERE name IN ('uniquejobname', 'origin', 'account', 'checkrepo') GROUP BY id ORDER BY uniquejob"

# Returns testids for all tests matching a repo
REPO_ID_SQL = r"SELECT id FROM testruns WHERE repo=?"

# Select a set of all the unique test jobs on a repo. The uniqueness is a single string which
# is the concatenation of: [account,]repo,origin,uniquejobname
UNIQUE_JOBS_SQL = f"SELECT DISTINCT GROUP_CONCAT(value) uniquejob FROM testrunmeta INNER JOIN ({REPO_ID_SQL}) AS repoid ON repoid.id = testrunmeta.id WHERE name IN ('uniquejobname', 'origin', 'account', 'checkrepo') GROUP BY testrunmeta.id ORDER BY uniquejob"

# Select the id and unique job name for each test run
# This includes runs from pull requests, which must be removed later if undesired
RUNS_WITH_UNIQUE_JOB_SQL = r"SELECT id, GROUP_CONCAT(value) uniquejob FROM testrunmeta WHERE name IN ('uniquejobname', 'origin', 'account', 'checkrepo') GROUP BY id ORDER BY name"

# Select the set of IDs of jobs that match a particular unique job name, sorted down by time
# The unique job identifier comes from the RUNS_WITH_UNIQUE_JOB_SQL query.
# This includes runs from pull requests, which must be removed later if undesired
RUNS_BY_UNIQUE_JOB_SQL = f"SELECT testruns.id, testruns.time from ({RUNS_WITH_UNIQUE_JOB_SQL}) AS runs INNER JOIN testruns ON testruns.id=runs.id WHERE uniquejob=? AND testruns.time >= ? AND testruns.time < ? ORDER BY testruns.time DESC"

# Internal configuration consistency checks
assert config.get('flaky_builds_min') >= config.get('flaky_failures_min') * 2
assert (config.get('flaky_builds_min')
        >= config.get('report_consecutive_failures') * 2 + config.get('flaky_failures_min'))


@dataclass
class TestJobInfo:
    """Information about a test job"""
    testid: int   # testid (a.k.a. test run record ID in the database)
    jobtime: int  # timestamp of job
    failed_tests: List[str]      # list of failed test names
    attempted_tests: List[str]   # list of attempted test names
    successful_tests: List[str]  # list of successful test names
    url: str                     # URL to web page about the job
    checkrepo: str               # source code repository
    commit: str                  # git commit hash
    is_aborted: bool             # whether the job timed out or aborted
    test_result: str             # what the test suite thought about the tests


class ResultsOverTimeByUniqueJob:
    def __init__(self, ds: db.Datastore):
        self.ds = ds
        self.all_jobs_status = []  # type: List[TestJobInfo]

    @staticmethod
    def _try_integer(val: str) -> Union[int, str]:
        """Try to convert the value to an integer, but return string if it cannot

        Use a a sort key function to sort numeric test names by numeric value and string
        test names alphabetically.  A more general alternative would be natsort.natsorted()
        """
        try:
            return int(val)
        except ValueError:
            return val

    def make_global_unique_job(self, meta: TestMeta) -> str:
        """The concatenation of: [account,]repo,origin,uniquejobname

        This is used as a key to get info on a unique job name.
        """
        maybe_account = meta['account'] + ',' if 'account' in meta else ''
        return f"{maybe_account}{meta['checkrepo']},{meta['origin']},{meta['uniquejobname']}"

    def check_aborted(self, meta: TestMeta) -> bool:
        "Check if the tests's metadata indicates an aborted test run"
        if meta['origin'] == 'circle' and meta.get('cistepresult', '') == 'timedout':
            return True
        if meta['origin'] == 'azure' and meta.get('cistepresult', '') == 'canceled':
            return True
        if meta['origin'] == 'cirrus' and meta['ciresult'] == 'aborted':
            return True
        # This was only added 2023-08-03
        if (meta['origin'] == 'gha'
                and 'cistepresult' in meta and meta['cistepresult'] == 'cancelled'):
            return True
        # There seems to be no way to unambiguously determine this on Appveyor (checking if
        # the test run time >1h is too brittle).

        # This is a generic method that should work anywhere
        if meta.get('testresult', '') == 'truncated':
            return True
        return False

    def find_first_failing_job(self, testname: str, num_fails: int) -> Optional[TestJobInfo]:
        """First test run that started failing

        num_fails is the index into self.all_jobs_status of the entry prior to the
        first one that failed.
        """
        assert num_fails < len(self.all_jobs_status)
        first_test_fail = self.all_jobs_status[num_fails - 1]
        logging.debug('test %s commit #%s', testname, first_test_fail.testid)
        # Keep searching backwards until we find a run that did succeed,
        # or we reach the end of the list. This gives the oldest possible
        # commit+1 that introduced the failure.

        # See if test was attempted in a previous run. If so, it probably
        # succeeded (since it wasn't in the fail list) but this isn't definite
        # (it might have been aborted, for example).
        # But, that commit appears to have changed how the test worked, even
        # if it was previously skipped or fail ignored, so it's still probably
        # the right thing to give the user.

        # TODO: these runs are in order by date, but might not necessarily be
        # in order by commit, if a commit run was delayed.
        last_good = None
        for run in range(num_fails, len(self.all_jobs_status)):
            last_job_status = self.all_jobs_status[run]
            if testname in last_job_status.successful_tests:
                logging.debug('Found a success; last good test run #%d', run)
                last_good = last_job_status
                break
            elif testname in last_job_status.attempted_tests:
                logging.debug('Only attempted (not run) in run #%d', run)
            elif testname in last_job_status.failed_tests:
                logging.debug('Hmmm...another failure run #%d', run)
            else:
                logging.debug('No sign of test in #%d', run)
                # TODO: maybe treat this the same as success; it will be in
                # the case of a new test. If so, check to the end of the runs
                # to make sure it never shows up again. Still, it's not
                # always going to be correct

        else:
            logging.info(
                "None of the prior test runs attempted to run this test")
        return last_good

    def load_unique_job(self, unique: str, from_time: int, to_time: int):
        """Load tests for the unique job name"""
        assert self.ds.cur  # satisfy pytype that this isn't None
        self.ds.cur.execute(RUNS_BY_UNIQUE_JOB_SQL, (unique, from_time, to_time))
        testids = self.ds.cur.fetchall()
        self.all_jobs_status = []
        # Iterate over all jobs for this unique job name
        for testid, jobtime in testids:
            # Retrieve metadata for this run
            meta = self.ds.collect_meta(testid)
            if meta.get('pullrequest', 0):
                # skip pull requests
                continue
            url = meta.get('url', '')
            commit = meta.get('commit', '')
            is_aborted = self.check_aborted(meta)
            test_result = meta.get('testresult', 'unknown')

            # Get test cases for this job
            testcases = self.ds.select_test_results(testid)

            # Split test cases into categories
            failed_tests = []
            attempted_tests = []
            success_tests = []
            skipped_statuses = frozenset((TestResult.UNKNOWN, TestResult.SKIP))
            for tc in testcases:
                if tc[1] == TestResult.PASS:
                    # All tests that succeeded
                    success_tests.append(tc[0])
                elif tc[1] == TestResult.FAIL:
                    # All tests that failed
                    failed_tests.append(tc[0])
                if tc[1] not in skipped_statuses:
                    # All tests that were attempted to be run
                    attempted_tests.append(tc[0])

            # Sort the lists
            failed_tests.sort(key=self._try_integer)
            attempted_tests.sort(key=self._try_integer)
            success_tests.sort(key=self._try_integer)

            self.all_jobs_status.append(TestJobInfo(testid, jobtime,
                                        failed_tests, attempted_tests, success_tests, url,
                                        meta['checkrepo'], commit, is_aborted, test_result))

    def find_commit_range(self, last_good: TestJobInfo, first_fail: TestJobInfo
                          ) -> Tuple[CommitInfo, int]:
        "Walk the commit chain to find all the commits in a range"
        logging.debug('Looking up commits before %s', last_good.commit)
        branch = config.expand('branch')
        commits = self.ds.select_all_commit_after_commit(
            last_good.checkrepo, branch, last_good.commit)
        # List must have at least one good and one bad commit
        assert len(commits) >= 2
        first_bad = commits[-2]  # commit immediately before the good one

        # Count the commits in the range
        for i, commit in enumerate(commits):
            if commit.commit_hash == first_bad.commit_hash:
                first_bad_index = i
            if commit.commit_hash == first_fail.commit:
                fail_index = i
        commit_range = first_bad_index - fail_index + 1
        return (first_bad, commit_range)

    def recent_failed_link(self, testname: str) -> str:
        "Find a link for the most recent test failure for this test"
        for job_status in self.all_jobs_status:
            if testname in job_status.failed_tests:
                if job_status.url:
                    return job_status.url
        return ''

    def report_permafail(self, testname: str, num_fails: int) -> str:
        assert num_fails >= 1  # only call this with a failed test
        msg = "<internal error>"
        # Make sure that the count+1 test shows a succeeded test (not unknown).
        if num_fails >= len(self.all_jobs_status):
            # Bypass all the analysis below when there's no point. The end result
            # will be the same, anyway.
            msg = (f'Test {testname} has been failing too long to know '
                   'when the problem started')
        else:
            # First test run that started failing
            last_good = self.find_first_failing_job(testname, num_fails)
            if not last_good:
                msg = ('The commit that introduced this failure '
                       'could not be determined (it may be failing for too long)')
            else:
                # Walk the commit chain to find all the commits in which the
                # problem may have started
                first_test_fail = self.all_jobs_status[num_fails - 1]
                first_bad, commit_range = self.find_commit_range(
                    last_good, first_test_fail)
                if first_test_fail.commit == first_bad.commit_hash:
                    msg = (f"Failures started with commit {first_bad.commit_hash:.9} "
                           f"(last success: {last_good.url}")
                else:
                    msg = (f"Failures started somewhere in the commit range "
                           f"{first_bad.commit_hash:.9}^..{first_test_fail.commit:.9} "
                           f"({commit_range} possible commits) "
                           f"(last success: {last_good.url}")
        return msg

    def analyze_by_unique_job(self, globaluniquejob: str):
        """Analyze a unique job series

        globaluniquejob is the concatenation of metadata fields:
          [account,]repo,origin,uniquejobname
        """
        print(f'Analyzing unique job {globaluniquejob}')
        flaky, first_failure = self.prepare_uniquejob_analysis(globaluniquejob)
        if flaky:
            print("These tests were found to be flaky:")
            flaky.sort(key=lambda x: self._try_integer(x[0]))
            for testname, ratio in flaky:
                urltext = (f" (latest failure: {url})"
                           if (url := self.recent_failed_link(testname)) else "")
                print(f'{testname} fails {ratio * 100:.1f}%{urltext}')

        if self.all_jobs_status:
            # Look at the most recent run to determine what is still failing
            job_status = self.all_jobs_status[0]
            if job_status.failed_tests:
                # Latest job has failed. See how long it has been failing.
                # TODO: can I get the info from first_failure somewhere else instead?
                _, _, current_failure_counts = first_failure
                permafails = [failure for failure in job_status.failed_tests
                              if (current_failure_counts[failure]
                                  > config.get('permafail_failures_min'))]
                if permafails:
                    if job_status.test_result == 'success':
                        print("Some tests are failing but the test was marked as successful. "
                              "These tests were likely marked to be ignored.")
                    print("These tests are now consistently failing:")
                    permafails.sort(key=self._try_integer)
                    for testname in permafails:
                        print(testname)

                    # Now, find the commit (or range of commits) that introduced this error.
                    # TODO: Get job number by getting the count from unique_failures and
                    # looking in all_jobs_status to get the testid
                    # - return a range of commits, if there were no builds between two
                    # candidates
                    for testname in permafails:
                        num_fails = current_failure_counts[testname]
                        print(self.report_permafail(testname, num_fails))

                    print('Latest failure:', job_status.url)

            elif job_status.is_aborted:
                print("No tests are currently failing on this job but the last test run aborted, "
                      "probably due to a timeout")
        print()

    def analyze_all_by_unique_job(self, repo: str):
        "Look for consistent failures for all unique job names"
        assert self.ds.db  # satisfy pytype that this isn't None
        uniquejobs = self.ds.db.cursor()
        uniquejobs.execute(UNIQUE_JOBS_SQL, (repo,))
        while globalunique := uniquejobs.fetchone():
            self.analyze_by_unique_job(globalunique[0])

    def show_job_failure_table(self, repo: str):
        "Create a table showing failures in jobs"
        assert self.ds.db  # satisfy pytype that this isn't None
        uniquejobs = self.ds.db.cursor()
        uniquejobs.execute(UNIQUE_JOBS_SQL, (repo,))
        now = datetime.datetime.now(datetime.timezone.utc)
        print(textwrap.dedent("""\
            <!DOCTYPE html>
            <html><head><title>Test Job Failures</title>
            <style type="text/css">
             /* test success/failure */
             .success    {background-color: limegreen;}
             .successold {background-color: yellowgreen;}
             .failure    {background-color: orangered;}
             .failureold {background-color: tomato;}
             .aborted    {background-color: yellow;}
             .unknown    {background-color: orange;}
             .jobfailure {background-color: orange;}
             .disabled   {background-color: silver;}

             td {padding: 0.3em;}
             .arrow {font-size: 200%;}

             .jobname {min-width: 30em; }
            </style>\
            """))
        print(textwrap.dedent(f"""\
            <meta name="generator" content="Test Clutch {testclutch.__version__}">
            </head>
            <body>
            <h1>Test report for {escape(repo)}</h1>
            Report generated {escape(now.strftime('%a, %d %b %Y %H:%M:%S %z'))}
            covering runs over the past {config.get('analysis_hours') / 24:.0f} days
            <p>
            Hover over cells for more information.
            <br><span class="success">successful test run</span>
                <span class="successold" title="Older than {round(config.get('old_job_hours')) / 24:.0f} days">successful older test run</span>
            <br><span class="failure">*failed test run</span>
                <span class="failureold" title="Older than {round(config.get('old_job_hours')) / 24:.0f} days">*failed older test run</span>
            <br><span class="aborted" title="Test run did not complete">aborted test run</span>
            <br><span class="unknown" title="Test results were inconclusive">unknown test run</span>
            <br><span class="disabled" title="No results for {round(config.get('disabled_job_hours')) / 24:.0f} days">disabled job</span>

            <table class="testtable"><tr>
            <th title="configured test job name" class="jobname">Job Name</th>
            <th title="test flakiness">Flake<span class="arrow">&nbsp;</span></th>
            <th title="the most recent test run is on the left">
            Older runs <span class="arrow">&rarr;</span></th></tr></table>
            """))

        while globalunique := uniquejobs.fetchone():
            self.show_unique_job_failures_table(globalunique[0])

        print('</body></html>')

    def prepare_uniquejob_analysis(self, globaluniquejob: str
                                   ) -> Tuple[List[Tuple[str, float]], TestFailCount]:
        """Perform the bulk of the analysis work of a uniquejob"""
        logging.info('Analyzing unique job %s', globaluniquejob)
        to_time = int(datetime.datetime.now().timestamp())
        from_time = int((datetime.datetime.now()
                         - datetime.timedelta(hours=config.get('analysis_hours'))).timestamp())
        self.load_unique_job(globaluniquejob, from_time, to_time)

        # print('Failures over time:')
        # for recit, jobtime, failures, attempted, successes in self.all_jobs_status:
        #     print(recid, jobtime, failures, len(attempted), len(successes))

        unique_failures = self.find_uniquejob_consecutive_failures()
        # print('# consistent failures over time for', globaluniquejob)
        # print('id timestamp  [ test, # failures in a row ...]')
        # for recid, jobtime, failure_counts in unique_failures:
        #     This is an attempt to reduce false positives during flaky tests, but it masks
        #     the true start of the problem. Find a better way to hide flaky tests.
        #     significant_failure_counts = {test: count
        #                                   for test, count in failure_counts.items()
        #                                   if count > config.get(
        #                                       'report_consecutive_failures')}
        #     print(recid, jobtime, list(failure_counts.items()))
        successes = self.find_uniquejob_successes(config.get('flaky_builds_max'))
        flaky = self.detect_flaky_tests(unique_failures[:config.get('flaky_builds_max')], successes)
        if unique_failures:
            recent_failures = unique_failures[0]
        else:
            # brand new job with no history
            # this will not actually ever be referenced so it doesn't need to make sense
            recent_failures = (0, 0, {})
        return (flaky, recent_failures)

    def show_unique_job_failures_table(self, globaluniquejob: str):
        logging.info('Analyzing unique job %s', globaluniquejob)
        flaky, first_failure = self.prepare_uniquejob_analysis(globaluniquejob)
        if not self.all_jobs_status:
            logging.info('Nothing to analyze for %s', globaluniquejob)
            return

        # This puts a scroll bar on the individual table
        # print('<div style="width: 100%; overflow: auto;">')
        print('<table class="testtable"><tr><th title="job name" class="jobname">'
              '<!--Unique Job Name--></th></tr>')
        print('<tbody>')

        # Look for permafailing jobs
        permafails = []
        if self.all_jobs_status[0].failed_tests:
            last_job_status = self.all_jobs_status[0]
            # A test might be on the failure list even if the job is successful if the test result
            # was marked to be ignored. Don't consider that a failure.
            if last_job_status.test_result != 'success':
                _, _, current_failure_counts = first_failure
                min_fails = config.get('permafail_failures_min')
                permafails = [failure for failure in last_job_status.failed_tests
                              if (current_failure_counts[failure] > min_fails)]

        oldjobtimestamp = (datetime.datetime.now()
                           - datetime.timedelta(hours=config.get('old_job_hours'))).timestamp()

        disabledjobtimestamp = (datetime.datetime.now() - datetime.timedelta(
            hours=config.get('disabled_job_hours'))).timestamp()

        # All testids will be the same, so just grab the first one
        testid = self.all_jobs_status[0].testid
        meta = self.ds.collect_meta(testid)
        origin = meta['origin']
        assert isinstance(origin, str)  # satisfy pytype that this isn't int
        ciname = meta.get('ciname', '')
        if origin.casefold() == ciname.casefold():
            # reduce duplication of information
            origin = ''
        else:
            origin = f"[{origin}] "
        cijob = meta.get('cijob', '')
        testformat = f" ({meta['testformat']})" if 'testformat' in meta else ''
        name = f'{origin}{ciname} / {cijob}{testformat}'
        maybedisabled = (' disabled' if self.all_jobs_status[0].jobtime < disabledjobtimestamp
                         else '')
        print(f'<tr><td class="jobname{maybedisabled}">{escape(name)}</td>')

        badtitle = []  # in raw HTML
        if permafails:
            permafails.sort(key=self._try_integer)
            badtitle = (['These tests are now consistently failing:']
                        + [testname for testname in permafails])
            badtext = 'permafail'
        elif flaky:
            flaky.sort(key=lambda x: self._try_integer(x[0]))
            num_builds = min(len(self.all_jobs_status), config.get('flaky_builds_max'))
            badtitle.append(f"Over the past {num_builds} builds:")
            for testname, ratio in flaky:
                badtitle.append(f'Test {escape(testname)} fails {ratio * 100:.1f}%')
            badtext = 'flaky'
        else:
            badtext = '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        jobclass = 'jobfailure' if badtitle else ''
        print(f'<td title="{"&#10;".join(badtitle)}" class="{jobclass}">{badtext}</td>')

        for job_status in self.all_jobs_status:
            # title must contain safe HTML as it will not be escaped
            title = datetime.datetime.fromtimestamp(
                job_status.jobtime, tz=datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
            # Cannot use summarize_totals here because we have the wrong structure
            title = (title
                     + f'&#10;Success: {len(job_status.successful_tests)}'
                     + f', Failed: {len(job_status.failed_tests)}'
                     + f', Attempted: {len(job_status.attempted_tests)}'
                     + f'&#10;Result: {escape(job_status.test_result)}')

            prefix_char = ''
            if job_status.test_result == 'success':
                cssclass = 'success'
                num = len(job_status.successful_tests)
            elif job_status.test_result == 'truncated' or job_status.is_aborted:
                cssclass = 'aborted'
                if len(job_status.failed_tests) == 0:
                    num = len(job_status.successful_tests)
                else:
                    num = len(job_status.failed_tests)
                    prefix_char = '*'
            elif job_status.test_result == 'failure':
                cssclass = 'failure'
                num = len(job_status.failed_tests)
                prefix_char = '*'
            elif job_status.test_result == 'unknown':
                # Shouldn't normally be encountered for tests ingested after Aug 1/23.
                # just look at the # failures in this case
                if len(job_status.failed_tests) == 0:
                    cssclass = 'success'
                    num = len(job_status.successful_tests)
                else:
                    cssclass = 'unknown'
                    num = len(job_status.failed_tests)
                    prefix_char = '*'
            else:
                # Not sure what this is
                logging.error('Internal error determining job status for %s', globaluniquejob)
                cssclass = 'failure'
                num = len(job_status.failed_tests)
                prefix_char = '*'

            # Mark old jobs in a different colour
            if job_status.jobtime < oldjobtimestamp:
                if cssclass == 'success':
                    cssclass = 'successold'
                elif cssclass == 'failure':
                    cssclass = 'failureold'

            print(f'<td class="{cssclass}" title="{title}"><a href="{escape(job_status.url)}">'
                  f'{prefix_char}{num}</a></td>')

        print('</tr>')
        print('</tbody>')
        print('</table>')
        # print('</div>')

    def _count_consecutive_failures(self) -> List[Dict[str, int]]:
        """Count consecutive failures of all tests for all jobs

        Loops from the end of the list to the beginning so it counts as
        it goes.
        """
        result = []
        if self.all_jobs_status:
            prev_failure_count = collections.Counter()
            for job_status in reversed(self.all_jobs_status):
                failed = set(job_status.failed_tests)
                # These failed on the last run, too
                still_failed_count = collections.Counter({k: prev_failure_count[k] for k in failed})
                failure_count = collections.Counter(failed) + still_failed_count
                result.insert(0, failure_count)

                # Note: If a test was skipped during a run (due to a test crash or timeout, for
                # example) it will be removed from the new_failure_set and the count will reset.
                # This is not what we want. In that case, don't add a failure count but leave it in
                # the set to check next time.
                attempted_set = set(job_status.attempted_tests)
                failed_missed = set(prev_failure_count) - attempted_set
                failed_missed_count = collections.Counter(
                    {k: prev_failure_count[k] for k in failed_missed})
                prev_failure_count = failure_count + failed_missed_count
        return result

    def find_uniquejob_failures(self) -> Dict[str, int]:
        "Count the total failures in the current uniquejob by test name"
        counts = collections.Counter()
        for job_status in self.all_jobs_status:
            counts += collections.Counter(set(job_status.failed_tests))
        return counts

    def find_uniquejob_consecutive_failures(self) -> List[TestFailCount]:
        """Analyze the current uniquejob for consistent failures over time

        Must have called load_unique_job() beforehand.
        Returns a list of failures in a row per test, by run
        """
        failure_counts = self._count_consecutive_failures()
        assert len(self.all_jobs_status) == len(failure_counts)
        # Add the job info
        result = []
        for job_status, failures in zip(self.all_jobs_status, failure_counts):
            result.append((job_status.testid, job_status.jobtime, failures))
        return result

    def find_uniquejob_successes(self, num_builds: int) -> Set[str]:
        """Returns the set of tests that succeeded at least once

        num_builds is the number of recent builds to look at.
        """
        any_successes = set()
        for i, job_status in enumerate(self.all_jobs_status[:num_builds]):
            any_successes |= frozenset(job_status.successful_tests)
        return any_successes

    def find_uniquejob_attempts(self) -> Dict[str, int]:
        """Returns the count of number of test attempts per test
        """
        counts = collections.Counter()
        for job_status in self.all_jobs_status:
            counts += collections.Counter(set(job_status.attempted_tests))
        return counts

    def detect_flaky_tests(self, unique_failures: List[TestFailCount],
                           successes: Set[str]) -> List[Tuple[str, float]]:
        """Detects flaky tests in all the builds for one unique job
        """
        if len(unique_failures) < config.get('flaky_builds_min'):
            logging.info('Not enough data to perform flakiness analysis')
            return []

        # Set of all test names that had at least one failure in this unique job
        any_failed = set(testname
                         for recid, jobtime, failure_counts in unique_failures
                         for testname in failure_counts.keys())

        # Track the number of times each test started to fail
        fail_changes = {}
        # Look at all tests that failed, one at a time
        for failed_test in any_failed:
            fail_changes[failed_test] = len([
                1
                for recid, jobtime, failure_counts in unique_failures
                if failure_counts[failed_test] == 1
            ])

        # A flaky test must have at least one success; a test can't be flaky unless it
        # both succeeds and fails.
        # A test can't be flaky unless it flakes at least flaky_failures_min times.
        # A test can't be flaky unless we have enough runs to be statistically interesting
        # (i.e. flaky_builds_min, which is checked at the entrance to this function).
        flaky_tests = [test
                       for test in fail_changes
                       if test in successes
                       and fail_changes[test] >= config.get('flaky_failures_min')]
        test_attempt_counts = self.find_uniquejob_attempts()
        test_fail_counts = self.find_uniquejob_failures()
        flaky_tests.sort(key=self._try_integer)
        flaky_rates = []
        for flake in flaky_tests:
            # Calculate the ratio of failures to attempts
            flaky_rates.append((flake, test_fail_counts[flake] / test_attempt_counts[flake]))
        return flaky_rates

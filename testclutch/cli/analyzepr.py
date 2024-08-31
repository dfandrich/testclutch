"""Perform analysis of tests run on a pull request
"""

import argparse
import collections
import datetime
import enum
import logging
import textwrap
from collections.abc import Container
from contextlib import nullcontext
from email import utils
from html import escape
from typing import Optional, Sequence

import testclutch
from testclutch import analysis
from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch import prdef
from testclutch import summarize
from testclutch import urls
from testclutch.ingest import gha
from testclutch.ingest import ghaapi
from testclutch.ingest import prappveyor
from testclutch.ingest import prazure
from testclutch.ingest import prcircleci
from testclutch.ingest import prcirrus
from testclutch.ingest import prgha
from testclutch.logdef import ParsedLog, TestCases, TestMeta
from testclutch.testcasedef import TestResult

# Test states that are considered to be failed tests
# TestResult.UNKNOWN is left out because parsing errors can cause it (due to e.g. Python errors in
# test servers)
FAIL_TEST_RESULTS = frozenset((TestResult.FAIL, TestResult.TIMEOUT))

# Number of test failures to mention in the comment, per origin
MAX_NOTIFIED_PER_ORIGIN = 7


class PRStatus(enum.IntEnum):
    """Status of CI jobs for a PR

    These are in numerical order where higher-numbered statuses override lower-numbered one.
    """
    READY = 0    # CI jobs are complete (and successful)
    FAILURE = 1  # CI jobs are complete (and at least one failed)
    PENDING = 2  # CI jobs are still running for this PR
    CLOSED = 3   # PR already closed
    ERROR = 4    # invalid PR


def parse_args(args: Optional[argparse.Namespace] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Perform analysis of tests run on a pull request')
    argparsing.arguments_logging(parser)
    argparsing.arguments_ci(parser, required=False)
    parser.add_argument(
        '--html',
        action='store_true',
        help='Output PR analysis report in HTML form instead of text')
    parser.add_argument(
        '--html-fragment',
        action='store_true',
        help='Whether to skip HTML page header and footer')
    with nullcontext(parser.add_mutually_exclusive_group(required=True)) as pr_source:
        pr_source.add_argument(
            '--pr',
            type=int,
            nargs='+',
            help='pull request number on the --checkrepo to analyze')
        pr_source.add_argument(
            '--ready-prs',
            action='store_true',
            help='Look at all recent PRs that are ready instead of specified ones')
    parser.add_argument(
        '--oldest',
        type=int,
        help='Oldest PR to consider ready for --ready-prs, in hours')
    parser.add_argument(
        '--only-failed-prs',
        action='store_true',
        help='Only include PRs showing a failure status in the --ready-prs set')
    parser.add_argument(
        '--rerun',
        action='store_true',
        help='Rerun step even if run before')
    # Put these at end so they're easier for the user to see
    with nullcontext(parser.add_mutually_exclusive_group(required=True)) as output_mode:
        output_mode.add_argument(
            '--ci-status',
            action='store_true',
            help="Check the status of CI runs associated with this PR")
        output_mode.add_argument(
            '--report',
            action='store_true',
            help='Output PR analysis report')
        output_mode.add_argument(
            '--gather-analysis',
            action='store_true',
            help='Gather information needed to comment on a PR')
        output_mode.add_argument(
            '--comment',
            action='store_true',
            help='Comment on a PR')
    return parser.parse_args(args=args)


def success_fail_count(meta: TestMeta, testcases: TestCases, is_aborted: bool) -> tuple[str, str]:
    test_result = meta.get('testresult', 'unknown')
    prefix_char = ''
    if test_result == 'success':
        cssclass = 'success'
        num = len([1 for x in testcases if x.result == TestResult.PASS])
    elif test_result == 'truncated' or is_aborted:
        cssclass = 'aborted'
        num_failed = len([1 for x in testcases if x.result == TestResult.FAIL])
        if num_failed == 0:
            num = len([1 for x in testcases if x.result == TestResult.PASS])
        else:
            num = num_failed
            prefix_char = '*'
    elif test_result == 'failure':
        cssclass = 'failure'
        num = len([1 for x in testcases if x.result == TestResult.FAIL])
        prefix_char = '*'
    elif test_result == 'unknown':
        # Shouldn't normally be encountered for tests ingested after Aug 1/23.
        # just look at the # failures in this case
        num_failed = len([1 for x in testcases if x.result == TestResult.FAIL])
        if num_failed == 0:
            cssclass = 'success'
            num = len([1 for x in testcases if x.result == TestResult.PASS])
        else:
            cssclass = 'unknown'
            num = num_failed
            prefix_char = '*'
    else:
        # Not sure what this is
        logging.error('Internal error determining job status for %s', meta['cijob'])
        cssclass = 'failure'
        num = len([1 for x in testcases if x.result == TestResult.FAIL])
        prefix_char = '*'

    return (f'{prefix_char}{num}', cssclass)


def print_html_header(pr: int):
    print(textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html><head><title>PR#{pr} Test Analysis</title>
        <meta name="generator" content="Test Clutch {testclutch.__version__}">
        """))
    print(textwrap.dedent("""\
        <style type="text/css">
         /* test success/failure */
         .success {background-color: limegreen;}
         .successold {background-color: yellowgreen;}
         .failure {background-color: orangered;}
         .failureold {background-color: tomato;}
         .aborted {background-color: yellow;}
         .unknown {background-color: orange;}
         .flaky   {background-color: orange;}
         .ignoredfailures  {background-color: mediumseagreen;}

         td {padding: 0.3em;}
         .arrow {font-size: 200%;}

         .jobname {min-width: 30em; }
        </style>
        </head>
        <body>
        """))


def print_html_footer():
    print('</body>')
    print('</html>')


def analyze_pr_html(pr: int, test_results: Sequence[ParsedLog], ds: db.Datastore, fragment: bool):
    logging.info('Analyzing %d test results', len(test_results))
    if not fragment:
        print_html_header(pr)
        now = datetime.datetime.now(datetime.timezone.utc)
        print(textwrap.dedent(f"""\
            <h1>Test report for PR#{pr} as of
                {escape(now.strftime('%a, %d %b %Y %H:%M:%S %z'))}</h1>

            Test analysis covers the past {config.get('analysis_hours') / 24:.0f} days.
            Hover over cells for more information.
            <br><span class="success">successful test run</span>
            <br><span class="failure">*failed test run</span>
            <br><span class="aborted">aborted test run</span>
            <br><span class="unknown">unknown test run</span>
            """))
    print(textwrap.dedent("""\
        <table class="testtable"><tr>
        <th title="configured test job name" class="jobname">Job Name</th>
        <th title="test flakiness">Upstream<span class="arrow">&nbsp;</span></th>
        <th title="count of test passes or failures">
        Pass/fail count</th></tr></table>
        """))
    print('<table class="testtable"><tr><th title="job name" class="jobname">'
          '<!--Unique Job Name--></th></tr>')
    print('<tbody>')

    analyzer = analysis.ResultsOverTimeByUniqueJob(ds)
    for meta, testcases in test_results:
        print('<tr>')

        # First, show job name
        origin = meta['origin']
        assert isinstance(origin, str)  # satisfy pytype that this isn't int
        ciname = meta.get('ciname', '')
        if origin.casefold() == ciname.casefold():
            # reduce duplication of information displayed
            origin = ''
        else:
            origin = f"[{origin}] "
        cijob = meta.get('cijob', '')
        testformat = f" ({meta['testformat']})" if 'testformat' in meta else ''
        name = f'{origin}{ciname} / {cijob}{testformat}'
        print(f'<td class="jobname">{escape(name)}</td>')

        # Next, show flaky main tests
        globaluniquejob = analyzer.make_global_unique_job(meta)
        flaky, first_failure = analyzer.prepare_uniquejob_analysis(globaluniquejob)
        flakytitle = ''
        if flaky:
            # Some tests were found to be flaky
            flaky.sort(key=lambda x: summarize.try_integer(x[0]))
            flakytitle = 'This test is flaky already, even without this PR; link goes to example'
            flakyfailurl = ''
            for testname, ratio in flaky:
                if not flakyfailurl:
                    flakyfailurl = analyzer.recent_failed_link(testname)
                flakytitle = flakytitle + f'\nTest {escape(testname)} fails {ratio * 100:.1f}%'

        # Now, look at permafails in main tests
        permafailtitle = ''
        job_status = analyzer.all_jobs_status[0]
        if job_status.test_result == 'success' and job_status.failed_tests:
            permafailtitle = ('Some tests are failing but the test was marked as successful, '
                              'so these test results were likely marked to be ignored. ')
        current_failure_counts = first_failure[2]
        permafails = analyzer.get_permafails(current_failure_counts)
        # A test might be on the permafail list even if the job is successful if the test result
        # was marked to be ignored. Don't consider that a failure worth reporting.
        if permafails and job_status.test_result != 'success':
            permafailtitle = permafailtitle + "These tests are now consistently failing: "
            permafails.sort(key=summarize.try_integer)
            permafailtitle = permafailtitle + (
                ', '.join([escape(testname) for testname in permafails]))

        if flakytitle:
            print('<td class="flaky">'
                  f'<a href="{escape(flakyfailurl)}" title="{flakytitle}">flaky</a>')
            if permafailtitle:
                # TODO: get permafailurl
                print(f'<span title="{escape(permafailtitle)}" class="flaky">Failures</span>')
        else:
            if permafailtitle:
                if job_status.test_result == 'success':
                    failclass = 'ignoredfailures'
                    failtext = '(Failures)'
                else:
                    failclass = 'flaky'
                    failtext = 'Failures'
                # TODO: get permafailurl
                print(f'<td title="{escape(permafailtitle)}" class="{failclass}">{failtext}')
            else:
                print('<td title="not flaky">')
        print('</td>')

        # Finally, show results of PR
        jobtime = (meta['runtriggertime'] if 'runtriggertime' in meta else
                   meta['runstarttime'] if 'runstarttime' in meta else meta['runfinishtime'])
        # title must contain safe HTML as it will not be escaped
        # TODO: include commit ID in message
        title = datetime.datetime.fromtimestamp(
            jobtime, tz=datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')
        summary = summarize.summarize_totals(testcases)
        is_aborted = analyzer.check_aborted(meta)
        test_result = 'aborted' if is_aborted else meta.get('testresult', 'unknown')
        title = (title + '\n' + escape(', '.join([s.strip() for s in summary]))
                 + '\nResult: ' + escape(test_result))

        num, cssclass = success_fail_count(meta, testcases, is_aborted)

        url = f'<a href="{escape(meta["url"])}">' if 'url' in meta else ''
        url_end = '</a>' if 'url' in meta else ''
        print(f'<td class="{cssclass}" title="{title}">{url}'
              f'{num}{url_end}</td>')
        print('</tr>')

    print('</tbody>')
    print('</table>')
    if not fragment:
        print_html_footer()


def analyze_pr(pr: int, test_results: Sequence[ParsedLog], ds: db.Datastore):
    print(f'Analyzing pull request {pr}')
    logging.info('Analyzing %d test results', len(test_results))
    for testmeta, testcases in test_results:
        analyzer = analysis.ResultsOverTimeByUniqueJob(ds)
        print(f"Test [{testmeta['origin']}] {testmeta['ciname']} / {testmeta['cijob']} ({testmeta['testformat']})")
        failed = [x for x in testcases if x.result == TestResult.FAIL]
        if not failed:
            logging.debug('All tests succeeded; no failures to analyze')
            if analyzer.check_aborted(testmeta):
                print('Test run seems to have aborted, probably due to timeout')
            else:
                # Nothing to analyze
                continue
        if testmeta.get('testresult', 'unknown') == 'success':
            print('Test was marked as successful even though it had test failures. '
                  'The failing tests were likely marked to be ignored so no analysis of the '
                  'failures is necessary.')
            continue

        summary = summarize.summarize_totals(testcases)
        for l in summary:
            print(l.strip())
        if failed:
            print('Some test(s) failed:')
            for test in failed:
                print(f'{test.name} (failed in {test.reason})')
        print('Here is an analysis of this test in this environment recently in the repo')

        globaluniquejob = analyzer.make_global_unique_job(testmeta)
        analyzer.analyze_by_unique_job(globaluniquejob)
        print()
    print()


def appveyor_analyze_pr(args: argparse.Namespace, ds: Optional[db.Datastore],
                        prs: list[int]) -> int:
    account, project = urls.get_project_name(args)
    av = prappveyor.AppveyorAnalyzeJob(account, project, args.checkrepo, ds, None)

    for pr in prs:
        logging.info(f'Analyzing pull request {pr}')
        results = av.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(pr, results, ds)
    return PRStatus.READY


def azure_analyze_pr(args: argparse.Namespace, ds: db.Datastore, prs: list[int]) -> int:
    owner, project = urls.get_project_name(args)
    azure = prazure.AzureAnalyzer(owner, project, args.checkrepo, ds)

    for pr in prs:
        logging.info(f'Analyzing pull request {pr}')
        results = azure.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(pr, results, ds)
    return PRStatus.READY


def circle_analyze_pr(args: argparse.Namespace, ds: db.Datastore, prs: list[int]) -> int:
    ci = prcircleci.CircleAnalyzer(args.checkrepo, ds)

    for pr in prs:
        logging.info(f'Analyzing pull request {pr}')
        results = ci.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(pr, results, ds)
    return PRStatus.READY


def cirrus_analyze_pr(args: argparse.Namespace, ds: db.Datastore, prs: list[int]) -> int:
    cirrus = prcirrus.CirrusAnalyzer(args.checkrepo, ds, None)

    for pr in prs:
        logging.info(f'Analyzing pull request {pr}')
        results = cirrus.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(pr, results, ds)
    return PRStatus.READY


def gha_analyze_pr(args: argparse.Namespace, ds: db.Datastore, prs: list[int]) -> int:
    owner, project = urls.get_project_name(args)
    ghi = prgha.GithubAnalyzeJob(owner, project, gha.read_token(args.authfile), ds)

    for pr in prs:
        logging.info(f'Analyzing pull request {pr}')
        results = ghi.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(pr, results, ds)
    return PRStatus.READY


class GHAPRReady:
    "Class to determine if CI jobs for PRs have completed"

    def __init__(self, args: argparse.Namespace):
        if urls.url_host(args.checkrepo) != 'github.com':
            # This function only makes sense when source is hosted on GitHub
            raise RuntimeError(f'Invalid GitHub repository URL {args.checkrepo}')
        self.args = args
        owner, project = urls.get_generic_project_name(args.checkrepo)
        self.gh = ghaapi.GithubApi(owner, project, gha.read_token(args.authfile))

    def get_ready_prs(self, authors: Container[str]) -> list[int]:
        "Return recent PRs that have not been closed"
        pulls = self.gh.get_pulls('open')
        pr_recency = self.args.oldest if self.args.oldest else config.get('pr_ready_age_hours_max')
        recent = (datetime.datetime.now(tz=datetime.timezone.utc)
                  - datetime.timedelta(hours=pr_recency))
        recent_prs = [pr['number'] for pr in pulls
                      if (ghaapi.convert_time(pr['created_at']) > recent
                          and (not authors or pr['user']['login'] in authors))]
        logging.info(f'{len(pulls)} open PRs of which {len(recent_prs)} are recent ones (within '
                     f'{pr_recency} hours)%s', ' and matching allowed authors' if authors else '')

        for prnum in recent_prs:
            logging.info(f'PR#{prnum} is eligible to be analyzed')
        return recent_prs

    def check_gha_pr_state(self, pr: int) -> PRStatus:
        pull = self.gh.get_pull(pr)
        if pull['state'] == 'closed':
            logging.warning(f'PR is in state {pull["state"]}')
            return PRStatus.CLOSED
        if pull['state'] != 'open':
            logging.warning(f'PR is in unknown state {pull["state"]}')
            return PRStatus.ERROR
        if pull['locked']:
            logging.warning('PR is locked; aborting')
            return PRStatus.ERROR
        commit = pull['head']['sha']
        logging.info(f'PR#{pr} commit {commit}')

        # CI status are spread over commit statuses and check-runs, so check them both
        status = self.gh.get_commit_status(commit)
        logging.debug(f'{len(status["statuses"])} commit statuses')
        logging.debug(f'Overall commit status state: {status["state"]}')
        jobcount = len(status['statuses'])
        pending = 0
        ret = PRStatus.READY
        for stat in status['statuses']:
            # (success, failure, pending)
            if stat['state'] == 'pending':
                ret = max(PRStatus.PENDING, ret)
                pending += 1
            elif stat['state'] != 'success':
                logging.debug(f"failed with state {stat['state']}")
                ret = max(PRStatus.FAILURE, ret)

        checkruns = self.gh.get_check_runs(commit)
        logging.debug(f"{len(checkruns['check_runs'])} check runs")
        jobcount += len(checkruns['check_runs'])
        for run in checkruns['check_runs']:
            # (queued, in_progress, completed)
            if run['status'] != 'completed':
                logging.debug(f"check run {run['id']} is in state {run['status']}")
                ret = max(PRStatus.PENDING, ret)
                pending += 1
            # (success, neutral, failure)
            elif run['conclusion'] == 'failure':
                logging.debug(f"check run {run['id']} concluded with {run['conclusion']}")
                ret = max(PRStatus.FAILURE, ret)

        logging.info(f'PR#{pr} has ready state {ret.name} '
                     f'with {pending} jobs out of {jobcount} still pending')
        return ret

    def check_gha_pr_states(self, prs: list[int]) -> list[tuple[int, PRStatus]]:
        states = []
        for pr in prs:
            states.append((pr, self.check_gha_pr_state(pr)))
        return states


def dedentnonl(text: str) -> str:
    """Remove leading space like dedent() then replace any \n with a space

    This is useful when generating Markdown for GitHub comments, which, unlike other Markdown
    parsers, treats each \n as an actual end of line, not just two \n in a row.
    """
    return textwrap.dedent(text).replace('\n', ' ')


class GatherPRAnalysis:
    "Class for gathering data to analyze and comment on a PR"

    def __init__(self, ds: db.Datastore, args: argparse.Namespace):
        self.ds = ds
        self.args = args
        self.analysisstate = prdef.PRAnalysisState()

    def read_analyses(self, lock: bool) -> dict[int, prdef.PRAnalysis]:
        """Return the analyses so far for this repo

        Args:
            lock: True if the analysis data may be written later; this adds an exclusive lock
            on the file
        """
        self.allpranalyses = self.analysisstate.read_state(lock)
        if self.args.checkrepo not in self.allpranalyses:
            # Create new dict for this checkrepo
            self.allpranalyses[self.args.checkrepo] = {}
        return self.allpranalyses[self.args.checkrepo]

    def write_analyses(self):
        assert self.allpranalyses  # read_analyses() MUST have been called first
        self.analysisstate.write_state(self.allpranalyses)
        del self.allpranalyses  # force user to read again in case file was updated outside

    def gather_failed(self, origin: str, pr: int
                      ) -> tuple[Optional[list[prdef.FailedTest]], str]:
        logging.info(f'Gathering {origin} analysis for pull request {pr}')
        if origin == 'appveyor':
            return self.appveyor_gather_pr_failures(pr)

        elif origin == 'azure':
            return self.azure_gather_pr_failures(pr)

        elif origin == 'circle':
            return self.circle_gather_pr_failures(pr)

        elif origin == 'cirrus':
            return self.cirrus_gather_pr_failures(pr)

        elif origin == 'gha':
            return self.gha_gather_pr_failures(pr)

        logging.error(f'Unsupported origin {origin}')
        return (None, '')

    def gather_analysis(self, prs: list[int]) -> int:
        """Gather information needed to analyze one or more PRs"""
        pranalyses = self.read_analyses(True)  # lock for writing
        origin = self.args.origin

        # Prune out old entries
        oldest = (datetime.datetime.now()
                  - datetime.timedelta(hours=config.get('pr_gather_age_hours_max'))).timestamp()
        # Make a list of the keys to fix them because we might be deleting them from the dict
        for pr in list(pranalyses.keys()):
            if pranalyses[pr].start < oldest:
                logging.debug(f'Aging out PR#{pr} from cache (time {pranalyses[pr].start})')
                del pranalyses[pr]

        rc = PRStatus.READY
        for pr in prs:
            if pr not in pranalyses or self.args.rerun:
                logging.info(f'Starting new analysis of PR #{pr}')
                thispr = prdef.PRAnalysis(pr, self.args.checkrepo,
                                          int(datetime.datetime.now().timestamp()),
                                          {}, {}, {}, {}, 0)
                pranalyses[pr] = thispr
            else:
                thispr = pranalyses[pr]

            # For any new PRs we haven't seen before, look up which tests failed
            if origin not in thispr.failed:
                failed, commit = self.gather_failed(origin, pr)
                if failed is not None:
                    thispr.failed[origin] = failed
                    thispr.commit[origin] = commit
            else:
                logging.debug(f'Already have failed list for PR#{pr} from {origin}')

            # Now, analyze flakiness & permafails for this origin ONLY if there is at least one
            # failed test. No need to check both flaky AND permafails as they are set at once.
            if origin not in thispr.flaky and origin in thispr.failed and thispr.failed[origin]:
                analyzer = analysis.ResultsOverTimeByUniqueJob(self.ds)

                uniquejobs = {fail.uniquejob for fail in thispr.failed[origin]}
                flaky = []
                permafail = []
                for job in uniquejobs:
                    # load and general analysis
                    jobflaky, first_failure = analyzer.prepare_uniquejob_analysis(job)

                    # flakiness
                    flaky.extend([prdef.FailingTest(job, test[0], test[1]) for test in jobflaky])

                    # permafails
                    current_failure_counts = first_failure[2]
                    permafails = analyzer.get_permafails(current_failure_counts)
                    # A test might be on the permafail list even if the job is successful if the
                    # test result was marked to be ignored. Don't consider that a failure worth
                    # reporting.
                    if (permafails and analyzer.all_jobs_status
                            and analyzer.all_jobs_status[0].test_result == 'success'):
                        permafails = []
                    permafail.extend([prdef.FailingTest(job, test, 1.0) for test in permafails])

                thispr.flaky[origin] = flaky
                thispr.permafail[origin] = permafail

            else:
                logging.debug(f"Don't need to get flaky list for PR#{pr} from {origin}")

        self.write_analyses()

        return rc

    def appveyor_gather_pr_failures(self, pr: int) -> tuple[list[prdef.FailedTest], str]:
        account, project = urls.get_project_name(self.args)
        av = prappveyor.AppveyorAnalyzeJob(account, project, self.args.checkrepo, self.ds, None)
        results = av.gather_pr(pr)
        commit = results[0][0]['commit'] if results else ''
        assert isinstance(commit, str)  # satisfy pytype that this isn't int
        if any(result[0]['commit'] != commit for result in results):
            logging.error('PR results have been gathered for more than one commit, not just '
                          f'{commit:.9}')
        return (self.select_failures(results), commit)

    def azure_gather_pr_failures(self, pr: int) -> tuple[list[prdef.FailedTest], str]:
        owner, project = urls.get_project_name(self.args)
        azure = prazure.AzureAnalyzer(owner, project, self.args.checkrepo, self.ds)
        results = azure.gather_pr(pr)
        commit = results[0][0]['commit'] if results else ''
        assert isinstance(commit, str)  # satisfy pytype that this isn't int
        if any(result[0]['commit'] != commit for result in results):
            logging.error('PR results have been gathered for more than one commit, not just '
                          f'{commit:.9}')
        return (self.select_failures(results), commit)

    def circle_gather_pr_failures(self, pr: int) -> tuple[list[prdef.FailedTest], str]:
        ci = prcircleci.CircleAnalyzer(self.args.checkrepo, self.ds)
        results = ci.gather_pr(pr)
        commit = results[0][0]['commit'] if results else ''
        assert isinstance(commit, str)  # satisfy pytype that this isn't int
        if any(result[0]['commit'] != commit for result in results):
            logging.error('PR results have been gathered for more than one commit, not just '
                          f'{commit:.9}')
        return (self.select_failures(results), commit)

    def cirrus_gather_pr_failures(self, pr: int) -> tuple[list[prdef.FailedTest], str]:
        cirrus = prcirrus.CirrusAnalyzer(self.args.checkrepo, self.ds, None)
        results = cirrus.gather_pr(pr)
        commit = results[0][0]['commit'] if results else ''
        assert isinstance(commit, str)  # satisfy pytype that this isn't int
        if any(result[0]['commit'] != commit for result in results):
            logging.error('PR results have been gathered for more than one commit, not just '
                          f'{commit:.9}')
        return (self.select_failures(results), commit)

    def gha_gather_pr_failures(self, pr: int) -> tuple[list[prdef.FailedTest], str]:
        owner, project = urls.get_project_name(self.args)
        ghi = prgha.GithubAnalyzeJob(owner, project, gha.read_token(self.args.authfile), self.ds)
        results = ghi.gather_pr(pr)
        commit = results[0][0]['commit'] if results else ''
        assert isinstance(commit, str)  # satisfy pytype that this isn't int
        if any(result[0]['commit'] != commit for result in results):
            logging.error('PR results have been gathered for more than one commit, not just '
                          f'{commit:.9}')
        return (self.select_failures(results), commit)

    def select_failures(self, results: list[ParsedLog]) -> list[prdef.FailedTest]:
        results.sort(key=lambda x: x[0]['uniquejobname'])

        analyzer = analysis.ResultsOverTimeByUniqueJob(self.ds)
        failed_tests = []
        for meta, testcases in results:
            logging.debug(
                f'Checking run {meta["runid"]}'
                f'{"/" if "cijob" in meta else ""}{meta.get("cijob", "")} for failed tests')
            failed = [tc for tc in testcases if tc.result in FAIL_TEST_RESULTS]
            if failed:
                globaluniquejob = analyzer.make_global_unique_job(meta)
                logging.info(f'Found {len(failed)} failed tests in job {globaluniquejob}')
                failed_tests.extend((prdef.FailedTest(
                    globaluniquejob, fail.name, meta.get('url', '')) for fail in failed))

        return failed_tests

    def all_origins(self) -> set[str]:
        """Returns the set of all origins to check before commenting"""
        origins = config.get('pr_comment_origins')
        if not origins:
            origins = set(argparsing.KNOWN_ORIGINS)
        return origins

    def comment(self, prs: list[int]) -> int:
        """Comment on a PR"""
        if not self.args.dry_run:
            owner, project = urls.get_generic_project_name(self.args.checkrepo)
            gh = ghaapi.GithubApi(owner, project, gha.read_token(self.args.authfile))

        pranalyses = self.read_analyses(True)
        for pr in prs:
            # Check that we're ready to comment
            if pr not in pranalyses:
                logging.warning(f'PR #{pr} has not started analysis yet; skipping')
                continue
            analysis = pranalyses[pr]

            logging.info(f'Data for PR#{pr}: '
                         f'{len(analysis.failed)} origins checked, '
                         f'{sum(len(t) for t in analysis.failed.values())} failed tests, '
                         f'{sum(len(t) for t in analysis.flaky.values())} flaky tests, '
                         f'{sum(len(t) for t in analysis.permafail.values())} permafailing tests')

            # These are the origins that must have already been checked before commenting
            origins = self.all_origins()
            remaining = origins - frozenset(analysis.failed)
            if remaining:
                logging.warning(f'PR #{pr} has not completed failure checking yet '
                                f'(missing {", ".join(remaining)}); skipping')
                continue

            if not any(origin for origin in origins if analysis.failed[origin]):
                logging.warning(f'PR #{pr} has no failed tests so no need to comment; skipping')
                continue

            flakyremaining = (frozenset(k for k, v in analysis.failed.items() if v)
                              - frozenset(analysis.flaky))
            if flakyremaining:
                logging.warning(f'PR #{pr} has not completed flaky analysis yet '
                                f'(missing {", ".join(flakyremaining)}); skipping')
                continue

            if analysis.commented and not self.args.dry_run:
                date = utils.format_datetime(
                    datetime.datetime.fromtimestamp(analysis.commented))
                logging.warning(f"Already commented on PR#{pr} on {date}; won't comment again")
            else:
                message = self.compose_text(analysis)
                logging.info(f'PR #{pr} message: {message}')
                if self.args.dry_run:
                    logging.info('Skipping actual commenting in dry-run mode')
                else:
                    logging.info(f'Adding to comment on PR#{pr}')

                    # Write the comment to the PR thread
                    gh.create_comment(pr, message)

                    analysis.commented = int(datetime.datetime.now().timestamp())

        # Update with the commented times
        self.write_analyses()

        return PRStatus.READY

    def compose_text(self, analysis: prdef.PRAnalysis) -> str:
        """Compose text for a comment about a PR

        Text is in MarkDown format.
        """
        # First, check the consistency of the commits used in the analysis.
        #
        # It can happen that we analyze the results from one CI service at one commit, but the user
        # then pushes a new commit to the PR and we get the results from another CI service at that
        # second commit.
        #
        # Ideally, for consistency of analysis we would detect this situation and invalidate the
        # older results (by deleting them out of "analysis") and wait for the new results to come
        # in.  The problem with that approach is that it's possible that the new commit causes
        # the CI service with the outdated results to not be triggered (e.g. due to path exclusions)
        # so when the results are read again they will still be from the older commit. Under this
        # invalidation approach, that would cause the OTHER CI service's results to be invalidated
        # this time (because we can't unambiguously tell which is the newer of the two commits) and
        # we would end up in an endless loop of invalidating some results on each iteration and
        # never getting them all at the same consistent commit.
        #
        # Instead, we just detect the situation, which should be fairly rare, and merely warn the
        # user.
        commits = frozenset(v for v in analysis.commit.values() if v)
        committext = ''
        commitwarning = ''
        if len(commits) == 1:
            # This only works if checkrepo is GitHub
            commit = next(iter(commits))
            url = f'{self.args.checkrepo}/commit/{commit}'
            committext = f' at [{commit:.8}]({escape(url)})'
        elif len(commits) > 1:
            commitwarning = (
                f'###### Note that this analysis is based on tests run on {len(commits)} different '
                'commits from this PR on different CI services\n')
        else:
            # This should never happen
            logging.error('No commits found in PR#%d analysis', analysis.num)

        text = f'Analysis of PR #{analysis.num}{committext}:\n\n'
        # Count of all tests that failed for this PR, by testname
        count_failed = collections.Counter(
            fail.testname for oneorigin in analysis.failed.values() for fail in oneorigin)
        mentioned = set()
        for origin in self.all_origins():
            nummentioned = 0
            for fail in analysis.failed[origin]:
                if fail.testname not in mentioned:
                    logging.debug(f'test {fail.testname} on uniquejob {fail.uniquejob}')
                    # TODO: display "cijob" or similar; maybe create function from
                    # "First, show job name" code and use that; can you make it a tooltip in
                    # markdown instead?
                    text += f'[Test {fail.testname} failed]({escape(fail.url)}),'
                    flakyfailuniquejob = [flake for flake in analysis.flaky[origin]
                                          if flake.uniquejob == fail.uniquejob]
                    flakyfail = [flake for flake in flakyfailuniquejob
                                 if flake.testname == fail.testname]
                    assert len(flakyfail) <= 1  # should be at most one entry per uniquejob+testname
                    if flakyfail:
                        text += dedentnonl(f"""
                            but it has been {flakyfail[0].rate * 100:.1f}% flaky lately,
                            so it's *probably NOT* a fault of the PR.
                            """)
                    else:
                        # check for permafail
                        if any(perma for perma in analysis.permafail[origin]
                               if (perma.uniquejob == fail.uniquejob
                                   and perma.testname == fail.testname)):
                            text += dedentnonl("""
                                but it has been permanently failing lately,
                                so it's *probably NOT* a fault of the PR.
                                """)
                        else:
                            text += dedentnonl("""
                                which has NOT been flaky recently,
                                so **there could be a real issue in the PR**.
                                """)
                    if count_failed[fail.testname] > 1:
                        text += dedentnonl(f"""
                            Note that this test has failed in {count_failed[fail.testname]}
                            different CI jobs (the link just goes to one of them).
                            """)
                    if len(flakyfailuniquejob) > 1:
                        text += dedentnonl(f"""
                            Note that this CI job has had a number of other flaky tests recently
                            ({len(flakyfailuniquejob)}, to be exact) so it may be that this failure
                            is rather a systemic issue with this job and not with this specific PR.
                            """)

                    text = text.strip()
                    text += '\n\n'  # blank line separating tests
                    nummentioned += 1

                    mentioned.add(fail.testname)
                    if nummentioned >= MAX_NOTIFIED_PER_ORIGIN:
                        text += textwrap.dedent(f"""\
                            There are more failures, but that's enough from {origin.title()}.

                        """)
                        break

        text += commitwarning
        text += f'###### Generated by [Testclutch]({config.get("pr_comment_url")})\n'
        return text


def main():
    args = parse_args()
    log.setup(args)

    if args.comment and not args.authfile and not args.dry_run:
        logging.error('--authfile is required with --comment')
        return 1

    if args.only_failed_prs and (not args.authfile or (args.origin and args.origin != 'gha')):
        logging.warning(
            '--only-failed-prs without GHA --authfile may fail due to insufficient quota')

    prready = GHAPRReady(args)
    prs = prready.get_ready_prs(config.get('pr_ready_logins')) if args.ready_prs else args.pr
    prstates = None
    if args.only_failed_prs:
        prstates = prready.check_gha_pr_states(prs)
        # Only include PRs that GHA shows have failed CI jobs
        # This takes three network requests to determine (each), but it can save downloading and
        # processing hundreds of log files when a PR's CI jobs were all successful.
        prstates = [(pr, state) for pr, state in prstates if state == PRStatus.FAILURE]
        prs = [pr for pr, state in prstates]

    # Check CI job status for PR
    if args.ci_status:
        if args.html:
            logging.warning('--html is ignored with --ci-status')
        print(' '.join(str(pr) for pr in prs))

        if prstates is None:
            prstates = prready.check_gha_pr_states(prs)

        # The highest value for PRStatus wins as the result code for the batch
        status = max(prstates, key=lambda x: x[1])[1] if prstates else PRStatus.READY
        if status == PRStatus.ERROR:
            logging.error("A PR is in an unacceptable state")
        logging.warning(f'Overall status return code is {status.name}')
        return status

    # Generate CI job results report for PR
    if args.report and not args.origin:
        logging.error('--origin is required with --report')
        return PRStatus.ERROR

    if args.origin == 'gha' and not args.authfile:
        logging.error('--authfile is required with gha')
        return PRStatus.ERROR

    ds = db.Datastore()
    ds.connect()

    if args.gather_analysis:
        ga = GatherPRAnalysis(ds, args)
        rc = ga.gather_analysis(prs)

    elif args.comment:
        ga = GatherPRAnalysis(ds, args)
        rc = ga.comment(prs)

    else:  # must be --report
        # Analyze only one origin at a time because each one might have different login credentials
        if args.origin == 'appveyor':
            rc = appveyor_analyze_pr(args, ds, prs)
        elif args.origin == 'azure':
            rc = azure_analyze_pr(args, ds, prs)
        elif args.origin == 'circle':
            rc = circle_analyze_pr(args, ds, prs)
        elif args.origin == 'cirrus':
            rc = cirrus_analyze_pr(args, ds, prs)
        elif args.origin == 'gha':
            rc = gha_analyze_pr(args, ds, prs)
        else:
            logging.error(f'Unsupported origin {args.origin}')
            rc = PRStatus.ERROR

    ds.close()
    return rc


if __name__ == '__main__':
    main()

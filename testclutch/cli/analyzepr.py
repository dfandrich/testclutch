"""Perform analysis of tests run on a pull request
"""

import argparse
import datetime
import enum
import logging
import textwrap
from contextlib import nullcontext
from html import escape
from typing import Optional, Sequence, Tuple

import testclutch
from testclutch import analysis
from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
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


def parse_args(args: Optional[argparse.Namespace] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Perform analysis of tests run on a pull request')
    argparsing.arguments_logging(parser)
    argparsing.arguments_ci(parser, required=False)
    with nullcontext(parser.add_mutually_exclusive_group(required=True)) as output_mode:
        output_mode.add_argument(
            '--ci-status',
            action='store_true',
            help="Check the status of CI runs associated with this PR")
        output_mode.add_argument(
            '--report',
            action='store_true',
            help='Output PR analysis report')
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
    return parser.parse_args(args=args)


def success_fail_count(meta: TestMeta, testcases: TestCases, is_aborted: bool) -> Tuple[str, str]:
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
            flaky.sort(key=lambda x: analyzer._try_integer(x[0]))
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
        if permafails:
            permafailtitle = permafailtitle + "These tests are now consistently failing: "
            permafails.sort(key=analyzer._try_integer)
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
    return 0


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
    return 0


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
    return 0


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
    return 0


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
    return 0


class PRStatus(enum.IntEnum):
    READY = 0    # PR jobs are complete
    PENDING = 1  # CI jobs are still running for this PR
    CLOSED = 2   # PR already closed
    ERROR = 3    # invalid PR


def check_gha_pr_ready(args: argparse.Namespace, prs: list[int]) -> PRStatus:
    try:
        owner, project = urls.get_project_name(args)
    except RuntimeError:
        return PRStatus.ERROR

    if urls.url_host(args.checkrepo) != 'github.com':
        # This function only makes sense when source is hosted on GitHub
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return PRStatus.ERROR

    owner, project = urls.get_project_name(args)
    gh = ghaapi.GithubApi(owner, project, gha.read_token(args.authfile))

    # The highest value for PRStatus wins as the result code for the batch
    ret = PRStatus.READY
    for pr in prs:
        pull = gh.get_pull(pr)
        if pull['state'] == 'closed':
            logging.warn(f'PR is in state {pull["state"]}')
            ret = max(PRStatus.CLOSED, ret)
            continue
        if pull['state'] != 'open':
            logging.warn(f'PR is in state {pull["state"]}')
            ret = max(PRStatus.ERROR, ret)
            continue
        if pull['locked']:
            logging.warn('PR is locked; aborting')
            ret = max(PRStatus.ERROR, ret)
            continue
        commit = pull['head']['sha']
        logging.info(f'PR#{pr} commit {commit}')

        status = gh.get_commit_status(commit)
        logging.debug(f'{len(status["statuses"])} commit statuses')
        logging.debug(f'Overall state: {status["state"]}')
        pending = 0
        jobcount = len(status['statuses'])
        for stat in status['statuses']:
            if stat['state'] != 'success':
                logging.debug(f"status is in state {stat['state']}")
            # success, pending
            if stat['state'] == 'pending':
                ret = max(PRStatus.PENDING, ret)
                pending += 1

        checkruns = gh.get_check_runs(commit)
        logging.debug(f"{len(checkruns['check_runs'])} check runs")
        jobcount += len(checkruns['check_runs'])
        for run in checkruns['check_runs']:
            # queued, in_progress, completed
            if run['status'] != 'completed':
                logging.debug(f"check run {run['id']} is in state {run['status']}")
                ret = max(PRStatus.PENDING, ret)
                pending += 1

        logging.info(f'{pending} jobs of {jobcount} still pending for PR#{pr}')

    return ret


def get_ready_prs(args: argparse.Namespace) -> list[int]:
    try:
        owner, project = urls.get_project_name(args)
    except RuntimeError:
        return []

    if urls.url_host(args.checkrepo) != 'github.com':
        # This function only makes sense when source is hosted on GitHub
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return []

    gh = ghaapi.GithubApi(owner, project, gha.read_token(args.authfile))

    pulls = gh.get_pulls('open')
    pr_recency = args.oldest if args.oldest else config.get('pr_ready_age_hours_max')
    recent = (datetime.datetime.now(tz=datetime.timezone.utc)
              - datetime.timedelta(hours=pr_recency))
    recent_prs = [pr['number'] for pr in pulls
                  if ghaapi.convert_time(pr['created_at']) > recent]
    logging.info(f'{len(pulls)} open PRs of which {len(recent_prs)} are recent ones (within '
                 f'{pr_recency} hours)')
    for prnum in recent_prs:
        logging.info(f'PR#{prnum} is eligible to be analyzed')
    return recent_prs


def main():
    args = parse_args()
    log.setup(args)

    if args.dry_run:
        logging.warning('--dry-run does nothing in this program')

    if args.ready_prs:
        prs = get_ready_prs(args)
    else:
        prs = args.pr

    # Check CI job status for PR
    if args.ci_status:
        if args.html:
            logging.warning('--html is ignored with --ci-status')
        status = check_gha_pr_ready(args, prs)
        if status == PRStatus.ERROR:
            logging.error("A PR is in an unacceptable state")
        print(status.name)
        return status

    # Generate CI job results report for PR
    if not args.origin:
        logging.error('--origin is required with --report')
        return 1

    if not args.authfile and args.origin == 'gha':
        logging.error('--authfile is required with gha')
        return 1

    ds = db.Datastore()
    ds.connect()

    # Analyze only one origin at a time because each one might have different login credentials
    if args.origin == 'gha':
        rc = gha_analyze_pr(args, ds, prs)
    elif args.origin == 'appveyor':
        rc = appveyor_analyze_pr(args, ds, prs)
    elif args.origin == 'circle':
        rc = circle_analyze_pr(args, ds, prs)
    elif args.origin == 'azure':
        rc = azure_analyze_pr(args, ds, prs)
    elif args.origin == 'cirrus':
        rc = cirrus_analyze_pr(args, ds, prs)
    else:
        logging.error(f'Unsupported origin {args.origin}')
        rc = 1

    ds.close()
    return rc


if __name__ == '__main__':
    main()

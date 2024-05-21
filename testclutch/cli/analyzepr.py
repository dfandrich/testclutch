"""Perform analysis of tests run on a pull request
"""

import argparse
import datetime
import logging
import sys
import textwrap
import urllib
from html import escape
from typing import Optional, Sequence, Tuple

import testclutch
from testclutch import analysis
from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch import summarize
from testclutch.ingest import prappveyor
from testclutch.ingest import prazure
from testclutch.ingest import prcircleci
from testclutch.ingest import prcirrus
from testclutch.ingest import prgha
from testclutch.logdef import ParsedLog, TestCases, TestMeta
from testclutch.testcasedef import TestResult


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Perform analysis of tests run on a pull request')
    argparsing.arguments_logging(parser)
    argparsing.arguments_ci(parser)
    parser.add_argument(
        '--pr',
        required=True,
        type=int,
        nargs='+',
        help='pull request number on the --checkrepo to analyze')
    parser.add_argument(
        '--html',
        action='store_true',
        help='Output results in HTML')
    parser.add_argument(
        '--html-fragment',
        action='store_true',
        help='Whether to output HTML page header and footers')
    return parser.parse_args(args=args)


def success_fail_count(meta: TestMeta, testcases: TestCases, is_aborted: bool) -> Tuple[str, str]:
    test_result = meta.get('testresult', 'unknown')
    prefix_char = ''
    if test_result == 'success':
        cssclass = 'success'
        num = len([1 for x in testcases if x[1] == TestResult.PASS])
    elif test_result == 'truncated' or is_aborted:
        cssclass = 'aborted'
        num_failed = len([1 for x in testcases if x[1] == TestResult.FAIL])
        if num_failed == 0:
            num = len([1 for x in testcases if x[1] == TestResult.PASS])
        else:
            num = num_failed
            prefix_char = '*'
    elif test_result == 'failure':
        cssclass = 'failure'
        num = len([1 for x in testcases if x[1] == TestResult.FAIL])
        prefix_char = '*'
    elif test_result == 'unknown':
        # Shouldn't normally be encountered for tests ingested after Aug 1/23.
        # just look at the # failures in this case
        num_failed = len([1 for x in testcases if x[1] == TestResult.FAIL])
        if num_failed == 0:
            cssclass = 'success'
            num = len([1 for x in testcases if x[1] == TestResult.PASS])
        else:
            cssclass = 'unknown'
            num = num_failed
            prefix_char = '*'
    else:
        # Not sure what this is
        logging.error('Internal error determining job status for %s', meta['cijob'])
        cssclass = 'failure'
        num = len([1 for x in testcases if x[1] == TestResult.FAIL])
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
    analyzer = analysis.ResultsOverTimeByUniqueJob(ds)
    if not fragment:
        print_html_header(pr)
        now = datetime.datetime.now(datetime.timezone.utc)
        print(textwrap.dedent(f"""\
            <h1>Test report for PR#{pr} as of
                {escape(now.strftime('%a, %d %b %Y %H:%M:%S %z'))}</h1>
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

    for meta, testcases in test_results:
        print('<tr>')

        # First, show job name
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
        if analyzer.all_jobs_status:
            # Look at the most recent run to determine what is still failing
            job_status = analyzer.all_jobs_status[0]
            if job_status.failed_tests:
                # Latest job has failed. See how long it has been failing.
                # TODO: can I get the info from first_failure somewhere else instead?
                _, _, current_failure_counts = first_failure
                permafails = [failure for failure in job_status.failed_tests
                              if (current_failure_counts[failure]
                                  > config.get('permafail_failures_min'))]
                if permafails:
                    if job_status.test_result == 'success':
                        permafailtitle = ("Some tests are failing but the test was marked as "
                                          "successful, so "
                                          "these test results were likely marked to be ignored.")
                    permafailtitle = permafailtitle + "These tests are now consistently failing: "
                    permafails.sort(key=analyzer._try_integer)
                    permafailtitle = permafailtitle + (
                        ', '.join([escape(testname) for testname in permafails]))

        if flakytitle:
            print('<td class="flaky">'
                  f'<a href="{escape(flakyfailurl)}" title="{flakytitle}">Flaky</a>')
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
        if is_aborted:
            test_result = 'aborted'
        else:
            test_result = meta.get('testresult', 'unknown')
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


def analyze_pr(test_results: Sequence[ParsedLog], ds: db.Datastore):
    logging.info('Analyzing %d test results', len(test_results))
    for testmeta, testcases in test_results:
        analyzer = analysis.ResultsOverTimeByUniqueJob(ds)
        print(f"Test [{testmeta['origin']}] {testmeta['ciname']} / {testmeta['cijob']} ({testmeta['testformat']})")
        failed = [x for x in testcases if x[1] == TestResult.FAIL]
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
                print(f'{test[0]} (failed in {test[2]})')
        print('Here is an analysis of this test in this environment recently in the repo')

        globaluniquejob = analyzer.make_global_unique_job(testmeta)
        analyzer.analyze_by_unique_job(globaluniquejob)
        print()


def appveyor_analyze_pr(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1
    account = args.account
    if not account:
        account = path.split('/')[1]
    project = args.project
    if not project:
        project = path.split('/')[2]

    av = prappveyor.AppveyorAnalyzeJob(account, project, args.checkrepo, ds, None)

    for pr in args.pr:
        logging.info(f'Analyzing pull request {pr}')
        results = av.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(results, ds)
    return 0


def azure_analyze_pr(args: argparse.Namespace, ds: db.Datastore) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1
    organization = args.account
    if not organization:
        organization = path.split('/')[1]
    project = args.project
    if not project:
        project = path.split('/')[2]

    azure = prazure.AzureAnalyzer(organization, project, args.checkrepo, ds)

    for pr in args.pr:
        logging.info(f'Analyzing pull request {pr}')
        results = azure.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(results, ds)
    return 0


def circle_analyze_pr(args: argparse.Namespace, ds: db.Datastore) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    ci = prcircleci.CircleAnalyzer(args.checkrepo, ds)

    for pr in args.pr:
        logging.info(f'Analyzing pull request {pr}')
        results = ci.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(results, ds)
    return 0


def cirrus_analyze_pr(args: argparse.Namespace, ds: db.Datastore) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    cirrus = prcirrus.CirrusAnalyzer(args.checkrepo, ds, None)

    for pr in args.pr:
        logging.info(f'Analyzing pull request {pr}')
        results = cirrus.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(results, ds)
    return 0


def gha_analyze_pr(args: argparse.Namespace, ds: db.Datastore) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    token = args.authfile.read().strip()
    ghi = prgha.GithubAnalyzeJob(parts[1], parts[2], token, ds)

    for pr in args.pr:
        logging.info(f'Analyzing pull request {pr}')
        results = ghi.gather_pr(pr)
        results.sort(key=lambda x: x[0]['uniquejobname'])
        if args.html:
            analyze_pr_html(pr, results, ds, args.html_fragment)
        else:
            analyze_pr(results, ds)
    return 0


def main():
    args = parse_args()
    log.setup(args)

    if args.dry_run:
        logging.warning('--dry-run does nothing in thie program')

    if not args.authfile and args.origin == 'gha':
        logging.error('--authfile is mandatory with --pr')
        sys.exit(1)

    ds = db.Datastore()
    ds.connect()

    # Analyze only one origin at a time because each on might have different login credentials
    if args.origin == 'gha':
        rc = gha_analyze_pr(args, ds)
    elif args.origin == 'appveyor':
        rc = appveyor_analyze_pr(args, ds)
    elif args.origin == 'circle':
        rc = circle_analyze_pr(args, ds)
    elif args.origin == 'azure':
        rc = azure_analyze_pr(args, ds)
    elif args.origin == 'cirrus':
        rc = cirrus_analyze_pr(args, ds)
    else:
        logging.error(f'Unsupported origin {args.origin}')
        rc = 1

    ds.close()
    return rc


if __name__ == '__main__':
    main()

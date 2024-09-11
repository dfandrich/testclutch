"""Query database of tests
"""

import argparse
import datetime
import logging
import re
import sys

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch import summarize


NVO_RE = re.compile(r'^([^<>=!%]+)(=|<>|!=|<=|>=|<|>|%|!%)(.*)$')


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Query database of tests')
    argparsing.arguments_logging(parser)
    parser.add_argument(
        '-t', '--show-tests',
        action='store_true',
        help='Show test results')
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--since',
        help='Only look at logs created since this ISO date or number of hours')
    parser.add_argument(
        'query',
        nargs='?',
        help='DB query arguments')
    return parser.parse_args(args=args)


def operator_from_matcher(matcher: str) -> str:
    """Convert the command-line operator to a SQL operator"""
    if matcher == '%':
        return 'LIKE'
    if matcher == '!%':
        return 'NOT LIKE'
    return matcher


def main():
    args = parse_args()
    log.setup(args)

    if args.since:
        try:
            since = datetime.datetime.now() - datetime.timedelta(hours=int(args.since))
        except ValueError:
            since = datetime.datetime.fromisoformat(args.since)
    else:
        # Default to same time as logfile analysis time since it's probably only
        # recent tests we would want to see
        since = (datetime.datetime.now()
                 - datetime.timedelta(hours=config.get('analysis_hours')))

    ds = db.Datastore()
    ds.connect()

    if args.query:
        # Search for logs matching metadata
        # e.g. runid=1234567, runtestsduration>555000000
        val = NVO_RE.search(args.query)
        if not val:
            logging.error('Invalid match query: %s', args.query)
            sys.exit(1)
        op = operator_from_matcher(val.group(2))
        rows = ds.select_meta_test_runs(args.checkrepo, since,
                                        val.group(1), op, val.group(3))

    else:
        # Show all logs
        rows = ds.select_all_test_runs(args.checkrepo, since)

    for row in rows:
        print(row[0], row[1])
        meta = row[2]
        for n, v in meta.items():
            print(f'{n}={v}')
        testcases = ds.select_test_results(row[0])
        summarize.show_totals(testcases)
        if args.show_tests:
            testcases.sort(key=lambda x: summarize.try_integer(x[0]))
            for t in testcases:
                print(t)
        print()

    ds.close()
    print(f'{len(rows)} matching logs')


if __name__ == '__main__':
    main()

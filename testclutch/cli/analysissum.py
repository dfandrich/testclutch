"""Generate analysis summary of test data."""

import argparse
import logging
import sys

from testclutch import analysis
from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze test results in the database')
    argparsing.arguments_logging(parser)
    argparsing.arguments_config(parser)
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--uniquejob',
        nargs=1,
        help='unique test job ID')
    parser.add_argument(
        '--html',
        action='store_true',
        help='Output test summary in HTML')
    return parser.parse_args(args=args)


def main():
    args = parse_args()
    log.setup(args)

    if args.uniquejob and args.html:
        print('--uniquejob and --html are not compatible', file=sys.stderr)
        sys.exit(1)

    with db.Datastore() as ds:
        analyzer = analysis.ResultsOverTimeByUniqueJob(ds, args.checkrepo)

        if args.uniquejob:
            logging.info(f'Analyzing job {args.uniquejob[0]}')
            analyzer.analyze_by_unique_job(args.uniquejob[0])
        elif args.html:
            logging.info('Analyzing all unique jobs and creating table')
            analyzer.show_job_failure_table(args.checkrepo)
        else:
            logging.info('Analyzing all unique jobs')
            analyzer.analyze_all_by_unique_job(args.checkrepo)


if __name__ == '__main__':
    main()

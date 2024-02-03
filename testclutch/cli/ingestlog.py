"""Ingests a curl test log file into the database
"""

import argparse
import logging
import os
import stat
import sys
import urllib.parse
from typing import Dict, Optional

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import summarize
from testclutch.ingest import appveyor
from testclutch.ingest import azure
from testclutch.ingest import circleci
from testclutch.ingest import cirrus
from testclutch.ingest import curlauto
from testclutch.ingest import gha
from testclutch.logparser import logparse


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Ingest test log files into the database')
    argparsing.arguments_logging(parser)
    argparsing.arguments_ci(parser)
    parser.add_argument(
        '--branch',
        default=config.expand('branch'),
        help="Branch to use when searching for test logs to ingest")
    parser.add_argument(
        '--runid',
        nargs='+',
        help='unique test run ID(s) (specific to the origin)')
    parser.add_argument(
        '--meta',
        action='append',
        help='metadata to add to the log(s), of the form field=value; use once per value')
    parser.add_argument(
        '--howrecent',
        type=int,
        help='Maximum age of logs to ingest, in hours')
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Whether to overwrite an existing test log, if found')
    parser.add_argument('files', nargs='*', type=argparse.FileType('r'), default=[sys.stdin])
    return parser.parse_args(args=args)


def gha_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    token = args.authfile.read().strip()
    ghi = gha.GithubIngestor(parts[1], parts[2], token, ds, args.overwrite)

    for run in args.runid:
        ghi.ingest_a_run(int(run))
    return 0


def circle_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    ci = circleci.CircleIngestor(args.checkrepo, ds, args.overwrite)

    for run in args.runid:
        ci.ingest_a_run(int(run))
    return 0


def cirrus_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    ci = cirrus.CirrusIngestor(args.checkrepo, ds, None, args.overwrite)

    for run in args.runid:
        ci.ingest_a_run(int(run))
    return 0


def appveyor_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
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

    av = appveyor.AppveyorIngestor(account, project, args.checkrepo, ds, None, args.overwrite)

    for run in args.runid:
        av.ingest_a_run(int(run))
    return 0


def azure_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
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

    azurei = azure.AzureIngestor(organization, project, args.checkrepo, ds, args.overwrite)

    for run in args.runid:
        azurei.ingest_a_run(int(run))
    return 0


def curlauto_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    if args.checkrepo != 'https://github.com/curl/curl':
        logging.error('Invalid GitHub repository URL for curlauto: %s', args.checkrepo)
        return 1

    curlautoi = curlauto.CurlAutoIngestor(args.checkrepo, ds, args.overwrite)

    for run in args.runid:
        curlautoi.ingest_run(run)
    return 0


def gha_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    token = args.authfile.read().strip()
    ghi = gha.GithubIngestor(parts[1], parts[2], token, ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} from GHA')
    ghi.ingest_all_logs(args.branch, args.howrecent)
    return 0


def cirrus_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    ci = cirrus.CirrusIngestor(args.checkrepo, ds, None, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} from Cirrus')
    ci.ingest_all_logs(args.branch, args.howrecent)
    return 0


def circle_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    scheme, netloc, path, query, fragment = urllib.parse.urlsplit(args.checkrepo)
    parts = path.split('/')
    if netloc.casefold() != 'github.com' or len(parts) != 3:
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    circle = circleci.CircleIngestor(args.checkrepo, ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} '
                 'from CircleCI')
    circle.ingest_all_logs(args.branch, args.howrecent)
    return 0


def appveyor_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
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

    av = appveyor.AppveyorIngestor(account, project, args.checkrepo, ds, None, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs '
                 f'for branch {args.branch} from Appveyor')
    av.ingest_all_logs(args.branch, args.howrecent)
    return 0


def azure_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
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

    azurei = azure.AzureIngestor(organization, project, args.checkrepo, ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs '
                 f'for branch {args.branch} from Azure')
    azurei.ingest_all_logs(args.branch, args.howrecent)
    return 0


def curlauto_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    if args.checkrepo != 'https://github.com/curl/curl':
        logging.error('Invalid GitHub repository URL for curlauto: %s', args.checkrepo)
        return 1

    curlautoi = curlauto.CurlAutoIngestor(args.checkrepo, ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs')
    curlautoi.ingest_all_logs(args.howrecent)
    return 0


def parse_meta(args: argparse.Namespace) -> Dict:
    """Parse the --meta option(s) to produce a dict"""
    meta = {}
    if args.meta:
        for metaval in args.meta:
            try:
                n, v = metaval.split('=', 1)
            except ValueError:
                # Handle the case of a missing = by treating the value as empty
                n = metaval
                v = ''
            meta[n] = v
    return meta


def ingest_files(args: argparse.Namespace):
    if not args.dry_run:
        ds = db.Datastore()
        ds.connect()

    extrameta = parse_meta(args)

    for file in args.files:
        meta, testcases = logparse.parse_log_file(file)
        meta['origin'] = args.origin
        meta['checkrepo'] = args.checkrepo
        absfn = os.path.abspath(file.name)
        # We have nothing else to go on, so use the file name as the unique job name
        # which means that you can't correlate between jobs stored in different files.
        # The same goes for runid.
        meta['uniquejobname'] = absfn
        meta['runid'] = absfn
        # We don't have anything better than this
        meta['cijob'] = os.path.basename(file.name)
        # TODO: catch exceptions
        meta['runfinishtime'] = os.fstat(file.fileno())[stat.ST_MTIME]
        meta['jobfinishtime'] = meta['runfinishtime']

        # Any of the above can be overridden on the command-line
        meta = {**meta, **extrameta}

        if args.verbose:
            for n, v in meta.items():
                print(f'{n}={v}')
            if args.debug:
                for c in testcases:
                    print(c)
            summarize.show_totals(testcases)
            print()

        logging.info('Retrieved test for %s %s %s',
                     meta['origin'], meta['checkrepo'], file.name)

        if not args.dry_run:
            try:
                ds.store_test_run(meta, testcases)
            except db.IntegrityError:
                logging.warning('Log file has already been ingested!')

    if not args.dry_run:
        ds.close()


def main():
    args = parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(levelno)s %(filename)s: %(message)s',)
        args.verbose = True
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format='%(filename)s: %(message)s',)

    if args.runid:
        if not args.authfile and args.origin == 'gha':
            logging.error('--authfile is mandatory with --runid')
            sys.exit(1)
        if args.meta:
            logging.error('Metadata fields cannot be added with --runid')
            sys.exit(1)

        if not args.dry_run:
            ds = db.Datastore()
            ds.connect()
        else:
            ds = None

        if args.origin == 'gha':
            sys.exit(gha_ingest_runs(args, ds))
        elif args.origin == 'circle':
            sys.exit(circle_ingest_runs(args, ds))
        elif args.origin == 'cirrus':
            sys.exit(cirrus_ingest_runs(args, ds))
        elif args.origin == 'appveyor':
            sys.exit(appveyor_ingest_runs(args, ds))
        elif args.origin == 'azure':
            sys.exit(azure_ingest_runs(args, ds))
        elif args.origin == 'curlauto':
            sys.exit(curlauto_ingest_runs(args, ds))
        else:
            logging.error('Origin %s is not supported with --runid', args.origin)
            if ds:
                ds.close()
            sys.exit(1)

        if ds:
            ds.close()

    if args.howrecent:
        if args.meta:
            logging.error('Metadata fields cannot be added in search mode')
            sys.exit(1)

        if not args.dry_run:
            ds = db.Datastore()
            ds.connect()
        else:
            ds = None

        if args.origin == 'gha':
            sys.exit(gha_ingest_recent_runs(args, ds))
        elif args.origin == 'circle':
            sys.exit(circle_ingest_recent_runs(args, ds))
        elif args.origin == 'cirrus':
            sys.exit(cirrus_ingest_recent_runs(args, ds))
        elif args.origin == 'appveyor':
            sys.exit(appveyor_ingest_recent_runs(args, ds))
        elif args.origin == 'azure':
            sys.exit(azure_ingest_recent_runs(args, ds))
        elif args.origin == 'curlauto':
            sys.exit(curlauto_ingest_recent_runs(args, ds))
        else:
            logging.error('Origin %s is not supported with --howrecent', args.origin)
            if ds:
                ds.close()
            sys.exit(1)

        if ds:
            ds.close()

    if args.origin != 'local':
        logging.warning(f"It's odd to be reading {args.origin} logs from files, but ok")

    ingest_files(args)


if __name__ == '__main__':
    main()

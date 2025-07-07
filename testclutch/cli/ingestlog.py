"""Ingests a curl test log file into the database."""

import argparse
import contextlib
import logging
import os
import stat
import sys
from typing import Optional

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch import summarize
from testclutch import urls
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
    argparsing.arguments_config(parser)
    argparsing.arguments_ci(parser)
    parser.add_argument(
        '--branch',
        default=config.expand('branch'),
        help='Branch to use when searching for test logs to ingest')
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
    if urls.url_host(args.checkrepo) != 'github.com':
        # This function only makes sense when source is hosted on GitHub
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    owner, project = urls.get_project_name(args)
    ghi = gha.GithubIngestor(owner, project, gha.read_token(args.authfile), ds, args.overwrite)

    for run in args.runid:
        ghi.ingest_a_run(int(run))
    return 0


def circle_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    ci = circleci.CircleIngestor(args.checkrepo, ds, args.overwrite)

    for run in args.runid:
        ci.ingest_a_run(int(run))
    return 0


def cirrus_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    ci = cirrus.CirrusIngestor(args.checkrepo, ds, None, args.overwrite)

    for run in args.runid:
        ci.ingest_a_run(int(run))
    return 0


def appveyor_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    account, project = urls.get_project_name(args)
    av = appveyor.AppveyorIngestor(account, project, args.checkrepo, ds, None, args.overwrite)

    for run in args.runid:
        av.ingest_a_run(int(run))
    return 0


def azure_ingest_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    account, project = urls.get_project_name(args)
    azurei = azure.AzureIngestor(account, project, args.checkrepo, ds, args.overwrite)

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
    if urls.url_host(args.checkrepo) != 'github.com':
        # This function only makes sense when source is hosted on GitHub
        logging.error('Invalid GitHub repository URL: %s', args.checkrepo)
        return 1

    owner, project = urls.get_project_name(args)
    ghi = gha.GithubIngestor(owner, project, gha.read_token(args.authfile), ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} from GHA')
    ghi.ingest_all_logs(args.branch, args.howrecent)
    return 0


def cirrus_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    ci = cirrus.CirrusIngestor(args.checkrepo, ds, None, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} from Cirrus')
    ci.ingest_all_logs(args.branch, args.howrecent)
    return 0


def circle_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    circle = circleci.CircleIngestor(args.checkrepo, ds, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs for branch {args.branch} '
                 'from CircleCI')
    circle.ingest_all_logs(args.branch, args.howrecent)
    return 0


def appveyor_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    account, project = urls.get_project_name(args)
    av = appveyor.AppveyorIngestor(account, project, args.checkrepo, ds, None, args.overwrite)

    logging.info(f'Retrieving {args.howrecent} hours of logs '
                 f'for branch {args.branch} from Appveyor')
    av.ingest_all_logs(args.branch, args.howrecent)
    return 0


def azure_ingest_recent_runs(args: argparse.Namespace, ds: Optional[db.Datastore]) -> int:
    account, project = urls.get_project_name(args)
    azurei = azure.AzureIngestor(account, project, args.checkrepo, ds, args.overwrite)

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


def parse_meta(args: argparse.Namespace) -> dict:
    """Parse the --meta option(s) to produce a dict."""
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
        for meta, testcases in logparse.parse_log_files(file):
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
                    logging.info('Log file has already been ingested!')

    if not args.dry_run:
        ds.close()


def main() -> int:
    args = parse_args()
    log.setup(args, subprogram=args.origin)

    if not args.authfile and args.origin == 'gha':
        logging.error('--authfile is required with --origin=gha')
        return 1

    if args.runid:
        if args.meta:
            logging.error('Metadata fields cannot be added with --runid')
            return 1

        with db.Datastore() if not args.dry_run else contextlib.nullcontext() as ds:
            if args.origin == 'gha':
                return gha_ingest_runs(args, ds)
            if args.origin == 'circle':
                return circle_ingest_runs(args, ds)
            if args.origin == 'cirrus':
                return cirrus_ingest_runs(args, ds)
            if args.origin == 'appveyor':
                return appveyor_ingest_runs(args, ds)
            if args.origin == 'azure':
                return azure_ingest_runs(args, ds)
            if args.origin == 'curlauto':
                return curlauto_ingest_runs(args, ds)

            logging.error('Origin %s is not supported with --runid', args.origin)
            return 1

    if args.howrecent:
        if args.meta:
            logging.error('Metadata fields cannot be added in search mode')
            return 1

        with db.Datastore() if not args.dry_run else contextlib.nullcontext() as ds:
            if args.origin == 'gha':
                return gha_ingest_recent_runs(args, ds)
            if args.origin == 'circle':
                return circle_ingest_recent_runs(args, ds)
            if args.origin == 'cirrus':
                return cirrus_ingest_recent_runs(args, ds)
            if args.origin == 'appveyor':
                return appveyor_ingest_recent_runs(args, ds)
            if args.origin == 'azure':
                return azure_ingest_recent_runs(args, ds)
            if args.origin == 'curlauto':
                return curlauto_ingest_recent_runs(args, ds)

            logging.error('Origin %s is not supported with --howrecent', args.origin)
            return 1

    if args.origin != 'local':
        logging.warning(f"It's odd to be reading {args.origin} logs from files, but ok")

    ingest_files(args)
    return 0


if __name__ == '__main__':
    main()

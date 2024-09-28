"""Ingest logs from Cirrus CI."""

import datetime
import logging
import re
import urllib.parse
from typing import Any, Iterable, Optional

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import cirrusapi
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


DEFAULT_EXT = '.log'
LOGSUBDIR = 'cirrus'

SANITIZE_PATH_RE = re.compile(r'[^-\w+!@#%^&()]')


def sanitize_path(path: str) -> str:
    """Convert the given URL path into one that is not too problematic to have on a filesystem."""
    return SANITIZE_PATH_RE.sub('-', path)


class CirrusIngestor:
    """Ingest logs from Cirrus CI."""

    def __init__(self, repo: str, ds: Optional[db.Datastore], token: Optional[str],
                 overwrite: bool = False):
        # TODO: probably need account/project to be passed in, like Appveyor
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(repo)
        safe_path = sanitize_path(path)
        self.repo = f'{netloc}{safe_path}'
        self.cirrus = cirrusapi.CirrusApi(repo, token)
        self.ds = ds
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'cirrus',
                     'checkrepo': repo
                     }
        logcache.create_dirs(LOGSUBDIR)

    def _log_file_path(self, run_id: int, task_id: int, command_name: str) -> str:
        command_name.replace('/', '_')  # sanitize file name
        return f'{LOGSUBDIR}/cirrus-{self.repo}-{run_id}-{task_id}-{command_name}{DEFAULT_EXT}'

    def ingest_all_logs(self, branch: str, hours: int):
        since = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=hours)
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        # TODO: try to figure out how to filter by hours in GraphQL instead of filtering here.
        # GraphQL schema which "fetching only nodes after this node (exclusive): after:"
        rsp = self.cirrus.get_runs(branch)
        for run in rsp['data']['ownerRepository']['builds']['edges']:
            node = run['node']
            if node['status'] not in frozenset(('ABORTED', 'FAILED', 'COMPLETED')):
                # Run is not complete; ignore it
                skipped += 1
                logging.debug('Run %s status is %s', node['id'], node['status'])
                continue
            if node['pullRequest']:
                # Not a normal run on a branch; ignore it
                skipped += 1
                logging.debug('Run %s is a pull request #%d', node['id'], node['pullRequest'])
                continue
            if datetime.datetime.fromtimestamp(node['buildCreatedTimestamp'] / 1000,
                                               tz=datetime.timezone.utc) < since:
                # Build is too old
                skipped += 1
                logging.debug('Run %s is too old', node['id'])
                continue
            count += 1
            self.ingest_a_run(node['id'])
        logging.debug(f'{count} matching runs found, {skipped} skipped')

    def ingest_a_run(self, run_id: int):
        logging.debug('Getting run %s', run_id)
        run = self.cirrus.get_run(run_id)
        self.ingest_run(run)

    def ingest_run(self, run: dict[str, Any]):
        """Ingests not one log, but logs for one job."""
        build = run['data']['build']
        if not build:
            raise RuntimeError('Run ID is invalid')
        run_id = int(build['id'])

        cimeta = {}
        cimeta['runid'] = run_id
        cimeta['commit'] = build['changeIdInRepo']
        cimeta['summary'] = build['changeMessageTitle']
        cimeta['branch'] = build['branch']
        cimeta['runtriggertime'] = int(build['buildCreatedTimestamp'] / 1000)
        cimeta['ciresult'] = build['status'].lower()
        # If all the tasks are skipped (yes, despite the run being completed),
        # then this can be None
        if build['durationInSeconds'] is not None:
            cimeta['runduration'] = int(build['durationInSeconds']) * 1000000
        if build['pullRequest']:
            cimeta['pullrequest'] = int(build['pullRequest'])

        found_jobs = set()
        for task in run['data']['build']['latestGroupTasks']:
            task_id = int(task['id'])
            if task['status'] == 'SKIPPED':
                # A task can be SKIPPED even if the run is COMPLETED
                logging.debug('Task %s was skipped', task_id)
                continue
            jobmeta = {}
            jobmeta['jobid'] = task_id
            jobmeta['ciname'] = 'Cirrus'
            jobmeta['ciarch'] = task['instanceArchitecture'].lower()
            jobmeta['cios'] = task['instancePlatform'].lower()
            jobmeta['cijob'] = task['name']
            if jobmeta['cijob'] in found_jobs:
                # User needs to modify the CI job configuration to avoid duplicate job names
                logging.error('Job name %s is not unique; skipping further duplicate instances',
                              jobmeta['cijob'])
                continue
            if task['executingTimestamp']:
                jobmeta['jobstarttime'] = int(task['executingTimestamp'] / 1000)
            if task['finalStatusTimestamp']:
                jobmeta['jobfinishtime'] = int(task['finalStatusTimestamp'] / 1000)
            jobmeta['jobduration'] = int(task['durationInSeconds']) * 1000000

            found_jobs.add(jobmeta['cijob'])
            jobmeta['url'] = f'https://cirrus-ci.com/task/{task_id}'
            commands = [c['name'] for c in task['commands']]

            if not self.download_log(run_id, task_id, commands):
                meta = {**cimeta, **jobmeta}
                self.ingest_log(run_id, task_id, commands, meta)
            else:
                logging.error('Could not download a log for run %d task %d', run_id, task_id)

    def download_log(self, run_id: int, task_id: int, task_commands: Iterable[str]
                     ) -> Optional[str]:
        for command_name in task_commands:
            newfn = self._log_file_path(run_id, task_id, command_name)
            if logcache.in_cache(newfn):
                logging.debug('Log file is in cache as %s', newfn)
            else:
                try:
                    fn, ft = self.cirrus.get_logs(task_id, command_name)
                except cirrusapi.HTTPError as e:
                    logging.error(e.args[0])
                    if e.response.status_code == 404:
                        return 'Log not found on server error'
                    return 'Unknown error downloading log'
                logging.debug(f'fn {fn} type {ft}')
                logging.debug('Moving file to %s', newfn)
                logcache.move_into_cache_compressed(fn, newfn)
        return None

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        """Store the data about one test.

        This method may be overridden to do something other than storing.
        """
        if not self.dry_run:
            try:
                self.ds.store_test_run(meta, testcases)
            except db.IntegrityError:
                logging.info('Log file has already been ingested!')
                if self.overwrite:
                    logging.info('Overwriting old log')
                    rec_id = self.ds.select_rec_id(meta)
                    if rec_id is None:
                        logging.error(f'Unable to find existing test for run {meta["runid"]}')
                    else:
                        self.ds.delete_test_run(rec_id)
                        self.ds.store_test_run(meta, testcases)

    def ingest_log_file(self, fn: str, cimeta: TestMeta):
        logging.debug('Ingesting file %s', fn)
        # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
        readylog = logcache.open_cache_file(fn)
        meta, testcases = logparse.parse_log_file(readylog)
        if meta:
            # combine ci metadata with metadata from log file
            meta = {**self.meta, **meta, **cimeta}
            # Unique CI job identifier
            # This is the human-specified name, which is probably possible to
            # make duplicate, so this isn't ideal.
            meta['uniquejobname'] = meta['cijob'] + '!' + meta['testformat']

            logging.info('Retrieved test for %s %s %s',
                         meta['origin'], meta['checkrepo'], meta['cijob'])
            for n, v in meta.items():
                logging.debug(f'{n}={v}')
            summary = summarize.summarize_totals(testcases)
            for l in summary:
                logging.debug('%s', l.strip())
            logging.debug('')

            self.store_test_run(meta, testcases)

    def ingest_log(self, run_id: int, task_id: int, commands: Iterable[str], cimeta: TestMeta):
        for command in commands:
            jobmeta = {}
            jobmeta['cistep'] = command
            meta = {**cimeta, **jobmeta}
            self.ingest_log_file(self._log_file_path(run_id, task_id, command), meta)

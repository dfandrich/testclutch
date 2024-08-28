"""Ingest logs from Appveyor"""

import datetime
import logging
import re
from typing import Any, Optional

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import appveyorapi
from testclutch.ingest import logprefix
from testclutch.ingest import msbuild
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


DEFAULT_EXT = '.log'
LOGSUBDIR = 'appveyor'

AV_TIME_RE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d{1,7})([-+]\d\d):(\d\d)$')


class AppveyorIngestor:
    def __init__(self, account: str, project: str, repo: str, ds: Optional[db.Datastore],
                 token: Optional[str], overwrite: bool = False):
        self.account = account
        self.project = project
        self.repo = repo
        self.av = appveyorapi.AppveyorApi(account, project, token)
        self.ds = ds
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'appveyor', 'checkrepo': repo}
        logcache.create_dirs(LOGSUBDIR)

    def ingest_a_run(self, run_id: int):
        logging.debug('Getting run %s', run_id)
        run = self.av.get_run(run_id)
        self.ingest_run(run)

    def ingest_a_run_by_buildver(self, build_ver: str):
        logging.debug('Getting run %s', build_ver)
        run = self.av.get_run_by_buildver(build_ver)
        self.ingest_run(run)

    def _convert_time(self, timestamp: str) -> datetime.datetime:
        """Converts an Appveyor time into a datetime object.

        The microseconds field has too many digits and strptime barfs on it.
        """
        t = AV_TIME_RE.search(timestamp)
        if not t:
            logging.error('Cannot parse date: %s', timestamp)
            return datetime.datetime.fromtimestamp(0)
        microsec = t.group(2)[:7]
        return datetime.datetime.strptime(t.group(1) + microsec + t.group(3) + t.group(4),
                                          '%Y-%m-%dT%H:%M:%S.%f%z')

    def ingest_run(self, run: dict[str, Any]):
        """Ingests not one log, but logs for one job"""
        project = run['project']
        build = run['build']
        build_id = build['buildId']
        cimeta = {}
        cimeta['ciname'] = 'Appveyor'
        cimeta['account'] = f'{self.account}/{self.project}'
        cimeta['runid'] = build_id
        cimeta['buildver'] = build['version']
        cimeta['commit'] = build['commitId']
        cimeta['summary'] = build['message']
        cimeta['branch'] = build['branch']
        if project['repositoryScm'] == 'git' and project['repositoryType'] == 'gitHub':
            cimeta['sourcerepo'] = 'https://github.com/' + project['repositoryName']
        else:
            logging.warning('Unknown source repository type: %s', project['repositoryType'])
        if 'pullRequestId' in build:
            cimeta['pullrequest'] = build['pullRequestId']

        found_jobs = set()
        for job in build['jobs']:
            if 'started' not in job:
                # This job probably hasn't started yet or something has gone wrong
                continue

            job_id = job['jobId']

            # Gather metadata about this run
            jobmeta = {}
            jobmeta['jobid'] = job_id
            jobmeta['cijob'] = job['name']
            # Unique CI job identifier
            # This is the human-specified name, which is probably possible to
            # make duplicate, so this isn't ideal.
            if jobmeta['cijob'] in found_jobs:
                # User needs to modify the CI job configuration to avoid duplicate job names
                logging.error('Job name %s is not unique; skipping further duplicate instances',
                              jobmeta['cijob'])
                continue
            found_jobs.add(jobmeta['cijob'])
            jobmeta['url'] = f"https://ci.appveyor.com/project/{project['accountName']}/{project['slug']}/builds/{build['buildId']}/job/{job['jobId']}"
            jobmeta['jobstarttime'] = int(self._convert_time(job['started']).timestamp())
            jobmeta['runtriggertime'] = int(self._convert_time(job['created']).timestamp())
            jobmeta['jobfinishtime'] = int(self._convert_time(job['finished']).timestamp())
            jobmeta['jobstarttime'] = int(self._convert_time(job['started']).timestamp())
            runduration = (self._convert_time(job['finished'])
                           - self._convert_time(job['started']))
            jobmeta['runduration'] = runduration.seconds * 1000000 + runduration.microseconds
            jobmeta['cios'] = job['osType']
            jobmeta['ciresult'] = job['status']

            if self.download_log(build_id, job_id):
                meta = {**cimeta, **jobmeta}
                self.process_log_file(self._log_file_path(build_id, job_id), meta)
            else:
                logging.info("No logs available to ingest")

    def _log_file_path(self, build_id: int, job_id: str) -> str:
        if not job_id.isalnum():
            # Should never happen, but do this to avoid filesystem attacks
            job_id = hash(job_id)
        return f'{LOGSUBDIR}/appveyor-{self.account}-{self.project}-{build_id}-{job_id}{DEFAULT_EXT}'

    def download_log(self, build_id: int, job_id: str) -> str:
        newfn = self._log_file_path(build_id, job_id)
        if logcache.in_cache(newfn):
            logging.debug('Log file is in cache as %s', newfn)
        else:
            fn, ft = self.av.get_logs(job_id)
            logging.debug(f'fn {fn} type {ft}')
            logging.debug('Moving file to %s', newfn)
            logcache.move_into_cache_compressed(fn, newfn)
        return newfn

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        """Store the data about one test

        This method may be overridden to do something other than storing.
        """
        if not self.dry_run:
            logging.info('Storing test result in database')
            try:
                self.ds.store_test_run(meta, testcases)
            except db.IntegrityError:
                logging.info('Log file has already been ingested!')
                if self.overwrite:
                    logging.info('Overwriting old log')
                    rec_id = self.ds.select_rec_id(meta)
                    if rec_id is None:
                        logging.error(f"Unable to find existing test for run {meta['runid']}")
                    else:
                        self.ds.delete_test_run(rec_id)
                        self.ds.store_test_run(meta, testcases)

    def process_log_file(self, fn: str, cimeta: TestMeta):
        logging.debug('Processing file %s', fn)
        # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
        readylog = msbuild.MsBuildLog(
            logprefix.FixedPrefixedLog(logcache.open_cache_file(fn), prefixlen=11))
        meta, testcases = logparse.parse_log_file(readylog)
        if meta:
            # combine ci metadata with metadata from log file
            meta = {**self.meta, **meta, **cimeta}
            meta['uniquejobname'] = meta['cijob'] + '!' + meta['testformat']

            logging.info('Retrieved test for %s %s %s',
                         meta['origin'], meta['checkrepo'], meta['cijob'])
            for n, v in meta.items():
                logging.debug(f'{n}={v}')
            summary = summarize.summarize_totals(testcases)
            for l in summary:
                logging.debug("%s", l.strip())
            logging.debug('')
            self.store_test_run(meta, testcases)

    def ingest_all_logs(self, branch: str, hours: int):
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        # TODO: try to figure out how to filter by hours
        runs = self.av.get_runs(branch)
        for job in runs['builds']:
            if job['status'] not in frozenset(('success', 'failed', 'cancelled')):
                # Run is not complete; ignore it
                skipped += 1
                logging.debug('Job %s status is %s', job['buildId'], job['status'])
                continue
            if 'pullRequestId' in job:
                # Not a normal run on a branch; ignore it
                skipped += 1
                logging.debug('Job %s is a pull request #%s', job['buildId'], job['pullRequestId'])
                continue
            if self._convert_time(job['created']) < since:
                # Build is too old
                skipped += 1
                logging.debug('Job %s is too old: %s', job['buildId'], self._convert_time(job['created']).ctime())
                continue
            count += 1
            self.ingest_a_run_by_buildver(job['version'])
        logging.debug(f'{count} matching runs found, {skipped} skipped')

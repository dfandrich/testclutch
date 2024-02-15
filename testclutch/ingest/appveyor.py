"""Ingest logs from Appveyor"""

import datetime
import logging
import re
from typing import Any, Callable, Dict, Optional, TextIO

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import appveyorapi
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


DEFAULT_EXT = '.log'
LOGSUBDIR = 'appveyor'

AV_TIME_RE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d{1,7})([-+]\d\d):(\d\d)$')


class MassagedLog(TextIO):
    """Remove the timestamp at the head of every log line"""
    def __init__(self, f):
        self.file_obj = f

    def __getattr__(self, attr):
        return getattr(self.file_obj, attr)

    def readline(self):
        l = self.file_obj.readline()
        if l:
            l = l[11:]
        return l


class MsBuildLog(MassagedLog):
    """Remove the indentation that msbuild adds to child output

    This issue mentions the indentation that is done and implies that there is no way to
    stop it (as of 2021, anyway):
    https://github.com/dotnet/msbuild/issues/6614#issuecomment-866447382

    This has been tested with msbuild ver. 4.8.3761.0, 15.9.21+g9802d43bc3 for .NET,
    17.7.2+d6990bcfa for .NET
    """
    def __init__(self, f):
        super().__init__(f)
        self.in_msbuild = False

    def readline(self):
        l = super().readline()
        if l.startswith('Microsoft (R) Build Engine') or l.startswith('MSBuild version '):
            # Start of indented section
            self.in_msbuild = True
        elif self.in_msbuild:
            # In indented section
            if l.startswith('  '):
                # Strip off indentation
                l = l[2:]
            elif l.startswith('CUSTOMBUILD : warning :'):
                # This must be some kind of special msbuild escaping going on
                l = 'Warning' + l[22:]

            # Let through special cases: two strings that are part of the headers
            # that begin the indented section, a completely empty line, and CUSTOMBUILD.
            # Anything else not beginning with two spaces is the sign we've exited msbuild.
            #
            # NOTE: this is not a completely reliable indication. I don't know if CUSTOMBUILD
            # is the only weird string to suddenly show up in the middle. This means that
            # once we detect msbuild, we can't reliable switch out of it; there seems to be no
            # magic string shown afterward, and there are cases where nonindented strings can
            # appear in the middle. So, just leave it in dedenting mode once we detect msbuild
            # is in use; it's highly likely that any log we're interested in in this case will
            # be run under msbuild so it will work just fine.
            #  elif (not l.startswith('[Microsoft .NET Framework')
            #      and not l.startswith('Copyright (C) Microsoft Corporation')
            #      and l.rstrip('\r\n')):
            #      self.in_msbuild = False
        return l


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
        self.process_a_run_by_buildver(build_ver, self.store_test_run)

    def process_a_run_by_buildver(self, build_ver: str,
                                  log_processor: Callable[[TestMeta, TestCases], None]):
        logging.debug('Getting run %s', build_ver)
        run = self.av.get_run_by_buildver(build_ver)
        self.process_run(run, log_processor)

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

    def ingest_run(self, run: Dict[str, Any]):
        self.process_run(run, self.store_test_run)

    def process_run(self, run: Dict[str, Any],
                    log_processor: Callable[[TestMeta, TestCases], None]):
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
                self.process_log_file(self._log_file_path(build_id, job_id), meta, log_processor)
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
            logging.debug('Log file is already in %s', newfn)
        else:
            fn, ft = self.av.get_logs(job_id)
            logging.debug(f'fn {fn} type {ft}')
            logging.debug('Moving file to %s', newfn)
            logcache.move_into_cache_compressed(fn, newfn)
        return newfn

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        if not self.dry_run:
            logging.info('Storing test result in database')
            try:
                self.ds.store_test_run(meta, testcases)
            except db.IntegrityError:
                logging.warning('Log file has already been ingested!')
                if self.overwrite:
                    logging.info('Overwriting old log')
                    rec_id = self.ds.select_rec_id(meta)
                    if rec_id is None:
                        logging.error(f"Unable to find existing test for run {meta['runid']}")
                    else:
                        self.ds.delete_test_run(rec_id)
                        self.ds.store_test_run(meta, testcases)

    def process_log_file(self, fn: str, cimeta: TestMeta,
                         log_processor: Callable[[TestMeta, TestCases], None]):
        logging.debug('Processing file %s', fn)
        # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
        readylog = MsBuildLog(logcache.open_cache_file(fn))
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
            log_processor(meta, testcases)

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

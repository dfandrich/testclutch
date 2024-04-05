"""Ingest logs from GitHub Actions

GitHub API docs are at https://docs.github.com/en/rest?apiVersion=2022-11-28
"""

import datetime
import io
import logging
import posixpath
import re
import zipfile
from typing import Any, Callable, Dict, Optional

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import ghaapi
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


DEFAULT_EXT = '.zip'  # simplifying assumption, that all log files are of this type
LOGSUBDIR = 'gha'
EVENT = 'push'  # only look at logs of this event type
# This is the Python character map in which the logs are assumed. This has a mapping for all 256
# bytes so it will never have a conversion failure. And as long as the log regex parsing only looks
# at bytes in the ASCII, everything will succeed.
LOG_CHARMAP = 'ISO-8859-1'

# Matches may fail if GHA does filename substitution on characters other that this
KNOWN_LOG_FN_RE = re.compile(r'^[-a-zA-Z0-9 .@,_/(){}$]*$')

# Strip these characters from filename to make them storable in a ZIP file
# This MUST match the way that GHA does it. Update KNOWN_LOG_FN_RE if this is changed.
STRIP_LOG_FN_RE = re.compile(r'[/]')

# Matches a time stamp the includes a time zone.
# Unfortunately, sometimes GHA includes one and sometimes it doesn't.
TIME_WITH_ZONE_RE = re.compile(r'^.{19}.*[-+]')


def file_ext_from_type(content_type: str) -> str:
    if content_type == 'application/zip':
        return '.zip'
    if content_type == 'application/x-tgz':
        return '.tgz'
    return '.bin'


class MassagedLog(io.TextIOWrapper):
    """TextIOWrapper that removes the timestamp at the head of every log line"""
    def readline(self, size: int = -1):
        # Earlier Python versions don't support size, so assume the default is never changed
        assert (size == -1)
        l = super().readline()
        if l:
            l = l[29:]
        return l


class GithubIngestor:
    def __init__(self, owner: str, repo: str, token: str, ds: Optional[db.Datastore],
                 overwrite: bool = False):
        self.owner = owner
        self.repo = repo
        self.ds = ds
        self.gh = ghaapi.GithubApi(owner, repo, token)
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'gha',
                     'checkrepo': f'https://github.com/{self.owner}/{self.repo}'
                     }
        logcache.create_dirs(LOGSUBDIR)

    def _convert_time(self, timestamp: str) -> datetime.datetime:
        """Converts a GitHub time into a datetime object.

        There seem to be three kinds of time formats used:
            2023-07-24T15:16:01.000-07:00
            2023-07-24T22:03:10Z
            2023-08-15T13:03:32.000Z
        """
        if not TIME_WITH_ZONE_RE.search(timestamp):
            if timestamp.find('.') > 0:
                # need to add this so the datetime object will be time zone aware, with sub-seconds
                return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%S.%fZ%z')
            else:
                # need to add this so the datetime object will be time zone aware
                return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%SZ%z')
        return datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f%z')

    def ingest_a_run(self, run_id: int):
        self.process_a_run(run_id, self.store_test_run)

    def process_a_run(self, run_id: int,
                      log_processor: Callable[[TestMeta, TestCases], None]):
        logging.debug('Getting run %s', run_id)
        run = self.gh.get_run(run_id)
        self.process_run(run, log_processor)

    def ingest_run(self, run: Dict[str, Any]):
        self.process_run(run, self.store_test_run)

    def process_run(self, run: Dict[str, Any],
                    log_processor: Callable[[TestMeta, TestCases], None]):
        run_id = run['id']

        if run['status'] != 'completed':
            # This should have been filtered out in ingest_all_logs; this is a secondary check
            # (the in after gh.get_jobs IS necessary, whereas this one might not be).
            logging.warning('Run %d is (strangely) %s; skipping', run_id, run['status'])
            return

        # Gather metadata about this run
        cimeta = {}
        cimeta['ciname'] = run['name']
        cimeta['cidef'] = run['path']
        cimeta['runid'] = run['id']
        cimeta['commit'] = run['head_sha']
        cimeta['summary'] = run['display_title']
        cimeta['branch'] = run['head_branch']
        # This is the repo which contained the source that was built
        cimeta['sourcerepo'] = f'https://github.com/{run["head_repository"]["full_name"]}'
        # This is the repo for which the job is running (should be the same as 'checkrepo')
        cimeta['runrepo'] = f'https://github.com/{run["repository"]["full_name"]}'
        cimeta['url'] = run['html_url']
        # Note: there doesn't seem to be a way to get the pull request # from these data
        # or from tun runs data).  "trigger" at least lets you see that it was due to a PR.
        cimeta['trigger'] = run['event']
        cimeta['runstarttime'] = int(self._convert_time(run['run_started_at']).timestamp())
        cimeta['runtriggertime'] = int(self._convert_time(run['created_at']).timestamp())
        cimeta['runfinishtime'] = int(self._convert_time(run['updated_at']).timestamp())

        if self.download_log(run_id):
            self.process_log_file(self._log_file_path(run_id), cimeta, log_processor)
        else:
            logging.info("No logs available to ingest")

    def ingest_all_logs(self, branch: str, hours: int):
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        runs = self.gh.get_runs(branch=branch,
                                since=datetime.datetime.now() - datetime.timedelta(hours=hours))
        if runs:
            for run in runs['workflow_runs']:
                if run['head_branch'] == branch and run['event'] == EVENT:
                    run_id = run['id']
                    logging.debug('%s #%s', run['name'], run_id)
                    count += 1
                    self.ingest_a_run(run_id)
                else:
                    logging.debug('Job %s is on wrong branch: %s or event: %s',
                                  run['id'], run['head_branch'], run['event'])
                    skipped += 1
                    continue
        else:
            logging.info(f'No runs found in the last {hours} hours')

        logging.debug(f'{count} matching runs found, {skipped} skipped')

    def _log_file_path(self, run_id: int) -> str:
        return f'{LOGSUBDIR}/gha-{self.owner}-{self.repo}-{run_id}-logs{DEFAULT_EXT}'

    def download_log(self, run_id: int) -> Optional[str]:
        """Download the logs corresponding to this run.

        If the log file is already found in the cache directory, it is not downloaded.
        """
        newfn = self._log_file_path(run_id)
        if logcache.in_cache(newfn):
            logging.debug('Log file is already in %s', newfn)
        else:
            try:
                fn, ft = self.gh.get_logs(run_id)
            except ghaapi.HTTPError as e:
                # Not sure why GHA ever has no logs ready when we ask for them
                if e.response.status_code == 404:
                    logging.error('Log for for run %d reported by servers as Not Found', run_id)
                else:
                    logging.error(e.args[0])
                    # Re-raise the exception for better visibility for now
                    raise e
                return None

            logging.debug(f'fn {fn} type {ft}')
            assert file_ext_from_type(ft) == DEFAULT_EXT

            logging.debug('Moving file to %s', newfn)
            logcache.move_into_cache(fn, newfn)
        return newfn

    # TODO: remove this
    def ingest_log(self, run_id: int, cimeta: TestMeta):
        return self.ingest_log_file(self._log_file_path(run_id), cimeta)

    # TODO: remove this
    def ingest_log_file(self, fn: str, cimeta: TestMeta):
        "Processes log file and calls store_test_run on each log in turn to store it"
        self.process_log_file(fn, cimeta, self.store_test_run)

    def sanitize_log_fn(self, fn: str) -> str:
        "Sanitize the log file name for storing in a zip file, like GHA does"
        if not KNOWN_LOG_FN_RE.search(fn):
            # If this triggers, we might possibly need to to more sanitization
            logging.error('Possible internal inconsistency: check what GHA does on '
                          'file names like %s', fn)
        return STRIP_LOG_FN_RE.sub('', fn)

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

    def find_job_step(self, jobs: Dict[str, Any], meta: TestMeta) -> Dict[str, Any]:
        assert jobs
        job = self.find_job(jobs, meta)
        ci_step_fn = meta['cistep']
        for step in job['steps']:
            step_fn = self.sanitize_log_fn(f"{step['number']}_{step['name']}.txt")
            if ci_step_fn == step_fn:
                return step
        return {}

    def find_job(self, jobs: Dict[str, Any], meta: TestMeta) -> Dict[str, Any]:
        "Find the right job step in the GHA job info for this job"
        workflow_name = meta['ciname']
        job_name = meta['cijob']

        for job in jobs['jobs']:
            if job['workflow_name'] == workflow_name and job['name'] == job_name:
                return job
        return {}

    def process_log_file(self, fn: str, cimeta: TestMeta,
                         log_processor: Callable[[TestMeta, TestCases], None]):
        try:
            log = zipfile.ZipFile(logcache.open_cache_file(fn, 'rb'))
        except zipfile.BadZipFile:
            logging.error(f'Zip file {fn} is corrupt; cannot process (delete it and try again)')
            return
        jobs = self.gh.get_jobs(cimeta['runid'])
        logging.debug('Processing all files from %s', fn)
        for fileinfo in log.infolist():
            if fileinfo.is_dir():
                # empty directory entry
                continue
            if fileinfo.filename.find('/') < 0:
                # GitHub stores the log entries in zip files twice--once as complete logs
                # in the root, and once in separate steps in subdirectories. We don't need
                # both, so ignore the root copies and just use the once in the subdirectories.
                continue
            logging.debug('Processing member %s', fileinfo.filename)
            readylog = MassagedLog(log.open(fileinfo.filename), encoding=LOG_CHARMAP)
            meta, testcases = logparse.parse_log_file(readylog)
            if meta:
                # combine ci metadata with metadata from log file
                meta = {**self.meta, **meta, **cimeta}
                meta['cijob'] = posixpath.dirname(fileinfo.filename)
                meta['cistep'] = posixpath.basename(fileinfo.filename)
                assert meta['cijob']  # true because we eliminate others above
                if 'cidef' in meta:
                    # Unique CI job identifier
                    # The // here makes the name impossible to collide with a new job definition
                    # or name.
                    meta['uniquejobname'] = (
                        f"{meta['cidef']}//{meta['cijob']}//{meta['testformat']}")
                if 'ciname' in meta:
                    # This might not be available if this was not called by this ingestor
                    logging.info('Retrieved test for %s %s %s',
                                 meta['origin'], meta['checkrepo'], meta['ciname'])
                job = self.find_job(jobs, meta)
                if job:
                    if job['status'] != 'completed':
                        # This should have been filtered out in ingest_all_logs and process_run,
                        # but sometimes the status shows completed there but in_progress here.
                        logging.warning('Run %d is (strangely) %s in jobs; skipping',
                                        cimeta['runid'], job['status'])
                        return
                    meta['ciresult'] = job['conclusion']
                    duration = (self._convert_time(job['completed_at'])
                                - self._convert_time(job['started_at']))
                    meta['jobduration'] = duration.seconds * 1000000 + duration.microseconds
                    step = self.find_job_step(jobs, meta)
                    if step:
                        if step['conclusion']:
                            meta['cistepresult'] = step['conclusion']
                        else:
                            # If the step conclusion is None, reuse the job conclusion.
                            # This happens in a timeout scenario, for example.
                            meta['cistepresult'] = job['conclusion']
                        if step['completed_at'] and step['started_at']:
                            duration = (self._convert_time(step['completed_at'])
                                        - self._convert_time(step['started_at']))
                            meta['steprunduration'] = (duration.seconds * 1000000
                                                       + duration.microseconds)

                for n, v in meta.items():
                    logging.debug(f'{n}={v}')
                summary = summarize.summarize_totals(testcases)
                for l in summary:
                    logging.debug("%s", l.strip())
                logging.debug('')

                log_processor(meta, testcases)

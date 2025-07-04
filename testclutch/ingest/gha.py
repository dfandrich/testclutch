"""Ingest logs from GitHub Actions.

GitHub API docs are at https://docs.github.com/en/rest?apiVersion=2022-11-28
"""

import datetime
import io
import logging
import posixpath
import re
import zipfile
from typing import Any, Optional

from testclutch import config
from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import ghaapi
from testclutch.ingest import logprefix
from testclutch.ingest import msbuild
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


DEFAULT_EXT = '.zip'  # simplifying assumption, that all log files are of this type
LOGSUBDIR = 'gha'
EVENT = 'push'  # only look at logs of this event type

# Matches may fail if GHA does filename substitution on characters other that this
KNOWN_LOG_FN_RE = re.compile(r'^[-a-zA-Z0-9 .@,_(){}$&/]*$')

# Strip these characters from filename to make them storable in a ZIP file
# This MUST match the way that GHA does it. Update KNOWN_LOG_FN_RE if this is changed.
STRIP_LOG_FN_RE = re.compile(r'[/]')

# Match a timestamp at the start of a log line.
# Example: 2024-05-25T21:43:17.7471243Z
LOG_TIMESTAMP_RE = re.compile(r'^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{7}Z ')

# Format of a log filename in a zip archive
LOG_NAME_RE = re.compile(r'^([0-9]+)_(.*)\.txt$')


MIME_EXT = {
    'application/zip': '.zip',
    'application/x-tgz': '.tgz'
}


def file_ext_from_type(content_type: str) -> str:
    return MIME_EXT.get(content_type, '.bin')


def read_token(authfile: Optional[str]) -> Optional[str]:
    """Read the authorization token supplied in the file."""
    if not authfile:
        return None
    with open(authfile) as tokfile:
        return tokfile.read().strip()


class GithubIngestor:
    """Ingest logs from GitHub Actions."""

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

    def ingest_a_run(self, run_id: int):
        logging.debug('Getting run %s', run_id)
        run = self.gh.get_run(run_id)
        self.ingest_run(run)

    def ingest_run(self, run: dict[str, Any]):
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
        cimeta['runurl'] = run['html_url']
        # This should almost always be replaced with a more specific URL later
        cimeta['url'] = run['html_url']
        # Note: there doesn't seem to be a way to get the pull request # from these data
        # or from the runs data).  "trigger" at least lets you see that it was due to a PR.
        cimeta['trigger'] = run['event']
        cimeta['runstarttime'] = int(ghaapi.convert_time(run['run_started_at']).timestamp())
        cimeta['runtriggertime'] = int(ghaapi.convert_time(run['created_at']).timestamp())
        cimeta['runfinishtime'] = int(ghaapi.convert_time(run['updated_at']).timestamp())

        if self.download_log(run_id):
            self.process_log_file(self._log_file_path(run_id), cimeta)
        else:
            logging.info('No logs available to ingest')

    def ingest_all_logs(self, branch: str, hours: int):
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        runs = self.gh.get_runs(
            branch=branch,
            since=datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=hours))
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
            logging.debug('Log file is in cache as %s', newfn)
        else:
            try:
                fn, ft = self.gh.get_logs(run_id)
            except ghaapi.HTTPError as e:
                # Not sure why GHA would ever have no logs ready when we ask for them, but it does
                if e.response.status_code == 404:
                    logging.error('Log for run %d reported by server as Not Found', run_id)
                else:
                    logging.error(e.args[0])
                    # Re-raise the exception for better visibility for now
                    raise
                return None

            logging.debug(f'fn {fn} type {ft}')
            assert file_ext_from_type(ft) == DEFAULT_EXT, 'assumption about log format is wrong'

            logging.debug('Moving file to %s', newfn)
            logcache.move_into_cache(fn, newfn)
        return newfn

    def sanitize_log_fn(self, fn: str) -> str:
        """Sanitize the log file name for storing in a zip file, like GHA does."""
        if not KNOWN_LOG_FN_RE.search(fn):
            # If this triggers, we might possibly need to to more sanitization
            logging.error('Possible internal inconsistency: check what GHA does on '
                          'file names like %s', fn)
        return STRIP_LOG_FN_RE.sub('', fn)

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        """Store the data about one test.

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
                        logging.error(f'Unable to find existing test for run {meta["runid"]}')
                    else:
                        self.ds.delete_test_run(rec_id)
                        self.ds.store_test_run(meta, testcases)

    def find_job_step(self, jobs: dict[str, Any], meta: TestMeta) -> dict[str, Any]:
        assert jobs
        if 'cistep' in meta:
            ci_step_fn = meta['cistep']
            job = self.find_job(jobs, meta)
            for step in job['steps']:
                step_fn = self.sanitize_log_fn(f'{step["number"]}_{step["name"]}.txt')
                if ci_step_fn == step_fn:
                    return step
        return {}

    def find_job(self, jobs: dict[str, Any], meta: TestMeta) -> dict[str, Any]:
        """Find the right job step in the GHA job info for this job."""
        workflow_name = meta['ciname']
        job_name = meta['cijob']

        for job in jobs['jobs']:
            if job['workflow_name'] == workflow_name and job['name'] == job_name:
                return job
        return {}

    def process_log_file(self, fn: str, cimeta: TestMeta):
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
                logging.debug('Ignoring directory placeholder %s', fileinfo.filename)
                continue
            # GHA stopped including the copies of logs in subdirectories about 2025-06-30
            # if fileinfo.filename.find('/') < 0:
            #     # GitHub stores the log entries in zip files twice--once as complete logs
            #     # in the root, and once in separate steps in subdirectories. We don't need
            #     # both, so ignore the root copies and just use the ones in the subdirectories.
            #     logging.debug('Skipping %s', fileinfo.filename)
            #     continue
            logging.debug('Processing member %s', fileinfo.filename)

            # If any bad characters are encountered while decoding using this charset (such as if a
            # binary file was displayed in a log dump), they will automatically be replaced with
            # backslash escapes.
            readylog = msbuild.MsBuildLog(logprefix.RegexPrefixedLog(
                io.TextIOWrapper(log.open(fileinfo.filename), encoding=config.expand('log_charset'),
                                 errors='backslashreplace'),
                regex=LOG_TIMESTAMP_RE))
            meta, testcases = logparse.parse_log_file(readylog)
            if meta:
                # combine ci metadata with metadata from log file
                meta = {**self.meta, **meta, **cimeta}
                # Before 2025-06-30 GHA included the job name as the directory name
                if n := posixpath.dirname(fileinfo.filename):
                    meta['cijob'] = posixpath.dirname(fileinfo.filename)
                    meta['cistep'] = posixpath.basename(fileinfo.filename)
                else:
                    # A file name has the form NN_NAME.txt
                    if r := LOG_NAME_RE.search(fileinfo.filename):
                        meta['cijob'] = r.group(2)
                    else:
                        logging.warning('Unexpected log file format %s', fileinfo.filename)
                        meta['cijob'] = fileinfo.filename
                assert meta['cijob']  # true because we eliminate others above
                if 'cidef' in meta:
                    # Unique CI job identifier
                    # The // here makes the name impossible to collide with a new job definition
                    # or name.
                    meta['uniquejobname'] = (
                        f'{meta["cidef"]}//{meta["cijob"]}//{meta["testformat"]}')
                if 'ciname' in meta:
                    # This might not be available if this was not called by this ingestor
                    logging.info('Retrieved test for %s %s %s',
                                 meta['origin'], meta['checkrepo'], meta['ciname'])
                job = self.find_job(jobs, meta)
                if not job:
                    logging.warning(
                        f'Could not find job {meta["cijob"]} in workflow {meta["ciname"]}')
                else:
                    if job['status'] != 'completed':
                        # This should have been filtered out in ingest_all_logs and ingest_run,
                        # but sometimes the status shows completed there but in_progress here.
                        logging.warning('Run %d is (strangely) %s in jobs; skipping',
                                        cimeta['runid'], job['status'])
                        return
                    meta['ciresult'] = job['conclusion']
                    # Replace the generic job link; should be replaced again below
                    meta['url'] = job['html_url']
                    duration = (ghaapi.convert_time(job['completed_at'])
                                - ghaapi.convert_time(job['started_at']))
                    meta['jobduration'] = duration.seconds * 1000000 + duration.microseconds
                    step = self.find_job_step(jobs, meta)
                    if not step:
                        logging.debug(
                            f'Could not find step {meta.get("cistep", "")}')
                    else:
                        if step['conclusion']:
                            meta['cistepresult'] = step['conclusion']
                        else:
                            # If the step conclusion is None, reuse the job conclusion.
                            # This happens in a timeout scenario, for example.
                            meta['cistepresult'] = job['conclusion']
                        if step['completed_at'] and step['started_at']:
                            duration = (ghaapi.convert_time(step['completed_at'])
                                        - ghaapi.convert_time(step['started_at']))
                            meta['steprunduration'] = (duration.seconds * 1000000
                                                       + duration.microseconds)
                        # Make the URL directly open this step using an anchor.
                        # This doesn't always work when first clicked on (probably due to delayed
                        # loading), but at the very least it's a clue as to where the log is on the
                        # page.
                        meta['url'] = f'{meta["url"]}#check-step-{step["number"]}'

                for n, v in meta.items():
                    logging.debug(f'{n}={v}')
                summary = summarize.summarize_totals(testcases)
                for l in summary:
                    logging.debug('%s', l.strip())
                logging.debug('')

                self.store_test_run(meta, testcases)

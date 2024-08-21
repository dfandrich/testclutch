"""Ingest logs from Circle CI

The pipeline ID in the URL of Circle CI log UI doesn't seem to be used in the API
anywhere, and the build_num used there isn't visible in the UI.
"""

import datetime
import io
import json
import logging
import re
import urllib
from typing import Any, Callable, Iterable, Optional, TextIO

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch import urls
from testclutch.ingest import circleciapi
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse

# Choose whether to use the private API to get the full log or the documented API that truncates it
GET_FULL_LOG = True

DEFAULT_EXT = '.log' if GET_FULL_LOG else '.json'
LOGSUBDIR = 'circleci'

SANITIZE_PATH_RE = re.compile(r"[^-\w+!@#%^&()]")

# Tasks created by CircleCI, whose logs we don't care about
SYSTEM_TASKS = frozenset(('Spin up environment', 'Preparing environment variables',
                          'Checkout code'))

# CPU architectures in the different resource classes
# See https://circleci.com/product/features/resource-classes/ and
# https://circleci.com/docs/configuration-reference/#resourceclass
RESOURCE_ARCH = {'arm-medium': 'aarch64',
                 'arm-large': 'aarch64',
                 'm1-free': 'aarch64',
                 'macos-m1-medium-gen1': 'aarch64',
                 'medium': 'x86_64',
                 'large': 'x86_64',
                 'macos-x86-medium-gen2': 'x86_64',     # deprecated June 28, 2024

                 # the following keys are guesses only so far & haven't been verified
                 'arm-xlarge': 'aarch64',
                 'arm-2xlarge': 'aarch64',
                 'macos-m1-large-gen1': 'aarch64',
                 'small': 'x86_64',
                 'medium+': 'x86_64',
                 'xlarge': 'x86_64',
                 '2xlarge': 'x86_64',
                 '2xlarge+': 'x86_64',
                 'macos-x86-medium-gen2': 'x86_64',
                 'windows-medium': 'x86_64',
                 'windows-large': 'x86_64',
                 'windows-xlarge': 'x86_64',
                 'windows-2xlarge': 'x86_64',
                 }


def sanitize_path(path: str) -> str:
    "Convert the given URL path into one that is not too problematic to have on a filesystem"
    return SANITIZE_PATH_RE.sub("-", path)


class MassagedLog(io.StringIO):
    """Extract the log from the JSON input coming from the official log output URL

    This URL truncates long logs, so it is not ideal.
    """
    def __init__(self, f: TextIO):
        log_content = json.load(f)
        # Go through array and make one string of all the sections.
        # Usually, there is just one section which is of type "out" but Circle CI itself will
        # create a type=="err" section for its own error messages
        content = ''
        # This loop would be slow if it had to concatenate a bunch of multiple large strings,
        # but it almost always only encounters a single string which will cause absolutely no
        # slowdown.
        for log in log_content:
            content += log['message']
            if 'truncated' in log and log['truncated']:
                logging.warning('Log was truncated by server')
                # Truncation will also be detected by the log parser
        super().__init__(content)


class CircleIngestor:
    def __init__(self, repo: str, ds: Optional[db.Datastore], overwrite: bool = False):
        scheme, netloc, path, query, fragment = urllib.parse.urlsplit(repo)
        safe_path = sanitize_path(path)
        self.repo = f'{netloc}{safe_path}'
        self.circle = circleciapi.CircleApi(repo)
        self.ds = ds
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'circle', 'checkrepo': repo}
        logcache.create_dirs(LOGSUBDIR)

    def _convert_time(self, timestamp: str) -> datetime.datetime:
        """Converts a CircleCI time into a datetime object.
        """
        if timestamp.find('.') >= 0:
            # This timestamp has subsecond resolution
            return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%S.%fZ%z')
        return datetime.datetime.strptime(timestamp + '+0000', '%Y-%m-%dT%H:%M:%SZ%z')

    def ingest_a_run(self, build_num: int):
        self.process_a_run(build_num, self.store_test_run)

    def process_a_run(self, build_num: int,
                      log_processor: Callable[[TestMeta, TestCases], None]):
        logging.debug('Getting build %s', build_num)
        build = self.circle.get_run(build_num)
        self.process_run(build, log_processor)

    # TODO: delete me
    def ingest_run(self, build: dict[str, Any]):
        self.process_run(build, self.store_test_run)

    def process_run(self, build: dict[str, Any],
                    log_processor: Callable[[TestMeta, TestCases], None]):
        """Ingests not one log, but logs for one job"""
        build_num = build['build_num']
        cimeta = {}
        cimeta['ciname'] = 'CircleCI'
        cimeta['runid'] = build_num
        cimeta['commit'] = build['vcs_revision']
        cimeta['summary'] = build['subject']
        cimeta['branch'] = build['branch']
        cimeta['sourcerepo'] = build['vcs_url']
        cimeta['runid'] = build_num
        cimeta['workflowid'] = build['workflows']['workflow_id']
        cimeta['cijob'] = build['workflows']['workflow_name']
        cimeta['url'] = build['build_url']
        cimeta['runtriggertime'] = int(self._convert_time(build['queued_at']).timestamp())
        if build['start_time']:
            # A PR had this None, even though the job was complete
            cimeta['runstarttime'] = int(self._convert_time(build['start_time']).timestamp())
        cimeta['runfinishtime'] = int(self._convert_time(build['stop_time']).timestamp())
        cimeta['trigger'] = build['why']
        if build['picard']:
            # A PR had this None, even though the job was complete
            cimeta['cios'] = build['picard']['executor']
            cimeta['cicores'] = build['picard']['resource_class']['cpu']
            cimeta['cinodetype'] = build['picard']['resource_class']['class']
            if cimeta['cinodetype'] in RESOURCE_ARCH:
                cimeta['ciarch'] = RESOURCE_ARCH[cimeta['cinodetype']]
        cimeta['ciresult'] = build['outcome']
        if build['pull_requests']:
            url = build['pull_requests'][0]['url']
            cimeta['pullrequest'] = urls.url_pr(url)

        # Skip if no logs to get or uninteresting system task
        steps = [step for step in build['steps']
                 if step['actions'][0]['has_output'] and step['name'] not in SYSTEM_TASKS]

        self.download_log(build_num, steps)
        self.process_log(build_num, steps, cimeta, log_processor)

    def download_log(self, build_run: int, job_steps: Iterable[dict[str, Any]]) -> str:
        """Downloads the given log file.

        Format is either JSON with a message member containing the text or the raw log, depending on
        the API used to get it.
        """
        newfn = ''
        for step in job_steps:
            action = step['actions'][0]
            step_id = action['step']
            newfn = self._log_file_path(build_run, step_id)
            if logcache.in_cache(newfn):
                logging.debug('Log file is in cache as %s', newfn)
            else:
                if GET_FULL_LOG:
                    # Full log using private API (raw log)
                    log_url = self.circle.make_log_url(build_run, step_id)
                else:
                    # Truncated log using public API (log wrapped in JSON)
                    log_url = action['output_url']
                fn, ft = self.circle.get_logs(log_url)
                logging.debug(f'fn {fn} type {ft}')
                logging.debug('Moving file to %s', newfn)
                logcache.move_into_cache_compressed(fn, newfn)
        return newfn

    def _log_file_path(self, build_run: int, step_id: str) -> str:
        return f'{LOGSUBDIR}/circleci-{self.repo}-{build_run}-{step_id}{DEFAULT_EXT}'

    def ingest_all_logs(self, branch: str, hours: int):
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        runs = self.circle.get_runs()

        for run in runs:
            build_num = run['build_num']
            if run['lifecycle'] != 'finished':
                # Run is not complete; ignore it
                skipped += 1
                logging.debug('Run %d status is %d', build_num, run['lifecycle'])
                continue
            if run['branch'] != branch:
                # Wrong branch
                skipped += 1
                logging.debug('Run %d is on the wrong branch %s, not %s',
                              build_num, run['branch'], branch)
                continue
            # TODO: skip pull requests here. CircleCI seems to not run on PR in the
            # curl project right now so I don't know how this is specified
#            if run['all_commit_details']['pull_request']:
#                # Not a normal run on a branch; ignore it
#                skipped += 1
#                logging.debug('Run %s is a pull request #%d', node['id'], node['pullRequest'])
#                continue
            if self._convert_time(run['queued_at']) < since:
                # Build is too old
                skipped += 1
                logging.debug('Run %d is too old', build_num)
                continue
            count += 1
            self.ingest_a_run(build_num)
        logging.debug(f'{count} matching runs found, {skipped} skipped')

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        if not self.dry_run:
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
        logging.debug('Ingesting file %s', fn)
        if GET_FULL_LOG:
            readylog = logcache.open_cache_file(fn)
        else:
            # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
            readylog = MassagedLog(logcache.open_cache_file(fn))
        meta, testcases = logparse.parse_log_file(readylog)
        if meta:
            # combine ci metadata with metadata from log file
            meta = {**self.meta, **meta, **cimeta}

            # Unique CI job identifier
            # This is based on the human-specified name, which is probably possible to
            # make duplicate, so this isn't ideal.
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

    def process_log(self, build_run: int, steps: Iterable[dict[str, Any]], cimeta: TestMeta,
                    log_processor: Callable[[TestMeta, TestCases], None]):
        for step in steps:
            assert len(step['actions']) == 1
            action = step['actions'][0]

            # Gather metadata about this run
            jobmeta = {}
            jobmeta['cistep'] = action['name']
            jobmeta['cistepid'] = action['step']
            jobmeta['stepstarttime'] = int(self._convert_time(action['start_time']).timestamp())
            jobmeta['stepfinishtime'] = int(self._convert_time(action['end_time']).timestamp())
            duration = (self._convert_time(action['end_time'])
                        - self._convert_time(action['start_time']))
            jobmeta['steprunduration'] = duration.seconds * 1000000 + duration.microseconds
            jobmeta['cistepresult'] = action['status']

            meta = {**cimeta, **jobmeta}
            self.process_log_file(self._log_file_path(build_run, jobmeta['cistepid']), meta,
                                  log_processor)

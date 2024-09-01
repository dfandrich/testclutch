"""Ingest logs from Azure"""

import datetime
import logging
import re
from typing import Any, Iterable, Optional

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import azureapi
from testclutch.ingest import logprefix
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse

DEFAULT_EXT = '.log'
LOGSUBDIR = 'azure'

# Azure timestamp
AV_TIME_RE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d{1,7})?Z$')
# Tasks created by Azure, whose logs we don't care about
SYSTEM_TASKS_RE = re.compile(r'^Initialize job$|^Initialize containers$|^Stop Containers$|'
                             r'^Finalize Job$|^Checkout |^Post-job: ')


class AzureIngestor:
    def __init__(self, organization: str, project: str, repo: str, ds: Optional[db.Datastore],
                 overwrite: bool = False):
        self.organization = organization
        self.project = project
        self.repo = repo
        self.azure = azureapi.AzureApi(organization, project)
        self.ds = ds
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'azure', 'checkrepo': repo}
        logcache.create_dirs(LOGSUBDIR)

    def _log_file_path(self, build_id: int, log_id: int) -> str:
        return f'{LOGSUBDIR}/azure-{self.organization}-{self.project}-{build_id}-{log_id}{DEFAULT_EXT}'

    def _convert_time(self, timestamp: str) -> datetime.datetime:
        """Converts an Azure time into a datetime object.

        The microseconds field has too many digits and strptime barfs on it.
        """
        t = AV_TIME_RE.search(timestamp)
        if not t:
            logging.error('Cannot parse date: %s', timestamp)
            return datetime.datetime.fromtimestamp(0)
        microsec = t.group(2)[:7] if t.group(2) else '.0'
        return datetime.datetime.strptime(t.group(1) + microsec + 'Z+0000',
                                          '%Y-%m-%dT%H:%M:%S.%fZ%z')

    def ingest_all_logs(self, branch: str, hours: int):
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')

        full_branch = f'refs/heads/{branch}'
        builds = self.azure.get_builds(full_branch, hours)
        for build in builds['value']:
            if build['status'] != 'completed':
                # Run is not complete; ignore it
                skipped += 1
                # Warning because the statusFilter should have excluded this
                logging.warning('Build %s status is %d', build['id'], build['status'])
                continue
            if 'pr.sourceSha' in build['triggerInfo']:
                # Not a normal run on a branch (probably a pull request); ignore it
                skipped += 1
                logging.debug('Build %s is a pull request #%d',
                              build['id'], build['triggerInfo']['pr.number'])
                continue
            if 'ci.sourceBranch' not in build['triggerInfo']:
                skipped += 1
                logging.debug('Build %s is not a CI build', build['id'])
                continue
            if build['triggerInfo']['ci.sourceBranch'] != full_branch:
                skipped += 1
                # Warning, because we shouldn't have gotten this build given to
                # use in the search results due to the query parameters there
                logging.warning('Build %s is on the wrong branch %s, not %s',
                                build['id'], build['triggerInfo']['ci.sourceBranch'], branch)
                continue

            count += 1
            self.ingest_a_run(build['id'])

        logging.debug(f'{count} matching runs found, {skipped} skipped')

    def ingest_a_run(self, build_id: int):
        logging.debug('Getting build %s', build_id)
        build = self.azure.get_build(build_id)
        self.ingest_run(build)

    def ingest_run(self, build: dict[str, Any]):
        """Ingests not one log, but logs for one job"""
        build_id = build['id']
        cimeta = {}
        cimeta['ciname'] = build['project']['name']
        cimeta['account'] = f'{self.organization}/{self.project}'
        cimeta['runid'] = build_id
        cimeta['runtriggertime'] = int(self._convert_time(build['queueTime']).timestamp())
        cimeta['runstarttime'] = int(self._convert_time(build['startTime']).timestamp())
        cimeta['runfinishtime'] = int(self._convert_time(build['finishTime']).timestamp())
        # TODO: This is the length of the entire run, which isn't that interesting. Better would be
        # the length of each individual build, but that probably means looking at the timeline
        runduration = (self._convert_time(build['finishTime'])
                       - self._convert_time(build['startTime']))
        cimeta['runduration'] = runduration.seconds * 1000000 + runduration.microseconds
        if build['repository']['type'] == 'GitHub':
            cimeta['sourcerepo'] = 'https://github.com/' + build['repository']['id']
        cimeta['trigger'] = build['reason']
        if 'pr.number' in build['triggerInfo']:
            # This is a pull request
            cimeta['pullrequest'] = build['triggerInfo']['pr.number']
            cimeta['commit'] = build['triggerInfo']['pr.sourceSha']
            cimeta['summary'] = build['triggerInfo']['pr.title']
            # This gives the PR source branch, which isn't interesting
            # cimeta['branch'] = build['triggerInfo']['pr.sourceBranch']
        else:
            # This is a CI build
            cimeta['commit'] = build['triggerInfo']['ci.sourceSha']
            cimeta['summary'] = build['triggerInfo']['ci.message']
            cimeta['branch'] = build['triggerInfo']['ci.sourceBranch']
        # Use .removeprefix() in >=py3.9
        if 'branch' in cimeta and cimeta['branch'].startswith('refs/heads/'):
            cimeta['branch'] = cimeta['branch'][11:]
        cimeta['ciresult'] = build['result']
        cimeta['runurl'] = build['_links']['web']['href']

        timeline = self.azure.get_build_timelines(build_id)

        # Process timeline to build a tree of events
        event_nodes = {}  # nodes of trees, by id
        parents = {}      # list of nodes IDs of trees, by parent id
        stages = []       # list of roots of trees, the stages
        for task in timeline['records']:
            event_nodes[task['id']] = task
            if task['parentId']:
                parents.setdefault(task['parentId'], []).append(task['id'])
            else:
                stages.append(task['id'])

        # Depth-first tree traversal to get to tasks & logs
        for stage in stages:
            logging.debug('Processing stage %s: %s (%s)',
                          stage, event_nodes[stage]['name'], event_nodes[stage]['type'])
            if event_nodes[stage]['type'] != 'Stage':
                logging.error('Unexpected node: %s, not Stage', event_nodes[stage]['type'])
            if event_nodes[stage]['state'] != 'completed':
                logging.info('Skipping stage in progress: %', stage)
                continue

            for phase in parents[stage]:
                logging.debug('  Processing phase %s: %s (%s)',
                              phase, event_nodes[phase]['name'], event_nodes[phase]['type'])
                if event_nodes[phase]['type'] == 'Checkpoint':
                    # Uninteresting node
                    continue
                if event_nodes[phase]['type'] != 'Phase':
                    logging.error('Unexpected node: %s, not Phase', event_nodes[phase]['type'])
                if phase not in parents:
                    logging.warning('Phase without children: %s', phase)
                    continue

                for job in parents[phase]:
                    logging.debug('    Processing job %s: %s (%s)',
                                  job, event_nodes[job]['name'], event_nodes[job]['type'])
                    if event_nodes[job]['type'] != 'Job':
                        logging.error('Unexpected node: %s, not Job', event_nodes[job]['type'])
                    if job not in parents:
                        logging.warning('Job without children: %s', job)
                        continue
                    jobmeta = {}
                    jobmeta['cijob'] = event_nodes[job]['name']
                    jobmeta['jobstarttime'] = int(
                        self._convert_time(event_nodes[stage]['startTime']).timestamp())
                    jobmeta['jobfinishtime'] = int(
                        self._convert_time(event_nodes[stage]['finishTime']).timestamp())

                    logs_tasks = []
                    for task in parents[job]:
                        task_info = event_nodes[task]
                        logging.debug('      Processing task %s: %s (%s)',
                                      task, task_info['name'], task_info['type'])
                        if task_info['type'] != 'Task':
                            logging.error('Unexpected node: %s, not Task', task_info['type'])
                        if task in parents:
                            logging.warning('Task with children: %s', task)
                        if SYSTEM_TASKS_RE.search(task_info['name']):
                            logging.debug('Skipping system task %s', task_info['name'])
                            continue

                        if task_info['log']:
                            logging.debug('        Need log %d', task_info['log']['id'])
                            logs_tasks.append(task_info)

                    if logs_tasks:
                        self.download_log(build_id, logs_tasks)
                        meta = {**cimeta, **jobmeta}
                        self.ingest_log(build_id, logs_tasks, meta)

    def download_log(self, build_id: int, tasks: Iterable[dict[str, Any]]):
        for task in tasks:
            log_id = task['log']['id']
            newfn = self._log_file_path(build_id, log_id)
            if logcache.in_cache(newfn):
                logging.debug('Log file is in cache as %s', newfn)
            else:
                fn, ft = self.azure.get_logs(build_id, log_id)
                logging.debug(f'fn {fn} type {ft}')
                logging.debug('Moving file to %s', newfn)
                logcache.move_into_cache_compressed(fn, newfn)
        return newfn

    def store_test_run(self, meta: TestMeta, testcases: TestCases):
        """Store the data about one test

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
                        logging.error(f"Unable to find existing test for run {meta['runid']}")
                    else:
                        self.ds.delete_test_run(rec_id)
                        self.ds.store_test_run(meta, testcases)

    def ingest_log_file(self, fn: str, cimeta: TestMeta):
        logging.debug('Ingesting file %s', fn)
        # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
        readylog = logprefix.FixedPrefixedLog(logcache.open_cache_file(fn), prefixlen=29)
        meta, testcases = logparse.parse_log_file(readylog)
        if meta:
            # combine ci metadata with metadata from log file
            meta = {**self.meta, **meta, **cimeta}
            # Make sure the job remains unique by prefixing with the (presumably) pipeline name
            meta['uniquejobname'] = meta['ciname'] + '!' + meta['cijob'] + '!' + meta['testformat']

            logging.info('Retrieved test for %s %s %s',
                         meta['origin'], meta['checkrepo'], meta['cijob'])
            for n, v in meta.items():
                logging.debug(f'{n}={v}')
            summary = summarize.summarize_totals(testcases)
            for l in summary:
                logging.debug("%s", l.strip())
            logging.debug('')

            self.store_test_run(meta, testcases)

    def ingest_log(self, build_id: int, tasks: Iterable[dict[str, Any]],
                   cimeta: dict[str, str]):
        for task in tasks:
            jobmeta = {}
            jobmeta['cistep'] = task['name']
            jobmeta['cistepresult'] = task['result']
            jobmeta['url'] = self.azure.get_build_log_url(build_id, task['parentId'], task['id'])
            meta = {**cimeta, **jobmeta}
            self.ingest_log_file(self._log_file_path(build_id, task['log']['id']), meta)

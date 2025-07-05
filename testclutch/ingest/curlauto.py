"""Ingest logs from curl's autobuild system."""

import datetime
import logging
import re
from typing import Optional, TextIO

from testclutch import db
from testclutch import logcache
from testclutch import summarize
from testclutch.ingest import curlautoapi
from testclutch.logdef import TestCases, TestMeta
from testclutch.logparser import logparse


LOGSUBDIR = 'curlauto'
LOG_URL = 'https://curl.se/dev/log.cgi?id={id}'

LOG_FILE_RE = re.compile(r'^build-(\d{14})-(\d+)\.log$')

# Log lines that might be missing a leading space
RE_FAILED = re.compile(r'^(\d{1,5}): ((\w+)( \(.*\))?) FAILED')
RE_IGNORED = re.compile(r'^(\d{1,5}): IGNORED: ')
RE_SKIPAFTERSTART_PART = re.compile(
    r'^((\d+) functions to make fail|^[^\s].*functions found, but only fail)')
# Obsolete after 2023-06-21
RE_EXITFAILED = re.compile(r'^(exit) FAILED$')
RE_TORTURESKIPPED = re.compile(r'^found (no functions to make fail)$')
RE_VALGRINDFAILED = re.compile(r'^(valgrind) ERROR')


class MassagedLog(TextIO):
    """Restore some missing spaces from logs.

    At some point in the data flow, leading spaces in log lines get removed in
    the curl autobuild logs.  This class restores them so that they can be
    correctly parsed by the curl log parser.

    TODO: The inpipe script in the mail handler on haxx.se was fixed 2024-09-10 to
    no longer strip spaces, so this class is now obsolete.
    """
    def __init__(self, f):
        self.file_obj = f

    def __getattr__(self, attr):
        """Pass any other references to the file object."""
        return getattr(self.file_obj, attr)

    def readline(self) -> str:
        l = self.file_obj.readline()
        if (RE_FAILED.search(l) or RE_IGNORED.search(l) or RE_SKIPAFTERSTART_PART.search(l)
            or RE_EXITFAILED.search(l) or RE_TORTURESKIPPED.search(l)
                or RE_VALGRINDFAILED.search(l)):
            return ' ' + l
        return l


class CurlAutoIngestor:
    """Ingest logs from curl's autobuild system."""

    def __init__(self, repo: str, ds: Optional[db.Datastore], overwrite: bool = False):
        self.repo = repo
        self.curlauto = curlautoapi.CurlAutoApi()
        self.ds = ds
        self.dry_run = ds is None
        self.overwrite = overwrite
        # metadata that applies to all logs ingested here
        self.meta = {'origin': 'curlauto', 'checkrepo': repo}
        logcache.create_dirs(LOGSUBDIR)

    def _extract_run_info(self, fn: str) -> tuple[datetime.datetime, int]:
        run_info = LOG_FILE_RE.search(fn)
        if not run_info:
            raise RuntimeError(f'Unexpected log name: {fn}')
        d = datetime.datetime.strptime(run_info.group(1) + '+0000', '%Y%m%d%H%M%S%z')
        return (d, int(run_info.group(2)))

    def ingest_run(self, log_name: str):
        timestamp, ident = self._extract_run_info(log_name)

        cimeta = {}
        cimeta['runid'] = log_name
        # This is the time the log file was processed on the curl server
        cimeta['runprocesstime'] = int(timestamp.timestamp())

        self.download_log(log_name)
        self.ingest_log(log_name, cimeta)

    def _log_file_path(self, log_name: str) -> str:
        return f'{LOGSUBDIR}/curlauto-{log_name}'

    def ingest_all_logs(self, hours: int):
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        count = 0
        skipped = 0
        if self.dry_run:
            logging.info('Skipping ingestion into database')
        logs = self.curlauto.get_runs()
        for log_name in logs:
            timestamp, ident = self._extract_run_info(log_name)
            if timestamp < since:
                # Build is too old
                skipped += 1
                logging.debug('Log %s is too old', log_name)
                continue
            count += 1
            self.ingest_run(log_name)
        logging.debug(f'{count} matching runs found, {skipped} skipped')

    def download_log(self, log_name: str) -> str:
        newfn = self._log_file_path(log_name)
        if logcache.in_cache(newfn):
            logging.debug('Log file is in cache as %s', newfn)
        else:
            fn, ft = self.curlauto.get_logs(log_name)
            logging.debug(f'fn {fn} type {ft}')
            logging.debug('Moving file to %s', newfn)
            logcache.move_into_cache_compressed(fn, newfn)
        return newfn

    def ingest_log_file(self, fn: str, cimeta: TestMeta):
        logging.debug('Ingesting file %s', fn)
        # TODO: Assuming local charset; probably convert from ISO-8859-1 instead
        readylog = MassagedLog(logcache.open_cache_file(fn))
        for meta, testcases in logparse.parse_log_files(readylog):
            if meta:
                # combine ci metadata with metadata from log file
                meta = {**self.meta, **meta, **cimeta}

                # cijob is probably unique, but the buildcode really makes it so (just not in a
                # cryptographically secure fashion, so a malicious user could easily cause
                # duplicate codes).
                meta['uniquejobname'] = f'{meta["cijob"]} {meta["buildcode"]}!{meta["testformat"]}'
                meta['jobstarttime'] = meta['runstarttime']
                run_info = LOG_FILE_RE.search(meta['runid'])
                if run_info:
                    meta['url'] = LOG_URL.format(id=f'{run_info.group(1)}-{run_info.group(2)}')

                logging.info('Retrieved test for %s %s %s',
                             meta['origin'], meta['checkrepo'], meta['cijob'])
                for n, v in meta.items():
                    logging.debug(f'{n}={v}')
                summary = summarize.summarize_totals(testcases)
                for l in summary:
                    logging.debug('%s', l.strip())
                logging.debug('')
                self.store_test_run(meta, testcases)

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

    def ingest_log(self, log_name: str, cimeta: TestMeta):
        return self.ingest_log_file(self._log_file_path(log_name), cimeta)

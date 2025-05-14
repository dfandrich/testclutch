"""Query database of tests."""

import argparse
import collections
import datetime
import logging
import re
import sys
from typing import Optional

from testclutch import argparsing
from testclutch import config
from testclutch import db
from testclutch import log
from testclutch import summarize
from testclutch.testcasedef import TestResult


# OpenMetrics job label
JOB = 'testclutch'

NVO_RE = re.compile(r'^([^<>=!%]+)(=|<>|!=|<=|>=|<|>|%|!%)(.*)$')


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Query database of tests')
    argparsing.arguments_logging(parser)
    parser.add_argument(
        '-t', '--show-tests',
        action='store_true',
        help='Show test results')
    parser.add_argument(
        '--checkrepo',
        required=not config.expand('check_repo'),
        default=config.expand('check_repo'),
        help="URL of the source repository we're dealing with")
    parser.add_argument(
        '--since',
        help='Only look at logs created since this ISO date or number of hours')
    parser.add_argument(
        'query',
        nargs='?',
        help='DB query arguments')
    parser.add_argument(
        '--format',
        choices=['text', 'openmetrics'],
        default='text',
        help='Specify output format')
    parser.add_argument(
        '--instance',
        default='test',
        help='Instance name for openmetrics (defaults to "test")')
    return parser.parse_args(args=args)


def operator_from_matcher(matcher: str) -> str:
    """Convert the command-line operator to a SQL operator."""
    if matcher == '%':
        return 'LIKE'
    if matcher == '!%':
        return 'NOT LIKE'
    return matcher


def output_text(ds: db.Datastore, rows: db.TestRunRow, show_tests: bool):
    """Write the query results in a human-friendly format."""
    for row in rows:
        print(row[0], row[1])
        meta = row[2]
        for n, v in meta.items():
            print(f'{n}={v}')
        testcases = ds.select_test_results(row[0])
        summarize.show_totals(testcases)
        if show_tests:
            testcases.sort(key=lambda x: summarize.try_integer(x.name))
            for t in testcases:
                print(t)
        print()


class OpenMetricsBuilder:
    """Build OpenMetrics text format metrics."""
    LABEL0_RE = re.compile(r'[^_a-zA-Z]')
    LABEL_RE = re.compile(r'[^_a-zA-Z0-9]')
    VALUE_RE = re.compile('["\n\\\\\ud800-\udfff]')

    # Metric name extensions for 'summary' metrics
    SUMMARY_EXT = {'count', 'created', 'sum'}

    # Types of metrics if not 'gauge'
    METRIC_TYPE = {
        'testclutch_tests_seconds': 'summary'
    }

    # Help for each metric
    METRIC_HELP = {
        'testclutch_job_duration_seconds': 'How long the entire job took to run.',
        'testclutch_job_finish_seconds': 'When the job completed running.',
        'testclutch_job_start_seconds': 'When the job started running.',
        'testclutch_run_duration_seconds': 'How long the run took to complete.',
        'testclutch_run_finish_seconds': 'When the run completed running.',
        'testclutch_run_start_seconds': 'When the run started running.',
        'testclutch_run_trigger_seconds': 'When the run was triggered.',
        'testclutch_step_duration_seconds': 'How long the job step took to run.',
        'testclutch_step_finish_seconds': 'When the job step completed running.',
        'testclutch_step_start_seconds': 'When the job step started running.',
        'testclutch_tests_duration_seconds': 'How long the tests took to run (wall clock time).',
        'testclutch_tests_seconds': 'Time taken to run each test in the job.'
    }

    def __init__(self):
        self.labels = {}  # type: dict[str, str]
        self.timestamp = 0
        self.types = set()  # type: set[str]

    def set_labels(self, labels: dict[str, str]):
        """Set any additional labels to attach to metrics."""
        self.labels = labels

    def set_timestamp(self, timestamp: int):
        """Set the timestamp of the metrics."""
        self.timestamp = timestamp

    def sanitize_label(self, label: str) -> str:
        """Make a label name by replacing invalid characters with _."""
        return (self.LABEL0_RE.sub('_', label[0])
                + self.LABEL_RE.sub('_', label[1:]))

    def escape(self, value: str) -> str:
        """Make a label value by escaping special characters."""
        estring = self.VALUE_RE.sub(lambda x: '\\' + x.group(0), value)
        # newline is an exception to the escaping pattern
        return estring.replace('\n', 'n')

    def metric(self, metric: str, value: float, more_labels: Optional[dict[str, str]] = None
               ) -> str:
        """Print one OpenMetric metric line."""
        if more_labels:
            all_labels = {**self.labels, **more_labels}
        else:
            all_labels = self.labels
        metas = [f'{self.sanitize_label(n)}="{self.escape(v)}"' for n, v in all_labels.items()]
        labelstr = ('{' if metas else '') + ','.join(metas) + ('}' if metas else '')
        return f'{metric}{labelstr} {value} {self.timestamp}'

    def typeinfo(self, metric: str) -> str:
        """Return the OpenMetrics type information for a metric as a multiline string.

        After the first time for each metric, an empty string is returned.
        """
        metric_parts = metric.split('_')
        if metric_parts[-1] in self.SUMMARY_EXT and len(metric_parts) >= 3:
            metric_base = '_'.join(metric_parts[:-1])
            metric_unit = metric_parts[-2]
        else:
            metric_base = metric
            metric_unit = metric_parts[-1]
        if metric_base in self.types:
            return ''
        self.types.add(metric_base)

        return (
            f"# TYPE {metric_base} {self.METRIC_TYPE.get(metric_base, 'gauge')}\n"
            f'# UNIT {metric_base} {metric_unit}\n'
            f"# HELP {metric_base} {self.METRIC_HELP.get(metric_base, 'unknown')}\n"
        )


def output_openmetrics(ds: db.Datastore, rows: db.TestRunRow, instance: str):
    """Write the query results in OpenMetrics format."""
    # This metric dump doesn't quite meet the interleaving rules for OpenMetrics metrics.
    # It looks like we can only write one MetricFamily at a time before moving
    # onto the next, meaning we have to buffer them or do a dozen separate runs through
    # the database doing one MetricFamily at a time. Prometheus at least accepts them
    # this way, although perhaps it doesn't store them in optimum fashion.

    # Default labels added to all metrics
    job_labels = {'job': JOB, 'instance': instance}

    om = OpenMetricsBuilder()
    for row in rows:
        meta = row[2]
        # metadata ending in 'duration' or 'time' should be a metric, not a label
        labels = {f: v for f, v in meta.items() if not f.endswith('duration')
                  and not f.endswith('time')}

        # Set the metric time stamp to the latest time that we have available
        if 'runfinishtime' in meta:
            timestamp = int(meta['runfinishtime'])
        elif 'jobfinishtime' in meta:
            timestamp = int(meta['jobfinishtime'])
        else:
            # Since we don't have the actual run completion time, add whatever duration that's
            # available to the start time to approximate the finish time for better consistency with
            # the rest of the jobs.
            duration = int(meta.get('jobduration', meta.get('runduration',
                           meta.get('steprunduration', meta.get('runtestsduration', 0))))) / 1000000
            timestamp = int(duration) + int(meta.get('runstarttime', meta.get('runtriggertime')))

        om.set_labels(labels)
        om.set_timestamp(timestamp)

        if 'jobstarttime' in meta:
            print(om.typeinfo('testclutch_job_start_seconds'), end='')
            print(om.metric('testclutch_job_start_seconds', int(meta['jobstarttime']), job_labels))
        if 'jobfinishtime' in meta:
            print(om.typeinfo('testclutch_job_finish_seconds'), end='')
            print(om.metric('testclutch_job_finish_seconds', int(meta['jobfinishtime']),
                            job_labels))
        if 'jobduration' in meta:
            print(om.typeinfo('testclutch_job_duration_seconds'), end='')
            print(om.metric('testclutch_job_duration_seconds', int(meta['jobduration']) / 1e6,
                            job_labels))
        elif 'jobstarttime' in meta and 'jobfinishtime' in meta:
            print(om.typeinfo('testclutch_job_duration_seconds'), end='')
            print(om.metric('testclutch_job_duration_seconds',
                            (int(meta['jobfinishtime']) - int(meta['jobstarttime'])) / 1e6,
                            job_labels))
        if 'runtestsduration' in meta:
            print(om.typeinfo('testclutch_tests_duration_seconds'), end='')
            print(om.metric('testclutch_tests_duration_seconds',
                            int(meta['runtestsduration']) / 1e6, job_labels))
        if 'steprunduration' in meta:
            print(om.typeinfo('testclutch_step_duration_seconds'), end='')
            print(om.metric('testclutch_step_duration_seconds',
                            int(meta['steprunduration']) / 1e6, job_labels))
        if 'runtriggertime' in meta:
            print(om.typeinfo('testclutch_run_trigger_seconds'), end='')
            print(om.metric('testclutch_run_trigger_seconds', int(meta['runtriggertime']),
                            job_labels))
        if 'runstarttime' in meta:
            print(om.typeinfo('testclutch_run_start_seconds'), end='')
            print(om.metric('testclutch_run_start_seconds', int(meta['runstarttime']),
                            job_labels))
        if 'runfinishtime' in meta:
            print(om.typeinfo('testclutch_run_finish_seconds'), end='')
            print(om.metric('testclutch_run_finish_seconds', int(meta['runfinishtime']),
                            job_labels))
        if 'stepstarttime' in meta:
            print(om.typeinfo('testclutch_step_start_seconds'), end='')
            print(om.metric('testclutch_step_start_seconds', int(meta['stepstarttime']),
                            job_labels))
        if 'stepfinishtime' in meta:
            print(om.typeinfo('testclutch_step_finish_seconds'), end='')
            print(om.metric('testclutch_step_finish_seconds', int(meta['stepfinishtime']),
                            job_labels))
        if 'runduration' in meta:
            print(om.typeinfo('testclutch_run_duration_seconds'), end='')
            print(om.metric('testclutch_run_duration_seconds', int(meta['runduration']),
                            job_labels))

        # "runprocesstime" isn't exported because it's really not that interesting.

        testcases = ds.select_test_results(row[0])
        # Break these counts down by result code
        result_count = collections.Counter(result.result for result in testcases)
        test_sum = collections.defaultdict(int)
        for case in testcases:
            test_sum[case.result] += case.duration
        for result in result_count:
            print(om.typeinfo('testclutch_tests_seconds_sum'), end='')
            print(om.metric('testclutch_tests_seconds_sum', test_sum[result] / 1e6,
                            {**job_labels, 'result': TestResult(result).name}))
            print(om.typeinfo('testclutch_tests_seconds_count'), end='')
            print(om.metric('testclutch_tests_seconds_count', result_count[result],
                            {**job_labels, 'result': TestResult(result).name}))
    print('# EOF')


def main():
    args = parse_args()
    log.setup(args)

    if args.format == 'openmetrics' and args.show_tests:
        raise RuntimeError('--show_tests is only valid with --format=text')

    if args.since:
        try:
            since = (datetime.datetime.now(tz=datetime.timezone.utc)
                     - datetime.timedelta(hours=int(args.since)))
        except ValueError:
            since = datetime.datetime.fromisoformat(args.since)
    else:
        # Default to same time as logfile analysis time since it's probably only
        # recent tests we would want to see
        since = (datetime.datetime.now(tz=datetime.timezone.utc)
                 - datetime.timedelta(hours=config.get('analysis_hours')))

    with db.Datastore() as ds:
        if args.query:
            # Search for logs matching metadata
            # e.g. runid=1234567, runtestsduration>555000000
            val = NVO_RE.search(args.query)
            if not val:
                logging.error('Invalid match query: %s', args.query)
                sys.exit(1)
            op = operator_from_matcher(val.group(2))
            rows = ds.select_meta_test_runs(args.checkrepo, since,
                                            val.group(1), op, val.group(3))

        else:
            # Show all logs
            rows = ds.select_all_test_runs(args.checkrepo, since)

        if args.format == 'text':
            output_text(ds, rows, args.show_tests)
        else:
            # OpenMetrics always uses UTF-8, so override stdout to use that no matter what the
            # user's default encoding
            assert hasattr(sys.stdout, 'reconfigure')  # satisfy pytype that this exists
            sys.stdout.reconfigure(encoding='utf-8')
            output_openmetrics(ds, rows, args.instance)

    if args.format == 'text':
        print(f'{len(rows)} matching logs')


if __name__ == '__main__':
    main()

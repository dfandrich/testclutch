"""Test querytests."""

import unittest

from testclutch.cli import querytests  # noqa: I100


class TestOpenMetricsBuilder(unittest.TestCase):
    """Test querytests.OpenMetricsBuilder."""

    def test_sanitize_label(self):
        om = querytests.OpenMetricsBuilder()
        self.assertEqual(om.sanitize_label('foo123'), 'foo123')
        self.assertEqual(om.sanitize_label('0xyzzy'), '_xyzzy')
        self.assertEqual(om.sanitize_label('_!_@_"_\n'), '________')

    def test_escape(self):
        om = querytests.OpenMetricsBuilder()
        self.assertEqual(om.escape('foo123'), 'foo123')
        self.assertEqual(om.escape('quote:" nul:\u0000 nl:\n backslash:\\ d800:\ud800\udddd'),
                         'quote:\\" nul:\u0000 nl:\\n backslash:\\\\ d800:\\\ud800\\\udddd')

    def test_metric(self):
        om = querytests.OpenMetricsBuilder()
        om.set_labels({'std_label': 'std value'})
        om.set_timestamp(123)
        self.assertEqual(
            om.metric('metric_name', 98765.4, {}),
            'metric_name{std_label="std value"} 98765.4 123')

    def test_metric_extra(self):
        om = querytests.OpenMetricsBuilder()
        om.set_labels({'std_label': 'std value'})
        om.set_timestamp(123)
        self.assertEqual(
            om.metric('metric_name', 98765.4, {'extra_label': 'extra value'}),
            'metric_name{std_label="std value",extra_label="extra value"} 98765.4 123')

    def test_metric_nostd(self):
        om = querytests.OpenMetricsBuilder()
        om.set_timestamp(123)
        self.assertEqual(
            om.metric('metric_name', 98765.4, {'extra_label': 'extra value'}),
            'metric_name{extra_label="extra value"} 98765.4 123')

    def test_metric_nolabels(self):
        om = querytests.OpenMetricsBuilder()
        om.set_timestamp(123)
        self.assertEqual(
            om.metric('metric_name', 98765.4, {}),
            'metric_name 98765.4 123')

    def test_typeinfo_gauge(self):
        om = querytests.OpenMetricsBuilder()
        self.assertEqual(
            om.typeinfo('testclutch_run_finish_seconds'),
            '# TYPE testclutch_run_finish_seconds gauge\n'
            '# UNIT testclutch_run_finish_seconds seconds\n'
            '# HELP testclutch_run_finish_seconds When the run completed running.\n'
        )

    def test_typeinfo_summary(self):
        om = querytests.OpenMetricsBuilder()
        self.assertEqual(
            om.typeinfo('testclutch_tests_seconds_sum'),
            '# TYPE testclutch_tests_seconds summary\n'
            '# UNIT testclutch_tests_seconds seconds\n'
            '# HELP testclutch_tests_seconds Time taken to run each test in the job.\n'
        )

    def test_typeinfo_unknown(self):
        om = querytests.OpenMetricsBuilder()
        self.assertEqual(
            om.typeinfo('metric_name'),
            '# TYPE metric_name gauge\n'
            '# UNIT metric_name name\n'
            '# HELP metric_name unknown\n'
        )

"""Test analyzepr."""

import unittest
from unittest.mock import Mock, patch

from .context import testclutch  # noqa: F401

from testclutch.cli import analyzepr  # noqa: I100
from testclutch import logdef  # noqa: I100


def patch_config_get(key: str, value):
    """Mock config.get() to return a specific value for a given key.

    All other values return None, so this should only be used when a single config.get() is
    expected.
    """
    return patch('testclutch.config.get', side_effect=lambda k: value if k == key else None)


class TestGatherPRAnalysis(unittest.TestCase):
    """Test analyzepr.GatherPRAnalysis."""

    @patch_config_get('rerun_tests', False)
    def test_get_failures_norerun_success(self, config_mock):
        gpa = analyzepr.GatherPRAnalysis(Mock(), Mock())
        self.assertCountEqual(gpa.get_failures([
            logdef.SingleTestFinding('1', logdef.TestResult.PASS, '', 1),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('3', logdef.TestResult.UNKNOWN, 'unknown', 3),
            logdef.SingleTestFinding('2', logdef.TestResult.PASS, 'rerun test', 4),
        ]), [
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
        ])

    @patch_config_get('rerun_tests', True)
    def test_get_failures_rerun_success(self, config_mock):
        gpa = analyzepr.GatherPRAnalysis(Mock(), Mock())
        self.assertCountEqual(gpa.get_failures([
            logdef.SingleTestFinding('1', logdef.TestResult.PASS, '', 1),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('3', logdef.TestResult.UNKNOWN, 'unknown', 3),
            logdef.SingleTestFinding('2', logdef.TestResult.PASS, 'rerun test', 4),
        ]), [])

    @patch_config_get('rerun_tests', False)
    def test_get_failures_norerun_fail(self, config_mock):
        gpa = analyzepr.GatherPRAnalysis(Mock(), Mock())
        self.assertCountEqual(gpa.get_failures([
            logdef.SingleTestFinding('1', logdef.TestResult.PASS, '', 1),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('3', logdef.TestResult.UNKNOWN, 'unknown', 3),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'rerun test but fail again', 4),
        ]), [
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'rerun test but fail again', 4),
        ])

    @patch_config_get('rerun_tests', True)
    def test_get_failures_rerun_fail(self, config_mock):
        gpa = analyzepr.GatherPRAnalysis(Mock(), Mock())
        self.assertCountEqual(gpa.get_failures([
            logdef.SingleTestFinding('1', logdef.TestResult.PASS, '', 1),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('3', logdef.TestResult.UNKNOWN, 'unknown', 3),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'rerun test but fail again', 4),
        ]), [
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'rerun test but fail again', 4),
        ])

"""Test analyzepr."""

import unittest
from unittest.mock import Mock

from .context import testclutch  # noqa: F401

from testclutch.cli import analyzepr  # noqa: I100
from testclutch import logdef  # noqa: I100


class TestGatherPRAnalysis(unittest.TestCase):
    """Test analyzepr.GatherPRAnalysis."""

    def test_get_failures_rerun_success(self):
        gpa = analyzepr.GatherPRAnalysis(Mock(), Mock())
        self.assertCountEqual(gpa.get_failures([
            logdef.SingleTestFinding('1', logdef.TestResult.PASS, '', 1),
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
            logdef.SingleTestFinding('3', logdef.TestResult.UNKNOWN, 'unknown', 3),
            logdef.SingleTestFinding('2', logdef.TestResult.PASS, 'rerun test', 4),
        ]), [
            logdef.SingleTestFinding('2', logdef.TestResult.FAIL, 'failed', 2),
        ])

    def test_get_failures_rerun_fail(self):
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

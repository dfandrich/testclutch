"""Test unittestparse."""

import os
import unittest
from typing import TextIO

from .context import testclutch  # noqa: F401

from testclutch.logparser import unittestparse  # noqa: I100
from testclutch.logdef import SingleTestFinding  # noqa: I100

DATADIR = 'data'


class TestUnittestParse(unittest.TestCase):
    """Test unittestparse.parse_log_file."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000

    def open_data(self, fn: str) -> TextIO:
        return open(os.path.join(os.path.dirname(__file__), DATADIR, fn))

    # Log file was generated with Python 3.9 (3.10 is identical)
    def test_unittest(self):
        with self.open_data('unittest.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '1000',
            'testformat': 'unittest',
            'testresult': 'failure',
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_expected_failure',
                              unittestparse.TestResult.FAILIGNORE, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_expected_failure_but_success',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_failure',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_skipped',
                              unittestparse.TestResult.SKIP, 'skipped test', 0),
            # The subtests lines are mangled by unittest so they aren't parsed
            # SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_subtests_failure',
            #                   unittestparse.TestResult.FAIL, '', 0),
            # SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_subtests_success',
            #                   unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_success',
                              unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_unexpected_exception',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestSkippedClass.test_failure_but_skipped',
                              unittestparse.TestResult.SKIP, 'skipped class', 0),
            SingleTestFinding('tests.unittest_generate.TestSkippedClass.test_success_but_skipped',
                              unittestparse.TestResult.SKIP, 'skipped class', 0),
            SingleTestFinding('function_test_succeeds.tests.unittest_generate.TestFunctionSuccess',
                              unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('function_test_fails.tests.unittest_generate.TestFunctionFailure',
                              unittestparse.TestResult.FAIL, '', 0),
        ], testcases)

    # Log file was generated with Python 3.11
    # The only difference in 3.12 and 3.13 is failing code in the traceback gets underlined
    def test_unittest_311(self):
        with self.open_data('unittest_3.11.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '2000',
            'testformat': 'unittest',
            'testresult': 'failure',
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_expected_failure',
                              unittestparse.TestResult.FAILIGNORE, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_expected_failure_but_success',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_failure',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_skipped',
                              unittestparse.TestResult.SKIP, 'skipped test', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_subtests_failure',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_subtests_success',
                              unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_success',
                              unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests.unittest_generate.TestGenerateLogs.test_unexpected_exception',
                              unittestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests.unittest_generate.TestSkippedClass.test_failure_but_skipped',
                              unittestparse.TestResult.SKIP, 'skipped class', 0),
            SingleTestFinding('tests.unittest_generate.TestSkippedClass.test_success_but_skipped',
                              unittestparse.TestResult.SKIP, 'skipped class', 0),
            SingleTestFinding('function_test_succeeds.tests.unittest_generate.TestFunctionSuccess',
                              unittestparse.TestResult.PASS, '', 0),
            SingleTestFinding('function_test_fails.tests.unittest_generate.TestFunctionFailure',
                              unittestparse.TestResult.FAIL, '', 0),
        ], testcases)

    # Log file was generated with Python 3.9 (3.10 is identical)
    def test_unittest_success(self):
        with self.open_data('unittest_success.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '0',
            'testformat': 'unittest',
            'testresult': 'success'
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('tst.TestA.test_a',
                              unittestparse.TestResult.PASS, '', 0),
        ], testcases)

    # Log file was generated with Python 3.11 (3.12 and 3.13 are identical)
    def test_unittest_success_311(self):
        with self.open_data('unittest_success_3.11.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '0',
            'testformat': 'unittest',
            'testresult': 'success'
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('tst.TestA.test_a',
                              unittestparse.TestResult.PASS, '', 0),
        ], testcases)

    # Log file was generated with Python 3.9 (3.10 and 3.11 are identical)
    def test_unittest_none(self):
        with self.open_data('unittest_none.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '0',
            'testformat': 'unittest',
            'testresult': 'success',
        }, meta)
        self.assertCountEqual([
        ], testcases)

    # Log file was generated with Python 3.12
    def test_unittest_none_312(self):
        with self.open_data('unittest_none_3.12.log') as f:
            meta, testcases = unittestparse.parse_log_file(f)
        self.assertDictEqual({
            'runtestsduration': '0',
            'testformat': 'unittest',
            'testresult': 'success',
        }, meta)
        self.assertCountEqual([
        ], testcases)

    def dummy(self):
        """flake8 complains about the list in the previous method without something here."""

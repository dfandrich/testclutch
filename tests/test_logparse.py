"""Test logparse."""

import unittest

from .context import testclutch  # noqa: F401
from .util import open_data, patch_config_get

from testclutch.logdef import SingleTestFinding  # noqa: I100
from testclutch.logparser import logparse
from testclutch.testcasedef import TestResult

DATADIR = 'data'


class TestLogparse(unittest.TestCase):
    """Test logparse.parse_log_files."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000

    def test_single(self):
        """Parse with three parsers, only one of which will find anything."""
        with (patch_config_get('log_parsers', [
                'testclutch.logparser.unittestparse.parse_log_file',
                'testclutch.logparser.automakeparse.parse_log_file',
                'testclutch.logparser.pytestparse.parse_log_file']),
              patch_config_get('log_parse_single', True),
              open_data('automake_pytest_multiple.log') as f):
            result = [(meta, testcases) for meta, testcases in logparse.parse_log_files(f)]
            self.assertCountEqual([
                ({
                    'testformat': 'automake',
                    'testresult': 'success',
                    'testtarget': 'EXIF library 0.6.24.1',
                }, [
                    SingleTestFinding('check-localedir.sh', TestResult.PASS, '', 0),
                ])
            ], result)

    def test_multiple(self):
        """Parse with three parsers, only two of which will find anything."""
        with (patch_config_get('log_parsers', [
                'testclutch.logparser.unittestparse.parse_log_file',
                'testclutch.logparser.automakeparse.parse_log_file',
                'testclutch.logparser.pytestparse.parse_log_file']),
              patch_config_get('log_parse_single', False),
              open_data('automake_pytest_multiple.log') as f):
            result = [(meta, testcases) for meta, testcases in logparse.parse_log_files(f)]
            self.assertCountEqual([
                ({
                    'testformat': 'automake',
                    'testresult': 'success',
                    'testtarget': 'EXIF library 0.6.24.1',
                }, [
                    SingleTestFinding('check-localedir.sh', TestResult.PASS, '', 0),
                ]),
                ({
                    'os': 'linux',
                    'runtestsduration': '70000',
                    'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
                    'testformat': 'pytest',
                    'testresult': 'failure',
                }, [
                    SingleTestFinding('bar/test.py::TestParameterized::ciphers[TLSv1.3 +TLSv1.2-True]', TestResult.PASS, '', 0),
                    SingleTestFinding('foo_test.py::TestUupcCvt::test_ex', TestResult.FAIL, '', 0),
                    SingleTestFinding('skip_test.py::TestUupcCvt::test_ex', TestResult.SKIP, '', 0)
                ])
            ], result)

    def dummy(self):
        """flake8 complains about the list in the previous method without something here."""

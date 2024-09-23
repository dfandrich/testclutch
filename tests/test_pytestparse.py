import os
import unittest
from typing import TextIO

from .context import testclutch  # noqa: F401

from testclutch.logparser import pytestparse  # noqa: I100
from testclutch.logdef import SingleTestFinding  # noqa: I100

DATADIR = 'data'


class TestCurlParse(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.maxDiff = 4000

    def open_data(self, fn: str) -> TextIO:
        return open(os.path.join(os.path.dirname(__file__), DATADIR, fn))

    def test_success(self):
        with self.open_data('pytest_success.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
            'runtestsduration': '80000',
            'testformat': 'pytest',
            'testresult': 'success'
        }, meta)
        self.assertEqual([
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_aborted', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_event', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_short', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_torture', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_truncated', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_valgrind', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_pytestparse.py::TestCurlParse::test_truncated', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_pytestparse.py::TestCurlParse::test_verbose', pytestparse.TestResult.PASS, '', 0)
        ], testcases)

    def test_verbose(self):
        with self.open_data('pytest_verbose.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '70000',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertEqual([
            SingleTestFinding('bar_test.py::TestUupcCvt::test_ex', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('foo_test.py::TestUupcCvt::test_ex', pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('skip_test.py::TestUupcCvt::test_ex', pytestparse.TestResult.SKIP, '', 0)
        ], testcases)

    def test_truncated(self):
        # truncated log file
        with self.open_data('pytest_truncated.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
            'testformat': 'pytest',
            'testresult': 'truncated'
        }, meta)
        self.assertEqual([
            SingleTestFinding('bar_test.py::TestUupcCvt::test_ex', pytestparse.TestResult.PASS, '', 0),
        ], testcases)

    def test_faillogs(self):
        # several types of failures
        with self.open_data('pytest_faillogs.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '490000',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertEqual([
            SingleTestFinding('tests/test_curldailyinfo.py::TestCurlDailyInfo::test_dailyinfo', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_aborted', pytestparse.TestResult.FAILIGNORE, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_daily', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_event', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_faillogs', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_short', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_testcurlgit', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_torture', pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_truncated', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_valgrind', pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('tests/test_gitcommitinfo.py::TestGitCommitInfo::test_gitcommitinfo', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_pytestparse.py::TestCurlParse::test_success', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_pytestparse.py::TestCurlParse::test_truncated', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/test_pytestparse.py::TestCurlParse::test_verbose', pytestparse.TestResult.PASS, '', 0)
        ], testcases)

    def test_nonverbose(self):
        # several types of failures in a non-verbose log file
        with self.open_data('pytest_nonverbose.log') as f:
            meta, testcases = pytestparse.parse_log_file_summary(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '450000',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertEqual([
            SingleTestFinding('tests/test_curlparse.py::TestCurlParse::test_torture', pytestparse.TestResult.FAIL, 'AssertionError:...', 0),
        ], testcases)

    def test_longtime(self):
        # test takes over a minute, resulting in a slightly different summary line
        with self.open_data('pytest_longtime.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '61160000',
            'testdeps': 'Python 3.12.2, pytest-8.0.1, pluggy-1.4.0',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertEqual([
            SingleTestFinding('adddate_test.py::TestAdddateCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('adddate_test.py::TestAdddateCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('compuservecvt_test.py::TestCompuserveCvt::test_message_1', pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('compuservecvt_test.py::TestCompuserveCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('maillogcvt_test.py::TestMaillogCvt::test_message_1', pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('maillogcvt_test.py::TestMaillogCvt::test_message_2', pytestparse.TestResult.FAILIGNORE, '', 0),
            SingleTestFinding('mantes_test.py::TestMantesCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('uupccvt_test.py::TestUupcCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('uupccvt_test.py::TestUupcCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
        ], testcases)

    def test_xdist(self):
        with self.open_data('pytest_xdist.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '720000',
            'testdeps': 'Python 3.10.11, pytest-8.3.3, pluggy-1.5.0',
            'paralleljobs': '2',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('adddate_test.py::TestAdddateCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('adddate_test.py::TestAdddateCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('compuservecvt_test.py::TestCompuserveCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('compuservecvt_test.py::TestCompuserveCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('maillogcvt_test.py::TestMaillogCvt::test_message_1', pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('maillogcvt_test.py::TestMaillogCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('mantes_test.py::TestMantesCvt::test_message_1', pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('uupccvt_test.py::TestUupcCvt::test_message_1', pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('uupccvt_test.py::TestUupcCvt::test_message_2', pytestparse.TestResult.PASS, '', 0),
        ], testcases)

    def test_xdist_summary(self):
        with self.open_data('pytest_xdist_summary.log') as f:
            meta, testcases = pytestparse.parse_log_file_summary(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '730000',
            'testdeps': 'Python 3.10.11, pytest-8.3.3, pluggy-1.5.0',
            'paralleljobs': '2',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('uupccvt_test.py::TestUupcCvt::test_message_1', pytestparse.TestResult.FAIL, "AssertionError: 'From[9...", 0),
        ], testcases)

    def test_verbose_as_summary(self):
        # use the wrong parser on verbose logs
        for fn in ['pytest_success.log', 'pytest_verbose.log', 'pytest_truncated.log',
                   'pytest_faillogs.log', 'pytest_longtime.log', 'pytest_xdist.log']:
            with self.subTest(fn):
                with self.open_data(fn) as f:
                    meta, testcases = pytestparse.parse_log_file_summary(f)
                self.assertDictEqual({}, meta)
                self.assertEqual([], testcases)

    def test_summary_as_verbose(self):
        # use the wrong parser on summary logs
        for fn in ['pytest_nonverbose.log', 'pytest_xdist_summary.log']:
            with self.subTest(fn):
                with self.open_data(fn) as f:
                    meta, testcases = pytestparse.parse_log_file(f)
                self.assertDictEqual({}, meta)
                self.assertEqual([], testcases)

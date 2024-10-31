"""Test pytestparse."""

import os
import unittest
from typing import TextIO

from .context import testclutch  # noqa: F401

from testclutch.logparser import pytestparse  # noqa: I100
from testclutch.logdef import SingleTestFinding  # noqa: I100

DATADIR = 'data'


class TestParsePlatform(unittest.TestCase):
    """Test pytestparse.parse_platform."""

    def test_platform_linux(self):
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.6.43-desktop-1.mga9 but
            # there is no way to disambiguate the answer
            'systemosver': '6.6.43-desktop',
            'arch': 'x86_64'
        }, pytestparse.parse_platform('Linux-6.6.43-desktop-1.mga9-x86_64-with-glibc2.39'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.1.33-0-generic but
            # there is no way to disambiguate the answer
            'systemosver': '6.1.33-0',
            'arch': 'x86_64'
        }, pytestparse.parse_platform('Linux-6.1.33-0-generic-x86_64-with-libc'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.5.0-35-generic but
            # there is no way to disambiguate the answer
            'systemosver': '6.5.0-35',
            'arch': 'riscv64'
        }, pytestparse.parse_platform('Linux-6.5.0-35-generic-riscv64-with-glibc2.35'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.0.0-6-powerpc64 but
            # there is no way to disambiguate the answer
            'systemosver': '6.0.0-6',
            'arch': 'ppc64'
        }, pytestparse.parse_platform('Linux-6.0.0-6-powerpc64-ppc64-with-glibc2.40'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '6.8.9-0',
            'arch': 'riscv64'
        }, pytestparse.parse_platform('Linux-6.8.9-0-starfive-riscv64-with'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '4.9.79',
            # This is actually a buggy result since the real osver is 4.9.79-UBNT_E300 but
            # there is no way to disambiguate the answer
            'arch': 'mips64'
        }, pytestparse.parse_platform('Linux-4.9.79-UBNT_E300-mips64-with-debian-10.13'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 5.0.0-32-generic but
            # there is no way to disambiguate the answer
            'systemosver': '5.0.0-32',
            'arch': 'x86_64'
        }, pytestparse.parse_platform('Linux-5.0.0-32-generic-x86_64-with-Ubuntu-18.04-bionic'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '5.4.134-qgki',
            'arch': 'aarch64'
        }, pytestparse.parse_platform('Linux-5.4.134-qgki-g544c77a8a651-aarch64-with-libc'))

    def test_platform_windows(self):
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '6.1.7601',
        }, pytestparse.parse_platform('Windows-7-6.1.7601-SP1'))
        # This case comes from Python 2.7; it looks like Python 3 no longer uses this form
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '6.2.9200',
        }, pytestparse.parse_platform('Windows-8-6.2.9200'))
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '10.0.22621',
        }, pytestparse.parse_platform('Windows-10-10.0.22621-SP0'))

    def test_platform_java(self):
        # This comes from Jython 2.7.3
        self.assertDictEqual({
            'systemos': 'Java',
            'arch': 'amd64'
        }, pytestparse.parse_platform('Java-21.0.4-OpenJDK_64-Bit_Server_VM,_21.0.4+7-Ubuntu-1ubuntu224.04,_Ubuntu-on-Linux-6.6.43-desktop-1.mga9-amd64'))

    def test_platform_default(self):
        # The systemosver should be 7.1, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemosver': '1',
            'arch': 'powerpc',
            'archbits': '32'
        }, pytestparse.parse_platform('AIX-1-00F84C0C4C00-powerpc-32bit'))
        # The systemosver should be 7.3, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemosver': '3',
            'arch': 'powerpc',
            'archbits': '64'
        }, pytestparse.parse_platform('AIX-3-00F9C1964C00-powerpc-64bit'))
        self.assertDictEqual({
            'systemos': 'Haiku',
            'systemosver': '1',
            'arch': 'x86_64',
            'archbits': '64'
        }, pytestparse.parse_platform('Haiku-1-x86_64-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'OpenBSD',
            'systemosver': '7.5',
            'arch': 'amd64',
            'archbits': '64'
        }, pytestparse.parse_platform('OpenBSD-7.5-amd64-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemosver': '14.0-CURRENT',
            'arch': 'aarch64c',
            'archbits': '64'
        }, pytestparse.parse_platform('FreeBSD-14.0-CURRENT-arm64-aarch64c-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'NetBSD',
            'systemosver': '10.0',
            'arch': 'x86_64',
            'archbits': '64'
        }, pytestparse.parse_platform('NetBSD-10.0-amd64-x86_64-64bit-ELF'))
        # uname -r shows 5.10, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.10',
            'arch': 'sparc',
            'archbits': '32'
        }, pytestparse.parse_platform('Solaris-2.10-sun4u-sparc-32bit-ELF'))
        # uname -r shows 5.11, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.11',
            'arch': 'i386',
            'archbits': '64'
        }, pytestparse.parse_platform('Solaris-2.11-i86pc-i386-64bit'))
        # uname -r shows 5.11, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.11',
            'arch': 'sparc',
            'archbits': '64'
        }, pytestparse.parse_platform('Solaris-2.11-sun4v-sparc-64bit'))
        # This platform comes from Python >= 3.8; older ones say darwin instead of macOS
        self.assertDictEqual({
            'systemos': 'macOS',
            'systemosver': '12.6',
            'arch': 'arm',
            'archbits': '64'
        }, pytestparse.parse_platform('macOS-12.6-arm64-arm-64bit'))
        self.assertDictEqual({
            'systemos': 'macOS',
            'systemosver': '10.15.6',
            'arch': 'i386',
            'archbits': '64'
        }, pytestparse.parse_platform('macOS-10.15.6-x86_64-i386-64bit'))
        # This case comes from Python 2.7
        # The systemosver should be 0.6.7, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'syllable',
            'systemosver': '7',
            'arch': 'i586',
            'archbits': '32'
        }, pytestparse.parse_platform('syllable-7-i586-32bit'))
        self.assertDictEqual({
            'systemos': 'Fiwix',
            'systemosver': '1.5.0',
            'arch': 'i386',
            'archbits': '32'
        }, pytestparse.parse_platform('Fiwix-1.5.0-i386-32bit-ELF'))


class TestPytestParse(unittest.TestCase):
    """Test pytestparse.parse_log_file and pytestparse.parse_log_file_summary."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000

    def open_data(self, fn: str) -> TextIO:
        return open(os.path.join(os.path.dirname(__file__), DATADIR, fn))

    def test_success(self):
        with self.open_data('pytest_success.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'buildsystem': 'automake',
            'compiler': 'GNU_C',
            'compilerversion': '12',
            'configureargs': "'--enable-maintainer-mode'",
            'curlprotocols': 'dict file ftp ftps gopher gophers http https imap imaps ipfs ipns ldap ldaps mqtt pop3 pop3s rtsp smb smbs smtp smtps telnet tftp ws wss',
            'features': 'alt-svc AsynchDNS brotli Debug HSTS HTTP2 HTTPS-proxy IPv6 Largefile libz NTLM PSL SSL threadsafe TLS-SRP TrackMemory UnixSockets zstd',
            'hostarch': 'x86_64',
            'hostos': 'linux-gnu',
            'hosttriplet': 'x86_64-pc-linux-gnu',
            'hostvendor': 'pc',
            'os': 'linux',
            'runtestsduration': '80000',
            'targetarch': 'x86_64',
            'targetos': 'linux-gnu',
            'targettriplet': 'x86_64-pc-linux-gnu',
            'targetvendor': 'pc',
            'testdeps': 'Python 3.8.14, pytest-6.1.2, py-1.9.0, pluggy-0.13.1',
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
            SingleTestFinding('bar/test.py::TestParameterized::ciphers[TLSv1.3 +TLSv1.2-True]', pytestparse.TestResult.PASS, '', 0),
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
            'buildsystem': 'cmake/ninja',
            'buildsystemver': '3.30.4',
            'compiler': 'GNU',
            'compilerversion': '12.3.0',
            'configureargs': '-DBUILD_STATIC_LIBS="ON" -DCMAKE_C_COMPILER_TARGET="x86_64-pc-linux-gnu" -DCMAKE_UNITY_BUILD="ON" -DCURL_BROTLI="ON" -DCURL_CA_FALLBACK="ON" -DCURL_TEST_BUNDLES="ON" -DCURL_WERROR="ON" -DCURL_ZSTD="ON" -DENABLE_DEBUG="ON" -DHTTPD_NGHTTPX="/home/runner/nghttp2/build/bin/nghttpx" -DOPENSSL_ROOT_DIR="/home/runner/quiche/quiche/deps/boringssl/src" -DTEST_NGHTTPX="/home/runner/nghttp2/build/bin/nghttpx" -DUSE_QUICHE="ON"',
            'hostarch': 'x86_64',
            'hostos': 'Linux',
            'os': 'linux',
            'runtestsduration': '450000',
            'targetarch': 'x86_64',
            'targetos': 'Linux',
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
            'arch': 'x86_64',
            'os': 'linux',
            'runtestsduration': '720000',
            'testdeps': 'Python 3.10.11, pytest-8.3.3, pluggy-1.5.0',
            'paralleljobs': '2',
            'pyplatform': 'Linux-6.6.43-desktop-1.mga9-x86_64-with-glibc2.36',
            'systemos': 'Linux',
            'systemosver': '6.6.43-desktop',
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

    def test_unittest(self):
        with self.open_data('pytest_unittest.log') as f:
            meta, testcases = pytestparse.parse_log_file(f)
        self.assertDictEqual({
            'os': 'linux',
            'runtestsduration': '100000',
            'testdeps': 'Python 3.10.11, pytest-8.3.3, pluggy-1.5.0',
            'testformat': 'pytest',
            'testresult': 'failure'
        }, meta)
        self.assertCountEqual([
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_expected_failure',
                              pytestparse.TestResult.FAILIGNORE, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_expected_failure_but_success',
                              pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_failure',
                              pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_skipped',
                              pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_subtests_failure',
                              pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_subtests_success',
                              pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_success',
                              pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestGenerateLogs::test_unexpected_exception',
                              pytestparse.TestResult.FAIL, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestSkippedClass::test_failure_but_skipped',
                              pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestSkippedClass::test_success_but_skipped',
                              pytestparse.TestResult.SKIP, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestFunctionSuccess::runTest',
                              pytestparse.TestResult.PASS, '', 0),
            SingleTestFinding('tests/unittest_generate.py::TestFunctionFailure::runTest',
                              pytestparse.TestResult.FAIL, '', 0),
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

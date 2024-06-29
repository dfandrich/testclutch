import os
import unittest
from typing import TextIO

from .context import testclutch  # noqa: F401

from testclutch.logparser import automakeparse   # noqa: I100
from testclutch.logdef import SingleTestFinding   # noqa: I100

DATADIR = 'data'


class TestCurlParse(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 4000

    def open_data(self, fn: str) -> TextIO:
        return open(os.path.join(os.path.dirname(__file__), DATADIR, fn))

    def test_success(self):
        with self.open_data('automake_two.log') as f:
            meta, testcases = automakeparse.parse_log_file(f)
        self.assertDictEqual({
            'testformat': 'automake',
            'testresult': 'success',
            'testtarget': 'EXIF library 0.6.24.1',
        }, meta)
        self.assertEqual([
            SingleTestFinding('check-localedir.sh', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-fuzzer', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-mem', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-value', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-sorted', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-tagtable', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-parse-from-data', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-integers', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-parse', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test-null', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('check-failmalloc.sh', automakeparse.TestResult.SKIP, '', 0),
            SingleTestFinding('test-gps', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('parse-regression.sh', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('swap-byte-order.sh', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('extract-parse.sh', automakeparse.TestResult.PASS, '', 0)
        ], testcases)

    def test_two_logs_second_truncated(self):
        with self.open_data('automake_twotrunc.log') as f:
            meta, testcases = automakeparse.parse_log_file(f)
        self.assertDictEqual({
            'testformat': 'automake',
            'testresult': 'truncated',
            'testtarget': 'curl',
        }, meta)
        self.assertEqual([
            SingleTestFinding('check-easy', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('check-multi', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('1305', automakeparse.TestResult.PASS, 'internal hash create/destroy testing', 0),
            SingleTestFinding('1397', automakeparse.TestResult.PASS, 'Curl_cert_hostcheck unit tests', 0),
            SingleTestFinding('1396', automakeparse.TestResult.PASS, 'curl_easy_escape and curl_easy_unescape', 0),
            SingleTestFinding('1398', automakeparse.TestResult.PASS, 'curl_msnprintf unit tests', 0),
            SingleTestFinding('1600', automakeparse.TestResult.PASS, 'NTLM unit tests', 0),
            SingleTestFinding('1612', automakeparse.TestResult.PASS, 'HMAC unit tests', 0),
            SingleTestFinding('1614', automakeparse.TestResult.PASS, 'noproxy and cidr comparisons', 0),
            SingleTestFinding('1650', automakeparse.TestResult.PASS, 'DOH', 0),
            SingleTestFinding('1620', automakeparse.TestResult.PASS, 'unit tests for url.c', 0),
            SingleTestFinding('1655', automakeparse.TestResult.PASS, 'unit test for doh_encode', 0),
            SingleTestFinding('2603', automakeparse.TestResult.PASS, 'http1 parser unit tests', 0),
            SingleTestFinding('1654', automakeparse.TestResult.PASS, 'alt-svc', 0),
            SingleTestFinding('1653', automakeparse.TestResult.PASS, 'urlapi port number parsing', 0),
            SingleTestFinding('1621', automakeparse.TestResult.PASS, 'unit tests for stripcredentials from URL', 0),
            SingleTestFinding('2602', automakeparse.TestResult.PASS, 'dynhds unit tests', 0),
            SingleTestFinding('1610', automakeparse.TestResult.PASS, 'SHA256 unit tests', 0),
            SingleTestFinding('2601', automakeparse.TestResult.PASS, 'bufq unit tests', 0),
            SingleTestFinding('1608', automakeparse.TestResult.PASS, 'verify DNS shuffling', 0),
            SingleTestFinding('3200', automakeparse.TestResult.PASS, 'curl_get_line unit tests', 0),
            SingleTestFinding('1607', automakeparse.TestResult.PASS, 'CURLOPT_RESOLVE parsing', 0),
            SingleTestFinding('1606', automakeparse.TestResult.PASS, 'verify speedcheck', 0),
            SingleTestFinding('1604', automakeparse.TestResult.PASS, 'Test WIN32/MSDOS filename sanitization', 0),
            SingleTestFinding('1603', automakeparse.TestResult.PASS, 'Internal hash add, retrieval, deletion testing', 0),
            SingleTestFinding('1651', automakeparse.TestResult.PASS, 'x509 parsing', 0),
            SingleTestFinding('1660', automakeparse.TestResult.PASS, 'HSTS', 0),
            SingleTestFinding('1661', automakeparse.TestResult.PASS, 'bufref unit tests', 0),
            SingleTestFinding('1560', automakeparse.TestResult.PASS, 'URL API', 0),
            SingleTestFinding('1609', automakeparse.TestResult.PASS, 'CURLOPT_RESOLVE parsing', 0),
            SingleTestFinding('1399', automakeparse.TestResult.PASS, 'Curl_pgrsTime unit tests', 0),
            SingleTestFinding('1611', automakeparse.TestResult.PASS, 'MD4 unit tests', 0),
            SingleTestFinding('1652', automakeparse.TestResult.PASS, 'infof', 0),
            SingleTestFinding('1601', automakeparse.TestResult.PASS, 'MD5 unit tests', 0),
            SingleTestFinding('1323', automakeparse.TestResult.PASS, 'curlx_tvdiff', 0),
            SingleTestFinding('1308', automakeparse.TestResult.PASS, 'formpost unit tests', 0),
            SingleTestFinding('1306', automakeparse.TestResult.PASS, 'internal hash create/add/destroy testing', 0),
            SingleTestFinding('1394', automakeparse.TestResult.PASS, 'unit test for parse_cert_parameter()', 0),
            SingleTestFinding('1304', automakeparse.TestResult.PASS, 'netrc parsing unit tests', 0),
            SingleTestFinding('1303', automakeparse.TestResult.PASS, 'Curl_timeleft unit tests', 0),
            SingleTestFinding('1605', automakeparse.TestResult.PASS, 'Test negative data lengths as input to libcurl functions', 0),
            SingleTestFinding('1395', automakeparse.TestResult.PASS, 'Curl_dedotdotify', 0),
            SingleTestFinding('1602', automakeparse.TestResult.PASS, 'Internal hash create/add/destroy testing, exercising clean functions', 0),
            SingleTestFinding('1300', automakeparse.TestResult.PASS, 'llist unit tests', 0),
            SingleTestFinding('1302', automakeparse.TestResult.PASS, 'base64 encode/decode unit tests', 0),
            SingleTestFinding('517', automakeparse.TestResult.PASS, 'curl_getdate() testing', 0),
            SingleTestFinding('557', automakeparse.TestResult.PASS, 'curl_mprintf() testing', 0),
            SingleTestFinding('1309', automakeparse.TestResult.PASS, 'splay unit tests', 0),
            SingleTestFinding('3021', automakeparse.TestResult.FAIL, 'SFTP correct sha256 host key - data', 0),
            SingleTestFinding('3022', automakeparse.TestResult.FAIL, 'SCP correct sha256 host key - data', 0),
            SingleTestFinding('2600', automakeparse.TestResult.PASS, 'connection filter connect/destroy unit tests', 0)
        ], testcases)

    def test_synthesized(self):
        # These tests have synthesized names that include spaces
        with self.open_data('automake_synthesized.log') as f:
            meta, testcases = automakeparse.parse_log_file(f)
        self.assertDictEqual({
            'testformat': 'automake',
            'testresult': 'failure',
            'testtarget': 'libssh2',
        }, meta)
        self.assertEqual([
            SingleTestFinding('test_auth_password_fail_password', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_password_ok', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_password_fail_username', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_agent_forward_ok', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_keyboard_ok', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_fail', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_keyboard_fail', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_ed25519', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_dsa', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_ed25519_mem', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_ecdsa_signed', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_rsa', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_ed25519_encrypted', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_rsa_encrypted', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_keyboard_info_request', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_rsa_openssh', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_simple', automakeparse.TestResult.PASS, '', 0),
            SingleTestFinding('test_read', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_hostkey_hash', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_aa_warmup', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_ecdsa', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_hostkey', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_rsa_aes256gcm', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_auth_pubkey_ok_rsa_signed', automakeparse.TestResult.FAIL, '', 0),
            SingleTestFinding('test_sshd.test 1', automakeparse.TestResult.PASS, 'sshd-test_ssh2', 0),
            SingleTestFinding('test_sshd.test 2', automakeparse.TestResult.FAIL, 'sshd-test_auth_pubkey_ok_ed25519', 0),
            SingleTestFinding('test_read_algos.test 1', automakeparse.TestResult.FAIL, 'test_read-3des-cbc', 0),
            SingleTestFinding('test_read_algos.test 2', automakeparse.TestResult.FAIL, 'test_read-aes128-cbc', 0),
            SingleTestFinding('test_read_algos.test 3', automakeparse.TestResult.FAIL, 'test_read-aes128-ctr', 0),
            SingleTestFinding('test_read_algos.test 4', automakeparse.TestResult.FAIL, 'test_read-aes128-gcm@openssh.com', 0),
            SingleTestFinding('test_read_algos.test 5', automakeparse.TestResult.FAIL, 'test_read-aes192-cbc', 0),
            SingleTestFinding('test_read_algos.test 6', automakeparse.TestResult.FAIL, 'test_read-aes192-ctr', 0),
            SingleTestFinding('test_read_algos.test 7', automakeparse.TestResult.FAIL, 'test_read-aes256-cbc', 0),
            SingleTestFinding('test_read_algos.test 8', automakeparse.TestResult.FAIL, 'test_read-aes256-ctr', 0),
            SingleTestFinding('test_read_algos.test 9', automakeparse.TestResult.FAIL, 'test_read-aes256-gcm@openssh.com', 0),
            SingleTestFinding('test_read_algos.test 10', automakeparse.TestResult.FAIL, 'test_read-hmac-md5', 0),
            SingleTestFinding('test_read_algos.test 11', automakeparse.TestResult.FAIL, 'test_read-hmac-md5-96', 0),
            SingleTestFinding('test_read_algos.test 12', automakeparse.TestResult.FAIL, 'test_read-hmac-sha1', 0),
            SingleTestFinding('test_read_algos.test 13', automakeparse.TestResult.FAIL, 'test_read-hmac-sha1-96', 0),
            SingleTestFinding('test_read_algos.test 14', automakeparse.TestResult.FAIL, 'test_read-hmac-sha1-etm@openssh.com', 0),
            SingleTestFinding('test_read_algos.test 15', automakeparse.TestResult.FAIL, 'test_read-hmac-sha2-256', 0),
            SingleTestFinding('test_read_algos.test 16', automakeparse.TestResult.FAIL, 'test_read-hmac-sha2-256-etm@openssh.com', 0),
            SingleTestFinding('test_read_algos.test 17', automakeparse.TestResult.FAIL, 'test_read-hmac-sha2-512', 0),
            SingleTestFinding('test_read_algos.test 18', automakeparse.TestResult.FAIL, 'test_read-hmac-sha2-512-etm@openssh.com', 0),
            SingleTestFinding('mansyntax.sh', automakeparse.TestResult.PASS, '', 0)
        ], testcases)


if __name__ == '__main__':
    unittest.main()

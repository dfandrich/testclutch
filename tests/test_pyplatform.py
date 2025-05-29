"""Test pyplatform."""

import unittest

from testclutch import pyplatform  # noqa: I100

# flake8: noqa: PAR104


class TestParsePlatform(unittest.TestCase):
    """Test pyplatform.parse_platform."""

    def test_platform_linux(self):
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.6.43-desktop-1.mga9 but
            # there is no way to disambiguate the answer
            'systemosver': '6.6.43-desktop',
            'arch': 'x86_64'
        }, pyplatform.parse_platform('Linux-6.6.43-desktop-1.mga9-x86_64-with-glibc2.39'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.1.33-0-generic but
            # there is no way to disambiguate the answer
            'systemosver': '6.1.33-0',
            'arch': 'x86_64'
        }, pyplatform.parse_platform('Linux-6.1.33-0-generic-x86_64-with-libc'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.5.0-35-generic but
            # there is no way to disambiguate the answer
            'systemosver': '6.5.0-35',
            'arch': 'riscv64'
        }, pyplatform.parse_platform('Linux-6.5.0-35-generic-riscv64-with-glibc2.35'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 6.0.0-6-powerpc64 but
            # there is no way to disambiguate the answer
            'systemosver': '6.0.0-6',
            'arch': 'ppc64'
        }, pyplatform.parse_platform('Linux-6.0.0-6-powerpc64-ppc64-with-glibc2.40'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '6.8.9-0',
            'arch': 'riscv64'
        }, pyplatform.parse_platform('Linux-6.8.9-0-starfive-riscv64-with'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '4.9.79',
            # This is actually a buggy result since the real osver is 4.9.79-UBNT_E300 but
            # there is no way to disambiguate the answer
            'arch': 'mips64'
        }, pyplatform.parse_platform('Linux-4.9.79-UBNT_E300-mips64-with-debian-10.13'))
        self.assertDictEqual({
            'systemos': 'Linux',
            # This is actually a buggy result since the real osver is 5.0.0-32-generic but
            # there is no way to disambiguate the answer
            'systemosver': '5.0.0-32',
            'arch': 'x86_64'
        }, pyplatform.parse_platform('Linux-5.0.0-32-generic-x86_64-with-Ubuntu-18.04-bionic'))
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemosver': '5.4.134-qgki',
            'arch': 'aarch64'
        }, pyplatform.parse_platform('Linux-5.4.134-qgki-g544c77a8a651-aarch64-with-libc'))

    def test_platform_windows(self):
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '6.1.7601',
        }, pyplatform.parse_platform('Windows-7-6.1.7601-SP1'))
        # This case comes from Python 2.7; it looks like Python 3 no longer uses this form
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '6.2.9200',
        }, pyplatform.parse_platform('Windows-8-6.2.9200'))
        self.assertDictEqual({
            'systemos': 'Windows',
            'systemosver': '10.0.22621',
        }, pyplatform.parse_platform('Windows-10-10.0.22621-SP0'))

    def test_platform_java(self):
        # This comes from Jython 2.7.3
        self.assertDictEqual({
            'systemos': 'Java',
            'arch': 'amd64'
        }, pyplatform.parse_platform('Java-21.0.4-OpenJDK_64-Bit_Server_VM,_21.0.4+7-Ubuntu-1ubuntu224.04,_Ubuntu-on-Linux-6.6.43-desktop-1.mga9-amd64'))

    def test_platform_default(self):
        # The systemosver should be 7.1, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemosver': '1',
            'arch': 'powerpc',
            'archbits': '32'
        }, pyplatform.parse_platform('AIX-1-00F84C0C4C00-powerpc-32bit'))
        # The systemosver should be 7.3, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemosver': '3',
            'arch': 'powerpc',
            'archbits': '64'
        }, pyplatform.parse_platform('AIX-3-00F9C1964C00-powerpc-64bit'))
        self.assertDictEqual({
            'systemos': 'Haiku',
            'systemosver': '1',
            'arch': 'x86_64',
            'archbits': '64'
        }, pyplatform.parse_platform('Haiku-1-x86_64-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'OpenBSD',
            'systemosver': '7.5',
            'arch': 'amd64',
            'archbits': '64'
        }, pyplatform.parse_platform('OpenBSD-7.5-amd64-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemosver': '14.0-CURRENT',
            'arch': 'aarch64c',
            'archbits': '64'
        }, pyplatform.parse_platform('FreeBSD-14.0-CURRENT-arm64-aarch64c-64bit-ELF'))
        self.assertDictEqual({
            'systemos': 'NetBSD',
            'systemosver': '10.0',
            'arch': 'x86_64',
            'archbits': '64'
        }, pyplatform.parse_platform('NetBSD-10.0-amd64-x86_64-64bit-ELF'))
        # uname -r shows 5.10, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.10',
            'arch': 'sparc',
            'archbits': '32'
        }, pyplatform.parse_platform('Solaris-2.10-sun4u-sparc-32bit-ELF'))
        # uname -r shows 5.11, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.11',
            'arch': 'i386',
            'archbits': '64'
        }, pyplatform.parse_platform('Solaris-2.11-i86pc-i386-64bit'))
        # uname -r shows 5.11, so the wrong osver may be a Python issue
        self.assertDictEqual({
            'systemos': 'Solaris',
            'systemosver': '2.11',
            'arch': 'sparc',
            'archbits': '64'
        }, pyplatform.parse_platform('Solaris-2.11-sun4v-sparc-64bit'))
        # This pyplatform comes from Python >= 3.8; older ones say darwin instead of macOS
        self.assertDictEqual({
            'systemos': 'macOS',
            'systemosver': '12.6',
            'arch': 'arm',
            'archbits': '64'
        }, pyplatform.parse_platform('macOS-12.6-arm64-arm-64bit'))
        self.assertDictEqual({
            'systemos': 'macOS',
            'systemosver': '10.15.6',
            'arch': 'i386',
            'archbits': '64'
        }, pyplatform.parse_platform('macOS-10.15.6-x86_64-i386-64bit'))
        # This pyplatform comes from Python 3.13.3
        self.assertDictEqual({
            'systemos': 'macOS',
            'systemosver': '14.7.5',
            'arch': 'arm',
            'archbits': '64'
        }, pyplatform.parse_platform('macOS-14.7.5-arm64-arm-64bit-Mach-O'))
        # This case comes from Python 2.7
        # The systemosver should be 0.6.7, which could be considered a Python bug
        self.assertDictEqual({
            'systemos': 'syllable',
            'systemosver': '7',
            'arch': 'i586',
            'archbits': '32'
        }, pyplatform.parse_platform('syllable-7-i586-32bit'))
        self.assertDictEqual({
            'systemos': 'Fiwix',
            'systemosver': '1.5.0',
            'arch': 'i386',
            'archbits': '32'
        }, pyplatform.parse_platform('Fiwix-1.5.0-i386-32bit-ELF'))

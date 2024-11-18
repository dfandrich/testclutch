"""Test uname."""

import unittest

from testclutch import uname  # noqa: I100

# flake8: noqa: PAR104

class TestParseUname(unittest.TestCase):
    """Test uname.parse_uname."""

    def test_uname(self):
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': '0013249e7165',
            'systemosver': '6.5.0-1023-azure',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Linux 0013249e7165 6.5.0-1023-azure #24~22.04.1-Ubuntu SMP Wed Jun 12 19:55:26 UTC '
            '2024 x86_64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'ip-10-0-189-223',
            'systemosver': '5.4.0-1025-aws',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Linux ip-10-0-189-223 5.4.0-1025-aws #25-Ubuntu SMP Fri Sep 11 09:37:24 UTC 2020 '
            'x86_64 x86_64 x86_64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'gcc1-power7.osuosl.org',
            'systemosver': '3.10.0-1160.105.1.el7.ppc64',
            'arch': 'ppc64'
        }, uname.parse_uname(
            'Linux gcc1-power7.osuosl.org 3.10.0-1160.105.1.el7.ppc64 #1 SMP Thu Dec 7 16:07:07 '
            'UTC 2023 ppc64 ppc64 ppc64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'cfarm91',
            'systemosver': '5.18.11-starfive',
            'arch': 'riscv64'
        }, uname.parse_uname(
            'Linux cfarm91 5.18.11-starfive #1 SMP Sun Sep 4 12:09:06 CEST 2022 riscv64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'mgahost',
            'systemosver': '6.6.43-desktop-1.mga9',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Linux mgahost 6.6.43-desktop-1.mga9 #1 SMP PREEMPT_DYNAMIC Sat Jul 27 17:18:39 UTC '
            '2024 x86_64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'scan',
            'systemosver': '4.1.15-gentoo-r1',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Linux scan 4.1.15-gentoo-r1 #2 SMP Thu Feb 18 14:16:46 UTC 2016 x86_64 '
            'Intel(R) Xeon(R) CPU X5675 @ 3.07GHz GenuineIntel GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'buildnode',
            'systemosver': '6.6.37-desktop',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Linux buildnode 6.6.37-desktop #1 SMP PREEMPT_DYNAMIC Sat Jul  6 01:42:12 UTC 2024 '
            'x86_64 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'Linux',
            'systemhost': 'xyzzy',
            'systemosver': '4.4.302-st28',
            'arch': 'mips'
        }, uname.parse_uname(
            'Linux xyzzy 4.4.302-st28 #21521 Mon Feb 13 04:58:26 +06 2023 mips DD-WRT')
        )
        self.assertDictEqual({
            'systemos': 'CYGWIN_NT-10.0-20348',
            'systemhost': 'fv-az1105-214',
            'systemosver': '3.5.3-1.x86_64',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'CYGWIN_NT-10.0-20348 fv-az1105-214 3.5.3-1.x86_64 2024-04-03 17:25 UTC x86_64 Cygwin')
        )
        self.assertDictEqual({
            'systemos': 'MINGW64_NT-10.0-20348',
            'systemhost': 'fv-az980-747',
            'systemosver': '3.5.3-d8b21b8c.x86_64',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'MINGW64_NT-10.0-20348 fv-az980-747 3.5.3-d8b21b8c.x86_64 2024-07-09 18:03 UTC x86_64 '
            'Msys')
        )
        self.assertDictEqual({
            'systemos': 'MINGW32_NT-10.0-17763',
            'systemhost': '68ab3802cea0',
            'systemosver': '3.4.8.x86_64',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'MINGW32_NT-10.0-17763 68ab3802cea0 3.4.8.x86_64 2023-08-18 23:11 UTC x86_64 Msys')
        )
        self.assertDictEqual({
            'systemos': 'MINGW32_NT-6.2',
            'systemhost': 'D346320C23B2',
            'systemosver': '1.0.19(0.48/3/2)',
            'arch': 'i686'
        }, uname.parse_uname(
            'MINGW32_NT-6.2 D346320C23B2 1.0.19(0.48/3/2) 2016-07-13 17:45 i686 Msys')
        )
        self.assertDictEqual({
            'systemos': 'MSYS_NT-10.0-20348',
            'systemhost': 'fv-az1105-175',
            'systemosver': '3.5.3.x86_64',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'MSYS_NT-10.0-20348 fv-az1105-175 3.5.3.x86_64 2024-06-03 06:22 UTC x86_64 Msys')
        )
        self.assertDictEqual({
            'systemos': 'Darwin',
            'systemhost': 'Mac-1715788362745.local',
            'systemosver': '23.4.0',
            'arch': 'arm64'
        }, uname.parse_uname(
            'Darwin Mac-1715788362745.local 23.4.0 Darwin Kernel Version 23.4.0: Fri Mar 15 '
            '00:10:50 PDT 2024; root:xnu-10063.101.17~1/RELEASE_ARM64_VMAPPLE arm64')
        )
        self.assertDictEqual({
            'systemos': 'Darwin',
            'systemhost': 'Mac-1686140684611.local',
            'systemosver': '21.6.0',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Darwin Mac-1686140684611.local 21.6.0 Darwin Kernel Version 21.6.0: Thu Mar  9 '
            '20:08:59 PST 2023; root:xnu-8020.240.18.700.8~1/RELEASE_X86_64 x86_64')
        )
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemosver': '14.1-RELEASE',
            'arch': 'amd64'
        }, uname.parse_uname(
            'FreeBSD  14.1-RELEASE FreeBSD 14.1-RELEASE releng/14.1-n267679-10e31f0946d8 GENERIC '
            'amd64')
        )
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemhost': 'cirrus-task-4657416118206464',
            'systemosver': '14.0-RELEASE',
            'arch': 'amd64'
        }, uname.parse_uname(
            'FreeBSD cirrus-task-4657416118206464 14.0-RELEASE FreeBSD 14.0-RELEASE #0 '
            'releng/14.0-n265380-f9716eee8ab4: Fri Nov 10 05:57:23 UTC 2023     '
            'root@releng1.nyi.freebsd.org:/usr/obj/usr/src/amd64.amd64/sys/GENERIC amd64')
        )
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemhost': 'cirrus-task-5504721130094592',
            'systemosver': '12.4-RELEASE',
            'arch': 'amd64'
        }, uname.parse_uname(
            'FreeBSD cirrus-task-5504721130094592 12.4-RELEASE FreeBSD 12.4-RELEASE r372781 '
            'GENERIC  amd64')
        )
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemhost': 'FreeSBIE.LiveCD',
            'systemosver': '6.2-RELEASE',
            'arch': 'i386'
        }, uname.parse_uname(
            'FreeBSD FreeSBIE.LiveCD 6.2-RELEASE FreeBSD 6.2-RELEASE #11: Wed Feb  7 16:52:42 '
            'UTC 2007     root@kaiser.sig11.org:/usr/obj.gmv-i386/usr/src/sys/FREESBIE  i386')
        )
        self.assertDictEqual({
            'systemos': 'FreeBSD',
            'systemhost': 'cheribsd-morello-purecap',
            'systemosver': '15.0-CURRENT',
            'arch': 'arm64'
        }, uname.parse_uname(
            'FreeBSD cheribsd-morello-purecap 15.0-CURRENT FreeBSD 15.0-CURRENT #0 '
            'main-b2ad856aac65: Fri Jul 19 19:54:25 UTC 2024     '
            'jenkins@focal:/local/scratch/jenkins/workspace/CheriBSD-pipeline_main@2'
            '/cheribsd-morello-purecap-build/local/scratch/jenkins/workspace'
            '/CheriBSD-pipeline_main@2/cheribsd/arm64.aarch64c/sys/GENERIC-MORELLO-PURECAP arm64')
        )
        self.assertDictEqual({
            'systemos': 'OpenBSD',
            'systemhost': 'openbsd.my.domain',
            'systemosver': '7.5',
            'arch': 'amd64'
        }, uname.parse_uname(
            'OpenBSD openbsd.my.domain 7.5 GENERIC.MP#82 amd64')
        )
        self.assertDictEqual({
            'systemos': 'SunOS',
            'systemhost': 'omnios',
            'systemosver': '5.11',
            'arch': 'i386'
        }, uname.parse_uname(
            'SunOS omnios 5.11 omnios-r151048-24333ee74c i86pc i386 i86pc')
        )
        self.assertDictEqual({
            'systemos': 'SunOS',
            'systemhost': 'gcc-solaris11',
            'systemosver': '5.11',
            'arch': 'sparc'
        }, uname.parse_uname(
            'SunOS gcc-solaris11 5.11 11.3 sun4u sparc SUNW,SPARC-Enterprise')
        )
        self.assertDictEqual({
            'systemos': 'NetBSD',
            'systemosver': '10.0',
            'arch': 'amd64'
        }, uname.parse_uname(
            'NetBSD  10.0 NetBSD 10.0 (GENERIC) #0: Thu Mar 28 08:33:33 UTC 2024  '
            'mkrepro@mkrepro.NetBSD.org:/usr/src/sys/arch/amd64/compile/GENERIC amd64')
        )
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemhost': 'gcc119',
            'systemosver': '7.3',
        }, uname.parse_uname(
            'AIX gcc119 3 7 00F9C1964C00')
        )
        self.assertDictEqual({
            'systemos': 'AIX',
            'systemhost': 'power-aix',
            'systemosver': '7.1',
        }, uname.parse_uname(
            'AIX power-aix 1 7 00F84C0C4C00')
        )
        self.assertDictEqual({
            'systemos': 'Haiku',
            'systemhost': 'shredder',
            'systemosver': '1',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Haiku shredder 1 hrev56578+59 Dec 17 2022 07:02: x86_64 x86_64 Haiku')
        )
        self.assertDictEqual({
            'systemos': 'Minix',
            'systemhost': 'minix',
            'systemosver': '3.3.0',
            'arch': 'i386'
        }, uname.parse_uname(
            'Minix minix 3.3.0 Minix 3.3.0 (GENERIC) i386')
        )
        self.assertDictEqual({
            'systemos': 'Fiwix',
            'systemhost': 'fiwix',
            'systemosver': '1.5.0',
            'arch': 'i386'
        }, uname.parse_uname(
            'Fiwix fiwix 1.5.0 Wed Nov 15 07:36:37 UTC 2023 i386 Fiwix')
        )
        self.assertDictEqual({
            'systemos': 'SerenityOS',
            'systemhost': 'courage',
            'systemosver': '1.0-dev',
            'arch': 'i686'
        }, uname.parse_uname(
            'SerenityOS courage 1.0-dev 1dc05fc i686')
        )
        self.assertDictEqual({
            'systemos': 'Redox',
            'systemosver': '0.3.4',
            'arch': 'x86_64'
        }, uname.parse_uname(
            'Redox  0.3.4  x86_64')
        )
        self.assertDictEqual({
            'systemos': 'syllable',
            'systemhost': 'syllable',
            'systemosver': '0.6.7',
            'arch': 'i586'
        }, uname.parse_uname(
            'syllable syllable 7 0.6 i586 Syllable')
        )
        self.assertDictEqual({
            'systemos': 'NuttX',
            'systemhost': '15cb41b',
            'systemosver': '12.4.0',
            'arch': 'risc-v'
        }, uname.parse_uname(
            'NuttX 12.4.0 15cb41b Jan 19 2024 10:25:11 risc-v rv-virt')
        )
        self.assertDictEqual({
            'systemos': 'Zephyr',
            'systemhost': 'zephyr',
            'systemosver': '3.7.99',
            'arch': 'x86'
        }, uname.parse_uname(
            'Zephyr zephyr 3.7.99 v3.7.0-4020-g9f73988be029 Oct  7 2024 21:13:21 x86 qemu_x86')
        )
        self.assertDictEqual({
            'systemos': 'QNX',
            'systemhost': 'localhost',
            'systemosver': '6.5.0',
            'arch': 'x86'
        }, uname.parse_uname(
            'QNX localhost 6.5.0 2010/07/09-14:42:57EDT x86pc x86')
        )
        self.assertDictEqual({
            'systemos': 'ELKS',
            'systemhost': 'elks',
            'systemosver': '0.7.0',
            'arch': 'i8086'
        }, uname.parse_uname(
            'ELKS elks 0.7.0 commit d043b92d 03 Aug 2023 07:37:00 -0700 ibmpc i8086')
        )
        self.assertDictEqual({
            'systemos': 'Sortix',
            'systemhost': 'sortix',
            'systemosver': '1.0',
            'arch': 'i686'
        }, uname.parse_uname(
            'Sortix sortix 1.0 "Self-Hosting & Installable" Mar 28 2016 i686 i386 i386 Sortix')
        )
        self.assertDictEqual({
            'systemos': 'Tilck',
            'systemhost': 'tilck',
            'systemosver': '0.1.4',
            'arch': 'i686'
        }, uname.parse_uname(
            'Tilck tilck 0.1.4 4b1930d8 i686 GNU/Linux')
        )
        self.assertDictEqual({
            'systemos': 'AROS',
            'systemhost': 'arosbox.arosnet',
            'systemosver': '12.1',
            'arch': 'i386'
        }, uname.parse_uname(
            'AROS arosbox.arosnet 12.1 41 Nov 26 2018 i386 AROS')
        )

    def test_bad_uname(self):
        self.assertDictEqual({
            'systemos': 'xyzzy',
        }, uname.parse_uname('xyzzy'))
        self.assertDictEqual({
        }, uname.parse_uname(''))

"""Test analysis."""

import unittest
from unittest.mock import Mock

from .context import testclutch  # noqa: F401

from testclutch import analysis  # noqa: I100


class TestCompareHashes(unittest.TestCase):
    """Test analysis.compare_hashes."""

    def test_same_hashes(self):
        self.assertTrue(analysis.compare_hashes(
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'))
        self.assertTrue(analysis.compare_hashes(
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
            'aaaaaab'))
        self.assertTrue(analysis.compare_hashes(
            'aaaaaab',
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'))
        self.assertTrue(analysis.compare_hashes(
            '12345',
            '123456'))

    def test_different_hashes(self):
        self.assertFalse(analysis.compare_hashes(
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
            '0000000000111111111222222222233333333333'))
        self.assertFalse(analysis.compare_hashes(
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
            'aaaaaac'))
        self.assertFalse(analysis.compare_hashes(
            'aaaaaac',
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'))
        self.assertFalse(analysis.compare_hashes(
            '',
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'))
        self.assertFalse(analysis.compare_hashes(
            'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
            ''))
        self.assertFalse(analysis.compare_hashes(
            '',
            ''))


class TestCommitUrl(unittest.TestCase):
    """Test commit_url.."""

    HASH = 'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'

    def test_commit_url(self):
        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://github.com/user/proj')
        self.assertEqual('https://github.com/user/proj/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://github.com/user/proj/')
        self.assertEqual('https://github.com/user/proj/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://github.com/user/proj.git')
        self.assertEqual('https://github.com/user/proj/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://gitlab.com/user/repo.git')
        self.assertEqual('https://gitlab.com/user/repo/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://gitlab.com/user/repo')
        self.assertEqual('https://gitlab.com/user/repo/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://gitlab.com/user/repo/')
        self.assertEqual('https://gitlab.com/user/repo/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://invent.kde.org/pim/xyzzy')
        self.assertEqual('https://invent.kde.org/pim/xyzzy/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://invent.kde.org/pim/xyzzy/')
        self.assertEqual('https://invent.kde.org/pim/xyzzy/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://invent.kde.org/pim/xyzzy.git')
        self.assertEqual('https://invent.kde.org/pim/xyzzy/-/commit/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://pagure.io/category/repo.git')
        self.assertEqual('https://pagure.io/category/repo/c/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://pagure.io/category/repo')
        self.assertEqual('https://pagure.io/category/repo/c/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://pagure.io/category/repo/')
        self.assertEqual('https://pagure.io/category/repo/c/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://git.code.sf.net/p/legacy/code')
        self.assertEqual('https://sourceforge.net/p/legacy/code/ci/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://git.code.sf.net/p/legacy/')
        self.assertEqual('https://sourceforge.net/p/legacy/code/ci/' + self.HASH,
                         obj.commit_url(self.HASH))

        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://git.code.sf.net/p/legacy')
        self.assertEqual('https://sourceforge.net/p/legacy/code/ci/' + self.HASH,
                         obj.commit_url(self.HASH))

    def test_unknown(self):
        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://some.unknown.site/xyzzy.git')
        self.assertEqual('', obj.commit_url(self.HASH))

    def test_invalid(self):
        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://git.code.sf.net/p/')
        self.assertEqual('', obj.commit_url(self.HASH))

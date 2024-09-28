"""Test analysis."""

import unittest
from unittest.mock import Mock

from .context import testclutch  # noqa: F401

from testclutch import analysis  # noqa: I100


class TestCompareHashes(unittest.TestCase):
    """Test analysis.compare_hashes."""

    def test_same_hashes(self):
        for a, b in [
            ('aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
             'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'),
            ('aaaaaabbbbbbbbccccccdddddeeeeeefffffffff', 'aaaaaab'),
            ('aaaaaab', 'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'),
            ('12345', '123456')
        ]:
            with self.subTest(a=a, b=b):
                self.assertTrue(analysis.compare_hashes(a, b))

    def test_different_hashes(self):
        for a, b in [
            ('aaaaaabbbbbbbbccccccdddddeeeeeefffffffff',
             '0000000000111111111222222222233333333333'),
            ('aaaaaabbbbbbbbccccccdddddeeeeeefffffffff', 'aaaaaac'),
            ('aaaaaac', 'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'),
            ('', 'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'),
            ('aaaaaabbbbbbbbccccccdddddeeeeeefffffffff', ''),
            ('', '')
        ]:
            with self.subTest(a=a, b=b):
                self.assertFalse(analysis.compare_hashes(a, b))


class TestCommitUrl(unittest.TestCase):
    """Test commit_url."""

    HASH = 'aaaaaabbbbbbbbccccccdddddeeeeeefffffffff'

    def test_commit_url(self):
        for repo, url in [
            # The commit hash is simply appended to each of these urls, making them shorter and this
            # table easier to read.
            ('https://github.com/user/proj', 'https://github.com/user/proj/commit/'),
            ('https://github.com/user/proj/', 'https://github.com/user/proj/commit/'),
            ('https://github.com/user/proj', 'https://github.com/user/proj/commit/'),
            ('https://github.com/user/proj/', 'https://github.com/user/proj/commit/'),
            ('https://github.com/user/proj.git', 'https://github.com/user/proj/commit/'),
            ('https://gitlab.com/user/repo.git', 'https://gitlab.com/user/repo/-/commit/'),
            ('https://gitlab.com/user/repo', 'https://gitlab.com/user/repo/-/commit/'),
            ('https://gitlab.com/user/repo/', 'https://gitlab.com/user/repo/-/commit/'),
            ('https://invent.kde.org/pim/xyzzy', 'https://invent.kde.org/pim/xyzzy/-/commit/'),
            ('https://invent.kde.org/pim/xyzzy/', 'https://invent.kde.org/pim/xyzzy/-/commit/'),
            ('https://invent.kde.org/pim/xyzzy.git', 'https://invent.kde.org/pim/xyzzy/-/commit/'),
            ('https://pagure.io/category/repo.git', 'https://pagure.io/category/repo/c/'),
            ('https://pagure.io/category/repo', 'https://pagure.io/category/repo/c/'),
            ('https://pagure.io/category/repo/', 'https://pagure.io/category/repo/c/'),
            ('https://git.code.sf.net/p/legacy/code', 'https://sourceforge.net/p/legacy/code/ci/'),
            ('https://git.code.sf.net/p/legacy/', 'https://sourceforge.net/p/legacy/code/ci/'),
            ('https://git.code.sf.net/p/legacy', 'https://sourceforge.net/p/legacy/code/ci/')
        ]:
            with self.subTest(repo=repo, url=url):
                self.assertEqual(
                    url + self.HASH,
                    analysis.ResultsOverTimeByUniqueJob(
                        Mock(), repo).commit_url(self.HASH))

    def test_unknown(self):
        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://some.unknown.site/xyzzy.git')
        self.assertEqual('', obj.commit_url(self.HASH))

    def test_invalid(self):
        obj = analysis.ResultsOverTimeByUniqueJob(Mock(), 'https://git.code.sf.net/p/')
        self.assertEqual('', obj.commit_url(self.HASH))

import unittest
from dataclasses import dataclass

from .context import testclutch  # noqa: F401

from testclutch import urls  # noqa: I100


class TestUrls(unittest.TestCase):
    def test_get_generic_project_name(self):
        self.assertEqual(
            urls.get_generic_project_name('https://github.com/user/project'),
            ('user', 'project'))
        self.assertEqual(
            urls.get_generic_project_name('https://gitlab.com/gluser/glproject'),
            ('gluser', 'glproject'))
        self.assertEqual(
            urls.get_generic_project_name('https://example.com/a/b'),
            ('a', 'b'))
        # Not sure this should be accepted
        self.assertEqual(
            urls.get_generic_project_name('not-a-url/a/b'),
            ('a', 'b'))
        with self.assertRaises(RuntimeError):
            urls.get_generic_project_name('https://github.com/too/many/paths')
        with self.assertRaises(RuntimeError):
            urls.get_generic_project_name('https://github.com/too-few-paths')

    def test_get_project_name(self):
        self.assertEqual(
            urls.get_project_name('https://github.com/user/project'),
            ('user', 'project'))

        @dataclass
        class Args:
            checkrepo: str
            account: str
            project: str

        args = Args('https://github.com/user/project', '', '')
        self.assertEqual(
            urls.get_project_name(args),
            ('user', 'project'))

        args = Args('https://github.com/user/project', 'actualuser', '')
        self.assertEqual(
            urls.get_project_name(args),
            ('actualuser', 'project'))

        args = Args('https://github.com/user/project', '', 'actualproject')
        self.assertEqual(
            urls.get_project_name(args),
            ('user', 'actualproject'))

        args = Args('https://github.com/user/project', 'actualuser', 'actualproject')
        self.assertEqual(
            urls.get_project_name(args),
            ('actualuser', 'actualproject'))

    def test_url_host(self):
        self.assertEqual(
            urls.url_host('https://github.com/user/project'),
            'github.com')
        self.assertEqual(
            urls.url_host('http://example.com/long/and/unnecessary/path'),
            'example.com')

    def test_url_pr(self):
        self.assertEqual(
            urls.url_pr('https://github.com/user/project/pull/12345'),
            12345)
        self.assertEqual(
            urls.url_pr('https://github.com/user/project/pull/xyzzy'),
            0)
        self.assertEqual(
            urls.url_pr('https://github.com/user/project/pull/'),
            0)
        self.assertEqual(
            urls.url_pr('https://github.com/user/project/pull'),
            0)
        self.assertEqual(
            urls.url_pr('https://github.com/user/project/tree/master/12345'),
            0)
        self.assertEqual(
            urls.url_pr('https://gitlab.com/user/project/pull/123'),
            0)

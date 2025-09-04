"""Test urls."""

import argparse
import unittest

from .context import testclutch  # noqa: F401

from testclutch import urls  # noqa: I100


class TestUrls(unittest.TestCase):
    """Test urls."""

    def test_get_generic_project_name(self):
        self.assertEqual(('user', 'project'),
                         urls.get_generic_project_name('https://github.com/user/project'))
        self.assertEqual(('gluser', 'glproject'),
                         urls.get_generic_project_name('https://gitlab.com/gluser/glproject'))
        self.assertEqual(('a', 'b'),
                         urls.get_generic_project_name('https://example.com/a/b'))
        # Not sure this should be accepted
        self.assertEqual(('a', 'b'),
                         urls.get_generic_project_name('not-a-url/a/b'))
        with self.assertRaises(RuntimeError):
            urls.get_generic_project_name('https://github.com/too/many/paths')
        with self.assertRaises(RuntimeError):
            urls.get_generic_project_name('https://github.com/too-few-paths')

    def test_get_project_name(self):
        self.assertEqual(('user', 'project'),
                         urls.get_project_name('https://github.com/user/project'))

        def Args(checkrepo: str, account: str, project: str):
            return argparse.Namespace(checkrepo=checkrepo, account=account, project=project)

        args = Args('https://github.com/user/project', '', '')
        self.assertEqual(('user', 'project'),
                         urls.get_project_name(args))

        args = Args('https://github.com/user/project', 'actualuser', '')
        self.assertEqual(('actualuser', 'project'),
                         urls.get_project_name(args))

        args = Args('https://github.com/user/project', '', 'actualproject')
        self.assertEqual(('user', 'actualproject'),
                         urls.get_project_name(args))

        args = Args('https://github.com/user/project', 'actualuser', 'actualproject')
        self.assertEqual(('actualuser', 'actualproject'),
                         urls.get_project_name(args))

    def test_url_host(self):
        self.assertEqual('github.com',
                         urls.url_host('https://github.com/user/project'))
        self.assertEqual('example.com',
                         urls.url_host('http://example.com/long/and/unnecessary/path'))

    def test_url_pr(self):
        self.assertEqual(12345,
                         urls.url_pr('https://github.com/user/project/pull/12345'))
        self.assertEqual(0,
                         urls.url_pr('https://github.com/user/project/pull/xyzzy'))
        self.assertEqual(0,
                         urls.url_pr('https://github.com/user/project/pull/'))
        self.assertEqual(0,
                         urls.url_pr('https://github.com/user/project/pull'))
        self.assertEqual(0,
                         urls.url_pr('https://github.com/user/project/tree/master/12345'))
        self.assertEqual(0,
                         urls.url_pr('https://gitlab.com/user/project/pull/123'))

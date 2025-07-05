"""Test gitcommitinfo."""

import os
import unittest
from unittest import mock

from .context import testclutch  # noqa: F401
from .util import data_file

from testclutch import gitdef    # noqa: I100

DATADIR = 'data'


class TestGitCommitInfo(unittest.TestCase):
    """Test gitcommitinfo."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000
        # Replace XDG_CONFIG_HOME to prevent the user's testclutchrc file from being loaded
        self.env_patcher = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': '/dev/null'})
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        # Import the code to test only after XDG_CONFIG_HOME has been replaced
        global gitcommitinfo
        from testclutch.cli import gitcommitinfo

    def test_gitcommitinfo(self):
        git = gitcommitinfo.GitCommitIngestor('https://git.example.com/ex', None)
        results = git.extract_git_commit_info(data_file('test.git'),
                                              'master', '2023-08-01T00:00:00-0700')
        # There are three commits past the given time, but the last one is deliberately dropped
        self.assertEqual([
            gitdef.CommitInfo(1690873322,
                              'eb1397238f07f07d572dbb8f95de195ddf77dc2c',
                              '71dfa549a1fb66002684049914480808c318eca3',
                              'Committer',
                              'committer@example.com',
                              'Author',
                              'author@example.com',
                              'One more change'),
            gitdef.CommitInfo(1690873262,
                              '71dfa549a1fb66002684049914480808c318eca3',
                              'ae42d6cd32024d200dc9bfa1b3b3f6c45e377e15',
                              'Committer',
                              'committer',
                              'Author',
                              'author',
                              'This commit is missing the e-mail domains'),
        ],
            results)

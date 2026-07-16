"""Test prdef."""

import os
import tempfile
import unittest
from unittest import mock

from .context import testclutch  # noqa: F401
from .util import patch_config_get


class TestPRAnalysisState(unittest.TestCase):
    """Test prdef.PRAnalysisState."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000
        # Replace XDG_CONFIG_HOME to prevent the user's testclutchrc file from being loaded
        self.env_patcher = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': '/dev/null'})
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        # Import the code to test only after XDG_CONFIG_HOME has been replaced
        global prdef
        from testclutch import prdef

    def test_write_read_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            prfile = os.path.join(tempdir, 'pr.dat')
            with patch_config_get('pr_gather_path', prfile):
                state = prdef.PRAnalysisState()

                # Create empty file
                _ = state.read_state(True)

                # Generate something to store the store it
                pran = prdef.PRAnalysis(
                    num=123,
                    checkrepo='https://example.com/repo.git',
                    start=1234567890,
                    failed={'origin': [prdef.FailedTest(uniquejob='abc|jobname',
                                       testname='test1', url='http://example.com/url')]},
                    flaky={'origin': [prdef.FailingTest(uniquejob='abc|jobname',
                                      testname='test2', rate=0.123)]},
                    permafail={'origin': [prdef.FailingTest(uniquejob='abc|jobname',
                                          testname='test6', rate=0.999)]},
                    commit={'origin': 'deadbeef'},
                    commented=True
                )
                fullstate = {'http://example.com/url': {999: pran}}
                state.write_state(fullstate)

                # Read back what was just stored
                readdata = state.read_state(False)

                self.assertEqual(fullstate, readdata)

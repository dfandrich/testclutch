"""Test msbuild."""

import io
import textwrap
import unittest

from .context import testclutch  # noqa: F401

from testclutch.ingest import msbuild   # noqa: I100


class TestMsBuildLog(unittest.TestCase):
    """Test msbuild."""

    def test_msbuildlog(self):
        infile = io.StringIO(textwrap.dedent("""\
            First line
            Second line
            Microsoft (R) Build Engine version 4.8.3761.0
              Indented line
              Another indented
                Even more indented
            An unindented line
            CUSTOMBUILD : warning : some weird kind of escaping
              An indent without a special prefix line
            Final unindented line
        """))
        msbuildlog = msbuild.MsBuildLog(infile)
        lines = list(iter(msbuildlog.readline, ''))
        self.assertEqual([
            'First line\n',
            'Second line\n',
            'Microsoft (R) Build Engine version 4.8.3761.0\n',
            'Indented line\n',
            'Another indented\n',
            '  Even more indented\n',
            'An unindented line\n',
            'Warning: some weird kind of escaping\n',
            'An indent without a special prefix line\n',
            'Final unindented line\n'
        ],
            lines)

    def test_msbuildlog_seek(self):
        infile = io.StringIO(textwrap.dedent("""\
            First line
              Indented Second line
            Microsoft (R) Build Engine version 4.8.3761.0
              Indented build line
              Another indented
                Even more indented, and staying there
        """))
        msbuildlog = msbuild.MsBuildLog(infile)
        lines = list(iter(msbuildlog.readline, ''))
        self.assertEqual([
            'First line\n',
            '  Indented Second line\n',
            'Microsoft (R) Build Engine version 4.8.3761.0\n',
            'Indented build line\n',
            'Another indented\n',
            '  Even more indented, and staying there\n',
        ],
            lines)

        # Seek past the first line
        msbuildlog.seek(11, 0)
        lines = list(iter(msbuildlog.readline, ''))
        self.assertEqual([
            '  Indented Second line\n',
            'Microsoft (R) Build Engine version 4.8.3761.0\n',
            'Indented build line\n',
            'Another indented\n',
            '  Even more indented, and staying there\n',
        ],
            lines)

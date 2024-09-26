"""Test logprefix."""

import io
import re
import textwrap
import unittest

from .context import testclutch  # noqa: F401

from testclutch.ingest import logprefix   # noqa: I100


class TestLogPrefix(unittest.TestCase):
    """Test logprefix."""

    def test_fixedprefixed(self):
        infile = io.StringIO(textwrap.dedent("""\
            12345 First line
            67890 Second line
            Another line
            Short
            Final line
        """))
        fixedprefixed = logprefix.FixedPrefixedLog(infile, prefixlen=6)
        lines = list(iter(fixedprefixed.readline, ''))
        self.assertEqual([
            'First line\n',
            'Second line\n',
            'r line\n',
            '\n',
            'line\n'
        ], lines)

    def test_regexprefixed(self):
        infile = io.StringIO(textwrap.dedent("""\
            12345 First line
            67890 Second line
            1 Another line
            No match
            0000No space
            11111
            0 Final
        """))
        fixedprefixed = logprefix.RegexPrefixedLog(infile, regex=re.compile(r'^[0-9.]+ '))
        lines = list(iter(fixedprefixed.readline, ''))
        self.assertEqual([
            'First line\n',
            'Second line\n',
            'Another line\n',
            'No match\n',
            '0000No space\n',
            '11111\n',
            'Final\n'
        ], lines)

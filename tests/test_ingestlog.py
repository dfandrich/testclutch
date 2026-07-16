"""Test ingestlog."""

import unittest
from unittest.mock import Mock

from .context import testclutch  # noqa: F401

from testclutch.cli import ingestlog  # noqa: I100


class TestParseMeta(unittest.TestCase):
    """Test ingestlog.parse_meta."""

    def test_parse_meta(self):
        for a, b in [
                (['foo=bar'], {'foo': 'bar'}),
                (['first=1', 'second=2'], {'first': '1', 'second': '2'}),
                (['noequals'], {'noequals': ''}),
                (['with space=a'], {'with space': 'a'}),
                (['emptyvalue='], {'emptyvalue': ''}),
                (['no equals'], {'no equals': ''}),
                ([''], {'': ''}),
                ([], {}),
        ]:
            with self.subTest(a=a, b=b):
                args = Mock(meta=a)
                self.assertEqual(b, ingestlog.parse_meta(args))

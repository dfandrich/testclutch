"""Test ghaapi."""

import unittest

from .context import testclutch  # noqa: F401

from testclutch.ingest import ghaapi  # noqa: I100


class TestConvertTime(unittest.TestCase):
    """Test ghaapi.convert_time."""

    def test_convert_time(self):
        for text, timestamp in [
                ('2023-07-24T15:16:01.000-07:00', 1690236961.0),
                ('2023-07-24T22:03:10Z', 1690236190.0),
                ('2023-08-15T13:03:32.123Z', 1692104612.123),
        ]:
            with self.subTest(text=text, timestamp=timestamp):
                self.assertEqual(ghaapi.convert_time(text).timestamp(), timestamp)

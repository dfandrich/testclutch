"""Test curldailyinfo."""

import datetime
import unittest

from .context import testclutch  # noqa: F401
from .util import data_file

from testclutch.augment import curldailyinfo  # noqa: I100

DATADIR = 'data'


class TestCurlDailyInfo(unittest.TestCase):
    """Test curldailyinfo."""

    def setUp(self):
        super().setUp()
        self.maxDiff = 4000

    def test_dailyinfo(self):
        day_code, daily_time, commit = curldailyinfo.get_daily_info(
            data_file('curldailyinfo_commit.tar.xz'))
        self.assertEqual('20240805', day_code)
        self.assertEqual(datetime.datetime(2024, 8, 5, 0, 31, 1, tzinfo=datetime.timezone.utc),
                         daily_time)
        self.assertEqual('7b1444979094a365c82c665cce0e2ebc6b69467b', commit)

    def test_dailyinfo_nocommit(self):
        # tar ball missing commit file
        day_code, daily_time, commit = curldailyinfo.get_daily_info(
            data_file('curldailyinfo_basic.tar.xz'))
        self.assertEqual('20230801', day_code)
        self.assertEqual(datetime.datetime(2023, 8, 1, 0, 30, 18, tzinfo=datetime.timezone.utc),
                         daily_time)
        self.assertEqual('', commit)

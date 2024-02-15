import datetime
import os
import unittest

from .context import testclutch  # noqa: F401

from testclutch.augment import curldailyinfo  # noqa: I100

DATADIR = 'data'


class TestCurlDailyInfo(unittest.TestCase):
    def setUp(self):
        self.maxDiff = 4000

    def data_file(self, fn: str) -> str:
        return os.path.join(os.path.dirname(__file__), DATADIR, fn)

    def test_dailyinfo(self):
        day_code, daily_time, daily_title = curldailyinfo.get_daily_info(
            self.data_file('curldailyinfo_basic.tar.xz'))
        self.assertEqual('20230801', day_code)
        self.assertEqual(datetime.datetime(2023, 8, 1, 0, 30, 18, tzinfo=datetime.timezone.utc),
                         daily_time)
        self.assertEqual('curl: make %output{} in -w specify a file to write to', daily_title)


if __name__ == '__main__':
    unittest.main()

import unittest

from .context import testclutch  # noqa: F401

from testclutch.cli import metadatastats  # noqa: I100


class TestMetaDataStats(unittest.TestCase):
    def test_idify(self):
        self.assertEqual(metadatastats.idify('simple'), 'testsimple')
        self.assertEqual(metadatastats.idify('01234:567-89'), 'test01234:567-89')
        self.assertEqual(metadatastats.idify('with"quotes"'), 'testwith&quot;quotes&quot;')
        self.assertEqual(metadatastats.idify("invalid_chars&>#'"), 'testinvalid_chars____')

    def test_num_precision(self):
        self.assertEqual(metadatastats.num_precision(1.0, 1), 1)
        self.assertEqual(metadatastats.num_precision(1.0, 2), 2)
        self.assertEqual(metadatastats.num_precision(1.0, 3), 3)
        self.assertEqual(metadatastats.num_precision(2.718, 3), 2)
        self.assertEqual(metadatastats.num_precision(12345, 3), 0)
        self.assertEqual(metadatastats.num_precision(0.000005555, 3), 8)

    def test_try_integer(self):
        nums = ['98', '43', '77', '1', '1234567890', '56']
        self.assertEqual(
            sorted(nums, key=metadatastats._try_integer),
            ['1', '43', '56', '77', '98', '1234567890'])

        mixed = ['test50', '43', '77', 'notanint', '1234567890', '56', 'x']
        self.assertEqual(
            sorted(mixed, key=metadatastats._try_integer),
            ['43', '56', '77', '1234567890', 'notanint', 'test50', 'x'])

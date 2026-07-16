"""Test metadatastats."""

import os
import unittest
from unittest import mock

from .context import testclutch  # noqa: F401


class TestMetaDataStats(unittest.TestCase):
    """Test metadatastats."""

    def setUp(self):
        super().setUp()
        # Replace XDG_CONFIG_HOME to prevent the user's testclutchrc file from being loaded
        self.env_patcher = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': '/dev/null'})
        self.env_patcher.start()
        # Import the code to test only after XDG_CONFIG_HOME has been replaced
        global metadatastats
        from testclutch.cli import metadatastats

    def tearDown(self):
        self.env_patcher.stop()
        super().tearDown()

    def test_idify(self):
        self.assertEqual('testsimple', metadatastats.idify('simple'))
        self.assertEqual('test01234:567-89', metadatastats.idify('01234:567-89'))
        self.assertEqual('testwith&quot;quotes&quot;', metadatastats.idify('with"quotes"'))
        self.assertEqual('testinvalid_chars____', metadatastats.idify("invalid_chars&>#'"))

    def test_num_precision(self):
        self.assertEqual(1, metadatastats.num_precision(1.0, 1))
        self.assertEqual(2, metadatastats.num_precision(1.0, 2))
        self.assertEqual(3, metadatastats.num_precision(1.0, 3))
        self.assertEqual(2, metadatastats.num_precision(2.718, 3))
        self.assertEqual(0, metadatastats.num_precision(12345, 3))
        self.assertEqual(8, metadatastats.num_precision(0.000005555, 3))

    def test_try_integer(self):
        nums = ['98', '43', '77', '1', '1234567890', '56']
        self.assertEqual(
            ['1', '43', '56', '77', '98', '1234567890'],
            sorted(nums, key=metadatastats._try_integer))

        mixed = ['test50', '43', '77', 'notanint', '1234567890', '56', 'x']
        self.assertEqual(
            ['43', '56', '77', '1234567890', 'notanint', 'test50', 'x'],
            sorted(mixed, key=metadatastats._try_integer))

        mixed0 = ['0050', '043', '77', 'notanint', '1234567890', '000056', 'x', '00012']
        self.assertEqual(
            ['00012', '043', '0050', '000056', '77', '1234567890', 'notanint', 'x'],
            sorted(mixed0, key=metadatastats._try_integer))

    def test_MetadataAdjuster_split(self):
        adj = metadatastats.MetadataAdjuster({'testkey': r'::+', 'ignorekey': r' '}, {}, set({}))
        self.assertEqual(['Single:Value'], adj.split('testkey', 'Single:Value'))
        self.assertEqual(['Just Two', 'Values'], adj.split('testkey', 'Just Two::Values'))
        self.assertEqual(['Some', 'Values', 'Skipped', 'Blanks'],
                         adj.split('testkey', 'Some::Values::::Skipped::Blanks::'))
        self.assertEqual(['Not::Transformed'], adj.split('ignorekey', 'Not::Transformed'))

    def test_MetadataAdjuster_transform(self):
        adj = metadatastats.MetadataAdjuster(
            {},
            {'testkey': [(r'^changeme$', 'ChangeMe'), (r'^deleteme$', ''),
                         (r'rename([0-9]+)', r'NewNamed\1:')],
             'embedded': [(r'partial', 'practical'),
                          (r'act', 'play'),
                          (r'lay', 'place')],
             'ignorekey': [(r'.', 'XXX')]},
            set({}))
        self.assertEqual('unchanged', adj.transform('testkey', 'unchanged'))
        self.assertEqual('ChangeMe', adj.transform('testkey', 'changeme'))
        self.assertEqual('', adj.transform('testkey', 'deleteme'))
        self.assertEqual('IsANewNamed1234:', adj.transform('testkey', 'IsArename1234'))
        self.assertEqual('notrenamed', adj.transform('testkey', 'notrenamed'))
        self.assertEqual('imprpplaceical', adj.transform('embedded', 'impartial'))

    def test_MetadataAdjuster_adjust(self):
        adj = metadatastats.MetadataAdjuster(
            {'testkey': r'[ ,]', 'ignorekey': r' '},
            {'testkey': [(r'^changeme$', 'ChangeMe'), (r'^deleteme$', ''),
                         (r'rename([0-9]+)', r'NewNamed\1:')],
             'ignorekey': [(r'.', 'XXX')]},
            set({})
        )
        self.assertEqual(['a', 'bunch', 'of', 'values'], adj.adjust('testkey', 'a bunch,of values'))
        self.assertEqual(['ChangeMe', 'thenNewNamed99:me'],
                         adj.adjust('testkey', '  changeme deleteme,thenrename99me'))

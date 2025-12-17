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

        mixed0 = ['0050', '043', '77', 'notanint', '1234567890', '000056', 'x', '00012']
        self.assertEqual(
            sorted(mixed0, key=metadatastats._try_integer),
            ['00012', '043', '0050', '000056', '77', '1234567890', 'notanint', 'x'])

    def test_MetadataAdjuster_split(self):
        adj = metadatastats.MetadataAdjuster({'testkey': r'::+', 'ignorekey': r' '}, {}, set({}))
        self.assertEqual(adj.split('testkey', 'Single:Value'), ['Single:Value'])
        self.assertEqual(adj.split('testkey', 'Just Two::Values'), ['Just Two', 'Values'])
        self.assertEqual(adj.split('testkey', 'Some::Values::::Skipped::Blanks::'),
                         ['Some', 'Values', 'Skipped', 'Blanks'])
        self.assertEqual(adj.split('ignorekey', 'Not::Transformed'), ['Not::Transformed'])

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
        self.assertEqual(adj.transform('testkey', 'unchanged'), 'unchanged')
        self.assertEqual(adj.transform('testkey', 'changeme'), 'ChangeMe')
        self.assertEqual(adj.transform('testkey', 'deleteme'), '')
        self.assertEqual(adj.transform('testkey', 'IsArename1234'), 'IsANewNamed1234:')
        self.assertEqual(adj.transform('testkey', 'notrenamed'), 'notrenamed')
        self.assertEqual(adj.transform('embedded', 'impartial'), 'imprpplaceical')

    def test_MetadataAdjuster_adjust(self):
        adj = metadatastats.MetadataAdjuster(
            {'testkey': r'[ ,]', 'ignorekey': r' '},
            {'testkey': [(r'^changeme$', 'ChangeMe'), (r'^deleteme$', ''),
                         (r'rename([0-9]+)', r'NewNamed\1:')],
             'ignorekey': [(r'.', 'XXX')]},
            set({})
        )
        self.assertEqual(adj.adjust('testkey', 'a bunch,of values'), ['a', 'bunch', 'of', 'values'])
        self.assertEqual(adj.adjust('testkey', '  changeme deleteme,thenrename99me'),
                         ['ChangeMe', 'thenNewNamed99:me'])

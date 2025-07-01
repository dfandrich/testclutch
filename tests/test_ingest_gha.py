"""Test ingest.gha."""

import unittest
from unittest.mock import Mock

from .context import testclutch  # noqa: F401

from testclutch.ingest import gha  # noqa: I100


class TestSanitize(unittest.TestCase):
    """Test gha.sanitize_log_fn."""

    def test_sanitize_log_fn(self):
        ghi = gha.GithubIngestor('', '', '', Mock())
        for raw, sanitized in [
                ('simple_name',
                 'simple_name'),
                ('every-thing$ {passing}_through & (1,234.56@)',
                 'every-thing$ {passing}_through & (1,234.56@)'),
                ('slash must be /removed',
                 'slash must be removed'),
        ]:
            with self.subTest(raw=raw, sanitized=sanitized):
                self.assertEqual(ghi.sanitize_log_fn(raw), sanitized)

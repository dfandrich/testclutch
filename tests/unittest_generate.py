"""Define some unittest tests to generate sample logs.

Run this from the project root with one of the following to generate logs
to check Test Clutch's Python log parsers:
    python3 -m unittest discover -p 'unittest*' -v -b
    pytest -v tests/unittest_generate.py

This method runs the tests but generates less useful test names:
    python3 tests/unittest_generate.py -v -b
"""

import unittest


def function_test_succeeds():
    assert True, 'This test is designed to succeed'


def function_test_fails():
    assert not True, 'This test is designed to fail'


class TestGenerateLogs(unittest.TestCase):
    """Define a set of tests to generate test logs."""

    def test_success(self):
        self.assertEqual(1, 1)

    def test_failure(self):
        self.assertEqual(1, 0)

    def test_subtests_success(self):
        for n in [0, 1, 2, 3, 4]:
            with self.subTest(n=n):
                self.assertGreater(99, n)

    def test_subtests_failure(self):
        for n in [0, 1, 2, 3, 4]:
            with self.subTest(n=n):
                self.assertGreater(3, n)

    def test_unexpected_exception(self):
        raise RuntimeError('Exception was raised')

    @unittest.skip('skipped test')
    def test_skipped(self):
        self.assertEqual(1, 0)

    @unittest.expectedFailure
    def test_expected_failure(self):
        self.assertEqual(1, 0)

    @unittest.expectedFailure
    def test_expected_failure_but_success(self):
        self.assertEqual(1, 1)


@unittest.skip('skipped class')
class TestSkippedClass(unittest.TestCase):
    """Define a set of tests to be entirely skipped."""

    def test_success_but_skipped(self):
        self.assertEqual(1, 1)

    def test_failure_but_skipped(self):
        self.assertEqual(1, 0)


class TestFunctionSuccess(unittest.FunctionTestCase):
    """A test case using FunctionTestCase that succeeds."""
    def __init__(self, _):
        super().__init__(function_test_succeeds)


class TestFunctionFailure(unittest.FunctionTestCase):
    """A test case using FunctionTestCase that fails."""
    def __init__(self, _):
        super().__init__(function_test_fails, description='A function test that fails')


if __name__ == '__main__':
    unittest.main()

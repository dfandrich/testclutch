import time
import unittest

from .context import testclutch  # noqa: F401

from testclutch import netreq  # noqa: I100


class RaiseFirst:
    """Raise an exception on the first call, then succeed on subsequent calls"""
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        if self.count == 1:
            raise RuntimeError('First call')
        return self.count


class TestNetreq(unittest.TestCase):
    def test_retry_on_exception(self):
        # no exception
        result = netreq.retry_on_exception(lambda: 'OK', RuntimeError)
        assert result == 'OK'

        # call always raises exception
        with self.assertRaises(ZeroDivisionError):
            result = netreq.retry_on_exception(lambda: 1 / 0, ZeroDivisionError,
                                               retries=2, delay=0.1)

        # call always raises the wrong exception
        with self.assertRaises(ZeroDivisionError):
            result = netreq.retry_on_exception(lambda: 1 / 0, RuntimeError,
                                               retries=2, delay=0.1)

        # raise a single exception, then succeed
        start = time.time()
        result = netreq.retry_on_exception(RaiseFirst(), RuntimeError, retries=100, delay=0.1)
        assert result == 2
        assert time.time() - start < 9, 'too many retries'

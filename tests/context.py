"""More easily configure the test suite to test uninstalled modules
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import testclutch  # noqa: F401,E402

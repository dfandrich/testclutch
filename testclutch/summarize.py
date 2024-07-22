"""Debug program to summarize ingested logs"""

import contextlib
import io
from typing import List, Union

from testclutch.logdef import TestCases
from testclutch.testcasedef import TestResult


def show_totals(testcases: TestCases, details: bool = False):
    print(''.join(summarize_totals(testcases, details)))


def summarize_totals(testcases: TestCases, details: bool = False) -> List[str]:
    f = io.StringIO()
    print("OK:", len([1 for x in testcases if x.result == TestResult.PASS]), file=f)
    print("FAILED:", len([1 for x in testcases if x.result == TestResult.FAIL]), file=f)
    print("SKIPPED:", len([1 for x in testcases if x.result == TestResult.SKIP]), file=f)
    if match := [1 for x in testcases if x.result == TestResult.UNKNOWN]:
        print("UNKNOWN:", len(match), file=f)
    if match := [1 for x in testcases if x.result == TestResult.TIMEOUT]:
        print("TIMEDOUT:", len(match), file=f)
    if match := [1 for x in testcases if x.result == TestResult.FAILIGNORE]:
        print("FAILIGNORED:", len(match), file=f)
    if match := [1 for x in testcases if x.result == TestResult.ABORT]:
        print("ABORTED:", len(match), file=f)
    if match := [1 for x in testcases if x.result == TestResult.ERROR]:
        print("ERRORED:", len(match), file=f)
    if match := [1 for x in testcases if x.result > TestResult.LAST]:
        print("???:", len(match), file=f)
    print("TOTAL:", len(testcases), file=f)
    if details:
        # Display interesting test results
        for test in testcases:
            if test.result not in frozenset((TestResult.PASS, TestResult.SKIP)):
                print(test, file=f)
    f.seek(0)
    return f.readlines()


def try_integer(val: str) -> Union[int, str]:
    """Try to convert the value to an integer, but return string if it cannot

    Use as a sort key function to sort numeric test names by numeric value and string
    test names alphabetically.  When sorting, members of the list must be either all ints or all
    strings (not mixed). A more general alternative would be natsort.natsorted()
    """
    with contextlib.suppress(ValueError):
        return int(val)
    return val

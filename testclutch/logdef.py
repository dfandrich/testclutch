"""Type definitions of parsed logs."""

from dataclasses import dataclass
from typing import Union

from testclutch.testcasedef import TestResult


@dataclass
class SingleTestFinding:
    """Class to hold the result of a single run of a single test."""

    name: str           # test name
    result: TestResult  # test result
    reason: str         # reason for result (if any)
    duration: int       # test duration in microseconds


TestCases = list[SingleTestFinding]
TestMetaStr = dict[str, str]  # raw data from DB
TestMeta = dict[str, Union[str, int]]  # data to be stored into DB
ParsedLog = tuple[TestMeta, TestCases]

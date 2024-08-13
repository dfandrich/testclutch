"""Type definitions of parsed logs
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

from testclutch.testcasedef import TestResult


@dataclass
class SingleTestFinding:
    name: str           # test name
    result: TestResult  # test result
    reason: str         # reason for result (if any)
    duration: int       # test duration in microseconds


TestCases = List[SingleTestFinding]
TestMetaStr = Dict[str, str]  # raw data from DB
TestMeta = Dict[str, Union[str, int]]  # data to be stored into DB
ParsedLog = Tuple[TestMeta, TestCases]

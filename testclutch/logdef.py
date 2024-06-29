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
TestMeta = Dict[str, Union[str, int]]
ParsedLog = Tuple[TestMeta, TestCases]

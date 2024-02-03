"""Type definitions of parsed logs
"""

from typing import Dict, List, Tuple, Union


# TODO: use dataclasses for this
TestCases = List[Tuple[str, int, str, int]]
TestMeta = Dict[str, Union[str, int]]
ParsedLog = Tuple[TestMeta, TestCases]

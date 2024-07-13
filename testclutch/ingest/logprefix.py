"""Class to remove a prefix from each log line
"""

import re
from typing import TextIO


class FakeDerivedTextIOWithArgs(TextIO):
    """This class is only used for typing hints for duck typing TextIO, no in code

    We don't want to actually derive from TextIO in the classes that need this because then calls to
    the object's members won't be caught by the __getattr__ function and the wrong member will be
    accessed.
    """
    def __init__(self, *a1, **args):
        pass

    def __call__(self, *a2, **args) -> 'FakeDerivedTextIOWithArgs':
        "For some reason, pytype doesn't see that constructing this object actually uses __init__"
        return self


# pytype: disable=annotation-type-mismatch
class FixedPrefixedLog:  # type: FakeDerivedTextIOWithArgs
    # pytype: enable=annotation-type-mismatch
    """Remove the timestamp at the head of every log line

    Args:
        prefixlen - length of prefix to remove
    """
    def __init__(self, f: TextIO, prefixlen: int):
        self.file_obj = f
        self.prefixlen = prefixlen

    def __getattr__(self, attr: str):
        return getattr(self.file_obj, attr)

    def readline(self, size: int = -1):
        l = self.file_obj.readline(size)
        if l:
            l = l[self.prefixlen:]
        return l


# pytype: disable=annotation-type-mismatch
class RegexPrefixedLog:  # type: FakeDerivedTextIOWithArgs
    # pytype: enable=annotation-type-mismatch
    """TextIOWrapper that removes a matching regex at the head of every log line

    Lines that don't match are sent through unchanged.
    """
    def __init__(self, f: TextIO, regex: re.Pattern):
        self.file_obj = f
        self.regex = regex

    def __getattr__(self, attr: str):
        return getattr(self.file_obj, attr)

    def readline(self, size: int = -1):
        l = self.file_obj.readline(size)
        if l:
            # Unfortunately, some log files have timestamps and some don't. It's probably something
            # to do with embedded newlines in log messages, but I can't think of a more accurate way
            # to remove them than with a regular expression. This will erroneously match "extended"
            # log files that happen to include something that looks like a timestamp, but since
            # these extended lines almost never happen in the first place (so far it seems only
            # those using cross-platform-actions/action), this isn't a big concern.
            l = self.regex.sub('', l)
        return l

"""Class to remove a prefix from each log line."""

import re

from testclutch.filedef import TextIOReadline


class FixedPrefixedLog:
    """Remove the timestamp at the head of every log line.

    Args:
        prefixlen - length of prefix to remove
    """
    def __init__(self, f: TextIOReadline, prefixlen: int):
        self.file_obj = f
        self.prefixlen = prefixlen

    def __getattr__(self, attr: str):
        """Pass any other references to the file object."""
        return getattr(self.file_obj, attr)

    def readline(self, size: int = -1) -> str:
        l = self.file_obj.readline(size)
        if l:
            origl = l
            l = l[self.prefixlen:]
            if not l and origl.endswith('\n'):
                # If the line is too short but isn't the last one, return an empty line
                return '\n'

        return l

    def seek(self, offset: int, whence: int = 0) -> int:
        """Satisfy pytype, even though the __getattr__ actually does the same thing."""
        return self.file_obj.seek(offset, whence)


class RegexPrefixedLog:
    """TextIOWrapper that removes a matching regex at the head of every log line.

    Lines that don't match are sent through unchanged.
    """
    def __init__(self, f: TextIOReadline, regex: re.Pattern):
        self.file_obj = f
        self.regex = regex

    def __getattr__(self, attr: str):
        """Pass any other references to the file object."""
        return getattr(self.file_obj, attr)

    def readline(self, size: int = -1) -> str:
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

    def seek(self, offset: int, whence: int = 0) -> int:
        """Satisfy pytype, even though the __getattr__ actually does the same thing."""
        return self.file_obj.seek(offset, whence)

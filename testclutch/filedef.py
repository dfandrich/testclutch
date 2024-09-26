"""Type definitions for files."""

import io
from typing import Protocol


class TextIOReadline(Protocol):
    """A typing.TextIO class that provides only readline and seek methods."""

    def readline(self, size: int = -1) -> str:
        raise io.UnsupportedOperation

    def seek(self, offset: int, whence: int = 0) -> int:
        raise io.UnsupportedOperation

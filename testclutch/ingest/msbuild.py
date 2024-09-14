"""Class to handle builds created by MSBuild
"""

from testclutch.filedef import TextIOReadline


class MsBuildLog:
    """Remove the indentation that msbuild adds to child output

    This issue mentions the indentation that is done and implies that there is no way to
    stop it (as of 2021, anyway):
    https://github.com/dotnet/msbuild/issues/6614#issuecomment-866447382

    This has been tested with msbuild ver. 4.8.3761.0, 15.9.21+g9802d43bc3 for .NET and
    17.7.2+d6990bcfa for .NET
    """
    def __init__(self, f: TextIOReadline):
        self.file_obj = f
        self.in_msbuild = False

    def __getattr__(self, attr: str):
        """Send everything else to the embedded file"""
        return getattr(self.file_obj, attr)

    def seek(self, offset: int, whence: int = 0):
        """Capture to seek to reset the state"""
        if offset == 0 and whence < 16:
            # Stream is starting again from (near) the beginning
            self.in_msbuild = False
        return self.file_obj.seek(offset, whence)

    def readline(self, size: int = -1) -> str:
        l = self.file_obj.readline(size)
        if l.startswith('Microsoft (R) Build Engine') or l.startswith('MSBuild version '):
            # Start of indented section
            self.in_msbuild = True
        elif self.in_msbuild:
            # In indented section
            if l.startswith('  '):
                # Strip off indentation
                l = l[2:]
            elif l.startswith('CUSTOMBUILD : warning :'):
                # This must be some kind of special msbuild escaping going on
                l = 'Warning' + l[22:]

            # Let through special cases: two strings that are part of the headers
            # that begin the indented section, a completely empty line, and CUSTOMBUILD.
            # Anything else not beginning with two spaces is the sign we've exited msbuild.
            #
            # NOTE: this is not a completely reliable indication. I don't know if CUSTOMBUILD
            # is the only weird string to suddenly show up in the middle. This means that
            # once we detect msbuild, we can't reliable switch out of it; there seems to be no
            # magic string shown afterward, and there are cases where nonindented strings can
            # appear in the middle. So, just leave it in dedenting mode once we detect msbuild
            # is in use; it's highly likely that any log we're interested in in this case will
            # be run under msbuild so it will work just fine.
            #  elif (not l.startswith('[Microsoft .NET Framework')
            #      and not l.startswith('Copyright (C) Microsoft Corporation')
            #      and l.rstrip('\r\n')):
            #      self.in_msbuild = False
        return l

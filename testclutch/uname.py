"""Parses uname strings."""

# flake8: noqa: C901, SIM114

import re

from testclutch.logdef import TestMetaStr

# Match a valid year since Linux was created, also 1970 in case of time issue
LINUX_YEAR_RE = re.compile(r'^(20\d\d)|(199\d)|(1970)$')


def parse_uname(uname: str) -> TestMetaStr:
    """Parse the output of 'uname -a' from many OSes for relevant data."""
    meta = {}

    # This one treats multiple spaces as one separator (needed on Linux, NetBSD
    # and Darwin because they can have an extra space before a date)
    sysparts = uname.split()
    # This one treats multiple spaces as separators of empty items (needed on
    # FreeBSD at least because its hostname can be empty)
    syspartsblanks = uname.split(sep=' ')

    if syspartsblanks[0]:
        meta['systemos'] = syspartsblanks[0]
    if len(syspartsblanks) < 3:
        # This needs at least 3 parts to obtain any more details, which a real uname should provide
        return meta

    # hostname can be blank
    if syspartsblanks[1]:
        meta['systemhost'] = syspartsblanks[1]
    meta['systemosver'] = syspartsblanks[2]

    # We can get more info on some OSes
    if meta['systemos'] == 'Linux' and len(syspartsblanks) >= 12:
        for i in range(9, len(syspartsblanks) - 2):
            if LINUX_YEAR_RE.match(syspartsblanks[i]):
                # arch is found immediately after the kernel build year
                meta['arch'] = syspartsblanks[i + 1]
                break
    elif meta['systemos'] == 'FreeBSD' and len(syspartsblanks) in {8, 15}:
        meta['arch'] = syspartsblanks[-1]
    elif meta['systemos'] == 'FreeBSD' and len(sysparts) in {8, 14, 15}:
        meta['arch'] = sysparts[-1]
    elif meta['systemos'] in {'Darwin', 'NetBSD'} and len(sysparts) == 15:  # Darwin is macOS
        meta['arch'] = sysparts[-1]
    elif meta['systemos'] == 'NetBSD' and len(sysparts) == 14 and 'systemhost' not in meta:
        # If the host field is blank, it shifts all the other parts down
        # one. The other systems use syspartsblank to avoid this problem,
        # but NetBSD embeds a date in its uname -a which can likely
        # contain an extra space which would cause THAT workaround to
        # fail.
        meta['arch'] = sysparts[-1]
    elif meta['systemos'] in {'OpenBSD', 'Redox', 'SerenityOS'} and len(syspartsblanks) == 5:
        meta['arch'] = syspartsblanks[-1]
    elif meta['systemos'] == 'SunOS' and len(syspartsblanks) in {8, 7}:  # Solaris, OmniOS
        meta['arch'] = syspartsblanks[5]
    elif (meta['systemos'].startswith('MSYS_NT')
          or meta['systemos'].startswith('MINGW32_NT')
          or meta['systemos'].startswith('MINGW64_NT')
          or meta['systemos'].startswith('CYGWIN_NT')) and len(sysparts) == 8:
        meta['arch'] = sysparts[-2]
    elif (meta['systemos'].startswith('MSYS_NT')
          or meta['systemos'].startswith('MINGW32_NT')
          or meta['systemos'].startswith('MINGW64_NT')
          or meta['systemos'].startswith('CYGWIN_NT')) and len(sysparts) == 7:
        # This version is missing the time zone
        meta['arch'] = sysparts[-2]
    elif meta['systemos'] == 'AIX' and len(sysparts) == 5:
        # systemosver as set above is just the minor release number
        meta['systemosver'] = f'{sysparts[3]}.{sysparts[2]}'
    elif meta['systemos'] == 'Haiku' and len(syspartsblanks) == 11:
        meta['arch'] = syspartsblanks[-2]
        # TODO: OS revision is in syspartsblanks[3], which perhaps should be appended to
        # syspartsblanks[2] and go into meta['systemosver']. Take a look at how it presents
        # itself once it comes out of beta.
    elif meta['systemos'] == 'Minix' and len(syspartsblanks) == 7:
        meta['arch'] = syspartsblanks[-1]
    elif meta['systemos'] == 'Fiwix' and len(syspartsblanks) == 11:
        meta['arch'] = syspartsblanks[-2]
    elif meta['systemos'] == 'syllable' and len(syspartsblanks) == 6:
        # systemosver as set above is just the minor release number
        meta['systemosver'] = f'{sysparts[3]}.{sysparts[2]}'
        meta['arch'] = syspartsblanks[-2]
    elif meta['systemos'] == 'NuttX' and len(sysparts) == 9:
        meta['arch'] = sysparts[-2]
        # This uname swaps the normal host and version fields
        meta['systemhost'] = syspartsblanks[2]
        meta['systemosver'] = syspartsblanks[1]
    elif meta['systemos'] == 'Zephyr' and len(sysparts) == 10:
        meta['arch'] = sysparts[-2]
    elif meta['systemos'] == 'QNX' and len(sysparts) == 6:
        meta['arch'] = sysparts[-1]
    elif meta['systemos'] == 'ELKS' and len(sysparts) == 12:
        meta['arch'] = sysparts[-1]
    elif meta['systemos'] == 'Sortix' and len(sysparts) >= 11:
        meta['arch'] = sysparts[-4]
    elif meta['systemos'] == 'Tilck' and len(sysparts) == 6:
        meta['arch'] = sysparts[-2]

    return meta

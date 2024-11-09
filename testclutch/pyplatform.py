"""Parse Python platform strings."""

import re

from testclutch.logdef import TestMetaStr  # noqa: F401


# Python platform parsing regexes
PLAT_LINUX_RE = re.compile(r'^Linux-(?P<release>.+?)(-(?P<mach>[^-]+))?-(?P<proc>[^-]+)-with(-(?P<libcnamever>.+))?$')
PLAT_WINDOWS_RE = re.compile(r'^Windows-(?P<release>\d+)-(?P<version>[0-9.]+)(-(?P<csd>[^-]+))?$')
PLAT_JAVA_RE = re.compile(r'^Java-(.*?)-on-(.*)-(?P<proc>[^-]+)$')
PLAT_DEFAULT_RE = re.compile(r'^(?P<system>[^-]+)-(?P<release>.+?)(-(?P<mach>[^-]+))?-(?P<proc>[^-]+)-((?P<bits>1?\d\d)bit)(-(?P<linkage>[^-]+))?$')


def parse_platform(platform: str) -> TestMetaStr:
    """Parse the output of Python's 'platform.platform()'.

    This is explicitly not intended for parsing, but that's the easiest string to obtain in pytest
    output. This means it will be a bit brittle against future changes.
    """
    meta = {}

    # There are four formats of platform strings as of Python 3.13, so find which parser to use
    platparts = platform.split('-', maxsplit=1)
    meta['systemos'] = platparts[0]
    # TODO: Adapt to Python 3.13 which is supposed to return Android instead of Linux when relevant
    if (platparts[0] == 'Linux') and (r := PLAT_LINUX_RE.search(platform)):
        meta['systemosver'] = r.group('release')
        meta['arch'] = r.group('proc')
        # Note that mach can be miscategorized as the part of release if the actual mach is blank,
        # which happens surprisingly often. For that reason and because mach isn't that interesting,
        # don't bother including it in the metadata.

    elif platparts[0] == 'Windows' and (r := PLAT_WINDOWS_RE.search(platform)):
        meta['systemosver'] = r.group('version')

    elif platparts[0] == 'Java' and (r := PLAT_JAVA_RE.search(platform)):
        # The Java version of the platform string combines too much information to parse
        # reliably. Also, there's not much incentive to attempt to do so at the time of this writing
        # because Jython is only available for Python 2 code and so there is likely not much of it
        # in actual use. The simple parser used here just looks for one of two forms of the Java
        # string and extracts the architecture out of it, which is fairly unambiguously obtained.
        meta['arch'] = r.group('proc')

    elif r := PLAT_DEFAULT_RE.search(platform):
        meta['systemosver'] = r.group('release')
        meta['arch'] = r.group('proc')
        meta['archbits'] = r.group('bits')

    return meta

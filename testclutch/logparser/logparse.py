"""Parse test logs
"""

import importlib
import logging
import sys
from typing import TextIO

from testclutch import config
from testclutch import summarize
from testclutch.logdef import ParsedLog


def parse_log_file(f: TextIO) -> ParsedLog:
    """Tries one or more methods to parse a log file and returns the first one that works

    Returns: tuple of dict with metadata, list of tests
      If the test could not be parsed, the dict will be empty
    """
    # Get a list of functions to use to parse
    log_parsers = config.get('log_parsers')
    module_functions = [tuple(config.expandstr(p).rsplit('.', 1)) for p in log_parsers]
    errors = [m[0] for m in module_functions if len(m) != 2]
    if errors:
        for err in errors:
            logging.error('Invalid log_parsers entry %s; must have at least one dot', err)

    # Try all functions in order until one returns a result
    for mod, func in module_functions:
        logging.debug('Calling %s.%s()', mod, func)
        module = importlib.import_module(mod)
        meta, testcases = module.__dict__.get(func)(f)
        if testcases:
            break
        f.seek(0)

    return meta, testcases


# Debug interface
def main():
    logging.basicConfig(level=logging.DEBUG, format='%(levelno)s %(filename)s: %(message)s',)
    meta, testcases = parse_log_file(sys.stdin)
    for n, v in meta.items():
        print(f'{n}={v}')
    summarize.show_totals(testcases, details=True)


if __name__ == '__main__':
    main()

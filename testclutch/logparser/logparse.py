"""Parse test logs."""

import importlib
import logging
import sys
from typing import Iterable

from testclutch import config
from testclutch import summarize
from testclutch.filedef import TextIOReadline
from testclutch.logdef import ParsedLog


FULL_TEST_OUTPUT = False


def parse_log_files(f: TextIOReadline) -> Iterable[ParsedLog]:
    """Tries one or more methods to parse a log file and returns a generator that returns them all.

    Returns: For each parsed log, tuple of dict with metadata, list of tests
    """
    # Get a list of functions to use to parse
    log_parsers = config.get('log_parsers')
    module_functions = [tuple(config.expandstr(p).rsplit('.', 1)) for p in log_parsers]
    errors = [m[0] for m in module_functions if len(m) != 2]
    if errors:
        for err in errors:
            logging.error('Invalid log_parsers entry %s; must have at least one dot', err)

    # Try all functions in order until (at least) one returns a result
    found = False
    for mod, func in module_functions:
        logging.debug('Calling %s.%s()', mod, func)
        module = importlib.import_module(mod)
        meta, testcases = module.__dict__.get(func)(f)
        if testcases:
            # Data is only valid if at least one test case was found
            yield meta, testcases
            found = True
            if config.get('log_parse_single'):
                # Stop searching for more log files after the first one is found
                break
        f.seek(0)

    if not found:
        logging.debug('No tests could be found in the log file')


# Debug interface
def main():
    logging.basicConfig(level=logging.DEBUG, format='%(levelno)s %(filename)s: %(message)s',)
    for meta, testcases in parse_log_files(sys.stdin):
        for n, v in meta.items():
            print(f'{n}={v}')
        summarize.show_totals(testcases, details=True)
        if FULL_TEST_OUTPUT:
            for test in testcases:
                print(test.name)


if __name__ == '__main__':
    main()

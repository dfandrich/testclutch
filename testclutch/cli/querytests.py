"""Query database of tests
"""

import logging
import re
import sys

from testclutch import db
from testclutch import summarize


NVO_RE = re.compile(r'^([^<>=!]+)(=|<>|!=|<=|>=|<|>)(.*)$')


def main():
    logging.basicConfig(level=logging.INFO, format='%(filename)s: %(message)s',)
    ds = db.Datastore()
    ds.connect()

    showtests = False
    if len(sys.argv) > 1:
        argn = 1
        if sys.argv[argn] == '-t':
            showtests = True
            argn += 1
            if len(sys.argv) <= argn:
                logging.error('Missing match query')
                sys.exit(1)

        # Search for logs matching metadata
        # e.g. runid=1234567, runtestsduration>555000000
        val = NVO_RE.search(sys.argv[argn])
        if not val:
            logging.error('Invalid match query: %s', sys.argv[argn])
            sys.exit(1)

        rows = ds.select_meta_test_runs(val.group(1), val.group(2), val.group(3))

    else:
        # Show all logs
        rows = ds.select_all_test_runs()

    for row in rows:
        print(row[0], row[1])
        meta = row[2]
        for n, v in meta.items():
            print(f'{n}={v}')
        testcases = ds.select_test_results(row[0])
        summarize.show_totals(testcases)
        if showtests:
            testcases.sort(key=lambda x: summarize.try_integer(x[0]))
            for t in testcases:
                print(t)
        print()

    ds.close()
    print(f'{len(rows)} matching logs')


if __name__ == '__main__':
    main()

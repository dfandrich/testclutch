"""Database operations
"""


import datetime
import logging
import sqlite3
from typing import Dict, List, Optional, Sequence, Tuple

from testclutch import config
from testclutch.gitdef import CommitInfo
from testclutch.logdef import TestCases, TestMeta


# Timeout for database writes. Needed to turn a concurrent write error into a retry.
DB_TIMEOUT = 600

# Make this available transparently to users
IntegrityError = sqlite3.IntegrityError

# testid, rowtime, metadict
TestRunRow = Sequence[Tuple[int, datetime.datetime, TestMeta]]


# TODO: make this a context manager
class Datastore:
    def __init__(self, filename: Optional[str] = None):
        if not filename:
            filename = config.expand('database_path')
        self.filename = filename
        self.db = None   # type: Optional[sqlite3.Connection]
        self.cur = None  # type: Optional[sqlite3.Cursor]

    def connect(self):
        """Opens an existing DB or creates a new one"""
        try:
            self.db = sqlite3.connect(self.filename, timeout=DB_TIMEOUT)
        except sqlite3.OperationalError:
            logging.error(f'Cannot open or create database (permission? missing dir?): {self.filename}')
            raise

        self.cur = self.db.cursor()
        # Use WAL mode to allow multiple concurrent readers/writers
        self.cur.execute("PRAGMA journal_mode=WAL")
        if self.cur.fetchone()[0] != 'wal':
            logging.warning("Could not put DB into WAL mode")
        try:
            # See if table exists
            self.cur.execute("SELECT 1 FROM testruns LIMIT 1")
        except sqlite3.OperationalError:
            logging.warning("Creating new DB")
            self.create_new_db()
        self.cur.execute("PRAGMA foreign_keys = ON")
        self.cur.fetchall()
        self.db.commit()
        self.cur.execute("PRAGMA foreign_keys")

    def close(self):
        self.cur.close()
        self.db.close()

    def create_new_db(self):
        logging.info("Creating new database")
        # One per test run
        self.cur.execute("CREATE TABLE testruns (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "time INTEGER, repo TEXT NOT NULL, origin TEXT NOT NULL, "
                         "account TEXT, runid TEXT NOT NULL, "
                         "uniquejobname TEXT NOT NULL, ingesttime INTEGER, "
                         "UNIQUE (repo, origin, account, runid, uniquejobname))"
                         )
        self.cur.execute("CREATE INDEX testruns_index ON testruns (time)")
        # 0..n per test run
        self.cur.execute("CREATE TABLE testrunmeta(id INTEGER, name TEXT, value TEXT, "
                         "FOREIGN KEY (id) REFERENCES testruns (id) "
                         "ON UPDATE RESTRICT "
                         "ON DELETE RESTRICT)")
        self.cur.execute("CREATE INDEX testrunmeta_index ON testrunmeta (id, name, value)")
        # 0..n per test run
        # testid is the test number or identifier
        # result is 0: unknown, 1 success, 2 failed, 3 skipped, etc. (see TestResult)
        # resulttext is an optional textual description of the failure
        # runtime is the time it took to run the test in microsec
        self.cur.execute("CREATE TABLE testresults(id INTEGER, testid TEXT, result INTEGER, "
                         "resulttext TEXT, runtime INTEGER, "
                         "FOREIGN KEY (id) REFERENCES testruns (id) "
                         "ON UPDATE RESTRICT "
                         "ON DELETE RESTRICT)")
        self.cur.execute("CREATE INDEX testresults_index ON testresults (id)")

        self.cur.execute("CREATE TABLE commitinfo (commithash TEXT NOT NULL PRIMARY KEY, "
                         "prevhash TEXT, "
                         "repo TEXT NOT NULL, branch TEXT NOT NULL, committime INTEGER, "
                         "committeremail TEXT NOT NULL, authoremail TEXT NOT NULL, title TEXT)")
        self.cur.execute("CREATE INDEX commitinfo_index ON commitinfo "
                         "(commithash, prevhash, committime, repo, branch)")
        # TODO: create table to perform email->name mappings UNIQUE (repo, email)
        self.db.commit()

    def store_test_meta(self, recid: int, meta: Dict[str, str]):
        for k, v in meta.items():
            self.cur.execute("INSERT INTO testrunmeta VALUES (?, ?, ?)", (recid, k, v))
        self.db.commit()

    def store_test_run(self, meta: Dict[str, str], testresults: TestCases):
        index_time = (meta['runtriggertime'] if 'runtriggertime' in meta else
                      meta['runstarttime'] if 'runstarttime' in meta else meta['runfinishtime'])
        repo = meta['checkrepo']
        origin = meta['origin']
        # Sqlite3 doesn't enforce UNIQUE if this is None (a.k.a. NULL), only ''
        # See https://sqlite.org/faq.html#q26
        account = meta['account'] if 'account' in meta else ''
        runid = meta['runid']
        uniquejobname = meta['uniquejobname']
        self.cur.execute("INSERT INTO testruns (time, repo, origin, account, runid, uniquejobname, "
                         "ingesttime) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (index_time, repo, origin, account, runid, uniquejobname,
                          int(datetime.datetime.now().timestamp())))
        recid = self.cur.execute(
            "SELECT id FROM testruns WHERE rowid = ?", (self.cur.lastrowid, )).fetchone()[0]
        self.store_test_meta(recid, meta)
        for row in testresults:
            self.cur.execute("INSERT INTO testresults VALUES (?, ?, ?, ?, ?)", (recid, *row))
        self.db.commit()

    def collect_meta(self, testid: int) -> TestMeta:
        metacur = self.db.cursor()
        meta = metacur.execute("SELECT name, value FROM testrunmeta WHERE id = ?", (testid, ))
        metadict = {}
        # Collect over test run metadata items for one test run
        while metavalues := meta.fetchmany():
            for n, v in metavalues:
                metadict[n] = v

        return metadict

    def _collect_row(self, runs: sqlite3.dbapi2.Cursor) -> TestRunRow:
        """Collect test runs"""
        results = []
        while rows := runs.fetchmany():
            for row in rows:
                metadict = self.collect_meta(row[0])
                results.append(
                    (row[0],
                     datetime.datetime.fromtimestamp(row[1]).astimezone(datetime.timezone.utc),
                     metadict))
        return results

    def select_all_test_runs(self) -> TestRunRow:
        """Returns a list of all test runs"""
        runs = self.cur.execute("SELECT id, time FROM testruns")
        return self._collect_row(runs)

    def select_meta_test_runs(self, name: str, op: str, value: str) -> TestRunRow:
        "Returns the tests matching a given piece of metadata"
        VALID_OPERATORS = frozenset(("=", "<", ">", "<=", ">=", "<>", "!="))
        if op not in VALID_OPERATORS:
            logging.error("Invalid operator %s", op)
            return []
        logging.debug("testrunmeta.name = %s AND value %s %s", name, op, value)
        runs = self.cur.execute("SELECT testruns.id, time FROM testrunmeta "
                                "INNER JOIN testruns ON testruns.id=testrunmeta.id "
                                f"WHERE testrunmeta.name = ? AND value {op} ?", (name, value))
        return self._collect_row(runs)

    def select_test_results(self, testid: int) -> List[Tuple[str, int, str, int]]:
        "Returns the test results for a given test run"
        res = self.cur.execute("SELECT testid, result, resulttext, runtime FROM testresults "
                               "WHERE id = ?", (testid,))
        results = []
        # Collect test case results
        while rows := res.fetchmany():
            results.extend(rows)
        return results

#    def check_test_existence_UNUSED(self, meta: TestMeta) -> bool:
#        """Check if a test log has already been stored
#
#        This is only useful for origins that 1) can save a round-trip for a
#        request early, and 2) have enough information to uniquely define a test
#        without that round trip (excluding the test logs themselves, since they
#        will be cached so won't save anything). It's not clear if this is the
#        case for any origins right now.
#        """
#        repo = meta['checkrepo']
#        origin = meta['origin']
#        # Sqlite3 doesn't enforce UNIQUE if this is None (a.k.a. NULL), only ''
#        # See https://sqlite.org/faq.html#q26
#        account = meta['account'] if 'account' in meta else ''
#        runid = meta['runid']
#        uniquejobname = meta['uniquejobname']
#        # TODO: COMPLETE THIS IF IT MAKES SENSE. Right now, writes are unconditional
#        # and duplicate writes just raise IntegrityError which is ignored

    def select_rec_id(self, meta: Dict[str, str]) -> Optional[int]:
        "Return the record ID matching a given test run"
        repo = meta['checkrepo']
        origin = meta['origin']
        account = meta['account'] if 'account' in meta else ''
        runid = meta['runid']
        uniquejobname = meta['uniquejobname']
        res = self.cur.execute(
            "SELECT id FROM testruns WHERE "
            "repo = ? AND origin = ? AND account = ? AND runid = ? AND uniquejobname = ?",
            (repo, origin, account, runid, uniquejobname))
        ids = res.fetchall()
        if len(ids) != 1:
            return None
        return ids[0][0]

    def delete_test_run(self, rec_id: int):
        "Delete a test run and all its metadata, by record ID"
        # Delete in the right order to avoid failing FOREIGN KEY constraints
        self.cur.execute("DELETE FROM testrunmeta WHERE id=?", (rec_id, ))
        self.cur.execute("DELETE FROM testresults WHERE id=?", (rec_id, ))
        self.cur.execute("DELETE FROM testruns WHERE id=?", (rec_id, ))
        self.db.commit()

    def store_commit_info(self, repo: str, branch: str, info: CommitInfo):
        "Store information about a git commit in the repo"
        self.cur.execute("INSERT INTO commitinfo VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (info.commit_hash, info.prev_hash, repo, branch, info.commit_time,
                          info.committer_email, info.author_email, info.title))
        self.db.commit()

    def select_commit_before_time(self, repo: str, branch: str, since: int, num: int) -> List:
        "Find the commits just before a given moment in time"
        res = self.cur.execute("SELECT commithash, committime, title, committeremail, authoremail "
                               "FROM commitinfo WHERE repo = ? AND branch = ? AND committime <= ? "
                               "ORDER BY committime DESC LIMIT ?",
                               (repo, branch, since, num))
        return res.fetchall()

    def select_all_commit_after_commit(self, repo: str, branch: str, commit: str
                                       ) -> List[CommitInfo]:
        "Return the list of all commits starting with a given one"
        results = []
        # The LIMIT 1 in the SQL shouldn't be necessary since we import the commits as a
        # continuous singly-linked list.
        # Get info on the last commit
        res = self.cur.execute(
            "SELECT commithash, prevhash, committime, title, committeremail, authoremail "
            "FROM commitinfo WHERE repo = ? AND branch = ? AND commithash = ? LIMIT 1",
            (repo, branch, commit))
        data = res.fetchone()
        if not data:
            logging.warning('Could not find commit %s in database', commit)
        else:
            results.insert(0, CommitInfo(
                commit_time=data[2],
                commit_hash=data[0],  # a.k.a. commit
                prev_hash=data[1],
                committer_email=data[4],
                author_email=data[5],
                title=data[3]
            ))
            while commit:
                # Search backwards (away from HEAD) by searching for prev_hash
                res = self.cur.execute(
                    "SELECT commithash, prevhash, committime, title, committeremail, authoremail "
                    "FROM commitinfo WHERE repo = ? AND branch = ? AND prevhash = ? LIMIT 1",
                    (repo, branch, commit))
                data = res.fetchone()
                if not data:
                    break
                results.insert(0, CommitInfo(
                    commit_time=data[2],
                    commit_hash=data[0],
                    prev_hash=data[1],  # a.k.a. commit
                    committer_email=data[4],
                    author_email=data[5],
                    title=data[3]
                ))
                commit = data[0]  # commit_hash
        return results

    def select_all_commit_before_commit(self, repo: str, branch: str, commit: str
                                        ) -> List[CommitInfo]:
        "Return the list of all commits starting with a given one"
        results = []
        # The LIMIT 1 in the SQL shouldn't be necessary since we import the commits as a
        # continuous singly-linked list.
        # Get info on the last commit
        res = self.cur.execute(
            "SELECT commithash, prevhash, committime, title, committeremail, authoremail "
            "FROM commitinfo WHERE repo = ? AND branch = ? AND commithash = ? LIMIT 1",
            (repo, branch, commit))
        data = res.fetchone()
        if not data:
            logging.warning('Could not find commit %s in database', commit)
        else:
            results.append(CommitInfo(
                commit_time=data[2],
                commit_hash=data[0],  # a.k.a. commit
                prev_hash=data[1],
                committer_email=data[4],
                author_email=data[5],
                title=data[3]
            ))
            prev_commit = data[1]
            while prev_commit:
                logging.debug(prev_commit)
                # Search forwards (towards HEAD) by searching for commit_hash
                res = self.cur.execute(
                    "SELECT commithash, prevhash, committime, title, committeremail, authoremail "
                    "FROM commitinfo WHERE repo = ? AND branch = ? AND commithash = ? LIMIT 1",
                    (repo, branch, prev_commit))
                data = res.fetchone()
                if not data:
                    break
                results.append(CommitInfo(
                    commit_time=data[2],
                    commit_hash=data[0],
                    prev_hash=data[1],  # a.k.a. prev_commit
                    committer_email=data[4],
                    author_email=data[5],
                    title=data[3]
                ))
                prev_commit = data[1]  # prev_hash
        return results

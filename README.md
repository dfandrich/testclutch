![Test Clutch logo](test-clutch-logo.svg)

Test Clutch is a system for tracking and analyzing automated regression test
results over multiple continuous integration services. It was born from the
need in the curl project to make sense of the more than 300,000 tests run every
day over its six CI services.  It does not run tests itself, but rather
collects statistics from one or more test runners.

## Introduction

curl was spreading its CI load over the free tier of five different CI
providers (plus user-submitted builds run on their own build farms) so detailed
results could not be viewed in a single location. The summary provided by
GitHub for PRs showed only failed builds without much detail, and it ignored
entirely automated builds run by users on the daily tarballs provided by the
project. There was also no test summary of the master branch more than a simple
binary failed/succeeded in status badges.  Test Clutch brings into one place
information about millions of test runs and attempts to give the user a useful
view of them.

## Architecture

Test Clutch is built around a database of test results. Test results enter the
database in the ingestion phase where they can then be summarized or queried.
The database holds information down to the level of which test numbers were run
in a given run and their success or failure. Unlimited metadata can be attached
to each run to help in later analysis, ranging from the git commit of the test
source and the CI service being used, down to the hostname and OS version of
the test runner. sqlite3 is used as the database, which means the program does
not need an external database running.

### Ingestion

A periodic job polls the relevant CI services for new test results that are
stored in the database. The polling interval should be set depending on how
fresh you want the data to be versus how much load you want or are allowed to
put on the CI system.

### Augmentation

Some useful data may not be available from the CI service. Test data
augmentation can add data to the test runs in the database to fill in the gaps.
For example, a git hash might only be available in its short form; an
augmentation job can be run to expand the hash to its full value by looking it
up in a relevant git repository, making queries by hash behave consistently.

### Analysis

Once ingestion is complete, analysis of the runs can be performed. The main
analysis currently available is a summary of the most recent test runs showing
their overall success or failure, along with information on which tests have
been flaky recently.

A tool is also available to query the database to search for matching tests or
jobs manually.

## Installation

The latest source code can be obtained from
https://github.com/dfandrich/testclutch/

The code is written entirely in Python.  Build and install the latest code
from Github with:

  python -m pip install https://github.com/dfandrich/testclutch/archive/refs/heads/master.tar.gz

The regression test suite can be run with the command:

  pytest

or

  python -m unittest

Test Clutch does not require git for its basic functions, but those directly
involved in querying git (like tcgitcommitinfo) require the git command-line
tool be installed (version 1.8.3 and newer are known to work).

## Configuration

### Configuration File

Create a file `~/.config/testclutchrc` in the same format as `configdef.py`
(you can use the file `examples/testclutchrc` as a template).
Most items have sane defaults, but `check_repo` must be set to a URL for the
repository of your source code. This is used as an identifier in the database
and can be used by augmentation jobs.

### Ingestion Jobs

You must configure the ingestion jobs for the CI services you are using. Test
Clutch supports these CI services:

* Appveyor
* Azure
* Circle CI
* Cirrus
* GitHub Actions
* curl autobuild (specific to the curl project)

Some of these may require credentials to access the log files. These are
configured on the command-line according to each service's needs using the
`--account` and `--authfile` command-line options.

Test Clutch has built-in support for these test log formats:

* Pytest
* Gnu automake
* curl runtests (specific to the curl project)

If your test runner uses a different format for reporting on test results, you
will need to create a parser to ingest them.

### Reports Jobs

The most interesting report currently available is obtained by running
`tcanalysissum`. Another program `tcanalyzepr` is also available to download
test results relating to a GitHub PR to summarize the run tests and indicate
which failing tests have recently been flaky.

### Sample Update Script

The file `examples/daily-update` is an example that you can use to create a
custom periodic update script for your own use case. It can be installed as a
cron job to generate up-to-date test reports.

## Programs

These are the main entry points to Test Clutch. Most of them access `--help` to
show some information on using them.

### tcanalysissum

Analyze ingested data looking for patterns of failure in the tests and generate
a report in text or HTML formats.

### tcanalyzepr

Analyze logs from a GitHub PR for patterns of failure in the tests and generate
a report in text or HTML formats.

### tcaugmentcurldaily

Adds git commit hashes & summary to autobuilds built from curl's daily
tarballs.

### tcaugmentgithash

Adds full-length git commit hashes & summary to runs that only have a short
hash. This is currently only applicable to curl autobuild logs.

### tcfindtestruns

Finds test job runs in which a particular test failed or succeeded.

### tcgitcommitinfo

Reads in information about git commits into the database.

### tcingestlog

Reads test results from log files from CI services and ingests them into the
database.

### tcmetadatastats

Create a report summarizing the metadata and statistics about recent test logs.


## Debugging Programs

These are additional entry points that can be useful for debugging.

### tcquerytests

Show information about a specific ingested job based on specific metadata.

### tcdbutil

Perform low-level manipulations of the database.

### tclogparse

Parse a single log file on disk from stdin and view the parsed data on the
stdout.

## Code Structure

### logparser

Modules that parse different test log formats.

### ingest

Modules that ingest test logs from various CI services.

### augment

Modules that augment test metadata with additional data potentially from
elsewhere.

### tests

Modules for regression testing the rest of the code.

### examples

Some example configuration and script files are supplied for reference.

## Extending

You can create plug-ins for ingesting new log formats by writing a Python
module similar to the existing ingestion ones and by referencing it by name in
the `log_parsers` configuration entry. Try to use metadata in the same format
as existing parsers, if possible and relevant, to make future analysis tasks
simpler.  See [metadata](metadata.md) for a list of standard mandatory and some
optional metadata types.

## Compatibility

Test Clutch is in rapid development and no guarantees of compatibility with
future or previous versions is currently being made. Contact the developers if
you would like to propose an API be stabilized. The first one is likely to be
the test log parsing API.

## Future Work

Having a database filled with test run information opens up a range of
possibilities for its use. Here are some:

* determining which tests are flaky to prioritize work to fix them

* keeping track of the current success/failure status of tests on the master
  branch

* notifying developers who are responsible for submitting a change that caused
  tests to start failing

* notifying PR developers through GitHub PR comments about failing tests that
  are likely to be flaky and not the fault of the PR

* finding commonalities between failing tests, e.g. tests that fail only on ARM
  processors, or tests that fail only on a Linux 6.1 kernel, or tests that fail
  only with clang 11.

* identifying when a commit causes test coverage to suddenly drop

* identifying which CI builds have the most/least test coverage

* determine which builds are running a specific test number

* finding builds that match specific build criteria (e.g. compiler version, OS,
  curl features, curl dependencies) and looking at their test results

* seeing if specific tests started running faster (or slower) after a specific
  commit

* alerting somebody on specific conditions, such as if no tests have been run
  in 2 days, or the overall test success rate drops below 95%

## License

Copyright (C) 2023–2024  Daniel Fandrich dan@telarity.com

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

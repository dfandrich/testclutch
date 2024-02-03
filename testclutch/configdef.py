"""Testclutch default configuration file

Every configuration element ever used in the program must exist here.
These defaults may be overridden in the user's config file.

The variables guaranteed to be available are set in config.environ()
"""


# Path to local database
database_path = '{XDG_DATA_HOME}/testclutch.sqlite3'

# Path to root of log cache directory
log_cache_path = '{XDG_CACHE_HOME}/testclutchlogs'

# Code repository to work on
check_repo = ''

# git branch to use
branch = 'master'

# log parsing functions to try, in order
log_parsers = [
    'testclutch.logparser.pytestparse.parse_log_file',
    'testclutch.logparser.pytestparse.parse_log_file_summary',
    'testclutch.logparser.automakeparse.parse_log_file',
]

# Minimum number of failures in a row that need to occur before reporting on it
# (currently (mostly) ignored)
report_consecutive_failures = 3

# Minimum number of builds in order to perform flaky analysis
flaky_builds_min = 10

# Maximum number of builds to look at when performing flaky analysis
flaky_builds_max = 999999999

# Minimum number of different failures that need to occur before it's considered flaky
flaky_failures_min = 2

# Minimum number of recent failures before considering it a permafail
permafail_failures_min = 2

# Time in hours that maks a job "old"
old_job_hours = 24 * 3  # 3 days

# Time in hours that maks a job "disabled"
disabled_job_hours = 24 * 14  # 14 days

# Number of hours of runs to include in the analysis
analysis_hours = 24 * 90  # 90 days

# Number of hours back to first look for a requested PR;
# This is an optimization since we assume PRs will be checked soon after running
pr_age_hours_default = 18

# Maximum number of hours back to look for a requested PR;
# no PR runs older than this will ever be found
pr_age_hours_max = 14 * 24

# Character map used in git commit logs
git_comment_encoding = 'UTF-8'

# Don't compress a file if it's shorter than this length.
# 128 is the normal maximum length allowed for data inline in ext4 inodes, so using this
# will cause absolutely no disk space increase for such file on such filesystems.
compress_threshold_bytes = 128

# TODO:
# add per-CI service options, like azure_account

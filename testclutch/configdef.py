"""Testclutch default configuration file.

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

# Log parsing functions to try, in order
log_parsers = [
    'testclutch.logparser.pytestparse.parse_log_file',
    'testclutch.logparser.pytestparse.parse_log_file_summary',
    'testclutch.logparser.automakeparse.parse_log_file',
]

# Whether to stop searching for more log files after the first one is found
log_parse_single = True

# Use this character set when reading logs. Any errors when reading cause the bad bytes to be
# replaced with backslash escape sequences.
log_charset = 'UTF-8'

# Minimum number of failures in a row that need to occur before reporting on it
# (currently (mostly) ignored)
report_consecutive_failures = 3

# Minimum number of builds in order to perform flaky analysis
flaky_builds_min = 10

# Maximum number of builds to look at when performing flaky analysis
# This limit is on top of the regular one that limits builds by time
flaky_builds_max = 999999999

# Minimum number of different failures that need to occur before it's considered flaky
flaky_failures_min = 2

# Minimum number of recent failures before considering it a permafail
permafail_failures_min = 2

# Time in hours that makes a job "old"
old_job_hours = 24 * 3  # 3 days

# Time in hours that makes a job "disabled"
disabled_job_hours = 24 * 14  # 14 days

# Number of hours of runs to include in the analysis
analysis_hours = 24 * 90  # 90 days

# Number of hours back to first look for a requested PR;
# This is an optimization since we assume PRs will be checked soon after running
pr_age_hours_default = 18

# Maximum number of hours back to look for a requested PR;
# no PR runs older than this will ever be found (at least for some CI services)
pr_age_hours_max = 24 * 14  # 14 days

# Character map used in git commit logs
git_comment_encoding = 'UTF-8'

# Don't compress a file if it's shorter than this length.
# 128 is the normal maximum length allowed for data inline in ext4 inodes, so using this
# will cause absolutely no disk space increase for such files on such filesystems.
compress_threshold_bytes = 128

# Report configuration: test_results_count
# Number of failed tests for which to bother showing URLs (since that is slow)
test_results_count_max_urls = 75

# Number of recent URLs to show for each test in the test failure counts report
test_results_count_num_recent_urls = 5

# Oldest created PR in hours to include in the PR check
pr_ready_age_hours_max = 24 * 3  # 3 days

# Set of authors to which "ready" PRs will be limited, when set
pr_ready_logins = frozenset()

# Path to gather storage
pr_gather_path = '{XDG_CACHE_HOME}/testclutchpr.dat'

# How long to keep analysis data on a PR around before it needs to be retrieved again
# This should be no less than pr_ready_age_hours_max to avoid duplicate comments.
pr_gather_age_hours_max = 24 * 7  # 7 days

# Set of origins on which to perform analysis (default is all supported origins)
pr_comment_origins = frozenset()

# URL to use for Test Clutch in PR comments
pr_comment_url = 'https://github.com/dfandrich/testclutch'

# Regexes of metadata fields whose values are NOT dumped in the metadata_values report
metadata_stats_ignored = [r'(^host|^jobid|^runid|^runurl|^systemhost|^url|^workflowid|duration|time)$']

# Metadata fields over which to create the features matrix
matrix_meta_fields = []

# Metadata fields to split into subfields using a regular expression
# The format is {'fieldname': r'<regex>', ...}  where <regex> is passed to re.split to split a text
# string into multiple values, each of which is treated like a separate feature value.
# e.g. to split field 'features' on spaces and commas, use {'features': r'[ ,]'}
matrix_meta_splits = {}

# Transformations to perform on the metadata fields in matrix_meta_fields
# The format is {'fieldname': [('pattern1', 'replacement2'), ('pattern2', 'replacement2'), ...]
# where the pattern and replacement strings are as specified for re.sub(). They are executed in
# the order given for each fieldname and on each value resulting from matrix_meta_splits.
# e.g. to replace WINX (where X is any number) with 'WinX' in field 'winarch' use
# {'winarch': [(r'WIN([0-9]+)', r'Win\1')]}
matrix_meta_transforms = {}

# Metadata fields whose values should be simply displayed (after transformations)
matrix_meta_dump = frozenset({})

# Whether to look at only the last result of a test as its result if more than one result is found
# in a run.  This should be done if failing tests are automatically rerun in case of flakiness.
rerun_tests = False

# Path to root of log cache directory
# TODO:
# add per-CI service options, like azure_account

"""Git commit information structure."""

from dataclasses import dataclass


@dataclass
class CommitInfo:
    """Information about a git commit."""

    commit_time: int = 0
    commit_hash: str = ''        # git commit hash
    prev_hash: str = ''          # previous git commit hash; usually but not always the parent
    committer_name: str = ''
    committer_email: str = ''
    author_name: str = ''
    author_email: str = ''
    title: str = ''

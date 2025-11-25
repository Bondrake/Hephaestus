"""Git sensor for capturing repository activity."""

from pathlib import Path
from typing import List, Optional

from git import Repo

from src.core.models import DiffStats, GitSnapshot


class GitSensor:
    """Sensor for capturing git repository state and activity."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.repo = Repo(repo_path)

    def capture_snapshot(self, since_commit: Optional[str] = None) -> GitSnapshot:
        """Capture current git state."""
        
        # Get current head commit
        head_commit = self.repo.head.commit
        
        # Determine range of commits to analyze
        commits = []
        touched_files = set()
        insertions = 0
        deletions = 0
        files_changed = 0
        
        if since_commit:
            # Analyze commits from since_commit to HEAD
            # We use 'since_commit..HEAD' notation
            rev_range = f"{since_commit}..{head_commit.hexsha}"
            try:
                commit_list = list(self.repo.iter_commits(rev_range))
                for commit in commit_list:
                    commits.append(commit.hexsha)
                    
                    # Get stats for this commit
                    if commit.parents:
                        diffs = commit.parents[0].diff(commit)
                    else:
                        # Initial commit, diff against empty tree
                        diffs = commit.diff(None)
                        
                    for diff in diffs:
                        if diff.a_path:
                            touched_files.add(Path(diff.a_path))
                        if diff.b_path:
                            touched_files.add(Path(diff.b_path))
                            
                    # Aggregate stats (approximate from stats object)
                    stats = commit.stats.total
                    insertions += stats.get('insertions', 0)
                    deletions += stats.get('deletions', 0)
                    files_changed += stats.get('files', 0)
                    
            except Exception as e:
                # Fallback or handle error (e.g. if since_commit not found)
                print(f"Error analyzing git range: {e}")
                commits = [head_commit.hexsha]
        else:
            # Just capture HEAD
            commits = [head_commit.hexsha]
            # For single commit stats
            stats = head_commit.stats.total
            insertions = stats.get('insertions', 0)
            deletions = stats.get('deletions', 0)
            files_changed = stats.get('files', 0)
            
            # Get touched files for HEAD
            if head_commit.parents:
                diffs = head_commit.parents[0].diff(head_commit)
                for diff in diffs:
                    if diff.b_path:
                        touched_files.add(Path(diff.b_path))

        # Check for merge conflicts (simplified check)
        # In a real worktree, we might look for conflict markers or index state
        merge_conflicts = []
        if self.repo.index.unmerged_blobs():
            # If there are unmerged blobs, we have conflicts
            # We can try to identify which branches/commits are involved
            merge_conflicts = ["HEAD"] # Placeholder

        return GitSnapshot(
            commits=commits,
            touched_files=list(touched_files),
            diff_stats=DiffStats(
                insertions=insertions,
                deletions=deletions,
                files_changed=files_changed
            ),
            merge_conflicts_with=merge_conflicts
        )

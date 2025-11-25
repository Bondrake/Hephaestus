# Walkthrough - Fix Dangling Branches

I have implemented a comprehensive cleanup strategy to prevent `agent-*` branches and worktrees from accumulating.

## Changes

### 1. Worktree Cleanup Logic
Added `cleanup_agent_worktree` method to `WorktreeManager` in `src/core/worktree_manager.py`. This method:
- Identifies the worktree path and branch name for a given agent.
- Removes the git worktree directory (using `git worktree remove` or fallback to manual deletion).
- Deletes the git branch (`git branch -D`).
- Updates the database record status to `cleaned`.

### 2. Cleanup on Termination
Updated `AgentManager.terminate_agent` in `src/agents/manager.py` to call `cleanup_agent_worktree` when an agent is successfully terminated. This ensures that during normal operation, resources are released immediately.

### 3. Startup Sweeper
Added a startup event handler in `src/mcp/server.py` that:
- Scans for orphaned `wt_*` directories in the worktree base path.
- Checks if the corresponding agent is inactive (terminated or missing).
- Cleans up the worktree and branch if the agent is inactive.
This handles cases where the server crashed or was killed before cleanup could occur.

## Verification

### Automated Testing
Ran the E2E test `tests/e2e/test_ticket_lifecycle.py`.
- **Result**: PASSED
- **Log**:
  ```
  tests/e2e/test_ticket_lifecycle.py .                                                                                                                                     [100%]
  ============================================================================== 1 passed in 36.63s ==============================================================================
  ```

### Manual Verification
Checked for dangling branches and directories after the test run.
- **Command**: `git branch --list "agent-*" && ls -d wt_*`
- **Result**: No branches or directories found.

## Conclusion
The system now correctly manages the lifecycle of git worktrees and branches, preventing resource leaks and clutter.

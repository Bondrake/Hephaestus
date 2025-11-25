# Cleanup Plan: Dangling Agent Branches

## Problem Analysis
The system currently accumulates "dangling" git branches and worktrees (e.g., `agent-uuid...`) after agent execution. This was observed during E2E testing where multiple `agent-*` branches remained after test failures.

### Root Causes
1.  **Incomplete Termination Logic**: The `AgentManager.terminate_agent` method (src/agents/manager.py) kills the tmux session and updates the database status, but **does not** remove the associated git worktree or branch.
2.  **Missing Cleanup Method**: The `WorktreeManager` (src/core/worktree_manager.py) has internal `_cleanup_worktree` logic but exposes no public method for `AgentManager` to call upon task completion.
3.  **No Startup/Shutdown Sweeping**: The server (src/mcp/server.py) does not check for or clean up orphaned worktrees from previous crashed sessions (e.g., after a test failure or SIGKILL).

## Proposed Changes

### 1. Enhance WorktreeManager
Add a public `cleanup_agent_worktree` method to `src/core/worktree_manager.py`.

```python
def cleanup_agent_worktree(self, agent_id: str) -> bool:
    """
    Clean up worktree and branch for a terminated agent.
    1. Find worktree record
    2. Remove git worktree (force)
    3. Delete git branch (force)
    4. Update DB record status to 'cleaned'
    """
```

### 2. Update Agent Termination
Modify `AgentManager.terminate_agent` in `src/agents/manager.py` to call the new cleanup method.

```python
# In terminate_agent:
# ... existing tmux cleanup ...
try:
    self.worktree_manager.cleanup_agent_worktree(agent_id)
    logger.info(f"Cleaned up worktree for agent {agent_id}")
except Exception as e:
    logger.error(f"Failed to cleanup worktree: {e}")
```

### 3. Implement Startup Sweeper
Add logic to the `@app.on_event("startup")` handler in `src/mcp/server.py` to clean up orphans.

```python
# In startup_event:
# 1. List all worktrees in /private/tmp/hephaestus_worktrees/ (or configured path)
# 2. Extract agent_id from folder name
# 3. Check if agent is active in DB
# 4. If not active (or DB record missing), remove worktree and branch
```

## Verification Plan
1.  **Manual Test**: Create an agent, let it finish, verify worktree is gone.
2.  **Crash Test**: Kill the server while an agent is running, restart server, verify orphan is cleaned up.
3.  **E2E Test**: Run `test_full_ticket_lifecycle` and ensure no `agent-*` branches remain afterwards.

---
description: How to archive task artifacts (plans, walkthroughs, logs) to the history directory upon task completion.
---

When a significant task is completed, follow these steps to preserve the context and artifacts:

1.  **Create a History Directory**:
    Create a new directory in `docs/task_history/` with the format `YYYY-MM-DD_task_name_slug`.
    ```bash
    # Example
    mkdir -p docs/task_history/$(date +%Y-%m-%d)_my_task_name
    ```

2.  **Identify Artifacts**:
    Locate relevant artifacts in the brain directory (usually `~/.gemini/antigravity/brain/...`). Common files include:
    - `implementation_plan.md`
    - `walkthrough.md`
    - `task.md` (save as `task_snapshot.md`)
    - Any specific plans (e.g., `cleanup_plan.md`, `debug_plan.md`)

3.  **Copy Artifacts**:
    Copy these files to the created history directory.
    ```bash
    # Example
    cp /path/to/walkthrough.md docs/task_history/YYYY-MM-DD_task_name/
    cp /path/to/task.md docs/task_history/YYYY-MM-DD_task_name/task_snapshot.md
    ```

4.  **Commit**:
    Commit the archived files to the repository.
    ```bash
    git add docs/task_history/YYYY-MM-DD_task_name/
    git commit -m "docs: Archive artifacts for 'My Task Name'"
    ```

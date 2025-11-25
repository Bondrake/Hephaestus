# Debuggability Improvement Plan

## Root Cause Analysis: Why was troubleshooting difficult?

The debugging session for the E2E Agent Launch was prolonged by several factors that obscured the true nature of the failure.

### 1. Stale and Misleading Logs
*   **The Issue:** I initially relied on `hephaestus_server.log` using `tail -n 100`. However, the log file contained entries from previous runs (timestamp `12:44` vs current time `17:xx`).
*   **The Impact:** I saw a "Failed to create agent: " error with an empty message. This was a "red herring" from an older, unrelated failure. It led me to investigate `AgentManager` creation logic and add traceback logging, which was unnecessary for the *current* issue.
*   **Root Cause:** Lack of log rotation or cleanup between test runs, and my failure to verify log timestamps against the current time.

### 2. Silent API Failures (The "422" Mystery)
*   **The Issue:** The actual failure was that `stub_cli.py` sent invalid payloads to the API, resulting in `422 Unprocessable Entity` responses.
*   **The Impact:**
    *   **Server Side:** The server logged `POST /api/tickets/change-status 422`, but did **not** log the validation error details (e.g., "missing field 'new_status'").
    *   **Client Side:** The `stub_cli.py` caught the exception and logged "Error updating ticket status: ...", but did **not** log the response body from the server.
*   **Root Cause:** Insufficient logging of HTTP error details on both client and server. We knew *that* it failed, but not *why*.

### 3. Visibility into Subprocesses
*   **The Issue:** The agent runs as a subprocess (simulated via `MockTmuxServer`). Its output is captured but not immediately visible in the main test output unless explicitly printed or redirected.
*   **The Impact:** I had to rely on `stub_cli.log` (a separate file) or redirecting pytest output to see what the agent was actually doing.
*   **Root Cause:** Test infrastructure didn't automatically stream or dump subprocess logs on failure.

---

## Improvement Plan

To prevent this in the future, we will implement the following improvements:

### 1. Server-Side: Log Validation Errors
**Goal:** When the server returns a 422, log the specific validation errors so we know what fields are missing or invalid.

*   **Action:** Add an exception handler for `RequestValidationError` in `src/mcp/server.py` (or a middleware) that logs the error details before returning the 422 response.

### 2. Client-Side: Log Response Bodies
**Goal:** When an API call fails, the client should log the server's response to help debug "why".

*   **Action:** Update `stub_cli.py` (and potentially `src/agents/runtime_wrapper.py` and other clients) to read and log `response.text` when an HTTP error occurs.

### 3. Test Infrastructure: Fresh Logs
**Goal:** Ensure we are always looking at logs from the *current* run.

*   **Action:** Update `tests/e2e/conftest.py` to truncate or rotate `hephaestus_server.log` at the start of each test session.

### 4. Agent Manager: Robust Error Logging
**Goal:** Ensure exceptions in `AgentManager` are never swallowed or logged as empty strings.

*   **Action:** Permanently add the traceback logging to `AgentManager.create_agent_for_task` that I added temporarily. It's low-cost and high-value for debugging.

## Proposed Implementation Steps

1.  **Modify `src/mcp/server.py`**: Add `RequestValidationError` handler with logging.
2.  **Modify `src/mocks/stub_cli.py`**: Enhance error logging to include `response.text`.
3.  **Modify `tests/e2e/conftest.py`**: Clear logs on startup.
4.  **Modify `src/agents/manager.py`**: Restore traceback logging.

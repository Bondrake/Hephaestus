# Implementation Plan - Complete Work-Centric Supervision Refactor

The core infrastructure for Work-Centric Supervision is in place, but several components are stubbed or need verification. This plan outlines the steps to finalize the implementation and ensure system stability.

## Goal Description
Finalize the "Work-Centric Supervision" refactor by implementing missing logic in `ProjectSupervisor`, verifying the new `SteeringEvent` flow, and ensuring all QA tests pass.

## Proposed Changes

### 1. Verification & QA
Run existing QA tests to establish a baseline and identify broken components.
- `tests/qa/test_qa_supervisor.py`
- `tests/qa/test_qa_agents.py`
- `tests/qa/test_qa_workflows.py`

### 2. ProjectSupervisor Implementation
Replace stubs in `src/core/project_supervisor.py` with real logic.
- **Git Conflict Detection**: Implement `_check_merge_conflicts` using `git merge-tree` or similar.
- **Metrics**: Implement `throughput_7d` and `reopen_rate` calculations in `ProjectMetrics`.
- **Overlap Detection**: Refine `_detect_overlaps` to be more robust.

### 3. Integration Verification
Ensure `AgentManager` correctly handles `SteeringEvent`s sent by the `SupervisionService`.
- Verify `ControlChannel` communication.
- Ensure agents receive and acknowledge events.

## Verification Plan

### Automated Tests
- Run `tests/qa/test_qa_supervisor.py` to verify supervisor logic.
- Run `tests/qa/test_qa_agents.py` to verify agent interaction.

### Manual Verification
- Run `run_supervisor.py` and observe logs for correct cycle execution.
- Simulate a conflict or policy violation and verify the system generates a `SteeringEvent`.

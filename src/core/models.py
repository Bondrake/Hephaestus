"""Core data models for work-centric supervision."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class PhaseType(str, Enum):
    """Lifecycle phases for work items."""
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    COMPLETED = "completed"


class WorkItemStatus(str, Enum):
    """Status of a work item."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """Risk level of a work item."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DependencyKind(str, Enum):
    """Type of dependency between work items."""
    BLOCKS = "blocks"
    INFORMS = "informs"
    EXTENDS = "extends"


class ConstraintScope(str, Enum):
    """Scope of a constraint."""
    PROJECT = "project"
    PHASE = "phase"
    WORKITEM = "workitem"


class LifeSpan(str, Enum):
    """Lifespan of a constraint."""
    UNTIL_LIFTED = "until_lifted"
    TTL_SECONDS = "ttl_seconds"
    UNTIL_CONDITION = "until_condition"


class ArtifactKind(str, Enum):
    """Type of artifact produced by work."""
    COMMIT = "commit"
    TEST_REPORT = "test_report"
    PR = "pr"
    REVIEW = "review"
    MERGE = "merge"
    FILE = "file"


class TaskRunStatus(str, Enum):
    """Status of a task run."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class BuildStatus(str, Enum):
    """Status of a CI build."""
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    UNKNOWN = "unknown"


# === Core Objects ===

class WorkItem(BaseModel):
    """Atomic unit of supervision."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str
    phase: PhaseType
    status: WorkItemStatus = WorkItemStatus.PENDING
    parent_id: Optional[str] = None  # Epic/parent ticket

    # Risk/coupling metadata
    risk_level: RiskLevel = RiskLevel.MEDIUM
    coupling_score: float = 0.0  # 0-1, derived from file/module overlap
    volatility: float = 0.0  # churn rate, failure frequency

    # Execution metadata
    assigned_agent_id: Optional[str] = None
    worktree_path: Optional[Path] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class Dependency(BaseModel):
    """Edges in work graph."""
    upstream_id: str  # Must complete before...
    downstream_id: str  # ...this can start
    kind: DependencyKind


class Constraint(BaseModel):
    """Typed, scoped, revocable rules."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    scope: ConstraintScope
    target_id: str  # Which project/phase/workitem
    rule: str  # "no_external_dependencies", "max_diff_lines:500"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    lifespan: LifeSpan
    lift_condition: Optional[str] = None  # "tests_pass", "phase_complete"
    issuer: str  # human:<user_id> | policy:<policy_id>
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True


class Artifact(BaseModel):
    """Observable outputs."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str
    kind: ArtifactKind
    uri: str  # git sha, file path, URL
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# === Sensor Data ===

class DiffStats(BaseModel):
    """Statistics about a git diff."""
    insertions: int
    deletions: int
    files_changed: int


class GitSnapshot(BaseModel):
    """Hard facts from git."""
    commits: List[str]
    touched_files: List[Path]
    diff_stats: DiffStats
    merge_conflicts_with: List[str]  # Other branches


class TestRun(BaseModel):
    """Result of a single test execution."""
    test_id: str
    status: str  # passed | failed | skipped
    duration_ms: float
    error_message: Optional[str] = None


class CISnapshot(BaseModel):
    """Hard facts from CI."""
    test_runs: List[TestRun]
    coverage_delta: Optional[float] = None
    lint_errors: int
    build_status: BuildStatus


class NetworkCall(BaseModel):
    """Record of a network request."""
    url: str
    method: str
    status_code: Optional[int] = None
    timestamp: datetime


class FilesystemSnapshot(BaseModel):
    """Hard facts from agent sandbox."""
    files_read: List[Path]
    files_written: List[Path]
    executables_run: List[str]
    network_calls: List[NetworkCall]


class SensorsSnapshot(BaseModel):
    """Composite sensor reading."""
    git: GitSnapshot
    ci: CISnapshot
    fs: FilesystemSnapshot
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# === Trajectory ===

class TaskRun(BaseModel):
    """Single agent execution on a WorkItem."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    work_item_id: str
    agent_id: str
    phase: PhaseType
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    sensors: Optional[SensorsSnapshot] = None
    artifacts: List[Artifact] = Field(default_factory=list)
    status: TaskRunStatus = TaskRunStatus.RUNNING


class PhaseContract(BaseModel):
    """Expected behavior for current phase."""
    phase: PhaseType
    done_criteria: List[str]  # List of criteria descriptions
    allowed_tools: List[str]
    timeout_seconds: int


class TrajectorySnapshot(BaseModel):
    """Per-WorkItem trajectory at a point in time."""
    work_item: WorkItem
    task_runs: List[TaskRun]
    constraints: List[Constraint]
    dependencies: List[Dependency]
    sensors: SensorsSnapshot
    phase_contract: PhaseContract

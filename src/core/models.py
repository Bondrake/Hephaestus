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


class AuthorityLevel(str, Enum):
    """Level of authority required for an action."""
    AUTO_APPLY = "auto_apply"
    DUAL_CONTROL = "dual_control"
    HUMAN_REQUIRED = "human_required"


class SuggestedAction(str, Enum):
    """Actions that can be recommended."""
    PAUSE = "pause"
    TERMINATE = "terminate"
    MERGE = "merge"
    REVERT_ALL = "revert_all"
    RUN_TESTS = "run_tests"
    LINK_TICKET = "link_ticket"
    ROLLBACK = "rollback"
    CONTINUE = "continue"


class SystemActionKind(str, Enum):
    """Actions for system-level interventions."""
    PAUSE = "pause"
    QUEUE = "queue"
    RESCHEDULE = "reschedule"
    ALERT = "alert"

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


# === Analysis ===

class LLMAnalysis(BaseModel):
    """Structured output from LLM analysis."""
    is_aligned: bool
    alignment_score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    issues: List[str]
    recommendations: List[str]
    reasoning: str


class Recommendation(BaseModel):
    """A proposed intervention."""
    kind: SuggestedAction
    target_ids: List[str]
    reason: str
    evidence: Any  # Flexible evidence payload
    confidence: float
    suggested_action: SuggestedAction  # Alias for kind to match design doc usage


class ApprovedAction(BaseModel):
    """An action approved for execution."""
    recommendation: Recommendation
    authority: AuthorityLevel
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    approver_id: str  # "policy_engine" or user_id


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""
    max_auto_terminations_per_hour: int = 0
    require_human_for_high_risk: bool = True
    min_confidence_for_auto: float = 0.8


class WorkItemFinding(BaseModel):
    """Result of supervisor analysis."""
    work_item_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Deterministic checks
    is_blocked: bool
    blocker_reason: Optional[str] = None
    
    # LLM analysis
    llm_analysis: Optional[LLMAnalysis] = None
    
    # Synthesis
    needs_intervention: bool
    intervention_reason: Optional[str] = None
    suggested_action: Optional[str] = None  # Deprecated in favor of recommendations
    
    # Recommendations
    recommendations: List[Recommendation] = Field(default_factory=list)
    snapshot: Optional[TrajectorySnapshot] = None  # Reference to source snapshot
    recommendations: List[Recommendation] = Field(default_factory=list)
    snapshot: Optional[TrajectorySnapshot] = None  # Reference to source snapshot


# === Project Level ===

class ResourceMap(BaseModel):
    """Map of resources to work items."""
    # file_path -> list of (work_item_id, mode)
    # This is a simplified view; actual implementation might be more complex
    file_access: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)

    def files_for(self, work_item: WorkItem) -> List[str]:
        """Get files accessed by a work item."""
        files = []
        for file, accesses in self.file_access.items():
            for access in accesses:
                if access["work_item_id"] == work_item.id:
                    files.append(file)
        return files

    def access_mode(self, work_item: WorkItem, file: str) -> str:
        """Get access mode for a file."""
        for access in self.file_access.get(file, []):
            if access["work_item_id"] == work_item.id:
                return access["mode"]
        return "read" # Default


class ContentionMap(BaseModel):
    """Map of resource contention."""
    # file_path -> list of (work_item_id, mode)
    access_log: Dict[str, List[Dict[str, str]]] = Field(default_factory=dict)
    conflicts: Dict[str, List[str]] = Field(default_factory=dict) # file -> list of work_item_ids

    def add(self, file: str, work_item_id: str, mode: str):
        """Register access."""
        if file not in self.access_log:
            self.access_log[file] = []
        self.access_log[file].append({"work_item_id": work_item_id, "mode": mode})

    def mark_conflict(self, file: str, writers: List[Dict[str, str]]):
        """Mark a conflict."""
        self.conflicts[file] = [w["work_item_id"] for w in writers]
        
    def items(self):
        return self.access_log.items()


class Overlap(BaseModel):
    """Detected overlap between work items."""
    work_item_1: str
    work_item_2: str
    score: float
    file_overlap: int
    git_conflicts: bool
    scope_overlap: float


class ProjectMetrics(BaseModel):
    """Health metrics for the project."""
    wip_count: int
    blocked_count: int
    throughput_7d: float
    reopen_rate: float


class SystemRecommendation(BaseModel):
    """Recommendation for system-level action."""
    kind: SystemActionKind
    target_ids: List[str]
    reason: str
    evidence: Any
    confidence: float


class ProjectFinding(BaseModel):
    """Result of project-level analysis."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metrics: ProjectMetrics
    contention_map: ContentionMap
    overlaps: List[Overlap]
    violations: List[str]
    recommendations: List[SystemRecommendation]

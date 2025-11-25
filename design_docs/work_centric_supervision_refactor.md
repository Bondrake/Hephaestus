This is an excellent analysis. You've identified the fundamental architectural tension: Guardian/Conductor have the right *shape* (trajectory-level supervision), but they're pointed at the wrong *object* (agents instead of work) and using the wrong *signals* (LLM judgments over text instead of contracts + ground truth).

Let me make sure I understand the core refactor proposal:

## What I'm hearing

**Current state:**
```
Guardian: Agent → LLM(tmux logs, phase text) → alignment_score → steer agent
Conductor: [Guardian summaries] → LLM → coherence_score → terminate agents
```

**Target state:**
```
WorkItemSupervisor: WorkItem → Snapshot(tests, diffs, tasks, constraints) → LLM + deterministic checks → Verdict
ProjectSupervisor: [WorkItem snapshots] → overlaps/conflicts → Policy(risk, thresholds) → Actions (with gates)
```

The shift is:
- **Object**: Agent conversation → WorkItem trajectory
- **Input**: Text logs → Structured snapshot + supporting text
- **Output**: Scalar score → Structured verdict (multi-dimensional)
- **Authority**: Direct action → Recommendation → Policy layer → Action

## Clarifying questions before I propose a concrete design:

### 1. WorkItem scope and granularity

When you say "WorkItem as primary supervised object", I assume you mean the hierarchical structure we discussed earlier:

```
Epic (e.g., "Add OAuth support")
├── Ticket 1: "Implement token endpoint"
│   └── [Agent-001 worked here, made commits X,Y,Z]
├── Ticket 2: "Add token refresh logic"
│   └── [Agent-002 worked here, made commit A]
└── Ticket 3: "Write OAuth integration tests"
    └── [Agent-003 worked here, tests passed/failed]
```

Should supervision happen at:
- **Ticket level** (most atomic work unit)?
- **Epic level** (for detecting redundant/conflicting tickets)?
- **Both** (Ticket supervisor + Epic supervisor)?

### 2. TrajectorySnapshot composition

You mentioned it should include:
- WorkItem id, phase, risk/coupling tags
- List of tasks executed with status
- Structured test results
- Code changes (paths, LOC, static analysis)
- Explicit constraint list

Should this snapshot be:
a) **Point-in-time**: Current state of WorkItem right now
b) **Time-series**: History of changes over supervision intervals
c) **Diff-based**: What changed since last supervision cycle

For example, if an agent has been working on a ticket for 30 minutes across 5 supervision cycles, do we want:
- Just the current state?
- All 5 previous snapshots for trajectory analysis?
- Deltas between each cycle?

### 3. Deterministic vs LLM boundary

You said "push as much as possible into deterministic checks." For a done-definition like:

```yaml
done_definitions:
  - "auth.js created with generateToken() function"
  - "auth.test.js exists with 5+ test cases"
  - "All tests pass"
  - "Implementation follows no-external-libs constraint"
  - "Code is well-documented"
```

I see:
- **Lines 1-3**: Fully deterministic (file exists, function exists via AST, test count, test runner output)
- **Line 4**: Mixed (can check imports, but "follows constraint" may need LLM for edge cases)
- **Line 5**: Subjective (LLM territory)

Should the architecture be:

```python
class DoneDefinitionCheck:
    deterministic_checks: List[Check]  # Must all pass
    llm_checks: List[Check]  # For ambiguous cases

    def evaluate(self, snapshot: TrajectorySnapshot) -> Verdict:
        # Run deterministic first
        det_results = [check.run(snapshot) for check in self.deterministic_checks]
        if not all(det_results):
            return Verdict(status="incomplete", failed_checks=...)

        # Only call LLM for subjective/ambiguous criteria
        llm_results = [check.run_with_llm(snapshot) for check in self.llm_checks]
        ...
```

Or something else?

### 4. Policy layer design

For the recommendation → policy → action flow, what level of human-in-loop do you envision?

**Option A: Risk-based gates**
```python
if verdict.recommended_action == "terminate_agent":
    if workitem.risk_level == "high":
        await policy.request_human_approval(verdict)
    else:
        await policy.auto_execute(verdict)
```

**Option B: Confidence thresholds**
```python
if verdict.confidence < 0.9:
    # Only execute high-confidence recommendations
    await policy.defer_to_human(verdict)
```

**Option C: Action budgets**
```python
# Limit how many auto-terminations allowed per hour
if policy.budget_exhausted("terminate_agent"):
    await policy.escalate(verdict)
```

All of the above?

### 5. Duplicate detection mechanics

Current Conductor detects duplicates by comparing Guardian summaries (text similarity).

In work-centric world, you suggested "overlapping WorkItems (same requirements/code areas)". How would you operationalize this?

```python
def detect_overlaps(tickets: List[Ticket]) -> List[Overlap]:
    overlaps = []
    for t1, t2 in combinations(tickets, 2):
        # Check scope overlap
        if requirements_overlap(t1.description, t2.description):  # LLM?
            overlap_score += 0.3

        # Check code path overlap
        if file_overlap(t1.touched_files, t2.touched_files):  # Deterministic
            overlap_score += 0.5

        # Check git conflicts
        if would_conflict(t1.branch, t2.branch):  # git merge-tree
            overlap_score += 0.7

        if overlap_score > threshold:
            overlaps.append(Overlap(t1, t2, score, reason))

    return overlaps
```

Is this the right direction? Should file overlap use:
- Exact path matches?
- AST-level dependency analysis (calling same functions)?
- Git merge conflict detection?

### 6. Migration path

Given that Guardian/Conductor are currently deeply integrated:
- `monitor.py` runs them every 60s
- Frontend shows Guardian trajectories and Conductor coherence
- Database has `guardian_analyses` and `conductor_analyses` tables

Do you want:

**Big-bang refactor:** Replace Guardian/Conductor entirely with new work-centric supervisors?

**Gradual transition:**
1. Keep Guardian/Conductor running (legacy)
2. Build new `WorkItemSupervisor` in parallel
3. Run both, compare verdicts
4. Switch over when confident
5. Remove old system

**Hybrid:**
- Keep Conductor for system-level coordination
- Replace Guardian with work-centric version
- Share infrastructure (policy layer, snapshots)

---

Once you clarify these, I can propose:
1. Concrete Pydantic schemas for `TrajectorySnapshot`, `Verdict`, `Policy`
2. Refactored supervisor architecture
3. Migration plan from current Guardian/Conductor

What's your preference on these design choices?

---

# Unified Design Proposal: Work-Centric Supervision

## 1. Core Architecture

### Three-Plane Separation

```python
┌─────────────────────────────────────────────────────────────┐
│  SENSING PLANE (Facts)                                       │
│  - Canonical work graph (WorkItems, Dependencies)           │
│  - Hard sensors (git, CI, filesystem, network)              │
│  - Artifact store (commits, test reports, PRs)              │
│  - Constraint store (typed, scoped, with lift conditions)   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  SCORING PLANE (Findings)                                    │
│  - WorkItemSupervisor: per-ticket trajectory analysis       │
│  - ProjectSupervisor: system-level coherence                │
│  - Output: Structured findings with evidence                │
│  - No direct actuation                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  POLICY PLANE (Decisions)                                    │
│  - Deterministic rule engine                                │
│  - Risk-aware authority levels                              │
│  - Dual-control for destructive actions                     │
│  - Executes approved actions only                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  ACTUATION PLANE (Effects)                                   │
│  - Structured control channel (not free-text tmux)          │
│  - Pause-first (reversible before irreversible)             │
│  - Action logging and replay                                │
└─────────────────────────────────────────────────────────────┘
```

**Key invariant:** LLMs live only in the Scoring Plane. They produce findings, not actions.

---

## 2. Data Model (Canonical Work Graph)

```python
# === Core Objects ===

class WorkItem(BaseModel):
    """Atomic unit of supervision"""
    id: str
    title: str
    description: str
    phase: PhaseType
    status: WorkItemStatus
    parent_id: Optional[str]  # Epic/parent ticket

    # Risk/coupling metadata
    risk_level: RiskLevel  # low | medium | high | critical
    coupling_score: float  # 0-1, derived from file/module overlap
    volatility: float  # churn rate, failure frequency

    # Execution metadata
    assigned_agent_id: Optional[str]
    worktree_path: Optional[Path]
    created_at: datetime
    started_at: Optional[datetime]

class Dependency(BaseModel):
    """Edges in work graph"""
    upstream_id: str  # Must complete before...
    downstream_id: str  # ...this can start
    kind: DependencyKind  # blocks | informs | extends

class Constraint(BaseModel):
    """Typed, scoped, revocable rules"""
    id: str
    scope: ConstraintScope  # project | phase | workitem
    target_id: str  # Which project/phase/workitem
    rule: str  # "no_external_dependencies", "max_diff_lines:500"
    parameters: Dict[str, Any]
    lifespan: LifeSpan  # until_lifted | ttl_seconds | until_condition
    lift_condition: Optional[str]  # "tests_pass", "phase_complete"
    issuer: str  # human:<user_id> | policy:<policy_id>
    created_at: datetime

class Artifact(BaseModel):
    """Observable outputs"""
    id: str
    work_item_id: str
    kind: ArtifactKind  # commit | test_report | pr | review | merge
    uri: str  # git sha, file path, URL
    metadata: Dict[str, Any]
    created_at: datetime

# === Sensor Data ===

class GitSnapshot(BaseModel):
    """Hard facts from git"""
    commits: List[str]
    touched_files: List[Path]
    diff_stats: DiffStats  # insertions, deletions, files_changed
    merge_conflicts_with: List[str]  # Other branches

class CISnapshot(BaseModel):
    """Hard facts from CI"""
    test_runs: List[TestRun]
    coverage_delta: Optional[float]
    lint_errors: int
    build_status: BuildStatus

class FilesystemSnapshot(BaseModel):
    """Hard facts from agent sandbox"""
    files_read: List[Path]
    files_written: List[Path]
    executables_run: List[str]
    network_calls: List[NetworkCall]

class SensorsSnapshot(BaseModel):
    """Composite sensor reading"""
    git: GitSnapshot
    ci: CISnapshot
    fs: FilesystemSnapshot
    timestamp: datetime

# === Trajectory ===

class TaskRun(BaseModel):
    """Single agent execution on a WorkItem"""
    id: str
    work_item_id: str
    agent_id: str
    phase: PhaseType
    started_at: datetime
    ended_at: Optional[datetime]
    sensors: SensorsSnapshot
    artifacts: List[Artifact]
    status: TaskRunStatus  # running | completed | failed | paused

class TrajectorySnapshot(BaseModel):
    """Per-WorkItem trajectory at a point in time"""
    work_item: WorkItem
    task_runs: List[TaskRun]
    constraints: List[Constraint]  # Active constraints for this WorkItem
    dependencies: List[Dependency]  # Edges involving this WorkItem
    sensors: SensorsSnapshot  # Current sensor reading
    phase_contract: PhaseContract  # Expected behavior for current phase
```

---

## 3. Scoring Plane (LLM Layer)

### WorkItemSupervisor (replaces Guardian)

```python
class WorkItemSupervisor:
    """Monitors individual WorkItem trajectories"""

    async def analyze(
        self,
        snapshot: TrajectorySnapshot
    ) -> WorkItemFinding:
        """Produce structured findings from trajectory"""

        # Step 1: Deterministic checks (fast path)
        det_checks = await self._deterministic_checks(snapshot)

        # Step 2: LLM analysis (only if needed)
        if det_checks.needs_llm_analysis:
            llm_analysis = await self._llm_analysis(snapshot)
        else:
            llm_analysis = None

        # Step 3: Combine into structured finding
        return WorkItemFinding(
            work_item_id=snapshot.work_item.id,
            timestamp=datetime.utcnow(),

            # Multi-dimensional metrics (not single alignment_score)
            metrics=Metrics(
                throughput=det_checks.commits_per_hour,
                test_pass_rate=det_checks.test_pass_rate,
                diff_size_p50=det_checks.diff_size_p50,
                constraint_violations=det_checks.violations,
                phase_alignment=llm_analysis.phase_alignment if llm_analysis else 1.0,
            ),

            # Structured evidence
            evidence=Evidence(
                commits=snapshot.sensors.git.commits,
                test_results=snapshot.sensors.ci.test_runs,
                files_touched=snapshot.sensors.git.touched_files,
                constraint_checks=det_checks.constraint_checks,
            ),

            # Recommendations (not actions!)
            recommendations=[
                SteeringRecommendation(
                    reason_code=ReasonCode.STUCK,
                    evidence_refs=["test_run_123"],
                    suggested_action=SuggestedAction.REVERT_FILE,
                    confidence=0.85,
                )
            ],
        )

    async def _deterministic_checks(
        self,
        snapshot: TrajectorySnapshot
    ) -> DeterministicChecks:
        """Hard checks without LLM"""

        checks = DeterministicChecks()

        # Done-definition checks (typed)
        for criterion in snapshot.phase_contract.done_criteria:
            if criterion.kind == "file_exists":
                checks.add(self._check_file_exists(criterion, snapshot))
            elif criterion.kind == "tests_pass":
                checks.add(self._check_tests(criterion, snapshot))
            elif criterion.kind == "no_lint_errors":
                checks.add(self._check_lint(criterion, snapshot))
            # ... other deterministic checks

        # Constraint checks
        for constraint in snapshot.constraints:
            checks.add(self._check_constraint(constraint, snapshot))

        # Resource checks
        if snapshot.work_item.risk_level == RiskLevel.CRITICAL:
            checks.add(self._check_critical_paths(snapshot))

        return checks

    async def _llm_analysis(
        self,
        snapshot: TrajectorySnapshot
    ) -> LLMAnalysis:
        """LLM reasoning over structured snapshot + supporting text"""

        # Construct prompt from structured data
        prompt = f"""
        Analyze WorkItem trajectory:

        WorkItem: {snapshot.work_item.title}
        Phase: {snapshot.work_item.phase}
        Risk: {snapshot.work_item.risk_level}

        Constraints (active):
        {self._format_constraints(snapshot.constraints)}

        Recent activity (deterministic):
        - Commits: {len(snapshot.sensors.git.commits)}
        - Files touched: {snapshot.sensors.git.touched_files}
        - Tests: {self._format_test_results(snapshot.sensors.ci.test_runs)}
        - Diff size: {snapshot.sensors.git.diff_stats}

        Done criteria (from phase contract):
        {self._format_done_criteria(snapshot.phase_contract.done_criteria)}

        Question: Is the work aligned with phase contract and constraints?
        Focus on subjective criteria that cannot be checked deterministically.
        """

        # Call LLM with structured output
        return await self.llm.analyze(
            prompt=prompt,
            response_model=LLMAnalysis,
            temperature=0.0,  # Deterministic for supervision
        )
```

**Key differences from current Guardian:**
1. **Input**: `TrajectorySnapshot` (structured) instead of tmux logs (text)
2. **Deterministic first**: Fast path for objective checks
3. **LLM for subjective only**: "Is code well-documented?" not "Do tests pass?"
4. **Structured output**: `WorkItemFinding` with evidence, not just alignment_score
5. **No actuation**: Produces recommendations, doesn't send them

---

### ProjectSupervisor (replaces Conductor)

```python
class ProjectSupervisor:
    """System-level coherence and resource contention"""

    async def analyze(
        self,
        work_items: List[WorkItem],
        findings: List[WorkItemFinding],
        resources: ResourceMap,
    ) -> ProjectFinding:
        """Detect overlaps, contention, gaps in work graph"""

        # Step 1: Build contention map (deterministic)
        contention = self._build_contention_map(work_items, resources)

        # Step 2: Detect overlaps (file-based, not text-similarity)
        overlaps = self._detect_overlaps(work_items, resources)

        # Step 3: Check invariants
        violations = self._check_invariants(work_items)

        # Step 4: LLM synthesis (only for ambiguous cases)
        synthesis = await self._llm_synthesis(
            work_items, findings, overlaps, contention
        )

        return ProjectFinding(
            timestamp=datetime.utcnow(),

            # Multi-dimensional health
            metrics=ProjectMetrics(
                wip_count=len([w for w in work_items if w.status == "in_progress"]),
                blocked_count=len([w for w in work_items if w.status == "blocked"]),
                throughput_7d=self._calculate_throughput(work_items),
                reopen_rate=self._calculate_reopen_rate(work_items),
            ),

            # Resource contention (deterministic)
            contention_map=contention,

            # Overlapping work (file-based)
            overlaps=overlaps,

            # Invariant violations
            violations=violations,

            # Recommendations
            recommendations=[
                SystemRecommendation(
                    kind=SystemActionKind.PAUSE,
                    target_ids=["workitem-123"],
                    reason="Write-write conflict on auth.py",
                    evidence=contention.conflicts["auth.py"],
                    confidence=0.95,
                )
            ],
        )

    def _detect_overlaps(
        self,
        work_items: List[WorkItem],
        resources: ResourceMap,
    ) -> List[Overlap]:
        """Resource-based overlap detection"""
        overlaps = []

        for w1, w2 in combinations(work_items, 2):
            # Skip if not same phase (parallelism expected in exploration)
            if w1.phase != w2.phase:
                continue

            # Skip validators (they're supposed to be parallel)
            if self._is_validator(w1) or self._is_validator(w2):
                continue

            # File overlap (deterministic)
            file_overlap = len(
                set(resources.files_for(w1)) &
                set(resources.files_for(w2))
            )

            # Git merge conflicts (deterministic)
            git_conflicts = self._check_merge_conflicts(w1, w2)

            # Scope overlap (LLM, if files overlap)
            if file_overlap > 0:
                scope_overlap = await self._check_scope_overlap(w1, w2)
            else:
                scope_overlap = 0.0

            # Combined score
            overlap_score = (
                0.5 * (file_overlap / max(len(resources.files_for(w1)), 1)) +
                0.3 * (1.0 if git_conflicts else 0.0) +
                0.2 * scope_overlap
            )

            if overlap_score > 0.7:
                overlaps.append(Overlap(
                    work_item_1=w1.id,
                    work_item_2=w2.id,
                    score=overlap_score,
                    file_overlap=file_overlap,
                    git_conflicts=git_conflicts,
                    scope_overlap=scope_overlap,
                ))

        return overlaps

    def _build_contention_map(
        self,
        work_items: List[WorkItem],
        resources: ResourceMap,
    ) -> ContentionMap:
        """Who is reading/writing what"""
        contention = ContentionMap()

        for work_item in work_items:
            for file in resources.files_for(work_item):
                mode = resources.access_mode(work_item, file)  # read | write
                contention.add(file, work_item.id, mode)

        # Detect conflicts
        for file, access_list in contention.items():
            writers = [a for a in access_list if a.mode == "write"]
            if len(writers) > 1:
                contention.mark_conflict(file, writers)

        return contention
```

**Key differences from current Conductor:**
1. **File-based duplicate detection**: Not text similarity of summaries
2. **Explicit contention map**: Track read/write on actual resources
3. **Validator exclusion**: Built into logic, not hardcoded "never terminate"
4. **Deterministic first**: LLM only for ambiguous scope questions
5. **No termination**: Recommends pause/queue, policy decides

---

## 4. Policy Plane (Deterministic Rules)

```python
class PolicyEngine:
    """Evaluates findings and approves actions"""

    def __init__(self, config: PolicyConfig):
        self.config = config
        self.action_budget = ActionBudget()  # Rate limits
        self.approval_queue = ApprovalQueue()  # Human gates

    async def evaluate(
        self,
        finding: Union[WorkItemFinding, ProjectFinding],
    ) -> List[ApprovedAction]:
        """Convert recommendations to approved actions"""

        approved = []

        for rec in finding.recommendations:
            # Check authority level
            authority = self._compute_authority(rec, finding)

            if authority == AuthorityLevel.AUTO_APPLY:
                # Low risk, high confidence → auto-approve
                if self.action_budget.can_execute(rec.suggested_action):
                    approved.append(self._approve(rec))
                    self.action_budget.consume(rec.suggested_action)
                else:
                    # Budget exhausted → escalate
                    await self.approval_queue.request_human(rec)

            elif authority == AuthorityLevel.DUAL_CONTROL:
                # Need quorum from two scorers
                if await self._get_quorum(rec, finding):
                    approved.append(self._approve(rec))
                else:
                    # No quorum → reject or escalate
                    await self.approval_queue.request_human(rec)

            elif authority == AuthorityLevel.HUMAN_REQUIRED:
                # High risk → always human gate
                await self.approval_queue.request_human(rec)

        return approved

    def _compute_authority(
        self,
        rec: Recommendation,
        finding: Finding,
    ) -> AuthorityLevel:
        """Risk-aware authority calculation"""

        # Get WorkItem risk level
        risk = finding.work_item.risk_level if isinstance(finding, WorkItemFinding) else RiskLevel.MEDIUM

        # Destructive actions need higher authority
        if rec.suggested_action in [
            SuggestedAction.TERMINATE,
            SuggestedAction.MERGE,
            SuggestedAction.REVERT_ALL,
        ]:
            if risk >= RiskLevel.HIGH:
                return AuthorityLevel.HUMAN_REQUIRED
            else:
                return AuthorityLevel.DUAL_CONTROL

        # Reversible actions can be auto-applied at low risk
        if rec.suggested_action in [
            SuggestedAction.PAUSE,
            SuggestedAction.RUN_TESTS,
            SuggestedAction.LINK_TICKET,
        ]:
            if risk <= RiskLevel.MEDIUM and rec.confidence > 0.8:
                return AuthorityLevel.AUTO_APPLY
            else:
                return AuthorityLevel.DUAL_CONTROL

        # Default: dual control
        return AuthorityLevel.DUAL_CONTROL

    async def _get_quorum(
        self,
        rec: Recommendation,
        finding: Finding,
    ) -> bool:
        """Require two independent scorers to agree"""

        # Run second supervisor with different model
        second_finding = await self._run_backup_scorer(finding.snapshot)

        # Check if both recommend same action
        for rec2 in second_finding.recommendations:
            if (rec2.suggested_action == rec.suggested_action and
                rec2.confidence > 0.7):
                return True

        return False
```

**Key features:**
1. **Deterministic rules**: No LLM in policy evaluation
2. **Risk-aware**: Authority level depends on WorkItem risk + action type
3. **Reversible first**: Pause before terminate
4. **Dual-control**: Destructive actions need quorum or human
5. **Budget limits**: Max N terminations per hour

---

## 5. Actuation Plane (Structured Control)

```python
class ControlChannel:
    """Side-channel for structured agent control"""

    async def send(
        self,
        work_item_id: str,
        event: SteeringEvent,
    ) -> Acknowledgment:
        """Send structured event to agent"""

        # Write to control file (not tmux text injection)
        control_file = self._get_control_file(work_item_id)
        control_file.write_json({
            "event_id": event.id,
            "reason_code": event.reason_code.value,
            "evidence": [self._format_evidence(e) for e in event.evidence],
            "required_action": event.required_action.value,
            "parameters": event.parameters,
            "deadline": event.deadline.isoformat(),
            "authority": event.authority.value,
        })

        # Wait for agent acknowledgment (structured)
        ack = await self._wait_for_ack(event.id, timeout=60)

        return ack

    async def _wait_for_ack(
        self,
        event_id: str,
        timeout: int,
    ) -> Acknowledgment:
        """Read structured acknowledgment from agent"""

        ack_file = self._get_ack_file(event_id)

        # Poll for acknowledgment
        for _ in range(timeout):
            if ack_file.exists():
                ack_data = ack_file.read_json()
                return Acknowledgment(
                    event_id=event_id,
                    status=AckStatus(ack_data["status"]),
                    artifacts=ack_data.get("artifacts", []),
                    message=ack_data.get("message"),
                    timestamp=datetime.fromisoformat(ack_data["timestamp"]),
                )
            await asyncio.sleep(1)

        # Timeout
        return Acknowledgment(
            event_id=event_id,
            status=AckStatus.TIMEOUT,
            timestamp=datetime.utcnow(),
        )

class SteeringEvent(BaseModel):
    """Typed intervention (not free-text)"""
    id: str
    reason_code: ReasonCode  # stuck | drifting | constraint_violation | missed_step | idle
    evidence: List[EvidenceItem]  # File paths, test errors, commits
    required_action: RequiredAction  # run_tests | revert_file | link_ticket | fill_criteria
    parameters: Dict[str, Any]  # Action-specific params
    deadline: datetime
    authority: AuthorityLevel  # proposal_only | auto_apply_allowed

class Acknowledgment(BaseModel):
    """Structured response from agent"""
    event_id: str
    status: AckStatus  # acknowledged | completed | rejected | timeout
    artifacts: List[str]  # Commit SHAs, test reports, etc.
    message: Optional[str]
    timestamp: datetime
```

**Key differences:**
1. **Side-channel**: Control file, not tmux text
2. **Typed events**: Structured data, not prose
3. **Evidence-based**: References to artifacts, not descriptions
4. **Acknowledgment protocol**: Agent responds with structured data
5. **Auditable**: All events and acks logged for replay

---

## 6. Anti-Goodhart Patterns

```python
class SupervisionHarness:
    """Prevent optimization on supervision itself"""

    def __init__(self):
        self.holdout_fraction = 0.1  # 10% tickets never shown to supervisors
        self.model_pool = [ModelA, ModelB]  # Diverse models
        self.eval_set = self._load_golden_trajectories()

    async def run_supervision_cycle(self):
        """Main loop with anti-Goodhart measures"""

        # Get active work items
        work_items = self.work_graph.get_active()

        # Mark random 10% as holdout (supervisors don't score these)
        holdout_ids = random.sample(
            [w.id for w in work_items],
            k=int(len(work_items) * self.holdout_fraction),
        )

        # Run supervisors on non-holdout items only
        findings = []
        for work_item in work_items:
            if work_item.id in holdout_ids:
                continue  # Skip, will be human-reviewed

            snapshot = await self._build_snapshot(work_item)
            finding = await self.work_item_supervisor.analyze(snapshot)
            findings.append(finding)

        # Policy evaluation and actuation
        actions = await self.policy_engine.evaluate(findings)
        await self.actuator.execute(actions)

        # Holdout evaluation (for calibration)
        await self._evaluate_holdout(holdout_ids)

    async def _evaluate_holdout(self, holdout_ids: List[str]):
        """Human review of holdout items for calibration"""

        for work_item_id in holdout_ids:
            # Get human judgment
            human_verdict = await self.human_review.get_verdict(work_item_id)

            # Compare to what supervisor would have said (offline)
            snapshot = await self._build_snapshot_at_time(work_item_id, past=True)
            supervisor_verdict = await self.work_item_supervisor.analyze(snapshot)

            # Log discrepancy for calibration
            self.calibration_log.add(
                work_item_id=work_item_id,
                human=human_verdict,
                supervisor=supervisor_verdict,
                timestamp=datetime.utcnow(),
            )

    async def update_supervisors(self, new_prompts: Dict[str, str]):
        """Slow outer loop - never live in production"""

        # Offline evaluation on logged traces
        eval_results = await self._evaluate_on_golden_set(new_prompts)

        # Only deploy if no regressions
        if eval_results.meets_criteria():
            await self._deploy_prompts(new_prompts)
        else:
            logger.warning("Prompt update failed eval criteria")

    async def _run_with_quorum(self, snapshot: TrajectorySnapshot):
        """Multi-model scoring for dual-control actions"""

        # Run two different models
        finding_a = await self.supervisor_a.analyze(snapshot)
        finding_b = await self.supervisor_b.analyze(snapshot)

        # Only proceed if both agree
        if self._findings_agree(finding_a, finding_b):
            return finding_a
        else:
            # Escalate disagreement to human
            await self.escalation_queue.add(snapshot, finding_a, finding_b)
            return None
```

**Anti-Goodhart measures:**
1. **Holdout audits**: 10% of tickets always go to human, supervisors never see labels
2. **Model multiplexing**: Dual-control uses two diverse models
3. **Slow outer loop**: Prompt/model updates via offline eval, never hill-climbing on live scores
4. **Governance boundary**: Supervisors can't modify their own config/thresholds/eval sets

---

## 7. Constraint Store

```python
class ConstraintStore:
    """Typed, scoped, revocable rules"""

    def add(
        self,
        scope: ConstraintScope,
        target_id: str,
        rule: ConstraintRule,
        issuer: str,
        lifespan: LifeSpan,
    ) -> Constraint:
        """Add new constraint"""

        constraint = Constraint(
            id=uuid4(),
            scope=scope,
            target_id=target_id,
            rule=rule,
            parameters=rule.parameters,
            lifespan=lifespan,
            issuer=issuer,
            created_at=datetime.utcnow(),
        )

        self.db.constraints.insert(constraint)
        return constraint

    def get_active(
        self,
        work_item_id: str,
    ) -> List[Constraint]:
        """Get all active constraints for a WorkItem"""

        work_item = self.db.work_items.get(work_item_id)
        constraints = []

        # Project-level constraints
        constraints.extend(self.db.constraints.filter(
            scope="project",
            target_id=work_item.project_id,
            active=True,
        ))

        # Phase-level constraints
        constraints.extend(self.db.constraints.filter(
            scope="phase",
            target_id=work_item.phase,
            active=True,
        ))

        # WorkItem-level constraints
        constraints.extend(self.db.constraints.filter(
            scope="workitem",
            target_id=work_item_id,
            active=True,
        ))

        return constraints

    async def request_lift(
        self,
        constraint_id: str,
        work_item_id: str,
        evidence: List[Artifact],
        reason: str,
    ) -> LiftProposal:
        """Agent proposes lifting a constraint"""

        constraint = self.db.constraints.get(constraint_id)

        # Create lift proposal
        proposal = LiftProposal(
            id=uuid4(),
            constraint_id=constraint_id,
            work_item_id=work_item_id,
            evidence=evidence,
            reason=reason,
            status="pending",
        )

        # Auto-approve if condition met
        if constraint.lift_condition and self._check_condition(
            constraint.lift_condition, evidence
        ):
            proposal.status = "approved"
            constraint.active = False
            self.db.constraints.update(constraint)

        # Otherwise require human approval for high-risk scopes
        elif constraint.scope in ["project", "phase"]:
            await self.approval_queue.request_human(proposal)

        self.db.lift_proposals.insert(proposal)
        return proposal
```

**Key features:**
1. **Explicit storage**: Not rediscovered from chat
2. **Typed rules**: Enum of known constraint types
3. **Scoped**: Project/phase/workitem levels
4. **Revocable**: Structured lift proposals with evidence
5. **Governance**: High-scope lifts need human approval

---

## 8. Supervision Cadence (Dynamic)

```python
class AdaptiveCadence:
    """Risk-aware supervision intervals"""

    def compute_interval(
        self,
        work_item: WorkItem,
        history: WorkItemHistory,
    ) -> timedelta:
        """Calculate supervision interval for this WorkItem"""

        # Base interval from phase
        base = self.phase_intervals[work_item.phase]  # e.g., 60s for implementation

        # Modifiers based on risk/coupling/volatility
        risk_factor = {
            RiskLevel.LOW: 2.0,     # Check less often
            RiskLevel.MEDIUM: 1.0,
            RiskLevel.HIGH: 0.5,    # Check more often
            RiskLevel.CRITICAL: 0.25,
        }[work_item.risk_level]

        coupling_factor = 1.0 / (1.0 + work_item.coupling_score)  # High coupling → shorter interval

        volatility_factor = 1.0 / (1.0 + work_item.volatility)  # High churn → shorter interval

        # Task age (newer tasks need more frequent checks)
        age_hours = (datetime.utcnow() - work_item.started_at).total_seconds() / 3600
        age_factor = min(age_hours / 2.0, 2.0)  # Ramp up to 2x over first 2 hours

        # Combined interval
        interval = base * risk_factor * coupling_factor * volatility_factor * age_factor

        # Clamp to reasonable bounds
        return timedelta(seconds=max(15, min(600, interval)))
```

**Key features:**
1. **Risk-aware**: High-risk items supervised more frequently
2. **Coupling-aware**: Overlapping work needs tighter coordination
3. **Volatility-aware**: Churning tasks need attention
4. **Age-aware**: New tasks need more hand-holding
5. **Learned**: Base intervals can be fit from historical data

---

## 9. Migration Plan

### Phase 1: Sensing Infrastructure (Week 1-2)

**Goal:** Build canonical work graph and sensor layer without disrupting current system.

```
Tasks:
1. Create new tables:
   - work_items (migrate from tasks)
   - dependencies
   - constraints
   - artifacts
   - task_runs
   - sensors_snapshots

2. Build sensor collectors:
   - GitSensor: Hook into worktree commits
   - CISensor: Capture test results
   - FilesystemSensor: Log agent file access

3. Data pipeline:
   - Every agent operation logs to sensors
   - Build TrajectorySnapshot from sensors
   - Keep Guardian/Conductor running unchanged
```

**Success criteria:**
- All agent activity captured in sensors
- Can reconstruct trajectory from sensor data
- No regression in current functionality

### Phase 2: Structured Interventions (Week 3)

**Goal:** Replace free-text tmux steering with control channel.

```
Tasks:
1. Implement ControlChannel:
   - Control file protocol
   - SteeringEvent types
   - Acknowledgment handling

2. Modify agent runtime:
   - Poll control file
   - Handle typed events
   - Send structured acks

3. Bridge layer:
   - Convert Guardian steering to SteeringEvents
   - Send via ControlChannel instead of tmux
```

**Success criteria:**
- All steering goes through ControlChannel
- Agents acknowledge events
- Can replay control events from logs

### Phase 3: WorkItemSupervisor (Week 4-5)

**Goal:** New work-centric supervisor running in parallel.

```
Tasks:
1. Implement WorkItemSupervisor:
   - Deterministic checks
   - LLM analysis over snapshots
   - WorkItemFinding output

2. Run in shadow mode:
   - Analyze same WorkItems as Guardian
   - Log findings but don't act
   - Compare verdicts

3. Dashboard:
   - Show both Guardian and WorkItemSupervisor
   - Highlight disagreements
```

**Success criteria:**
- WorkItemSupervisor produces findings for all active work
- Findings include structured evidence
- Can compare to Guardian decisions

### Phase 4: Policy Engine (Week 6)

**Goal:** Separate scoring from actuation.

```
Tasks:
1. Implement PolicyEngine:
   - Risk-based authority
   - Action budgets
   - Approval queue

2. Dual-control:
   - Multi-model scoring
   - Quorum logic

3. Integration:
   - WorkItemSupervisor → PolicyEngine → ControlChannel
   - Guardian → PolicyEngine (bridge)
```

**Success criteria:**
- All actions go through policy evaluation
- High-risk actions gated correctly
- Dual-control working for destructive actions

### Phase 5: ProjectSupervisor (Week 7-8)

**Goal:** Replace Conductor with resource-aware system supervisor.

```
Tasks:
1. Implement ProjectSupervisor:
   - Contention map
   - File-based overlap detection
   - Invariant checks

2. Run in parallel:
   - Compare to Conductor verdicts
   - Log differences

3. Validator pooling:
   - Queue management
   - Backoff logic
```

**Success criteria:**
- ProjectSupervisor detects overlaps accurately
- Fewer false positives than Conductor
- Validator pooling prevents thrashing

### Phase 6: Cutover (Week 9)

**Goal:** Make new system primary, keep old as fallback.

```
Tasks:
1. Switch default:
   - WorkItemSupervisor becomes primary
   - ProjectSupervisor becomes primary
   - Guardian/Conductor still run but only log

2. Calibration:
   - Holdout audits
   - Brier scoring
   - Tune thresholds

3. Monitoring:
   - Track discrepancies
   - Measure impact on throughput/defect rate
```

**Success criteria:**
- New system handles 100% of traffic
- No increase in defect rate
- Throughput maintained or improved

### Phase 7: Cleanup (Week 10+)

**Goal:** Remove legacy system.

```
Tasks:
1. Deprecate Guardian/Conductor
2. Remove old tables/code
3. Update documentation
4. Train users on new system
```

---

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Sensor overhead** | Performance | Async logging, sampling for low-risk items |
| **False pause rate** | Throughput | Start with high thresholds, tune down |
| **Human approval bottleneck** | Latency | Start with low authority, expand auto-approve |
| **LLM cost** | Budget | Cache analyses, use fast models for supervision |
| **Migration bugs** | Stability | Shadow mode, gradual rollout, keep fallback |
| **Prompt drift** | Reliability | Freeze prompts in production, slow outer loop |

---

This design addresses both reviewers' critiques:
- Work-centric, not agent-centric
- Sensors provide ground truth
- Scalars are diagnostic, not objectives
- Scoring → Policy → Actuation separation
- Structured interventions
- Resource-based duplicate detection
- Dynamic thresholds
- Anti-Goodhart measures
- Governance boundaries

Ready to proceed with implementation, or would you like me to clarify any part of the design?

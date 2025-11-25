import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

# Set test DB before any other imports
os.environ["HEPHAESTUS_TEST_DB"] = "test_qa_supervisor.db"

from src.core.supervisor import WorkItemSupervisor
from src.core.policy import PolicyEngine
from src.core.models import (
    TrajectorySnapshot,
    WorkItem,
    PhaseType,
    PhaseContract,
    SensorsSnapshot,
    GitSnapshot,
    CISnapshot,
    RiskLevel,
    SuggestedAction,
    PolicyConfig,
    LLMAnalysis,
    Recommendation,
    AuthorityLevel,
    BuildStatus
)

class TestScenario3_Supervisor:
    """Scenario 3: Supervisor & Policy Control"""
    
    @pytest.fixture
    def mock_llm_provider(self):
        return AsyncMock()

    @pytest.fixture
    def supervisor(self, mock_llm_provider):
        return WorkItemSupervisor(llm_provider=mock_llm_provider)

    @pytest.fixture
    def policy_engine(self):
        config = PolicyConfig(
            min_confidence_for_auto=0.8,
            max_auto_terminations_per_hour=0,
            require_human_for_high_risk=True
        )
        return PolicyEngine(config)

    @pytest.fixture
    def base_snapshot(self):
        """Create a basic snapshot for testing."""
        return TrajectorySnapshot(
            work_item=WorkItem(
                id="test-ticket-1",
                title="Test Ticket",
                description="A test ticket",
                phase=PhaseType.EXECUTION,
                risk_level=RiskLevel.MEDIUM,
                status="in_progress"
            ),
            phase_contract=PhaseContract(
                phase=PhaseType.EXECUTION,
                allowed_tools=["edit_file", "run_test"],
                goals=["fix bug"],
                done_criteria=["tests pass"],
                timeout_seconds=3600
            ),
            task_runs=[],
            constraints=[],
            dependencies=[],
            sensors=SensorsSnapshot(
                git=GitSnapshot(
                    branch="feature/test",
                    files_changed=[],
                    commits_ahead=0,
                    commits=[],
                    touched_files=[],
                    diff_stats={"insertions": 0, "deletions": 0, "files_changed": 0},
                    merge_conflicts_with=[]
                ),
                ci=CISnapshot(
                    build_status=BuildStatus.SUCCESS,
                    lint_errors=0,
                    test_runs=[],
                    coverage_delta=0.0
                ),
                fs={"files_read": [], "files_written": [], "executables_run": [], "network_calls": []}
            ),
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_3_1_risk_assessment_high_risk(self, supervisor, policy_engine, base_snapshot, mock_llm_provider):
        """
        Scenario 3.1: Risk Assessment (High Risk)
        - Submit a high-risk change (simulated via LLM analysis or risk level)
        - Verify Supervisor/Policy flags it for human review
        """
        # 1. Setup High Risk Snapshot
        base_snapshot.work_item.risk_level = RiskLevel.HIGH
        
        # 2. Setup LLM Analysis to recommend a destructive action (e.g., TERMINATE or MERGE)
        # Note: MERGE is destructive in our policy model for high risk
        mock_llm_provider.analyze_trajectory.return_value = LLMAnalysis(
            is_aligned=True,
            alignment_score=0.9,
            confidence=0.95,
            issues=[],
            recommendations=["Ready to merge"],
            reasoning="Code looks good"
        )
        
        # Manually construct a finding with a high-risk recommendation since Supervisor.analyze 
        # currently defaults to PAUSE for misalignment. 
        # We want to test PolicyEngine's handling of specific actions.
        
        # Let's simulate the Supervisor returning a finding with a MERGE recommendation
        # In a real integration, the Supervisor would produce this based on LLM output.
        # For this unit test, we'll construct the Finding directly to test the Policy Engine.
        
        from src.core.models import WorkItemFinding
        
        finding = WorkItemFinding(
            work_item_id=base_snapshot.work_item.id,
            is_blocked=False,
            blocker_reason=None,
            llm_analysis=None,
            needs_intervention=False,
            intervention_reason=None,
            recommendations=[
                Recommendation(
                    kind=SuggestedAction.MERGE,
                    target_ids=[base_snapshot.work_item.id],
                    reason="Ready for merge",
                    evidence=[],
                    confidence=0.95,
                    suggested_action=SuggestedAction.MERGE
                )
            ],
            snapshot=base_snapshot
        )
        
        # 3. Evaluate with Policy Engine
        approved_actions = await policy_engine.evaluate(finding)
        
        # 4. Verify Result
        # Should NOT be in approved_actions (because it requires human approval)
        assert len(approved_actions) == 0
        
        # Verify it went to approval queue
        assert len(policy_engine.approval_queue.queue) == 1
        assert policy_engine.approval_queue.queue[0].kind == SuggestedAction.MERGE
        
        print("\n[PASS] Scenario 3.1: High Risk Action requires Human Approval")

    @pytest.mark.asyncio
    async def test_3_2_auto_approval_low_risk(self, supervisor, policy_engine, base_snapshot):
        """
        Scenario 3.2: Auto-Approval (Low Risk)
        - Submit a low-risk change
        - Verify Policy Engine auto-approves
        """
        # 1. Setup Low Risk Snapshot
        base_snapshot.work_item.risk_level = RiskLevel.LOW
        
        # 2. Construct Finding with Safe Action (e.g., RUN_TESTS)
        from src.core.models import WorkItemFinding
        
        finding = WorkItemFinding(
            work_item_id=base_snapshot.work_item.id,
            is_blocked=False,
            blocker_reason=None,
            llm_analysis=None,
            needs_intervention=False,
            intervention_reason=None,
            recommendations=[
                Recommendation(
                    kind=SuggestedAction.RUN_TESTS,
                    target_ids=[base_snapshot.work_item.id],
                    reason="Verify changes",
                    evidence=[],
                    confidence=0.9, # > 0.8 min confidence
                    suggested_action=SuggestedAction.RUN_TESTS
                )
            ],
            snapshot=base_snapshot
        )
        
        # 3. Evaluate with Policy Engine
        approved_actions = await policy_engine.evaluate(finding)
        
        # 4. Verify Result
        # Should be approved
        assert len(approved_actions) == 1
        assert approved_actions[0].recommendation.kind == SuggestedAction.RUN_TESTS
        assert approved_actions[0].authority == AuthorityLevel.AUTO_APPLY
        
        print("\n[PASS] Scenario 3.2: Low Risk Action Auto-Approved")

    @pytest.mark.asyncio
    async def test_3_3_supervisor_deterministic_blocker(self, supervisor, base_snapshot):
        """
        Scenario 3.3: Supervisor Deterministic Blocker
        - Simulate CI failure
        - Verify Supervisor blocks immediately
        """
        # 1. Setup Snapshot with CI Failure
        base_snapshot.sensors.ci.build_status = BuildStatus.FAILURE
        
        # 2. Run Supervisor Analysis
        finding = await supervisor.analyze(base_snapshot)
        
        # 3. Verify Result
        assert finding.is_blocked is True
        assert finding.blocker_reason == "CI Build Failed"
        assert finding.needs_intervention is True
        
        # Verify recommendation is PAUSE
        assert len(finding.recommendations) == 1
        assert finding.recommendations[0].kind == SuggestedAction.PAUSE
        
        print("\n[PASS] Scenario 3.3: Supervisor Correctly Identifies Deterministic Blocker")

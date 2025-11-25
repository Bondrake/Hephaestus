"""Verification script for the full supervision loop."""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.models import (
    AuthorityLevel,
    BuildStatus,
    CISnapshot,
    DiffStats,
    FilesystemSnapshot,
    GitSnapshot,
    LLMAnalysis,
    PhaseContract,
    PhaseType,
    PolicyConfig,
    Recommendation,
    RiskLevel,
    SensorsSnapshot,
    SuggestedAction,
    TrajectorySnapshot,
    WorkItem,
    WorkItemStatus,
)
from src.core.supervisor import WorkItemSupervisor
from src.core.policy import PolicyEngine
from src.core.control import ControlChannel, SteeringEvent, ReasonCode, RequiredAction, AuthorityLevel as ControlAuthorityLevel
from src.interfaces import LLMProviderInterface

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockLLMProvider(LLMProviderInterface):
    """Mock LLM provider for testing."""
    def get_model_name(self) -> str: return "mock-model"
    async def enrich_task(self, *args, **kwargs) -> Dict[str, Any]: return {}
    async def generate_embedding(self, text: str) -> List[float]: return [0.0] * 1536
    async def analyze_agent_state(self, *args, **kwargs) -> Dict[str, Any]: return {}
    async def generate_agent_prompt(self, *args, **kwargs) -> str: return "mock prompt"
    async def analyze_agent_trajectory(self, *args, **kwargs) -> Dict[str, Any]: return {}
    async def analyze_system_coherence(self, *args, **kwargs) -> Dict[str, Any]: return {}
    
    async def analyze_trajectory(self, context: Dict[str, Any]) -> LLMAnalysis:
        print("   🤖 Mock LLM analyzing trajectory...")
        # Simulate finding an issue
        return LLMAnalysis(
            is_aligned=False,
            alignment_score=0.4,
            issues=["Agent is stuck in a loop"],
            recommendations=["Pause execution"],
            reasoning="Agent has not produced artifacts in 30 minutes."
        )

async def verify_full_loop():
    print("🧪 Verifying Full Supervision Loop...")

    # 1. Setup Components
    llm_provider = MockLLMProvider()
    supervisor = WorkItemSupervisor(llm_provider)
    
    policy_config = PolicyConfig(
        max_auto_terminations_per_hour=10,
        require_human_for_high_risk=True,
        min_confidence_for_auto=0.8
    )
    policy_engine = PolicyEngine(policy_config)
    
    control_channel = ControlChannel(Path("./tmp/control")) # Use local tmp for testing

    # 2. Create Work Item (Low Risk to allow auto-apply)
    work_item = WorkItem(
        title="Implement Feature Z",
        description="Do the thing",
        phase=PhaseType.EXECUTION,
        status=WorkItemStatus.IN_PROGRESS,
        risk_level=RiskLevel.LOW
    )
    print(f"   📝 Created WorkItem: {work_item.id} (Risk: {work_item.risk_level})")

    # 3. Create Snapshot (Simulate Agent State)
    snapshot = TrajectorySnapshot(
        work_item=work_item,
        task_runs=[],
        constraints=[],
        dependencies=[],
        sensors=SensorsSnapshot(
            git=GitSnapshot(commits=[], touched_files=[], diff_stats=DiffStats(insertions=0, deletions=0, files_changed=0), merge_conflicts_with=[]),
            ci=CISnapshot(test_runs=[], lint_errors=0, build_status=BuildStatus.SUCCESS),
            fs=FilesystemSnapshot(files_read=[], files_written=[], executables_run=[], network_calls=[])
        ),
        phase_contract=PhaseContract(phase=PhaseType.EXECUTION, done_criteria=[], allowed_tools=[], timeout_seconds=3600)
    )
    print("   📸 Captured TrajectorySnapshot")

    # 4. Supervisor Analysis
    print("\n   🔍 Step 1: Supervisor Analysis")
    finding = await supervisor.analyze(snapshot)
    print(f"      Needs Intervention: {finding.needs_intervention}")
    print(f"      Reason: {finding.intervention_reason}")
    print(f"      Recommendations: {[r.kind for r in finding.recommendations]}")
    
    if not finding.needs_intervention:
        print("   ❌ Failed: Expected intervention from Mock LLM")
        return

    # 5. Policy Evaluation
    print("\n   ⚖️ Step 2: Policy Evaluation")
    approved_actions = await policy_engine.evaluate(finding)
    print(f"      Approved Actions: {len(approved_actions)}")
    
    if not approved_actions:
        print("   ❌ Failed: Expected approved action (Auto-Apply)")
        return
        
    action = approved_actions[0]
    print(f"      Action: {action.recommendation.kind}")
    print(f"      Authority: {action.authority}")

    # 6. Control Actuation
    print("\n   📡 Step 3: Control Actuation")
    
    # Map Policy Authority to Control Authority
    control_authority = ControlAuthorityLevel.PROPOSAL_ONLY
    if action.authority == AuthorityLevel.AUTO_APPLY:
        control_authority = ControlAuthorityLevel.AUTO_APPLY_ALLOWED
    
    event = SteeringEvent(
        reason_code=ReasonCode.STUCK if action.recommendation.kind == SuggestedAction.PAUSE else ReasonCode.DRIFTING,
        evidence=[],
        required_action=RequiredAction.RUN_TESTS, # Just a placeholder
        parameters={"message": action.recommendation.reason},
        authority=control_authority,
        deadline=datetime.utcnow()
    )
    
    print(f"      Sending Event: {event.id}")
    # We won't actually wait for ack here because we don't have a running agent to ack it.
    # We'll just verify we can write it.
    
    try:
        # Mock the _wait_for_ack to avoid timeout
        original_wait = control_channel._wait_for_ack
        async def mock_wait(*args, **kwargs):
            from src.core.control import Acknowledgment, AckStatus
            return Acknowledgment(event_id=event.id, status=AckStatus.ACKNOWLEDGED, timestamp=datetime.utcnow())
        
        control_channel._wait_for_ack = mock_wait
        
        ack = await control_channel.send(work_item.id, event)
        print(f"      Ack Status: {ack.status}")
        
        if ack.status == "acknowledged": # Enum string value
             print("   ✅ Full loop verified successfully!")
        else:
             print(f"   ❌ Failed: Ack status {ack.status}")

    except Exception as e:
        print(f"   ❌ Failed to send event: {e}")

if __name__ == "__main__":
    asyncio.run(verify_full_loop())

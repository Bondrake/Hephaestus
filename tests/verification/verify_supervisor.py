"""Verification script for WorkItemSupervisor."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.models import (
    BuildStatus,
    CISnapshot,
    Constraint,
    Dependency,
    DiffStats,
    FilesystemSnapshot,
    GitSnapshot,
    LLMAnalysis,
    PhaseContract,
    PhaseType,
    SensorsSnapshot,
    TaskRun,
    TrajectorySnapshot,
    WorkItem,
    WorkItemStatus,
)
from src.core.supervisor import WorkItemSupervisor
from src.interfaces import LLMProviderInterface


class MockLLMProvider(LLMProviderInterface):
    """Mock LLM provider for testing."""

    def get_model_name(self) -> str:
        return "mock-model"

    async def enrich_task(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    async def generate_embedding(self, text: str) -> List[float]:
        return [0.0] * 1536

    async def analyze_agent_state(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    async def generate_agent_prompt(self, *args, **kwargs) -> str:
        return "mock prompt"

    async def analyze_agent_trajectory(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    async def analyze_system_coherence(self, *args, **kwargs) -> Dict[str, Any]:
        return {}

    async def analyze_trajectory(self, context: Dict[str, Any]) -> LLMAnalysis:
        print("   🤖 Mock LLM analyzing trajectory...")
        return LLMAnalysis(
            is_aligned=True,
            alignment_score=0.9,
            confidence=0.95,
            issues=[],
            recommendations=["Keep going"],
            reasoning="Mock analysis: All good"
        )


async def verify_supervisor():
    print("🧪 Verifying WorkItemSupervisor...")
    
    # 1. Setup Mock Provider
    llm_provider = MockLLMProvider()
    supervisor = WorkItemSupervisor(llm_provider)
    
    # 2. Create Sample Work Item
    work_item = WorkItem(
        title="Implement Feature X",
        description="Do the thing",
        phase=PhaseType.EXECUTION,
        status=WorkItemStatus.IN_PROGRESS
    )
    
    # 3. Create Sample Sensors (Happy Path)
    sensors = SensorsSnapshot(
        git=GitSnapshot(
            commits=["feat: add feature x"],
            touched_files=[Path("src/feature_x.py")],
            diff_stats=DiffStats(insertions=10, deletions=0, files_changed=1),
            merge_conflicts_with=[]
        ),
        ci=CISnapshot(
            test_runs=[],
            lint_errors=0,
            build_status=BuildStatus.SUCCESS
        ),
        fs=FilesystemSnapshot(
            files_read=[],
            files_written=[],
            executables_run=[],
            network_calls=[]
        )
    )
    
    # 4. Create Snapshot
    snapshot = TrajectorySnapshot(
        work_item=work_item,
        task_runs=[],
        constraints=[],
        dependencies=[],
        sensors=sensors,
        phase_contract=PhaseContract(
            phase=PhaseType.EXECUTION,
            done_criteria=["Feature X implemented"],
            allowed_tools=["python"],
            timeout_seconds=3600
        )
    )
    
    # 5. Run Analysis (Happy Path)
    print("\n   🏃 Running Happy Path Analysis...")
    finding = await supervisor.analyze(snapshot)
    
    print(f"   📝 Result: Blocked={finding.is_blocked}, Intervention={finding.needs_intervention}")
    if not finding.is_blocked and not finding.needs_intervention:
        print("   ✅ Happy path passed")
    else:
        print(f"   ❌ Happy path failed: {finding.intervention_reason}")

    # 6. Run Analysis (Blocked Path - CI Failure)
    print("\n   🏃 Running Blocked Path Analysis (CI Failure)...")
    snapshot.sensors.ci.build_status = BuildStatus.FAILURE
    finding = await supervisor.analyze(snapshot)
    
    print(f"   📝 Result: Blocked={finding.is_blocked}, Reason={finding.blocker_reason}")
    if finding.is_blocked and finding.blocker_reason == "CI Build Failed":
        print("   ✅ Blocked path passed")
    else:
        print(f"   ❌ Blocked path failed: Expected 'CI Build Failed', got {finding.blocker_reason}")

    # 7. Run Analysis (Blocked Path - Lint Errors)
    print("\n   🏃 Running Blocked Path Analysis (Lint Errors)...")
    snapshot.sensors.ci.build_status = BuildStatus.SUCCESS
    snapshot.sensors.ci.lint_errors = 100
    finding = await supervisor.analyze(snapshot)
    
    print(f"   📝 Result: Blocked={finding.is_blocked}, Reason={finding.blocker_reason}")
    if finding.is_blocked and "Excessive Lint Errors" in (finding.blocker_reason or ""):
        print("   ✅ Lint error path passed")
    else:
        print(f"   ❌ Lint error path failed: Expected 'Excessive Lint Errors', got {finding.blocker_reason}")


if __name__ == "__main__":
    asyncio.run(verify_supervisor())

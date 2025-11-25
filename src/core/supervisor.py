"""Work-centric supervisor implementation."""

import logging
from typing import Optional

from src.core.models import (
    BuildStatus,
    LLMAnalysis,
    PhaseType,
    PhaseType,
    Recommendation,
    SuggestedAction,
    TrajectorySnapshot,
    WorkItemFinding,
)
from src.interfaces import LLMProviderInterface

logger = logging.getLogger(__name__)


class WorkItemSupervisor:
    """
    Analyzes individual work items using deterministic checks and LLM analysis.
    """

    def __init__(self, llm_provider: LLMProviderInterface):
        self.llm_provider = llm_provider

    async def analyze(self, snapshot: TrajectorySnapshot) -> WorkItemFinding:
        """
        Analyze a work item trajectory snapshot.
        
        Args:
            snapshot: The current state of the work item and its environment.
            
        Returns:
            A finding containing deterministic check results and optional LLM analysis.
        """
        logger.info(f"Analyzing work item {snapshot.work_item.id}")

        # 1. Deterministic Checks (Fast Path)
        is_blocked, blocker_reason = self._check_deterministic_blockers(snapshot)
        
        # 2. LLM Analysis (Slow Path)
        # Only run if not deterministically blocked (or if we want deeper insight regardless)
        # For now, we'll run it if there are no hard blockers, or if the blocker is "soft"
        llm_analysis = None
        if not is_blocked:
             llm_analysis = await self._run_llm_analysis(snapshot)

        # 3. Synthesis
        recommendations = []
        needs_intervention = False
        intervention_reason = None

        # Add deterministic recommendations
        if is_blocked:
            needs_intervention = True
            intervention_reason = blocker_reason
            recommendations.append(Recommendation(
                kind=SuggestedAction.PAUSE,
                target_ids=[snapshot.work_item.id],
                reason=blocker_reason or "Blocked by deterministic check",
                evidence=None,
                confidence=1.0,
                suggested_action=SuggestedAction.PAUSE
            ))

        # Add LLM recommendations
        if llm_analysis and not llm_analysis.is_aligned:
            needs_intervention = True
            if not intervention_reason:
                intervention_reason = f"LLM Alignment Issue: {llm_analysis.reasoning}"
            
            # Convert LLM string recommendations to structured ones
            # For now, we default to PAUSE if not aligned, but could parse more specific actions
            recommendations.append(Recommendation(
                kind=SuggestedAction.PAUSE,
                target_ids=[snapshot.work_item.id],
                reason=llm_analysis.reasoning,
                evidence=llm_analysis.issues,
                confidence=llm_analysis.confidence,
                suggested_action=SuggestedAction.PAUSE
            ))

        return WorkItemFinding(
            work_item_id=snapshot.work_item.id,
            is_blocked=is_blocked,
            blocker_reason=blocker_reason,
            llm_analysis=llm_analysis,
            needs_intervention=needs_intervention,
            intervention_reason=intervention_reason,
            suggested_action="pause" if needs_intervention else None, # Keep for backward compat if needed
            recommendations=recommendations,
            snapshot=snapshot
        )

    def _check_deterministic_blockers(self, snapshot: TrajectorySnapshot) -> tuple[bool, Optional[str]]:
        """Run fast, deterministic checks."""
        
        # Check 1: CI Status
        # If build failed, it's a blocker
        if snapshot.sensors.ci.build_status == BuildStatus.FAILURE:
            return True, "CI Build Failed"
            
        # Check 2: Lint Errors
        # If excessive lint errors, it's a blocker (threshold could be config)
        if snapshot.sensors.ci.lint_errors > 50:
             return True, f"Excessive Lint Errors ({snapshot.sensors.ci.lint_errors})"

        # Check 3: Phase Alignment (Basic)
        # Example: If in PLANNING phase, but modifying code files?
        # This is harder to check deterministically without strict rules.
        # For now, we'll check if allowed_tools are respected (if we had tool usage in snapshot)
        # snapshot.sensors.fs.executables_run vs snapshot.phase_contract.allowed_tools
        
        return False, None

    async def _run_llm_analysis(self, snapshot: TrajectorySnapshot) -> LLMAnalysis:
        """Run LLM analysis on the snapshot."""
        
        # Construct prompt context
        context = {
            "work_item": snapshot.work_item.model_dump(),
            "phase_contract": snapshot.phase_contract.model_dump(),
            "git_activity": snapshot.sensors.git.model_dump(),
            "ci_status": snapshot.sensors.ci.model_dump(),
            "recent_logs": "..." # TODO: Add logs to snapshot or fetch here
        }
        
        # Call LLM provider
        # Note: This assumes LLMProviderInterface has an analyze_trajectory method
        # If not, we might need to adapt or add it.
        # For this refactor, we are assuming the interface supports it or we mock it.
        
        try:
            return await self.llm_provider.analyze_trajectory(context)
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            # Return a safe default
            return LLMAnalysis(
                is_aligned=True, # Assume aligned if analysis fails to avoid blocking
                alignment_score=0.5,
                confidence=0.0,
                issues=["LLM Analysis Failed"],
                recommendations=[],
                reasoning=f"Analysis failed: {str(e)}"
            )

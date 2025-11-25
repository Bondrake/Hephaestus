"""Policy engine for decision making."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.core.models import (
    ApprovedAction,
    AuthorityLevel,
    PolicyConfig,
    Recommendation,
    RiskLevel,
    SuggestedAction,
    WorkItemFinding,
)

logger = logging.getLogger(__name__)


class ActionBudget:
    """Rate limits for automated actions."""

    def __init__(self):
        self.usage: Dict[str, List[datetime]] = {}

    def can_execute(self, action: SuggestedAction, limit_per_hour: int) -> bool:
        """Check if action is within budget."""
        if limit_per_hour <= 0:
            return False
            
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)
        
        # Clean up old usage
        if action.value in self.usage:
            self.usage[action.value] = [t for t in self.usage[action.value] if t > cutoff]
            
        current_usage = len(self.usage.get(action.value, []))
        return current_usage < limit_per_hour

    def consume(self, action: SuggestedAction):
        """Record usage of an action."""
        if action.value not in self.usage:
            self.usage[action.value] = []
        self.usage[action.value].append(datetime.utcnow())


class ApprovalQueue:
    """Queue for actions requiring human approval."""

    def __init__(self):
        self.queue: List[Recommendation] = []

    async def request_human(self, rec: Recommendation):
        """Add recommendation to approval queue."""
        logger.info(f"Requesting human approval for: {rec.kind} on {rec.target_ids}")
        self.queue.append(rec)
        # In a real system, this would trigger a notification/alert


class PolicyEngine:
    """Evaluates findings and approves actions."""

    def __init__(self, config: PolicyConfig):
        self.config = config
        self.action_budget = ActionBudget()
        self.approval_queue = ApprovalQueue()

    async def evaluate(self, finding: WorkItemFinding) -> List[ApprovedAction]:
        """Convert recommendations to approved actions."""
        approved = []

        for rec in finding.recommendations:
            # Check authority level
            authority = self._compute_authority(rec, finding)
            logger.info(f"Authority for {rec.kind}: {authority}")

            if authority == AuthorityLevel.AUTO_APPLY:
                # Low risk, high confidence -> auto-approve
                # For now, we only rate limit terminations, but could be broader
                limit = 100 # Default high limit for non-destructive
                if rec.kind == SuggestedAction.TERMINATE:
                    limit = self.config.max_auto_terminations_per_hour
                
                if self.action_budget.can_execute(rec.kind, limit):
                    approved.append(self._approve(rec, authority))
                    self.action_budget.consume(rec.kind)
                else:
                    logger.warning(f"Budget exhausted for {rec.kind}, escalating.")
                    await self.approval_queue.request_human(rec)

            elif authority == AuthorityLevel.DUAL_CONTROL:
                # Need quorum from two scorers
                if await self._get_quorum(rec, finding):
                    approved.append(self._approve(rec, authority))
                else:
                    # No quorum -> escalate
                    await self.approval_queue.request_human(rec)

            elif authority == AuthorityLevel.HUMAN_REQUIRED:
                # High risk -> always human gate
                await self.approval_queue.request_human(rec)

        return approved

    def _approve(self, rec: Recommendation, authority: AuthorityLevel) -> ApprovedAction:
        """Create approved action."""
        return ApprovedAction(
            recommendation=rec,
            authority=authority,
            approver_id="policy_engine"
        )

    def _compute_authority(
        self,
        rec: Recommendation,
        finding: WorkItemFinding,
    ) -> AuthorityLevel:
        """Risk-aware authority calculation."""
        
        # Determine risk level (default to MEDIUM if not available)
        risk = RiskLevel.MEDIUM
        if finding.snapshot and finding.snapshot.work_item:
            risk = finding.snapshot.work_item.risk_level

        # Destructive actions need higher authority
        if rec.kind in [
            SuggestedAction.TERMINATE,
            SuggestedAction.MERGE,
            SuggestedAction.REVERT_ALL,
            SuggestedAction.ROLLBACK,
        ]:
            if risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                return AuthorityLevel.HUMAN_REQUIRED
            else:
                return AuthorityLevel.DUAL_CONTROL

        # Reversible/Safe actions can be auto-applied at low risk
        if rec.kind in [
            SuggestedAction.PAUSE,
            SuggestedAction.RUN_TESTS,
            SuggestedAction.LINK_TICKET,
            SuggestedAction.CONTINUE,
        ]:
            if risk in [RiskLevel.LOW, RiskLevel.MEDIUM] and rec.confidence > self.config.min_confidence_for_auto:
                return AuthorityLevel.AUTO_APPLY
            else:
                return AuthorityLevel.DUAL_CONTROL

        # Default: dual control
        return AuthorityLevel.DUAL_CONTROL

    async def _get_quorum(
        self,
        rec: Recommendation,
        finding: WorkItemFinding,
    ) -> bool:
        """Require two independent scorers to agree."""
        # STUB: In the future, this would run a second model/supervisor
        # For now, we'll assume no quorum unless explicitly implemented
        return False

"""
Supervision Service Entrypoint.

This service runs the continuous supervision loop, monitoring active work items,
analyzing their trajectory, and applying policy-based interventions.
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.core.database import DatabaseManager, Task, Agent
from src.core.models import (
    WorkItem,
    WorkItemStatus,
    PhaseType,
    RiskLevel,
    TrajectorySnapshot,
    PolicyConfig,
    AuthorityLevel,
    SuggestedAction,
)
from src.core.sensing import SnapshotBuilder
from src.core.supervisor import WorkItemSupervisor
from src.core.policy import PolicyEngine
from src.core.control import ControlChannel, SteeringEvent, ReasonCode, RequiredAction, AuthorityLevel as ControlAuthorityLevel
from src.core.project_supervisor import ProjectSupervisor
from src.core.worktree_manager import WorktreeManager
from src.core.simple_config import get_config
from src.interfaces.llm_interface import get_llm_provider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("supervisor")

class SupervisionService:
    def __init__(self):
        self.config = get_config()
        self.db_manager = DatabaseManager(str(self.config.database_path))
        self.worktree_manager = WorktreeManager(self.db_manager)
        self.snapshot_builder = SnapshotBuilder(self.worktree_manager, self.db_manager)
        
        # Initialize components
        self.llm_provider = get_llm_provider()
        self.supervisor = WorkItemSupervisor(self.llm_provider)
        self.project_supervisor = ProjectSupervisor(self.db_manager)
        
        # Policy Config
        policy_config = PolicyConfig(
            max_auto_terminations_per_hour=self.config.max_auto_terminations_per_hour,
            require_human_for_high_risk=True,
            min_confidence_for_auto=0.85
        )
        self.policy_engine = PolicyEngine(policy_config)
        
        # Control Channel
        self.control_channel = ControlChannel(Path("./tmp/control")) # TODO: Configurable path
        
        self.running = False

    async def start(self):
        """Start the supervision loop."""
        logger.info("Starting Supervision Service...")
        self.running = True
        
        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        while self.running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Error in supervision cycle: {e}", exc_info=True)
            
            # Wait before next cycle
            await asyncio.sleep(10) # Run every 10 seconds

    async def stop(self):
        """Stop the service."""
        logger.info("Stopping Supervision Service...")
        self.running = False

    async def run_cycle(self):
        """Run a single supervision cycle."""
        logger.info("Running supervision cycle...")
        
        # 1. Fetch active tasks
        active_tasks = self._get_active_tasks()
        logger.info(f"Found {len(active_tasks)} active tasks")
        
        work_items = []
        snapshots = []
        
        for task in active_tasks:
            try:
                # Map to WorkItem
                work_item = self._map_task_to_work_item(task)
                work_items.append(work_item)
                
                # Build Snapshot
                if task.assigned_agent_id:
                    snapshot = await self.snapshot_builder.build_snapshot(
                        agent_id=task.assigned_agent_id,
                        work_item=work_item
                    )
                    snapshots.append(snapshot)
                else:
                    logger.warning(f"Task {task.id} has no assigned agent, skipping snapshot")
            except Exception as e:
                logger.error(f"Failed to process task {task.id}: {e}")

        # 2. Project-Level Analysis
        logger.info("Running Project-Level Analysis...")
        project_recommendations = await self.project_supervisor.analyze(work_items)
        for rec in project_recommendations:
            logger.info(f"Project Recommendation: {rec.action} for {rec.target_work_item_ids}")
            # TODO: Act on project recommendations (e.g., pause conflicting tasks)

        # 3. Work-Item Level Analysis & Policy
        for snapshot in snapshots:
            await self._process_work_item(snapshot)

    async def _process_work_item(self, snapshot: TrajectorySnapshot):
        """Process a single work item."""
        work_item = snapshot.work_item
        logger.info(f"Analyzing WorkItem: {work_item.id}")
        
        # Analyze
        finding = await self.supervisor.analyze(snapshot)
        
        if finding.needs_intervention:
            logger.info(f"Intervention needed for {work_item.id}: {finding.intervention_reason}")
            
            # Policy Evaluation
            approved_actions = await self.policy_engine.evaluate(finding)
            
            for action in approved_actions:
                logger.info(f"Executing Action: {action.recommendation.kind} (Authority: {action.authority})")
                await self._execute_action(work_item, action)
        else:
            logger.info(f"No intervention needed for {work_item.id}")

    async def _execute_action(self, work_item: WorkItem, action):
        """Execute an approved action."""
        # Map Policy Authority to Control Authority
        control_authority = ControlAuthorityLevel.PROPOSAL_ONLY
        if action.authority == AuthorityLevel.AUTO_APPLY:
            control_authority = ControlAuthorityLevel.AUTO_APPLY_ALLOWED
        
        # Map Recommendation to SteeringEvent
        event = SteeringEvent(
            reason_code=ReasonCode.DRIFTING, # Default, refine based on recommendation kind
            evidence=[], # TODO: Extract evidence from finding
            required_action=RequiredAction.Review_Plan, # Default
            parameters={"message": action.recommendation.reason},
            authority=control_authority,
            deadline=datetime.utcnow()
        )
        
        # Refine ReasonCode and RequiredAction
        if action.recommendation.kind == SuggestedAction.PAUSE:
            event.reason_code = ReasonCode.STUCK
            event.required_action = RequiredAction.STOP
        elif action.recommendation.kind == SuggestedAction.ROLLBACK:
            event.required_action = RequiredAction.REVERT_CHANGES
            
        # Send Event
        try:
            ack = await self.control_channel.send(work_item.id, event)
            logger.info(f"Sent SteeringEvent {event.id}, Ack: {ack.status}")
        except Exception as e:
            logger.error(f"Failed to send SteeringEvent: {e}")

    def _get_active_tasks(self) -> List[Task]:
        """Fetch active tasks from DB."""
        session = self.db_manager.get_session()
        try:
            tasks = session.query(Task).filter(
                Task.status.in_(["in_progress", "assigned", "under_review"])
            ).all()
            # Detach from session to avoid lazy loading issues after close
            session.expunge_all()
            return tasks
        finally:
            session.close()

    def _map_task_to_work_item(self, task: Task) -> WorkItem:
        """Map DB Task to Domain WorkItem."""
        # Map Status
        status_map = {
            "pending": WorkItemStatus.PENDING,
            "assigned": WorkItemStatus.IN_PROGRESS, # Assigned counts as in progress for supervision
            "in_progress": WorkItemStatus.IN_PROGRESS,
            "under_review": WorkItemStatus.IN_REVIEW,
            "done": WorkItemStatus.COMPLETED,
            "failed": WorkItemStatus.FAILED,
            "blocked": WorkItemStatus.BLOCKED,
        }
        
        # Map Phase (Simple heuristic if phase_id is not available or mapped)
        # Ideally we fetch Phase object and check its type
        phase_type = PhaseType.EXECUTION # Default
        
        # Map Risk (Simple heuristic)
        risk_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
        }
        
        return WorkItem(
            id=task.id,
            title=task.raw_description[:50], # Use first 50 chars as title
            description=task.enriched_description or task.raw_description,
            phase=phase_type,
            status=status_map.get(task.status, WorkItemStatus.IN_PROGRESS),
            risk_level=risk_map.get(task.priority, RiskLevel.MEDIUM),
            assigned_agent_id=task.assigned_agent_id,
            created_at=task.created_at,
            started_at=task.started_at,
        )

if __name__ == "__main__":
    service = SupervisionService()
    asyncio.run(service.start())

"""Bridge between Guardian monitoring and Control Channel."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.core.control import (
    AuthorityLevel,
    ControlChannel,
    EvidenceItem,
    ReasonCode,
    RequiredAction,
    SteeringEvent,
)
from src.core.database import AgentLog
from src.monitoring.guardian import Guardian, SteeringType

logger = logging.getLogger(__name__)


class GuardianBridge(Guardian):
    """
    Bridge that intercepts Guardian steering and sends structured events.
    
    Inherits from Guardian to maintain interface compatibility but
    overrides the actuation mechanism.
    """

    def __init__(self, db_manager, agent_manager, llm_provider):
        super().__init__(db_manager, agent_manager, llm_provider)
        # Initialize control channel
        # Assuming project root is available via config or relative path
        # For now, using a standard location relative to where this runs
        self.project_root = Path.cwd()
        self.control_channel = ControlChannel(self.project_root / ".hephaestus" / "control")

    async def steer_agent(
        self,
        agent,
        steering_type: str,
        message: str,
    ):
        """
        Override steer_agent to send structured events.
        """
        logger.info(f"[Bridge] Intercepting steering for agent {agent.id}: {steering_type}")

        # Map legacy steering type to ReasonCode
        reason_code = self._map_reason_code(steering_type)
        
        # Determine required action based on steering type and message content
        # This is a heuristic mapping since Guardian output is text
        required_action = self._determine_action(steering_type, message)

        # Create evidence item from the message
        evidence = [
            EvidenceItem(
                kind="guardian_analysis",
                content=message
            )
        ]

        # Create structured event
        event = SteeringEvent(
            reason_code=reason_code,
            evidence=evidence,
            required_action=required_action,
            parameters={"original_message": message},
            deadline=datetime.utcnow() + timedelta(minutes=10), # Default 10m deadline
            authority=AuthorityLevel.MANDATORY
        )

        # Send via control channel
        try:
            # We use current_task_id as work_item_id
            work_item_id = agent.current_task_id
            if not work_item_id:
                logger.warning(f"[Bridge] Agent {agent.id} has no current task, cannot send control event")
                return

            logger.info(f"[Bridge] Sending structured event {event.id} to {work_item_id}")
            ack = await self.control_channel.send(work_item_id, event)
            
            logger.info(f"[Bridge] Received acknowledgment: {ack.status}")

            # Log to DB as before (for history tracking)
            self._log_steering(agent, steering_type, message, event.id)

        except Exception as e:
            logger.error(f"[Bridge] Failed to send control event: {e}")
            # Fallback to legacy behavior? 
            # For now, just log error to avoid double-messaging if partial failure

    def _map_reason_code(self, steering_type: str) -> ReasonCode:
        """Map Guardian steering types to ReasonCodes."""
        mapping = {
            SteeringType.STUCK.value: ReasonCode.STUCK,
            SteeringType.DRIFTING.value: ReasonCode.DRIFTING,
            SteeringType.VIOLATING_CONSTRAINTS.value: ReasonCode.CONSTRAINT_VIOLATION,
            SteeringType.OVER_ENGINEERING.value: ReasonCode.DRIFTING,
            SteeringType.CONFUSED.value: ReasonCode.STUCK,
            SteeringType.OFF_TRACK.value: ReasonCode.DRIFTING,
        }
        return mapping.get(steering_type, ReasonCode.MANUAL_OVERRIDE)

    def _determine_action(self, steering_type: str, message: str) -> RequiredAction:
        """Heuristic to determine required action."""
        msg_lower = message.lower()
        
        if "test" in msg_lower:
            return RequiredAction.RUN_TESTS
        if "revert" in msg_lower or "undo" in msg_lower:
            return RequiredAction.REVERT_FILE
        if "ticket" in msg_lower or "issue" in msg_lower:
            return RequiredAction.LINK_TICKET
        if "criteria" in msg_lower or "definition" in msg_lower:
            return RequiredAction.FILL_CRITERIA
        if "stop" in msg_lower or "pause" in msg_lower:
            return RequiredAction.PAUSE
            
        # Default actions based on type
        if steering_type == SteeringType.STUCK.value:
            return RequiredAction.PAUSE # Pause to think/ask for help
        if steering_type == SteeringType.VIOLATING_CONSTRAINTS.value:
            return RequiredAction.REVERT_FILE
            
        return RequiredAction.RESUME # Default to just continuing with info

    def _log_steering(self, agent, steering_type, message, event_id):
        """Log steering to database."""
        session = self.db_manager.get_session()
        try:
            log_entry = AgentLog(
                agent_id=agent.id,
                log_type="steering",
                message=f"Guardian Bridge: {steering_type}",
                details={
                    "type": steering_type,
                    "message": message,
                    "event_id": event_id,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            session.add(log_entry)
            session.commit()
        finally:
            session.close()

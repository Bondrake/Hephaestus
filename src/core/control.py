"""Control channel for structured agent interventions."""

import asyncio
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ReasonCode(str, Enum):
    """Reason for the intervention."""
    STUCK = "stuck"
    DRIFTING = "drifting"
    CONSTRAINT_VIOLATION = "constraint_violation"
    MISSED_STEP = "missed_step"
    IDLE = "idle"
    MANUAL_OVERRIDE = "manual_override"


class RequiredAction(str, Enum):
    """Action required from the agent."""
    RUN_TESTS = "run_tests"
    REVERT_FILE = "revert_file"
    LINK_TICKET = "link_ticket"
    FILL_CRITERIA = "fill_criteria"
    PAUSE = "pause"
    RESUME = "resume"
    TERMINATE = "terminate"


class AuthorityLevel(str, Enum):
    """Authority level of the intervention."""
    PROPOSAL_ONLY = "proposal_only"
    AUTO_APPLY_ALLOWED = "auto_apply_allowed"
    MANDATORY = "mandatory"


class AckStatus(str, Enum):
    """Status of the acknowledgment."""
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class EvidenceItem(BaseModel):
    """Evidence supporting the intervention."""
    kind: str  # file | test_failure | diff | etc
    content: str
    location: Optional[str] = None


class SteeringEvent(BaseModel):
    """Typed intervention (not free-text)."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    reason_code: ReasonCode
    evidence: List[EvidenceItem]
    required_action: RequiredAction
    parameters: Dict[str, Any] = Field(default_factory=dict)
    deadline: datetime
    authority: AuthorityLevel
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Acknowledgment(BaseModel):
    """Structured response from agent."""
    event_id: str
    status: AckStatus
    artifacts: List[str] = Field(default_factory=list)
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ControlChannel:
    """Side-channel for structured agent control."""

    def __init__(self, control_dir: Path):
        self.control_dir = control_dir
        self.control_dir.mkdir(parents=True, exist_ok=True)

    def _get_control_file_path(self, work_item_id: str) -> Path:
        return self.control_dir / f"control_{work_item_id}.json"

    def _get_ack_file_path(self, event_id: str) -> Path:
        return self.control_dir / f"ack_{event_id}.json"

    async def send(
        self,
        work_item_id: str,
        event: SteeringEvent,
    ) -> Acknowledgment:
        """Send structured event to agent."""

        # Write to control file
        control_file = self._get_control_file_path(work_item_id)
        
        # In a real system, we might append to a queue or use a more robust mechanism
        # For now, we overwrite the current control file (assuming one active event at a time per agent)
        with open(control_file, "w") as f:
            f.write(event.model_dump_json(indent=2))

        # Wait for agent acknowledgment
        ack = await self._wait_for_ack(event.id, timeout=60)
        return ack

    async def _wait_for_ack(
        self,
        event_id: str,
        timeout: int,
    ) -> Acknowledgment:
        """Read structured acknowledgment from agent."""

        ack_file = self._get_ack_file_path(event_id)

        # Poll for acknowledgment
        for _ in range(timeout):
            if ack_file.exists():
                try:
                    with open(ack_file, "r") as f:
                        ack_data = json.load(f)
                    return Acknowledgment(**ack_data)
                except Exception as e:
                    print(f"Error reading ack file: {e}")
            
            await asyncio.sleep(1)

        # Timeout
        return Acknowledgment(
            event_id=event_id,
            status=AckStatus.TIMEOUT,
            timestamp=datetime.utcnow(),
            message="Timed out waiting for agent acknowledgment"
        )

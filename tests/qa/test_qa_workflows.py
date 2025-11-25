import pytest
import os
import json
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

# Set test DB before any other imports
os.environ["HEPHAESTUS_TEST_DB"] = "test_qa_workflows.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.mcp.server import app
from src.core.database import Base, get_db, Workflow, Agent, BoardConfig, Ticket, TicketHistory
from src.services.ticket_service import TicketService

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_qa_workflows.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def test_db():
    # Remove existing DB if any
    if os.path.exists("test_qa_workflows.db"):
        os.remove("test_qa_workflows.db")
        
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables
    Base.metadata.drop_all(bind=engine)
    # Cleanup
    if os.path.exists("test_qa_workflows.db"):
        os.remove("test_qa_workflows.db")

@pytest.fixture(scope="module")
def client(test_db):
    # Patch server_state and TicketSearchService
    with patch("src.mcp.server.server_state") as mock_state, \
         patch("src.services.ticket_service.TicketSearchService") as mock_search:
        
        # Setup mocks
        mock_state.broadcast_update = AsyncMock()
        mock_state.initialize = AsyncMock()
        mock_state.shutdown = AsyncMock()
        mock_state.db_manager.get_session.return_value = TestingSessionLocal()
        
        mock_search.index_ticket = AsyncMock(return_value="mock-embedding-id")
        mock_search.find_related_tickets = AsyncMock(return_value=[])
        mock_search.reindex_ticket = AsyncMock()
        
        # Initialize DB with required data
        db = TestingSessionLocal()
        
        # 1. Create Agent
        agent = Agent(
            id="qa-agent",
            created_at=datetime.utcnow(),
            system_prompt="You are a QA agent",
            status="idle",
            cli_type="claude",
            agent_type="phase"
        )
        db.add(agent)
        
        # 2. Create Workflow
        workflow_id = "qa-workflow"
        workflow = Workflow(
            id=workflow_id,
            name="QA Workflow",
            description="Workflow for QA testing",
            phases_folder_path="/tmp/qa",
            status="active"
        )
        db.add(workflow)
        
        # 3. Create BoardConfig
        board_config = BoardConfig(
            id=f"board-{uuid.uuid4()}",
            workflow_id=workflow_id,
            name="QA Board",
            columns=[
                {"id": "todo", "name": "To Do"},
                {"id": "in_progress", "name": "In Progress"},
                {"id": "done", "name": "Done"}
            ],
            ticket_types=["task", "bug", "feature"],
            default_ticket_type="task",
            initial_status="todo"
        )
        db.add(board_config)
        
        db.commit()
        db.close()
        
        with TestClient(app) as c:
            yield c

class TestScenario2_Workflows:
    """Scenario 2: Work Item Lifecycle (Tickets)"""
    
    workflow_id = "qa-workflow"
    agent_id = "qa-agent"
    ticket_id = None
    
    def test_2_1_create_ticket(self, client):
        """
        Scenario 2.1: Create Work Item
        - Create a new ticket via API
        - Verify it appears in DB
        """
        payload = {
            "workflow_id": self.workflow_id,
            "title": "Fix Login Bug",
            "description": "Users cannot login with special characters",
            "ticket_type": "bug",
            "priority": "high",
            "initial_status": "todo"
        }
        
        response = client.post(
            "/api/tickets/create",
            json=payload,
            headers={"X-Agent-ID": self.agent_id}
        )
        
        assert response.status_code == 200, f"Create ticket failed: {response.text}"
        data = response.json()
        
        assert data["success"] is True
        assert "ticket_id" in data
        assert data["status"] == "todo"
        
        TestScenario2_Workflows.ticket_id = data["ticket_id"]
        
        # Verify in DB
        db = TestingSessionLocal()
        ticket = db.query(Ticket).filter(Ticket.id == TestScenario2_Workflows.ticket_id).first()
        assert ticket is not None
        assert ticket.title == "Fix Login Bug"
        assert ticket.ticket_type == "bug"
        assert ticket.status == "todo"
        db.close()
        
        print(f"\n[PASS] Scenario 2.1: Ticket Created ({TestScenario2_Workflows.ticket_id})")

    def test_2_2_change_status(self, client):
        """
        Scenario 2.2: Phase Transition
        - Move ticket from 'todo' to 'in_progress'
        - Verify status change and history
        """
        assert TestScenario2_Workflows.ticket_id is not None
        
        payload = {
            "ticket_id": TestScenario2_Workflows.ticket_id,
            "new_status": "in_progress",
            "comment": "Starting work on this bug"
        }
        
        response = client.post(
            "/api/tickets/change-status",
            json=payload,
            headers={"X-Agent-ID": self.agent_id}
        )
        
        assert response.status_code == 200, f"Change status failed: {response.text}"
        data = response.json()
        
        assert data["success"] is True
        assert data["new_status"] == "in_progress"
        assert data["old_status"] == "todo"
        
        # Verify in DB
        db = TestingSessionLocal()
        ticket = db.query(Ticket).filter(Ticket.id == TestScenario2_Workflows.ticket_id).first()
        assert ticket.status == "in_progress"
        assert ticket.started_at is not None
        
        # Verify History
        history = db.query(TicketHistory).filter(
            TicketHistory.ticket_id == TestScenario2_Workflows.ticket_id,
            TicketHistory.change_type == "status_changed"
        ).first()
        assert history is not None
        assert history.agent_id == self.agent_id
        
        db.close()
        
        print("\n[PASS] Scenario 2.2: Status Changed to In Progress")

    def test_2_3_complete_ticket(self, client):
        """
        Scenario 2.3: Completion
        - Move ticket from 'in_progress' to 'done'
        - Verify completion
        """
        assert TestScenario2_Workflows.ticket_id is not None
        
        payload = {
            "ticket_id": TestScenario2_Workflows.ticket_id,
            "new_status": "done",
            "comment": "Bug fixed and verified"
        }
        
        response = client.post(
            "/api/tickets/change-status",
            json=payload,
            headers={"X-Agent-ID": self.agent_id}
        )
        
        assert response.status_code == 200, f"Complete ticket failed: {response.text}"
        data = response.json()
        
        assert data["success"] is True
        assert data["new_status"] == "done"
        
        # Verify in DB
        db = TestingSessionLocal()
        ticket = db.query(Ticket).filter(Ticket.id == TestScenario2_Workflows.ticket_id).first()
        assert ticket.status == "done"
        assert ticket.completed_at is not None
        
        db.close()
        
        print("\n[PASS] Scenario 2.3: Ticket Completed")

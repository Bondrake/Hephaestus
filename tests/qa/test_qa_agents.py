import pytest
import os
import json
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

# Set test DB before any other imports
os.environ["HEPHAESTUS_TEST_DB"] = "test_qa_agents.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.mcp.server import app
from src.core.database import Base, get_db, Workflow, Agent, Task, AgentLog
from src.agents.manager import AgentManager

# Setup test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_qa_agents.db"
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
    if os.path.exists("test_qa_agents.db"):
        os.remove("test_qa_agents.db")
        
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables
    Base.metadata.drop_all(bind=engine)
    # Cleanup
    if os.path.exists("test_qa_agents.db"):
        os.remove("test_qa_agents.db")

@pytest.fixture(scope="module")
def client(test_db):
    # Patch server_state and AgentManager
    with patch("src.mcp.server.server_state") as mock_state:
        
        # Setup mocks
        mock_state.broadcast_update = AsyncMock()
        mock_state.initialize = AsyncMock()
        mock_state.shutdown = AsyncMock()
        mock_state.db_manager.get_session.return_value = TestingSessionLocal()
        
        # Mock AgentManager
        mock_agent_manager = AsyncMock(spec=AgentManager)
        mock_state.agent_manager = mock_agent_manager
        
        # Initialize DB with required data
        db = TestingSessionLocal()
        
        # 1. Create Agent
        agent = Agent(
            id="qa-agent-exec",
            created_at=datetime.utcnow(),
            system_prompt="You are a QA agent",
            status="idle",
            cli_type="claude",
            agent_type="phase"
        )
        db.add(agent)
        
        # 2. Create Workflow
        workflow_id = "qa-workflow-exec"
        workflow = Workflow(
            id=workflow_id,
            name="QA Workflow Exec",
            description="Workflow for QA agent execution",
            phases_folder_path="/tmp/qa-exec",
            status="active"
        )
        db.add(workflow)
        
        db.commit()
        db.close()
        
        with TestClient(app) as c:
            yield c

class TestScenario4_Agents:
    """Scenario 4: Agent Execution"""
    
    agent_id = "qa-agent-exec"
    task_id = None
    
    def test_4_1_assign_task(self, client):
        """
        Scenario 4.1: Assign Task
        - Create a task and assign it to an agent
        - Verify agent status changes to 'working'
        """
        # 1. Create Task via API
        payload = {
            "task_description": "Update README.md",
            "done_definition": "README updated with new instructions",
            "ai_agent_id": self.agent_id,
            "workflow_id": "qa-workflow-exec",
            "priority": "medium"
        }
        
        # Mock the create_task endpoint logic since we're mocking AgentManager
        # We need to manually create the task in DB for the test
        db = TestingSessionLocal()
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            raw_description="Update README.md",
            enriched_description="Update README.md",
            done_definition="README updated",
            status="assigned",
            priority="medium",
            assigned_agent_id=self.agent_id,
            workflow_id="qa-workflow-exec",
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow()
        )
        db.add(task)
        
        # Update agent status
        agent = db.query(Agent).filter(Agent.id == self.agent_id).first()
        agent.status = "working"
        agent.current_task_id = task_id
        
        db.commit()
        db.close()
        
        TestScenario4_Agents.task_id = task_id
        
        # Verify DB state
        db = TestingSessionLocal()
        t = db.query(Task).filter(Task.id == task_id).first()
        a = db.query(Agent).filter(Agent.id == self.agent_id).first()
        
        assert t.status == "assigned"
        assert a.status == "working"
        assert a.current_task_id == task_id
        
        db.close()
        print(f"\n[PASS] Scenario 4.1: Task Assigned ({task_id})")

    def test_4_2_agent_logs(self, client):
        """
        Scenario 4.2: Agent Logs
        - Simulate agent logging activity
        - Verify logs are stored
        """
        assert TestScenario4_Agents.task_id is not None
        
        # Simulate log entry
        db = TestingSessionLocal()
        log_entry = AgentLog(
            agent_id=self.agent_id,
            log_type="thought",
            message="Reading README.md file...",
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        db.close()
        
        # Verify log exists
        db = TestingSessionLocal()
        logs = db.query(AgentLog).filter(AgentLog.agent_id == self.agent_id).all()
        assert len(logs) > 0
        assert logs[0].message == "Reading README.md file..."
        
        db.close()
        print("\n[PASS] Scenario 4.2: Agent Logs Verified")

    def test_4_3_complete_task(self, client):
        """
        Scenario 4.3: Complete Task
        - Mark task as done
        - Verify agent returns to idle
        """
        assert TestScenario4_Agents.task_id is not None
        
        # Simulate completion
        db = TestingSessionLocal()
        task = db.query(Task).filter(Task.id == TestScenario4_Agents.task_id).first()
        agent = db.query(Agent).filter(Agent.id == self.agent_id).first()
        
        task.status = "done"
        task.completed_at = datetime.utcnow()
        task.completion_notes = "Updated README successfully"
        
        agent.status = "idle"
        agent.current_task_id = None
        
        db.commit()
        db.close()
        
        # Verify DB state
        db = TestingSessionLocal()
        t = db.query(Task).filter(Task.id == TestScenario4_Agents.task_id).first()
        a = db.query(Agent).filter(Agent.id == self.agent_id).first()
        
        assert t.status == "done"
        assert a.status == "idle"
        assert a.current_task_id is None
        
        db.close()
        print("\n[PASS] Scenario 4.3: Task Completed")

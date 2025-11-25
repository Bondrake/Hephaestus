import pytest
import os
import subprocess
import time
import requests
import shutil
from pathlib import Path
import httpx

# Constants
SERVER_PORT = 8002 # Use a different port to avoid conflict with session server
SERVER_URL = f"http://localhost:{SERVER_PORT}"
TEST_DB_PATH = "test_workflows.db"

def get_example_workflows():
    """Get list of example workflow directories."""
    workflows_dir = Path("example_workflows")
    return [d.name for d in workflows_dir.iterdir() if d.is_dir() and (d / "phases.py").exists()]

@pytest.mark.parametrize("workflow_name", get_example_workflows())
def test_workflow_lifecycle(workflow_name):
    """Test the lifecycle of a specific example workflow."""
    print(f"\nTesting workflow: {workflow_name}")
    
    # 1. Setup Environment
    env = os.environ.copy()
    env["DATABASE_PATH"] = TEST_DB_PATH
    env["HEPHAESTUS_TEST_DB"] = TEST_DB_PATH
    env["DEFAULT_CLI_TOOL"] = "stub"
    env["HEPHAESTUS_LLM_PROVIDER"] = "stub"
    env["LLM_PROVIDER"] = "stub"  # Required by simple_config.py
    env["OPENAI_API_KEY"] = "stub" # Force stub mode
    env["HEPHAESTUS_PHASES_FOLDER"] = str(Path(os.getcwd()) / "example_workflows" / workflow_name)
    env["HEPHAESTUS_PROJECT_ROOT"] = os.getcwd()
    env["HEPHAESTUS_CLI_TOOL"] = "stub"
    env["PORT"] = str(SERVER_PORT)
    
    # Clean up previous DB
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        
    # 2. Start Server
    print("Starting server...")
    import sys
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.mcp.server:app", "--host", "0.0.0.0", "--port", str(SERVER_PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # 3. Wait for Startup
        for _ in range(30):
            try:
                requests.get(f"{SERVER_URL}/docs")
                break
            except requests.ConnectionError:
                time.sleep(1)
        else:
            proc.terminate()
            stdout, stderr = proc.communicate()
            print(f"Server stdout: {stdout}")
            print(f"Server stderr: {stderr}")
            raise RuntimeError("Server failed to start")
            
        print("Server started.")
        
        # 4. Run Test Logic
        with httpx.Client(base_url=SERVER_URL, timeout=30.0) as client:
            # Create Ticket
            payload = {
                "title": f"Test {workflow_name}",
                "description": "Test description",
                "priority": "medium",
                "ticket_type": "task",
                "workflow_id": "default" # The server loads the phases as 'default' workflow usually? 
                                         # Wait, PhaseLoader loads phases, but does it create a workflow entry?
                                         # In conftest.py we manually inserted a workflow.
                                         # Here the server might not have a workflow in DB yet.
            }
            
            # We need to ensure a workflow exists in the DB that uses these phases.
            # The server startup doesn't auto-create a workflow in DB from the folder, 
            # it just loads the definition into memory/PhaseManager?
            # Let's check server.py again.
            # It loads PhaseLoader.load_phases_from_folder.
            # But does it persist to DB?
            
            # Actually, for the test to work, we need to register the workflow in the DB.
            # We can use the API to create a workflow if available, or seed the DB.
            # Since we are starting fresh DB, we need to seed it.
            
            # Helper to seed DB via API or direct SQL?
            # Direct SQL is safer given we have the file path.
            import sqlite3
            conn = sqlite3.connect(TEST_DB_PATH)
            cursor = conn.cursor()
            
            # Create Agent
            cursor.execute("INSERT INTO agents (id, status, cli_type, agent_type, created_at, system_prompt) VALUES (?, ?, ?, ?, ?, ?)", 
                          ('test-agent', 'idle', 'stub', 'phase', '2024-01-01 00:00:00', 'You are a test agent'))
            
            # Create Workflow Definition
            cursor.execute("INSERT INTO workflow_definitions (id, name, phases_config, workflow_config, created_at) VALUES (?, ?, ?, ?, ?)",
                          ('default-def', 'Default', '[]', '{}', '2024-01-01 00:00:00'))
                          
            # Create Workflow linked to the loaded phases
            # The server loaded phases from env var. 
            # The Task creation needs a workflow_id.
            cursor.execute("INSERT INTO workflows (id, name, phases_folder_path, status, definition_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                          ('default', 'Default Workflow', env["HEPHAESTUS_PHASES_FOLDER"], 'active', 'default-def', '2024-01-01 00:00:00'))
            
            # Create Board Config
            import json
            columns = [{"id": "todo", "name": "To Do"}, {"id": "in_progress", "name": "In Progress"}, {"id": "done", "name": "Done"}]
            ticket_types = [{"id": "task", "name": "Task"}, {"id": "bug", "name": "Bug"}]
            cursor.execute("INSERT INTO board_configs (id, workflow_id, name, columns, ticket_types, initial_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          ('default-board', 'default', 'Default Board', json.dumps(columns), json.dumps(ticket_types), 'todo', '2024-01-01 00:00:00', '2024-01-01 00:00:00'))
            
            conn.commit()
            
            # Debug: Verify insertion
            cursor.execute("SELECT * FROM workflow_definitions WHERE id='default-def'")
            print(f"DEBUG: Definition in DB: {cursor.fetchone()}")
            
            cursor.execute("SELECT * FROM workflows WHERE id='default'")
            row = cursor.fetchone()
            print(f"DEBUG: Workflow in DB: {row}")
            
            conn.close()
            
            # Now create ticket
            headers = {"X-Agent-ID": "test-agent"}
            resp = client.post("/api/tickets/create", json=payload, headers=headers)
            assert resp.status_code == 200, f"Create ticket failed: {resp.text}"
            ticket_id = resp.json()["ticket_id"]
            
            # Create Task
            task_payload = {
                "task_description": "Do work",
                "done_definition": "Done",
                "ticket_id": ticket_id,
                "workflow_id": "default",
                "ai_agent_id": "test-agent"
            }
            resp = client.post("/create_task", json=task_payload, headers=headers)
            assert resp.status_code == 200, f"Create task failed: {resp.text}"
            
            # Verify it moves to in_progress (Agent picks it up)
            # We need to wait for the agent loop.
            print("Waiting for agent pickup...")
            for i in range(60):
                resp = client.get(f"/api/tickets/{ticket_id}")
                status = resp.json()["ticket"]["status"]
                if status != "todo":
                    break
                time.sleep(1)
            
            assert status in ["in_progress", "done"], f"Ticket stuck in todo for {workflow_name}"
            print(f"Workflow {workflow_name} passed basic lifecycle.")

    except Exception as e:
        print(f"\nTest failed: {e}")
        # Print server logs
        if proc.poll() is None:
            proc.terminate()
        stdout, stderr = proc.communicate()
        print(f"Server stdout:\n{stdout}")
        print(f"Server stderr:\n{stderr}")
        raise e

    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

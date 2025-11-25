import pytest
import subprocess
import time
import os
import signal
import requests
from pathlib import Path

# Constants
SERVER_PORT = 8001
SERVER_URL = f"http://localhost:{SERVER_PORT}"
TEST_DB_PATH = "test_e2e.db"

@pytest.fixture(scope="session")
def e2e_server():
    """Start the server as a subprocess for E2E testing."""
    
    # 1. Setup Environment
    # Set environment variables for the server process
    env = os.environ.copy()
    env["DATABASE_PATH"] = TEST_DB_PATH
    env["HEPHAESTUS_TEST_DB"] = TEST_DB_PATH
    env["DEFAULT_CLI_TOOL"] = "stub"
    env["HEPHAESTUS_LLM_PROVIDER"] = "stub" # We need to support this in get_llm_provider
    os.environ["HEPHAESTUS_PHASES_FOLDER"] = "/tmp"
    os.environ["HEPHAESTUS_PROJECT_ROOT"] = os.getcwd()
    env["HEPHAESTUS_CLI_TOOL"] = "stub"
    env["PORT"] = str(SERVER_PORT)
    
    # Clean up previous DB
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Clean up previous server log
    if os.path.exists("hephaestus_server.log"):
        open("hephaestus_server.log", "w").close()
        
    # 2. Start Server
    # Assuming we can run via uvicorn directly or a wrapper script
    # We'll use python -m uvicorn ...
    import sys
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.mcp.server:app", "--host", "0.0.0.0", "--port", str(SERVER_PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # 3. Wait for Startup
    max_retries = 30
    # 3. Wait for Server
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
        
    # Debug: Check if DB exists and has tables
    import sqlite3
    if os.path.exists(TEST_DB_PATH):
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        
        # Seed data
        try:
            # 1. Create Agent
            # Agent table: id, created_at, system_prompt, status, cli_type, agent_type
            cursor.execute("""
                INSERT OR IGNORE INTO agents (id, created_at, system_prompt, status, cli_type, agent_type) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('e2e-test-agent', '2024-01-01 00:00:00', 'You are a test agent', 'idle', 'stub', 'phase'))
            
            # 2. Create Workflow Definition (needed for Workflow)
            # WorkflowDefinition: id, name, description, phases_config, workflow_config, created_at
            cursor.execute("""
                INSERT OR IGNORE INTO workflow_definitions (id, name, description, phases_config, workflow_config, created_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('default-def', 'Default Definition', 'Default', '[]', '{}', '2024-01-01 00:00:00'))

            # 3. Create Workflow
            # Workflow: id, name, description, phases_folder_path, status, definition_id, created_at
            cursor.execute("""
                INSERT OR IGNORE INTO workflows (id, name, description, phases_folder_path, status, definition_id, created_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('default', 'Default Workflow', 'Test Workflow', '/tmp', 'active', 'default-def', '2024-01-01 00:00:00'))
            
            # 4. Create Board Config
            # BoardConfig: id, workflow_id, name, columns, ticket_types, initial_status, created_at, updated_at
            import json
            columns = [{"id": "todo", "name": "To Do"}, {"id": "in_progress", "name": "In Progress"}, {"id": "done", "name": "Done"}]
            ticket_types = [{"id": "task", "name": "Task"}, {"id": "bug", "name": "Bug"}]
            cursor.execute("""
                INSERT OR IGNORE INTO board_configs (id, workflow_id, name, columns, ticket_types, initial_status, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ('default-board', 'default', 'Default Board', json.dumps(columns), json.dumps(ticket_types), 'todo', '2024-01-01 00:00:00', '2024-01-01 00:00:00'))
            
            conn.commit()
        except Exception as e:
            print(f"Failed to seed data: {e}")
            
        conn.close()

    yield SERVER_URL
    
    # 4. Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        
    stdout, stderr = proc.communicate()
    print("\n=== SERVER STDOUT ===")
    print(stdout)
    print("\n=== SERVER STDERR ===")
    print(stderr)
        
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

import httpx

@pytest.fixture
def api_client(e2e_server):
    """Return a httpx client configured for the E2E server."""
    with httpx.Client(base_url=e2e_server, timeout=10.0) as client:
        yield client

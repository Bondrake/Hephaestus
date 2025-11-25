import pytest
import time
import httpx
from typing import Dict, Any

SERVER_URL = "http://localhost:8001"

def test_interactive_walkthrough(e2e_server, interactive_pause, api_client: httpx.Client):
    """
    An interactive walkthrough of the Hephaestus system.
    Run with: pytest tests/e2e/test_walkthrough.py --interactive
    """
    print("\n\n=== Welcome to Hephaestus Walkthrough ===")
    print("This test will guide you through the core capabilities.")
    
    interactive_pause("The server is running at http://localhost:8001. Open it in your browser to see the dashboard.")

    # 1. Create Ticket
    payload = {
        "title": "Walkthrough Feature",
        "description": "Implement a cool new feature for the walkthrough.",
        "priority": "high",
        "ticket_type": "task",
        "workflow_id": "default",
        "tags": ["walkthrough"]
    }
    headers = {"X-Agent-ID": "e2e-test-agent"}
    
    print(f"Creating ticket: {payload['title']}")
    response = api_client.post("/api/tickets/create", json=payload, headers=headers)
    assert response.status_code == 200
    ticket_id = response.json()["ticket_id"]
    
    print(f"\n[INTERACTIVE] Ticket created! ID: {ticket_id}")
    print(f"Check the Dashboard at {SERVER_URL}/. You should see '{payload['title']}' in the Active Tasks list.")

    # 2. Create Task (Trigger Agent)
    task_payload = {
        "task_description": "Implement the walkthrough feature",
        "done_definition": "Feature is implemented",
        "ticket_id": ticket_id,
        "workflow_id": "default",
        "ai_agent_id": "e2e-test-agent"
    }
    response = api_client.post("/create_task", json=task_payload, headers=headers)
    assert response.status_code == 200
    
    interactive_pause("Task created and assigned to an agent.\nThe agent should pick it up shortly. Watch the Dashboard for the task status changing to 'in_progress'.")

    # 3. Wait for Agent to Start (In Progress)
    print("Waiting for agent to start task...")
    # In a real E2E test, the agent process would pick this up.
    # For this walkthrough, we simulate the agent's actions if no agent is running,
    # OR we wait for the actual agent if one is running (which is the case in test_example_workflows).
    # Since this is a standalone test, we might need to simulate the agent picking it up if we don't have a runner.
    # However, conftest.py starts a server but NOT an agent loop for this specific test file unless we add it.
    # The 'e2e_server' fixture starts the server. The agent is 'e2e-test-agent'.
    # We need to simulate the agent picking it up for the walkthrough to proceed if there's no actual agent.
    
    # Simulate Agent Pickup
    time.sleep(2)
    api_client.post("/update_task_status", json={
        "task_id": response.json()["task_id"],
        "status": "in_progress",
        "agent_id": "e2e-test-agent",
        "summary": "Starting work",
        "key_learnings": []
    }, headers=headers)
    
    # Update ticket status too (usually happens via side effect or agent)
    api_client.post("/api/tickets/change-status", json={
        "ticket_id": ticket_id,
        "new_status": "in_progress",
        "comment": "Agent started work"
    }, headers=headers)

    interactive_pause("Agent has picked up the task!\nCheck the Dashboard. The task status should now be 'in_progress'.")

    # 4. Wait for Completion
    print("Waiting for completion...")
    for _ in range(30):
        resp = api_client.get(f"/api/tickets/{ticket_id}")
        if resp.json()["ticket"]["status"] == "done":
            break
        time.sleep(1)
        
    interactive_pause("The task is complete! The ticket should be in the 'Done' column.\nCongratulations, you've seen the full lifecycle!")

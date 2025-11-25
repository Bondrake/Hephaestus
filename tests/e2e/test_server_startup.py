import pytest
import requests

def test_server_health(api_client):
    """Verify server is healthy and running."""
    # Check /docs which is standard in FastAPI
    response = api_client.get("/docs")
    assert response.status_code == 200
    
def test_create_ticket(api_client):
    """Verify we can create a ticket using the stub LLM."""
    payload = {
        "workflow_id": "default",
        "title": "E2E Test Ticket",
        "description": "This is a test ticket created by E2E suite",
        "priority": "medium",
        "ticket_type": "task",
        "tags": ["e2e"]
    }
    
    headers = {
        "X-Agent-ID": "e2e-test-agent"
    }
    
    response = api_client.post("/api/tickets/create", json=payload, headers=headers)
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    assert response.status_code in [200, 201]
    data = response.json()
    assert data["success"] is True
    assert "ticket_id" in data

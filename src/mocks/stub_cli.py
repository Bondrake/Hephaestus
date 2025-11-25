#!/usr/bin/env python3
import sys
import time
import json
import os
import httpx
import re

def main():
    # Log to fixed absolute path
    log_file = "/Users/ent/code/gh/Hephaestus/stub_cli.log"
    with open(log_file, "w") as f:
        f.write("STUB CLI STARTED\n")
    
    print("STUB CLI STARTED")
    print("Ready")
    sys.stdout.flush()

    task_id = None
    agent_id = None
    
    port = os.environ.get("PORT", "8001")
    API_URL = f"http://localhost:{port}"
    
    with open(log_file, "a") as f:
        f.write(f"API_URL: {API_URL}\n")

    # Read input loop
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            # print(f"Received: {line.strip()}") # Debug
            with open(log_file, "a") as f:
                f.write(f"Received: {line}")
            
            sys.stdout.flush()

            # Parse IDs
            if "Task ID:" in line:
                task_id = line.split("Task ID:")[1].strip()
                with open(log_file, "a") as f:
                    f.write(f"Parsed Task ID: {task_id}\n")
            
            if "Agent ID:" in line:
                agent_id = line.split("Agent ID:")[1].strip()
                with open(log_file, "a") as f:
                    f.write(f"Parsed Agent ID: {agent_id}\n")

            # Check for end of prompt
            if "Begin working on your task now" in line or "User:" in line or "System:" in line:
                # Prompt received, time to act
                if task_id and agent_id:
                    with open(log_file, "a") as f:
                        f.write(f"Processing task {task_id} for agent {agent_id}\n")
                    
                    # 1. Get Ticket ID from Task
                    ticket_id = None
                    try:
                        # We need to fetch the task to get the ticket_id
                        # The server has a /task_progress endpoint or similar?
                        # Or we can query the ticket API if we knew the ticket ID.
                        # But we only have task_id.
                        # Let's assume the server exposes a way to get task details.
                        # For now, let's try to hit the /task_progress endpoint
                        resp = httpx.get(f"{API_URL}/task_progress?task_id={task_id}")
                        if resp.status_code == 200:
                            task_data = resp.json()
                            # Assuming task_data contains ticket_id or we can infer it
                            # The current /task_progress might not return ticket_id.
                            # We might need to update the server to return it.
                            # Let's check what it returns.
                            with open(log_file, "a") as f:
                                f.write(f"Task progress resp: {resp.text}\n")
                            
                            ticket_id = task_data.get("ticket_id")
                    except Exception as e:
                        with open(log_file, "a") as f:
                            f.write(f"Error fetching task info: {e}\n")

                    # 2. Update Ticket Status to In Progress
                    if ticket_id:
                        try:
                            httpx.post(f"{API_URL}/api/tickets/change-status", json={
                                "ticket_id": ticket_id,
                                "new_status": "in_progress",
                                "comment": "Starting work on this ticket via Stub CLI."
                            }, headers={"X-Agent-ID": agent_id})
                            with open(log_file, "a") as f:
                                f.write(f"Updated ticket {ticket_id} to in_progress\n")
                        except Exception as e:
                            with open(log_file, "a") as f:
                                f.write(f"Error updating ticket status: {e}\n")
                                if hasattr(e, 'response') and e.response:
                                    f.write(f"Response body: {e.response.text}\n")

                    # Simulate work
                    time.sleep(1)
                    
                    # 3. Update Ticket Status to Done
                    if ticket_id:
                        try:
                            httpx.post(f"{API_URL}/api/tickets/change-status", json={
                                "ticket_id": ticket_id,
                                "new_status": "done",
                                "comment": "Completed work on this ticket via Stub CLI."
                            }, headers={"X-Agent-ID": agent_id})
                            with open(log_file, "a") as f:
                                f.write(f"Updated ticket {ticket_id} to done\n")
                        except Exception as e:
                            with open(log_file, "a") as f:
                                f.write(f"Error updating ticket status: {e}\n")
                                if hasattr(e, 'response') and e.response:
                                    f.write(f"Response body: {e.response.text}\n")

                    # 4. Mark Task as Done
                    try:
                        httpx.post(f"{API_URL}/update_task_status", json={
                            "task_id": task_id,
                            "status": "done",
                            "summary": "Task completed by Stub CLI",
                            "key_learnings": ["Stub CLI works"]
                        }, headers={"X-Agent-ID": agent_id})
                        with open(log_file, "a") as f:
                            f.write(f"Updated task {task_id} to completed\n")
                    except Exception as e:
                        with open(log_file, "a") as f:
                            f.write(f"Error updating task status: {e}\n")
                            if hasattr(e, 'response') and e.response:
                                f.write(f"Response body: {e.response.text}\n")
                    
                    print("Task Completed")
                    sys.stdout.flush()
                    
                    # Reset for next task (if any)
                    task_id = None
                    # agent_id = None # Agent ID stays the same

        except Exception as e:
            with open(log_file, "a") as f:
                f.write(f"Error in main loop: {e}\n")
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    main()

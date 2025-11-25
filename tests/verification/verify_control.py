"""Verification script for control channel."""

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.control import (
    AuthorityLevel,
    ControlChannel,
    EvidenceItem,
    ReasonCode,
    RequiredAction,
    SteeringEvent,
)


async def verify_control():
    print("🧪 Verifying Control Channel...")
    
    project_root = Path.cwd()
    control_dir = project_root / ".hephaestus" / "control"
    
    # Clean up previous run
    if control_dir.exists():
        shutil.rmtree(control_dir)
    if os.path.exists("dummy_agent.log"):
        os.remove("dummy_agent.log")
        
    # Initialize channel
    channel = ControlChannel(control_dir)
    
    work_item_id = "test-work-item-123"
    agent_id = "test-agent-456"
    
    # Start runtime wrapper with dummy agent
    wrapper_path = project_root / "src" / "agents" / "runtime_wrapper.py"
    dummy_agent_path = project_root / "tests" / "verification" / "dummy_agent.py"
    
    cmd = f"python3 {wrapper_path} --agent-id {agent_id} --work-item-id {work_item_id} --cmd 'python3 {dummy_agent_path}'"
    
    print(f"   🚀 Starting runtime wrapper...")
    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for startup
    time.sleep(2)
    
    # Create event
    from datetime import datetime, timedelta
    event = SteeringEvent(
        reason_code=ReasonCode.STUCK,
        evidence=[EvidenceItem(kind="log", content="Agent is looping")],
        required_action=RequiredAction.PAUSE,
        parameters={},
        deadline=datetime.utcnow() + timedelta(minutes=5),
        authority=AuthorityLevel.MANDATORY
    )
    
    print(f"   📨 Sending steering event {event.id}...")
    
    # Send event (async)
    # We can't use channel.send() easily here because it waits for ack, 
    # and we want to verify the ack creation separately or run in parallel.
    # But channel.send() IS the verification that ack works.
    
    try:
        ack = await channel.send(work_item_id, event)
        print(f"   ✅ Received acknowledgment: {ack.status}")
        
        # Verify dummy agent received the message
        time.sleep(1) # Give time for file write
        
        if os.path.exists("dummy_agent.log"):
            with open("dummy_agent.log", "r") as f:
                content = f.read()
                if "SUPERVISOR INTERVENTION" in content:
                    print("   ✅ Agent received intervention message")
                else:
                    print("   ❌ Agent did NOT receive intervention message")
                    print(f"   Log content: {content}")
        else:
            print("   ❌ dummy_agent.log not found")
            
    except Exception as e:
        print(f"   ❌ Verification failed: {e}")
    finally:
        print("   🛑 Stopping process...")
        process.terminate()
        try:
            outs, errs = process.communicate(timeout=2)
            print(f"Wrapper stdout: {outs}")
            print(f"Wrapper stderr: {errs}")
        except subprocess.TimeoutExpired:
            process.kill()

if __name__ == "__main__":
    asyncio.run(verify_control())

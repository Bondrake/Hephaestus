"""Runtime wrapper for CLI agents to handle control events."""

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.control import AckStatus, Acknowledgment, ControlChannel, SteeringEvent


class AgentRuntime:
    """Wraps a CLI agent to provide control channel capabilities."""

    def __init__(self, agent_id: str, work_item_id: str, cli_command: str):
        self.agent_id = agent_id
        self.work_item_id = work_item_id
        self.cli_command = cli_command
        self.process: Optional[subprocess.Popen] = None
        self.running = True
        
        # Initialize control channel
        # Assuming project root is current directory or parent
        self.project_root = Path.cwd()
        self.control_channel = ControlChannel(self.project_root / ".hephaestus" / "control")

    def start(self):
        """Start the agent runtime."""
        print(f"[Runtime] Starting agent {self.agent_id} for work item {self.work_item_id}", file=sys.stderr)
        print(f"[Runtime] Command: {self.cli_command}", file=sys.stderr)

        # Start the CLI process
        # We use shell=True to handle complex commands with pipes/redirection if needed
        # But for security and signal handling, list of args is better if possible.
        # Given the complex commands from cli_interface (e.g. with $(cat ...)), shell=True is likely needed.
        self.process = subprocess.Popen(
            self.cli_command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            bufsize=1  # Line buffered
        )

        # Start control polling thread
        poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        poll_thread.start()

        # Forward stdin to process
        try:
            while self.running and self.process.poll() is None:
                # This is a blocking read, which is fine for a simple wrapper
                # In a real implementation, we might use select or asyncio
                line = sys.stdin.readline()
                if not line:
                    break
                if self.process.stdin:
                    self.process.stdin.write(line)
                    self.process.stdin.flush()
        except KeyboardInterrupt:
            self.stop()
        except Exception as e:
            print(f"[Runtime] Error in input forwarding: {e}", file=sys.stderr)
        finally:
            self.stop()

    def stop(self):
        """Stop the runtime and child process."""
        self.running = False
        if self.process and self.process.poll() is None:
            print("[Runtime] Terminating agent process...", file=sys.stderr)
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _poll_loop(self):
        """Poll for control events."""
        # Create a new event loop for this thread to run async code
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(self._async_poll_loop())
        loop.close()

    async def _async_poll_loop(self):
        """Async polling loop."""
        control_file = self.control_channel._get_control_file_path(self.work_item_id)
        last_mtime = 0

        while self.running:
            try:
                if control_file.exists():
                    mtime = control_file.stat().st_mtime
                    if mtime > last_mtime:
                        last_mtime = mtime
                        await self._handle_control_file(control_file)
                
                await asyncio.sleep(1)
            except Exception as e:
                print(f"[Runtime] Error in poll loop: {e}", file=sys.stderr)
                await asyncio.sleep(5)

    async def _handle_control_file(self, control_file: Path):
        """Handle a new control file."""
        try:
            with open(control_file, "r") as f:
                import json
                data = json.load(f)
                event = SteeringEvent(**data)

            print(f"\n[Runtime] Received steering event: {event.reason_code}", file=sys.stderr)
            
            # Inject message to agent
            message = self._format_event_message(event)
            if self.process and self.process.stdin:
                self.process.stdin.write(f"\n\n{message}\n\n")
                self.process.stdin.flush()

            # Auto-acknowledge receipt
            ack = Acknowledgment(
                event_id=event.id,
                status=AckStatus.ACKNOWLEDGED,
                message="Event received by runtime wrapper",
                timestamp=datetime.utcnow()
            )
            
            ack_file = self.control_channel._get_ack_file_path(event.id)
            with open(ack_file, "w") as f:
                f.write(ack.model_dump_json(indent=2))

        except Exception as e:
            print(f"[Runtime] Failed to handle control event: {e}", file=sys.stderr)

    def _format_event_message(self, event: SteeringEvent) -> str:
        """Format event as a message to the agent."""
        evidence_str = "\n".join([f"- {e.kind}: {e.content}" for e in event.evidence])
        
        return f"""
⚠️ SUPERVISOR INTERVENTION ⚠️
Reason: {event.reason_code.value}
Required Action: {event.required_action.value}
Deadline: {event.deadline}

Evidence:
{evidence_str}

Parameters:
{event.parameters}

Please acknowledge and take the required action immediately.
"""

def main():
    parser = argparse.ArgumentParser(description="Agent Runtime Wrapper")
    parser.add_argument("--agent-id", required=True, help="Agent ID")
    parser.add_argument("--work-item-id", required=True, help="Work Item ID")
    parser.add_argument("--cmd", required=True, help="CLI command to run")
    
    args = parser.parse_args()
    
    runtime = AgentRuntime(args.agent_id, args.work_item_id, args.cmd)
    runtime.start()

if __name__ == "__main__":
    main()

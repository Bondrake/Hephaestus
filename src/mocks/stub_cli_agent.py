from src.interfaces.cli_interface import CLIAgentInterface
import os
import sys
from pathlib import Path
from typing import Optional

class StubCLIAgent(CLIAgentInterface):
    """Stub CLI agent for testing purposes."""
    
    def get_launch_command(self, system_prompt: str, task_id: str) -> str:
        """Get the command to launch the stub CLI agent.
        
        Args:
            system_prompt: The system prompt to use
            task_id: The ID of the task being processed
            
        Returns:
            Command string to launch the agent
        """
        # Get path to stub_cli.py
        # It's in the same directory as this file
        current_dir = Path(__file__).parent
        stub_cli_path = current_dir / "stub_cli.py"
        
        # Use sys.executable to ensure we use the same python environment
        return f"{sys.executable} {stub_cli_path}"

    def get_health_check_pattern(self) -> str:
        """Return health check pattern for Stub CLI."""
        return r"(Ready|STUB CLI STARTED)"

    def format_message(self, message: str) -> str:
        """Format message for Stub CLI."""
        return message

    def get_stuck_patterns(self) -> list[str]:
        """Return stuck patterns for Stub CLI."""
        return [r"Error:"]

    def parse_output(self, output: str) -> dict:
        """Parse Stub CLI output."""
        return {
            "last_message": output,
            "is_waiting": True,
            "total_lines": len(output.split('\n'))
        }

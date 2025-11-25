"""Filesystem sensor for capturing file access and modifications."""

import time
from pathlib import Path
from typing import List, Set

from src.core.models import FilesystemSnapshot, NetworkCall


class FilesystemSensor:
    """Sensor for capturing filesystem activity."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._files_read: Set[Path] = set()
        self._files_written: Set[Path] = set()
        self._executables_run: List[str] = []
        self._network_calls: List[NetworkCall] = []

    def log_read(self, path: Path):
        """Log a file read event."""
        self._files_read.add(path)

    def log_write(self, path: Path):
        """Log a file write event."""
        self._files_written.add(path)

    def log_execution(self, command: str):
        """Log an execution event."""
        self._executables_run.append(command)

    def log_network_call(self, call: NetworkCall):
        """Log a network call."""
        self._network_calls.append(call)

    def capture_snapshot(self, clear_after: bool = True) -> FilesystemSnapshot:
        """Capture current filesystem activity snapshot."""
        
        # In a real implementation, we might also scan for recently modified files
        # as a backup if explicit logging is missed.
        
        snapshot = FilesystemSnapshot(
            files_read=list(self._files_read),
            files_written=list(self._files_written),
            executables_run=list(self._executables_run),
            network_calls=list(self._network_calls)
        )

        if clear_after:
            self._files_read.clear()
            self._files_written.clear()
            self._executables_run.clear()
            self._network_calls.clear()

        return snapshot

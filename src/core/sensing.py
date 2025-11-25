"""Sensing pipeline for building trajectory snapshots."""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.core.models import (
    Constraint,
    Dependency,
    PhaseContract,
    SensorsSnapshot,
    TaskRun,
    TrajectorySnapshot,
    WorkItem,
)
from src.sensors.ci_sensor import CISensor
from src.sensors.filesystem_sensor import FilesystemSensor
from src.sensors.git_sensor import GitSensor


class SnapshotBuilder:
    """Aggregates sensor data into trajectory snapshots."""

    def __init__(
        self,
        git_sensor: GitSensor,
        ci_sensor: CISensor,
        fs_sensor: FilesystemSensor,
    ):
        self.git_sensor = git_sensor
        self.ci_sensor = ci_sensor
        self.fs_sensor = fs_sensor

    def build_snapshot(
        self,
        work_item: WorkItem,
        task_runs: List[TaskRun],
        constraints: List[Constraint],
        dependencies: List[Dependency],
        phase_contract: PhaseContract,
        since_commit: Optional[str] = None
    ) -> TrajectorySnapshot:
        """Build a snapshot of the current trajectory."""

        # Capture sensor data
        git_snapshot = self.git_sensor.capture_snapshot(since_commit)
        ci_snapshot = self.ci_sensor.capture_snapshot()
        fs_snapshot = self.fs_sensor.capture_snapshot()

        sensors_snapshot = SensorsSnapshot(
            git=git_snapshot,
            ci=ci_snapshot,
            fs=fs_snapshot,
            timestamp=datetime.utcnow()
        )

        return TrajectorySnapshot(
            work_item=work_item,
            task_runs=task_runs,
            constraints=constraints,
            dependencies=dependencies,
            sensors=sensors_snapshot,
            phase_contract=phase_contract
        )

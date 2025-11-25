"""Verification script for sensing infrastructure."""

import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.models import PhaseContract, PhaseType, WorkItem
from src.core.sensing import SnapshotBuilder
from src.sensors.ci_sensor import CISensor
from src.sensors.filesystem_sensor import FilesystemSensor
from src.sensors.git_sensor import GitSensor


def main():
    """Verify sensing pipeline."""
    print("🧪 Verifying Sensing Infrastructure...")
    
    project_root = Path.cwd()
    print(f"   Project Root: {project_root}")
    
    # Initialize sensors
    try:
        git_sensor = GitSensor(project_root)
        ci_sensor = CISensor(project_root / "junit.xml") # Dummy path
        fs_sensor = FilesystemSensor(project_root)
        
        print("   ✅ Sensors initialized")
    except Exception as e:
        print(f"   ❌ Sensor initialization failed: {e}")
        return
        
    # Initialize builder
    builder = SnapshotBuilder(git_sensor, ci_sensor, fs_sensor)
    
    # Create dummy work item
    work_item = WorkItem(
        title="Verification Task",
        description="Verify sensing infrastructure",
        phase=PhaseType.EXECUTION
    )
    
    # Create dummy phase contract
    contract = PhaseContract(
        phase=PhaseType.EXECUTION,
        done_criteria=["Verify sensors"],
        allowed_tools=["python"],
        timeout_seconds=60
    )
    
    # Build snapshot
    try:
        print("   📸 Capturing snapshot...")
        snapshot = builder.build_snapshot(
            work_item=work_item,
            task_runs=[],
            constraints=[],
            dependencies=[],
            phase_contract=contract
        )
        
        print("   ✅ Snapshot captured successfully")
        print(f"   Git Commits: {len(snapshot.sensors.git.commits)}")
        print(f"   Touched Files: {len(snapshot.sensors.git.touched_files)}")
        print(f"   Timestamp: {snapshot.sensors.timestamp}")
        
    except Exception as e:
        print(f"   ❌ Snapshot capture failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

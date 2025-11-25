"""Verification script for ProjectSupervisor."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.core.models import (
    PhaseType,
    ResourceMap,
    WorkItem,
    WorkItemStatus,
)
from src.core.project_supervisor import ProjectSupervisor


async def verify_project_supervisor():
    print("🧪 Verifying ProjectSupervisor...")
    
    # 1. Setup Supervisor
    supervisor = ProjectSupervisor()
    
    # 2. Create Work Items
    w1 = WorkItem(title="Task 1", description="Edit auth", phase=PhaseType.EXECUTION, status=WorkItemStatus.IN_PROGRESS)
    w2 = WorkItem(title="Task 2", description="Edit auth too", phase=PhaseType.EXECUTION, status=WorkItemStatus.IN_PROGRESS)
    w3 = WorkItem(title="Task 3", description="Edit db", phase=PhaseType.EXECUTION, status=WorkItemStatus.IN_PROGRESS)
    
    work_items = [w1, w2, w3]
    
    # 3. Create Resource Map (Simulate file access)
    resources = ResourceMap()
    # Task 1 writes to auth.py
    resources.file_access["src/auth.py"] = [{"work_item_id": w1.id, "mode": "write"}]
    # Task 2 writes to auth.py (Conflict!)
    resources.file_access["src/auth.py"].append({"work_item_id": w2.id, "mode": "write"})
    # Task 3 reads db.py
    resources.file_access["src/db.py"] = [{"work_item_id": w3.id, "mode": "read"}]
    
    # 4. Run Analysis
    print("\n   🏃 Running Analysis...")
    finding = await supervisor.analyze(work_items, [], resources)
    
    # 5. Verify Contention
    print("\n   🔍 Checking Contention...")
    if "src/auth.py" in finding.contention_map.conflicts:
        conflicting_ids = finding.contention_map.conflicts["src/auth.py"]
        if w1.id in conflicting_ids and w2.id in conflicting_ids:
            print("   ✅ Detected write-write conflict on src/auth.py")
        else:
            print(f"   ❌ Conflict detected but IDs mismatch: {conflicting_ids}")
    else:
        print("   ❌ Failed to detect conflict on src/auth.py")

    # 6. Verify Overlaps
    print("\n   🔍 Checking Overlaps...")
    overlap_found = False
    for overlap in finding.overlaps:
        if (overlap.work_item_1 == w1.id and overlap.work_item_2 == w2.id) or \
           (overlap.work_item_1 == w2.id and overlap.work_item_2 == w1.id):
            print(f"   ✅ Detected overlap between Task 1 and Task 2 (Score: {overlap.score:.2f})")
            overlap_found = True
            break
    
    if not overlap_found:
        print("   ❌ Failed to detect overlap between Task 1 and Task 2")

    # 7. Verify Recommendations
    print("\n   🔍 Checking Recommendations...")
    rec_found = False
    for rec in finding.recommendations:
        if "src/auth.py" in rec.reason and w1.id in rec.target_ids:
            print("   ✅ Generated recommendation for conflict")
            rec_found = True
            break
            
    if not rec_found:
        print("   ❌ Failed to generate recommendation")


if __name__ == "__main__":
    asyncio.run(verify_project_supervisor())

"""Project-level supervision."""

import logging
from datetime import datetime
from itertools import combinations
from typing import List, Optional

from src.core.models import (
    ContentionMap,
    Overlap,
    ProjectFinding,
    ProjectMetrics,
    ResourceMap,
    SystemActionKind,
    SystemRecommendation,
    WorkItem,
    WorkItemFinding,
)

logger = logging.getLogger(__name__)


class ProjectSupervisor:
    """System-level coherence and resource contention."""

    async def analyze(
        self,
        work_items: List[WorkItem],
        findings: List[WorkItemFinding],
        resources: ResourceMap,
    ) -> ProjectFinding:
        """Detect overlaps, contention, gaps in work graph."""

        # Step 1: Build contention map (deterministic)
        contention = self._build_contention_map(work_items, resources)

        # Step 2: Detect overlaps (file-based, not text-similarity)
        overlaps = self._detect_overlaps(work_items, resources)

        # Step 3: Check invariants (Stub)
        violations = []

        # Step 4: Generate recommendations based on contention
        recommendations = []
        for file, work_item_ids in contention.conflicts.items():
            recommendations.append(
                SystemRecommendation(
                    kind=SystemActionKind.PAUSE,
                    target_ids=work_item_ids,
                    reason=f"Write-write conflict on {file}",
                    evidence=work_item_ids,
                    confidence=1.0, # Deterministic conflict
                )
            )

        return ProjectFinding(
            timestamp=datetime.utcnow(),
            metrics=ProjectMetrics(
                wip_count=len([w for w in work_items if w.status == "in_progress"]),
                blocked_count=len([w for w in work_items if w.status == "blocked"]),
                throughput_7d=0.0, # Stub
                reopen_rate=0.0, # Stub
            ),
            contention_map=contention,
            overlaps=overlaps,
            violations=violations,
            recommendations=recommendations,
        )

    def _detect_overlaps(
        self,
        work_items: List[WorkItem],
        resources: ResourceMap,
    ) -> List[Overlap]:
        """Resource-based overlap detection."""
        overlaps = []

        for w1, w2 in combinations(work_items, 2):
            # Skip if not same phase (parallelism expected in exploration)
            if w1.phase != w2.phase:
                continue

            # File overlap (deterministic)
            files1 = set(resources.files_for(w1))
            files2 = set(resources.files_for(w2))
            file_overlap = len(files1 & files2)

            # Git merge conflicts (Stub)
            git_conflicts = False

            # Scope overlap (Stub for LLM)
            scope_overlap = 0.0

            # Combined score
            denom = max(len(files1), 1)
            overlap_score = (
                0.5 * (file_overlap / denom) +
                0.3 * (1.0 if git_conflicts else 0.0) +
                0.2 * scope_overlap
            )

            if overlap_score > 0.1: # Low threshold for testing
                overlaps.append(Overlap(
                    work_item_1=w1.id,
                    work_item_2=w2.id,
                    score=overlap_score,
                    file_overlap=file_overlap,
                    git_conflicts=git_conflicts,
                    scope_overlap=scope_overlap,
                ))

        return overlaps

    def _build_contention_map(
        self,
        work_items: List[WorkItem],
        resources: ResourceMap,
    ) -> ContentionMap:
        """Who is reading/writing what."""
        contention = ContentionMap()

        for work_item in work_items:
            for file in resources.files_for(work_item):
                mode = resources.access_mode(work_item, file)  # read | write
                contention.add(file, work_item.id, mode)

        # Detect conflicts
        for file, access_list in contention.items():
            writers = [a for a in access_list if a["mode"] == "write"]
            if len(writers) > 1:
                contention.mark_conflict(file, writers)

        return contention

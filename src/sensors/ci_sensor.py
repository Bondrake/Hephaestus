"""CI sensor for capturing test results and build status."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from src.core.models import BuildStatus, CISnapshot, TestRun


class CISensor:
    """Sensor for capturing CI/Test results."""

    def __init__(self, report_path: Optional[Path] = None):
        self.report_path = report_path

    def capture_snapshot(self) -> CISnapshot:
        """Capture current CI state from report file."""
        
        test_runs = []
        build_status = BuildStatus.UNKNOWN
        lint_errors = 0
        
        if self.report_path and self.report_path.exists():
            try:
                tree = ET.parse(self.report_path)
                root = tree.getroot()
                
                # Parse JUnit XML format
                # Usually <testsuites> or <testsuite> root
                suites = root.findall('.//testsuite')
                if not suites and root.tag == 'testsuite':
                    suites = [root]
                    
                for suite in suites:
                    for case in suite.findall('testcase'):
                        test_id = f"{case.get('classname', 'unknown')}.{case.get('name', 'unknown')}"
                        duration = float(case.get('time', 0)) * 1000  # Convert to ms
                        
                        status = "passed"
                        error_msg = None
                        
                        failure = case.find('failure')
                        error = case.find('error')
                        skipped = case.find('skipped')
                        
                        if failure is not None:
                            status = "failed"
                            error_msg = failure.get('message')
                        elif error is not None:
                            status = "error"
                            error_msg = error.get('message')
                        elif skipped is not None:
                            status = "skipped"
                            error_msg = skipped.get('message')
                            
                        test_runs.append(TestRun(
                            test_id=test_id,
                            status=status,
                            duration_ms=duration,
                            error_message=error_msg
                        ))
                
                # Determine overall build status
                if any(t.status in ["failed", "error"] for t in test_runs):
                    build_status = BuildStatus.FAILURE
                else:
                    build_status = BuildStatus.SUCCESS
                    
            except Exception as e:
                print(f"Error parsing CI report: {e}")
                build_status = BuildStatus.UNKNOWN
        
        return CISnapshot(
            test_runs=test_runs,
            lint_errors=lint_errors,
            build_status=build_status,
            coverage_delta=None # TODO: Implement coverage parsing
        )

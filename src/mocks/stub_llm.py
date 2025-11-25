from typing import Dict, Any, List, Optional
import json
from src.interfaces.llm_interface import LLMProviderInterface
from src.core.models import LLMAnalysis

class StubLLMProvider(LLMProviderInterface):
    """Stub LLM provider for E2E testing."""
    
    def __init__(self):
        self.model = "stub-model"
        
    async def enrich_task(
        self,
        task_description: str,
        done_definition: str,
        context: List[str],
        phase_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "enriched_description": task_description,
            "completion_criteria": [done_definition],
            "agent_prompt": f"Complete this task: {task_description}",
            "required_capabilities": ["general"],
            "estimated_complexity": 1,
        }

    async def generate_embedding(self, text: str) -> List[float]:
        # Return a fixed size vector (OpenAI size)
        return [0.1] * 1536

    async def analyze_agent_state(
        self,
        agent_output: str,
        task_info: Dict[str, Any],
        project_context: str,
    ) -> Dict[str, Any]:
        return {
            "state": "healthy",
            "decision": "continue",
            "message": "",
            "reasoning": "Stub analysis",
            "confidence": 1.0,
        }

    async def generate_agent_prompt(
        self,
        task: Dict[str, Any],
        memories: List[Dict[str, Any]],
        project_context: str,
    ) -> str:
        return "You are a stub agent."

    def get_model_name(self) -> str:
        return self.model

    async def analyze_agent_trajectory(
        self,
        agent_output: str,
        accumulated_context: Dict[str, Any],
        past_summaries: List[Dict[str, Any]],
        task_info: Dict[str, Any],
        last_message_marker: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "current_phase": "execution",
            "trajectory_aligned": True,
            "alignment_score": 1.0,
            "alignment_issues": [],
            "steering_recommendation": None,
            "progress_estimate": 50,
            "last_claude_message_marker": "marker"
        }

    async def analyze_trajectory(
        self,
        context: Dict[str, Any],
    ) -> LLMAnalysis:
        return LLMAnalysis(
            is_aligned=True,
            alignment_score=1.0,
            confidence=1.0,
            issues=[],
            recommendations=[],
            reasoning="Stub trajectory analysis"
        )

    async def analyze_system_coherence(
        self,
        guardian_summaries: List[Dict[str, Any]],
        system_goals: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "duplicates": [],
            "coherence_score": 1.0,
            "termination_recommendations": [],
            "coordination_needs": []
        }

"""
CareLoop Agent Base Framework
Provides:
- Token budgeting and step limits per agent
- Task-scoped token acquisition from MCP gateway
- Structured JSON schema validation
- Free offline deterministic reasoning engine with optional LiteLLM/Gemini fallback
"""

import os
import json
from typing import Dict, Any, List, Optional
from services.gateway.scoping import token_manager
from services.control_plane.registry import agent_registry

class AgentBase:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.registry_entry = agent_registry.get_agent(agent_id)
        self.token_budget = self.registry_entry.token_budget_per_task if self.registry_entry else 2000
        self.step_limit = 5

    def get_scoped_token(self, task_id: str, patient_id: str, required_scopes: List[str]) -> str:
        """
        Requests task-scoped token from MCP gateway.
        """
        return token_manager.generate_task_token(
            agent_id=self.agent_id,
            task_id=task_id,
            patient_id=patient_id,
            scopes=required_scopes,
            ttl_seconds=300
        )

    def is_active(self) -> bool:
        entry = agent_registry.get_agent(self.agent_id)
        return entry.is_active and not entry.is_quarantined if entry else False

    def check_limits(self, tokens_used: int, steps_taken: int) -> bool:
        if steps_taken > self.step_limit:
            raise RuntimeError(f"Agent {self.agent_id} exceeded step limit of {self.step_limit}")
        if tokens_used > self.token_budget:
            raise RuntimeError(f"Agent {self.agent_id} exceeded token budget of {self.token_budget}")
        return True

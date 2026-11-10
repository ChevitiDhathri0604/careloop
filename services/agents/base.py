"""
CareLoop Agent Base Framework
Provides:
- Token budgeting and step limits per agent
- Task-scoped token acquisition from MCP gateway
- Structured JSON schema validation
- Integrated Multi-Provider LLM Gateway with provider switching & spend caps
"""

import os
import json
from typing import Dict, Any, List, Optional, Tuple
from services.gateway.scoping import token_manager
from services.control_plane.registry import agent_registry
from .llm_gateway import llm_gateway

class AgentBase:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.registry_entry = agent_registry.get_agent(agent_id)
        self.token_budget = self.registry_entry.token_budget_per_task if self.registry_entry else 2000
        self.step_limit = 5
        self.steps_taken = 0
        self.tokens_used_in_task = 0

    def get_scoped_token(self, task_id: str, patient_id: str, required_scopes: List[str]) -> str:
        """Requests task-scoped token from MCP gateway."""
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

    def call_llm(self, prompt: str, system_prompt: str = "", 
                 schema_instructions: str = "", model_tier: str = "small") -> Tuple[Dict[str, Any], int, str]:
        """
        Executes real LLM call via the LLM Gateway, checking step limit and agent token quota.
        """
        self.steps_taken += 1
        if self.steps_taken > self.step_limit:
            raise RuntimeError(f"Agent {self.agent_id} exceeded step limit of {self.step_limit}")

        data, tokens_used, provider = llm_gateway.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            schema_instructions=schema_instructions,
            model_tier=model_tier,
            agent_id=self.agent_id,
            max_tokens=self.token_budget - self.tokens_used_in_task
        )

        self.tokens_used_in_task += tokens_used
        if self.tokens_used_in_task > self.token_budget:
            print(f"[WARNING] Agent {self.agent_id} exceeded token budget: {self.tokens_used_in_task}/{self.token_budget}")

        return data, tokens_used, provider

    def check_limits(self, tokens_used: int, steps_taken: int) -> bool:
        if steps_taken > self.step_limit:
            raise RuntimeError(f"Agent {self.agent_id} exceeded step limit of {self.step_limit}")
        if tokens_used > self.token_budget:
            raise RuntimeError(f"Agent {self.agent_id} exceeded token budget of {self.token_budget}")
        return True

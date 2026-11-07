"""
CareLoop Agent Registry
Maintains agent identities, versions, allowed scopes, max risk tier, active/kill-switch status,
and earned autonomy metrics.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class AgentDefinition(BaseModel):
    id: str
    name: str
    version: str
    description: str
    allowed_tools: List[str]
    allowed_scopes: List[str]
    max_risk_tier: str  # T0, T1, T2, T3
    is_active: bool = True
    is_quarantined: bool = False
    override_count: int = 0
    approval_count: int = 0
    token_budget_per_task: int = 2000
    earned_autonomy_eligible: bool = False

class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, AgentDefinition] = {}
        self._bootstrap_agents()

    def _bootstrap_agents(self):
        # 1. Lab Results Agent
        self.register(AgentDefinition(
            id="lab-agent",
            name="Lab Results Classifier Agent",
            version="1.2.0",
            description="Analyzes post-discharge HL7/FHIR lab observations against clinical reference ranges",
            allowed_tools=["get_labs"],
            allowed_scopes=["read:labs"],
            max_risk_tier="T0",
            is_active=True,
            token_budget_per_task=1500
        ))

        # 2. Pharmacy Agent
        self.register(AgentDefinition(
            id="pharmacy-agent",
            name="Clinical Pharmacy Reconciliation Agent",
            version="1.4.1",
            description="Checks patient medication list for adverse drug-lab interactions (e.g., hyperkalemia & spironolactone)",
            allowed_tools=["get_medications"],
            allowed_scopes=["read:medications"],
            max_risk_tier="T0",
            is_active=True,
            token_budget_per_task=2000
        ))

        # 3. Scheduling Agent
        self.register(AgentDefinition(
            id="scheduling-agent",
            name="Urgent Appointment Scheduling Agent",
            version="1.1.0",
            description="Locates and reserves urgent follow-up outpatient appointment slots",
            allowed_tools=["get_slots", "book_slot"],
            allowed_scopes=["read:slots", "write:scheduling"],
            max_risk_tier="T1", # Can book reversible slots autonomously
            is_active=True,
            token_budget_per_task=1500
        ))

        # 4. Billing Agent
        self.register(AgentDefinition(
            id="billing-agent",
            name="Patient Invoicing & Billing Agent",
            version="1.0.5",
            description="Manages post-discharge patient billing and final invoice dispatch",
            allowed_tools=["create_invoice", "dispatch_invoice"],
            allowed_scopes=["write:billing"],
            max_risk_tier="T1",
            is_active=True,
            token_budget_per_task=1500
        ))

        # 5. Outreach Agent
        self.register(AgentDefinition(
            id="outreach-agent",
            name="Patient Clinical Outreach Agent",
            version="2.0.0",
            description="Drafts culturally concordant, multilingual clinical instructions (Telugu, Hindi, English)",
            allowed_tools=["get_patient_demographics", "draft_message"],
            allowed_scopes=["read:patient", "write:outreach"],
            max_risk_tier="T2", # Requires clinician sign-off
            is_active=True,
            token_budget_per_task=3000
        ))

    def register(self, agent: AgentDefinition):
        self.agents[agent.id] = agent

    def get_agent(self, agent_id: str) -> Optional[AgentDefinition]:
        return self.agents.get(agent_id)

    def list_agents(self) -> List[AgentDefinition]:
        return list(self.agents.values())

    def set_active_status(self, agent_id: str, is_active: bool) -> bool:
        if agent_id in self.agents:
            self.agents[agent_id].is_active = is_active
            return True
        return False

    def quarantine_agent(self, agent_id: str, reason: str) -> bool:
        """Emergency kill-switch / quarantine"""
        if agent_id in self.agents:
            self.agents[agent_id].is_active = False
            self.agents[agent_id].is_quarantined = True
            print(f"[KILL-SWITCH ACTIVATED] Agent {agent_id} quarantined: {reason}")
            return True
        return False

    def record_feedback(self, agent_id: str, approved: bool):
        """Updates earned autonomy metrics"""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        if approved:
            agent.approval_count += 1
        else:
            agent.override_count += 1

        total = agent.approval_count + agent.override_count
        if total >= 10:
            override_rate = agent.override_count / total
            if override_rate < 0.05 and agent.max_risk_tier == "T2":
                agent.earned_autonomy_eligible = True

agent_registry = AgentRegistry()

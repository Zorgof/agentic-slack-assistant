"""Agent definitions (triage router + specialist agents).

To add a capability: create a module exposing `SPEC: SpecialistSpec` and register it in
`default_specialists()`. The triage agent picks it up as a handoff target automatically.
"""

from trends_agent.agents import ai_trends
from trends_agent.core.registry import AgentRegistry


def default_specialists() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(ai_trends.SPEC)
    return registry

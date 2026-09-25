"""Registries that make tools and specialist agents pluggable.

Adding a capability = registering a new tool and/or a new `SpecialistSpec`;
the triage agent automatically gets every registered specialist as a handoff target.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from agents import Agent, Tool

from trends_agent.config import Settings


class ToolRegistry:
    """Name -> tool mapping; agents select their tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, tool: Tool) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def get(self, names: Iterable[str]) -> list[Tool]:
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise KeyError(f"Unknown tools: {missing}. Registered: {sorted(self._tools)}")
        return [self._tools[n] for n in names]

    def names(self) -> list[str]:
        return sorted(self._tools)


@dataclass(frozen=True)
class SpecialistSpec:
    """Declares a specialist agent the triage agent can hand off to."""

    name: str
    # Shown to the triage agent to decide when to route here.
    description: str
    build: Callable[[Settings, ToolRegistry], Agent[Any]]


class AgentRegistry:
    """Ordered collection of specialist agent specs."""

    def __init__(self) -> None:
        self._specs: dict[str, SpecialistSpec] = {}

    def register(self, spec: SpecialistSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Specialist '{spec.name}' is already registered")
        self._specs[spec.name] = spec

    def specs(self) -> list[SpecialistSpec]:
        return list(self._specs.values())

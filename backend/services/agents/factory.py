from ... import config
from .base import AgentProvider
from .copilot_agent import CopilotAgent

_REGISTRY: dict[str, type[AgentProvider]] = {
    "copilot": CopilotAgent,
}


def get_agent(agent_type: str | None = None) -> AgentProvider:
    name = agent_type or config.DEFAULT_AGENT
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知的 Agent 类型: {name}，可用: {list(_REGISTRY.keys())}")
    return cls()

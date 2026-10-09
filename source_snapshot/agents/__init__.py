"""KrAIonyx native Python medical-agent package."""


def __getattr__(name):
    """Lazy import to avoid circular/broken imports."""
    if name == "AGENT_REGISTRY":
        from agents.registry import AGENT_REGISTRY
        return AGENT_REGISTRY
    if name == "get_specialist":
        from agents.registry import get_specialist
        return get_specialist
    if name == "get_all_specialists":
        from agents.registry import get_all_specialists
        return get_all_specialists
    raise AttributeError(f"module 'agents' has no attribute {name!r}")

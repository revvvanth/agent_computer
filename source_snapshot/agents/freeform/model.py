"""Use the existing model router without its permissive JSON repair boundary."""

from __future__ import annotations


class RoutedModel:
    async def complete(
        self, *, system: str, user: str, max_tokens: int, timeout: float
    ) -> str:
        from agents.services.hybrid_llm_router import TaskType, call_llm

        # Runtime applies strict action validation. Never pass a schema through the
        # legacy router's repair path (which may log rejected model content).
        return str(
            await call_llm(
                TaskType.SPECIALIST_ANALYSIS,
                system=system,
                user=user,
                temperature=0.2,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        )

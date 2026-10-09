"""Run-scoped evidence gateway for free-form agents."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable

from agents.freeform.contracts import CapabilityDenied, Scope

_SAFE_EVIDENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    domain: str
    source_id: str
    title: str
    excerpt: str
    document_id: str | None = None
    page: int | None = None
    strategy: str | None = None

    def public(self) -> dict[str, Any]:
        return asdict(self)


KnowledgeSearch = Callable[..., Awaitable[dict[str, Any]]]


class EvidenceGateway:
    """Authorize selectors and register evidence for one investigation."""

    def __init__(
        self,
        *,
        rag_service: Any = None,
        knowledge_search: KnowledgeSearch | None = None,
    ) -> None:
        self._rag_service = rag_service
        self._knowledge_search = knowledge_search
        self._items: dict[str, EvidenceItem] = {}
        self._scope_key: tuple[Any, ...] | None = None

    def _bind(self, scope: Scope) -> None:
        key = (scope.tenant_id, scope.user_id, scope.encounter_id, scope.document_ids)
        if self._scope_key is None:
            self._scope_key = key
        elif self._scope_key != key:
            raise CapabilityDenied("evidence gateway scope cannot change during a run")

    @staticmethod
    def _id(domain: str, source_id: str, scope: Scope) -> str:
        digest = hashlib.sha256(
            f"{domain}\0{scope.tenant_id}\0{scope.user_id}\0{source_id}".encode()
        ).hexdigest()[:24]
        return f"ff-{domain[:1]}-{digest}"

    def seed(self, scope: Scope, evidence_context: str) -> None:
        """Register existing graph evidence IDs without treating prose as authority."""
        self._bind(scope)
        for match in re.finditer(r"(?m)^-\s+\[([^\]]+)\]\s*(.*)$", evidence_context):
            raw_id, excerpt = match.groups()
            evidence_id = (
                raw_id
                if _SAFE_EVIDENCE_ID.fullmatch(raw_id)
                else self._id("shared", raw_id, scope)
            )
            self._items.setdefault(
                evidence_id,
                EvidenceItem(
                    evidence_id,
                    "shared",
                    raw_id[:256],
                    "Shared verified evidence",
                    excerpt[:1200],
                ),
            )

    async def search(
        self,
        scope: Scope,
        *,
        corpus: str,
        query: str,
        top_k: int,
    ) -> list[EvidenceItem]:
        self._bind(scope)
        if corpus == "patient":
            return await self._search_patient(scope, query, top_k)
        if corpus == "knowledge":
            return await self._search_knowledge(scope, query, top_k)
        raise CapabilityDenied("unsupported evidence corpus")

    async def _search_patient(
        self, scope: Scope, query: str, top_k: int
    ) -> list[EvidenceItem]:
        if not scope.document_ids:
            raise CapabilityDenied(
                "patient search requires explicitly scoped document IDs"
            )
        rag = self._rag_service
        if rag is None:
            from unified_backend.services.multimodal_rag_service import (
                get_multimodal_rag_service_async,
            )

            rag = await get_multimodal_rag_service_async()
            self._rag_service = rag
        for document_id in scope.document_ids:
            document = await rag.get_document_status(
                document_id,
                scope.tenant_id,
                scope.user_id,
            )
            if document is None:
                raise CapabilityDenied(
                    "one or more documents are outside the authenticated scope"
                )
            document_tenant = str(document.get("tenant_id") or "")
            if document_tenant and document_tenant != scope.tenant_id:
                raise CapabilityDenied(
                    "one or more documents are outside the authenticated tenant scope"
                )
            document_encounter = str(document.get("encounter_id") or "")
            if document_encounter and document_encounter != scope.encounter_id:
                raise CapabilityDenied(
                    "one or more documents are outside the authenticated encounter scope"
                )
            if (
                os.getenv("ENVIRONMENT", "development").lower() == "production"
                and (not document_tenant or not document_encounter)
                and os.getenv("CDSS_ALLOW_LEGACY_USER_SCOPED_RAG", "false").lower()
                != "true"
            ):
                raise CapabilityDenied(
                    "patient document is missing required scope metadata"
                )
        result = await rag.query(
            query_text=query,
            tenant_id=scope.tenant_id,
            user_id=scope.user_id,
            doc_ids=list(scope.document_ids),
            top_k=top_k,
            encounter_id=scope.encounter_id,
            purpose="agent.freeform.patient_search",
            generate_answer=False,
        )
        items = []
        for source in list(result.sources or [])[:top_k]:
            if not isinstance(source, dict):
                continue
            metadata = source.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            document_id = str(source.get("doc_id") or "")
            if not document_id or document_id not in scope.document_ids:
                raise CapabilityDenied(
                    "retrieval returned evidence outside the requested document scope"
                )
            source_id = str(
                source.get("chunk_id") or source.get("doc_id") or "unknown"
            )[:256]
            raw_page = source.get("page")
            evidence_id = self._id("patient", source_id, scope)
            item = EvidenceItem(
                evidence_id=evidence_id,
                domain="patient",
                source_id=source_id,
                title=str(metadata.get("title") or "Patient document")[:500],
                excerpt=str(source.get("excerpt") or "")[:1200],
                document_id=document_id,
                page=raw_page
                if isinstance(raw_page, int) and not isinstance(raw_page, bool)
                else None,
                strategy=str(getattr(result, "strategy_used", "unknown"))[:120],
            )
            self._items[evidence_id] = item
            items.append(item)
        return items

    async def _search_knowledge(
        self, scope: Scope, query: str, top_k: int
    ) -> list[EvidenceItem]:
        search = self._knowledge_search
        if search is None:
            from unified_backend.medical_deep_research.service import (
                gather_shared_evidence,
            )

            search = gather_shared_evidence
            self._knowledge_search = search
        package = await search(query, tenant_id=scope.tenant_id)
        items = []
        for source in (package.get("research_evidence") or [])[:top_k]:
            if not isinstance(source, dict):
                continue
            source_id = str(
                source.get("evidence_id")
                or source.get("pmid")
                or source.get("url")
                or source.get("title")
            )[:500]
            evidence_id = self._id("knowledge", source_id, scope)
            item = EvidenceItem(
                evidence_id=evidence_id,
                domain="knowledge",
                source_id=source_id,
                title=str(source.get("title") or "Clinical evidence")[:500],
                excerpt=str(source.get("snippet") or "")[:1200],
                strategy="shared_research_broker",
            )
            self._items[evidence_id] = item
            items.append(item)
        return items

    def fetch(self, scope: Scope, evidence_ids: list[str]) -> list[EvidenceItem]:
        self._bind(scope)
        unknown = [item for item in evidence_ids if item not in self._items]
        if unknown:
            # Name what was wrong and what is allowed. A bare refusal made the model
            # repeat the same citation until the session hit its deadline: it was
            # citing chart values and guideline names, which have no evidence ID. The
            # refused strings are the model's own output and stay in this run's
            # encrypted checkpoint; they are never logged.
            offending = ", ".join(json.dumps(item[:50]) for item in unknown[:4])
            registered = list(self._items)[:6]
            raise CapabilityDenied(
                f"evidence ID is not registered in this investigation (unregistered: {offending})"
                + (
                    f"; cite only registered IDs: {', '.join(registered)}"
                    if registered
                    else "; none are registered, so evidence_references must be []"
                )
                + ". Chart values and guideline names are not evidence IDs: state them in"
                " key_findings or clinical_assessment instead."
            )
        return [self._items[item] for item in evidence_ids]

    def validate_references(self, scope: Scope, evidence_ids: list[str]) -> None:
        self.fetch(
            scope, list(dict.fromkeys(evidence_ids))
        ) if evidence_ids else self._bind(scope)

    def snapshot(self, scope: Scope) -> dict[str, Any]:
        """Return evidence registry state for encrypted run checkpointing."""
        self._bind(scope)
        return {"items": [item.public() for item in self._items.values()]}

    def restore(self, scope: Scope, snapshot: dict[str, Any]) -> None:
        """Restore only validated evidence records inside the original run scope."""
        self._bind(scope)
        restored: dict[str, EvidenceItem] = {}
        for raw in snapshot.get("items") or []:
            if not isinstance(raw, dict):
                raise CapabilityDenied("checkpoint evidence record is invalid")
            item = EvidenceItem(
                evidence_id=str(raw.get("evidence_id") or ""),
                domain=str(raw.get("domain") or ""),
                source_id=str(raw.get("source_id") or "")[:500],
                title=str(raw.get("title") or "")[:500],
                excerpt=str(raw.get("excerpt") or "")[:1200],
                document_id=(
                    str(raw["document_id"]) if raw.get("document_id") else None
                ),
                page=(raw.get("page") if isinstance(raw.get("page"), int) else None),
                strategy=(str(raw["strategy"])[:120] if raw.get("strategy") else None),
            )
            if not _SAFE_EVIDENCE_ID.fullmatch(item.evidence_id):
                raise CapabilityDenied("checkpoint evidence ID is invalid")
            if item.domain == "patient" and item.document_id not in scope.document_ids:
                raise CapabilityDenied(
                    "checkpoint contains evidence outside document scope"
                )
            restored[item.evidence_id] = item
        self._items = restored

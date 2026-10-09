"""Encrypted checkpoints and PHI-safe audit records for free-form agent runs."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from agents.freeform.contracts import Scope


class RunBusy(RuntimeError):
    """Another worker owns the unexpired run lease."""


class RunCancelled(RuntimeError):
    """The durable run was cancelled before it could finalize."""


@dataclass(frozen=True, slots=True)
class LeaseState:
    status: str
    snapshot: dict[str, Any] | None = None


class RunStore(Protocol):
    async def acquire(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        scope: Scope,
        specialty: str,
        workflow_id: str | None,
        lease_seconds: int,
    ) -> LeaseState: ...

    async def save(
        self,
        *,
        run_id: str,
        scope: Scope,
        status: str,
        snapshot: dict[str, Any],
        sessions: list[dict[str, Any]],
        events: list[dict[str, Any]],
        usage: dict[str, int],
        lease_seconds: int,
        error_type: str | None = None,
    ) -> None: ...


class NullRunStore:
    """Development-only store used when durable execution is not configured."""

    async def acquire(self, **_: Any) -> LeaseState:
        return LeaseState(status="new")

    async def save(self, **_: Any) -> None:
        return None


class RdsRunStore:
    """RDS-backed run lease, encrypted checkpoint, and operational event store."""

    _CHECKPOINT_VERSION = 1

    def __init__(self, database_url: str, aes_key: bytes) -> None:
        if len(aes_key) not in (16, 24, 32):
            raise RuntimeError("LANGGRAPH_AES_KEY must be 16, 24, or 32 bytes")
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self._aes_key = aes_key
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4()}"
        self._pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def _encrypt(self, run_id: str, value: dict[str, Any]) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        plaintext = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._aes_key).encrypt(
            nonce,
            plaintext,
            run_id.encode("utf-8"),
        )
        return nonce + ciphertext

    def _decrypt(
        self, run_id: str, payload: bytes | memoryview | None
    ) -> dict[str, Any] | None:
        if not payload:
            return None
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        packed = bytes(payload)
        if len(packed) < 28:
            raise RuntimeError("agent checkpoint is truncated")
        nonce, ciphertext = packed[:12], packed[12:]
        plaintext = AESGCM(self._aes_key).decrypt(
            nonce,
            ciphertext,
            run_id.encode("utf-8"),
        )
        value = json.loads(plaintext)
        if not isinstance(value, dict):
            raise RuntimeError("agent checkpoint has an invalid root type")
        return value

    async def acquire(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        scope: Scope,
        specialty: str,
        workflow_id: str | None,
        lease_seconds: int,
    ) -> LeaseState:
        return await asyncio.to_thread(
            self._acquire_sync,
            run_id,
            idempotency_key,
            scope,
            specialty,
            workflow_id,
            lease_seconds,
        )

    def _acquire_sync(
        self,
        run_id: str,
        idempotency_key: str,
        scope: Scope,
        specialty: str,
        workflow_id: str | None,
        lease_seconds: int,
    ) -> LeaseState:
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                "SELECT * FROM clinical_agent_runs WHERE run_id = %s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO clinical_agent_runs
                      (run_id, idempotency_key, tenant_id, user_id, encounter_id,
                       workflow_id, specialty, status, lease_owner, lease_expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'running', %s,
                            now() + make_interval(secs => %s))
                    """,
                    (
                        run_id,
                        idempotency_key,
                        scope.tenant_id,
                        scope.user_id,
                        scope.encounter_id,
                        workflow_id,
                        specialty,
                        self._worker_id,
                        lease_seconds,
                    ),
                )
                return LeaseState(status="new")

            ownership = (
                row.get("idempotency_key") == idempotency_key
                and row.get("tenant_id") == scope.tenant_id
                and row.get("user_id") == scope.user_id
                and row.get("encounter_id") == scope.encounter_id
                and row.get("specialty") == specialty
            )
            if not ownership:
                raise RuntimeError("agent run ownership mismatch")

            snapshot = self._decrypt(run_id, row.get("checkpoint"))
            if row.get("status") == "completed":
                return LeaseState(status="completed", snapshot=snapshot)
            if row.get("status") == "cancelled":
                raise RunCancelled("agent run was cancelled")

            lease_expires = row.get("lease_expires_at")
            now = datetime.now(timezone.utc)
            if (
                row.get("lease_owner")
                and row.get("lease_owner") != self._worker_id
                and lease_expires is not None
                and lease_expires > now
            ):
                raise RunBusy("agent run is owned by another worker")

            connection.execute(
                """
                UPDATE clinical_agent_runs
                SET status = 'running', lease_owner = %s,
                    lease_expires_at = now() + make_interval(secs => %s),
                    updated_at = now(), error_type = NULL, completed_at = NULL
                WHERE run_id = %s
                """,
                (self._worker_id, lease_seconds, run_id),
            )
            return LeaseState(status="recovered", snapshot=snapshot)

    async def save(
        self,
        *,
        run_id: str,
        scope: Scope,
        status: str,
        snapshot: dict[str, Any],
        sessions: list[dict[str, Any]],
        events: list[dict[str, Any]],
        usage: dict[str, int],
        lease_seconds: int,
        error_type: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._save_sync,
            run_id,
            scope,
            status,
            snapshot,
            sessions,
            events,
            usage,
            lease_seconds,
            error_type,
        )

    def _save_sync(
        self,
        run_id: str,
        scope: Scope,
        status: str,
        snapshot: dict[str, Any],
        sessions: list[dict[str, Any]],
        events: list[dict[str, Any]],
        usage: dict[str, int],
        lease_seconds: int,
        error_type: str | None,
    ) -> None:
        from psycopg.types.json import Jsonb

        encrypted = self._encrypt(run_id, snapshot)
        last_sequence = max((int(item["sequence"]) for item in events), default=0)
        terminal = status in {"completed", "failed", "cancelled"}
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                SELECT status, lease_owner FROM clinical_agent_runs
                WHERE run_id = %s AND tenant_id = %s AND user_id = %s
                  AND encounter_id = %s
                FOR UPDATE
                """,
                (run_id, scope.tenant_id, scope.user_id, scope.encounter_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("agent run disappeared during checkpoint")
            if row.get("status") == "cancelled" and status != "cancelled":
                raise RunCancelled("agent run was cancelled")
            if row.get("lease_owner") != self._worker_id and not terminal:
                raise RunBusy("agent run lease was lost")

            connection.execute(
                """
                UPDATE clinical_agent_runs
                SET status = %s, checkpoint = %s, checkpoint_version = %s,
                    last_sequence = %s, usage = %s, error_type = %s,
                    updated_at = now(),
                    lease_owner = CASE WHEN %s THEN NULL ELSE %s END,
                    lease_expires_at = CASE WHEN %s THEN NULL
                        ELSE now() + make_interval(secs => %s) END,
                    completed_at = CASE WHEN %s THEN now() ELSE NULL END
                WHERE run_id = %s
                """,
                (
                    status,
                    encrypted,
                    self._CHECKPOINT_VERSION,
                    last_sequence,
                    Jsonb(usage),
                    error_type,
                    terminal,
                    self._worker_id,
                    terminal,
                    lease_seconds,
                    terminal,
                    run_id,
                ),
            )

            for session in sessions:
                connection.execute(
                    """
                    INSERT INTO clinical_agent_sessions
                      (run_id, session_id, parent_session_id, depth, profile,
                       specialty, status, child_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, session_id) DO UPDATE SET
                      parent_session_id = EXCLUDED.parent_session_id,
                      depth = EXCLUDED.depth,
                      profile = EXCLUDED.profile,
                      specialty = EXCLUDED.specialty,
                      status = EXCLUDED.status,
                      child_count = EXCLUDED.child_count,
                      updated_at = now()
                    """,
                    (
                        run_id,
                        session["session_id"],
                        session.get("parent_id"),
                        session["depth"],
                        session["profile"],
                        session["specialty"],
                        session["status"],
                        session["child_count"],
                    ),
                )

            for event in events:
                connection.execute(
                    """
                    INSERT INTO clinical_agent_events
                      (run_id, sequence, session_id, action, status, elapsed_ms)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, sequence) DO NOTHING
                    """,
                    (
                        run_id,
                        event["sequence"],
                        event["session_id"],
                        event["action"],
                        event["status"],
                        event["elapsed_ms"],
                    ),
                )


def build_run_store() -> RunStore:
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    default_enabled = "true" if environment == "production" else "false"
    enabled = (
        os.getenv("CDSS_FREEFORM_DURABLE_STORE", default_enabled).lower() == "true"
    )
    if not enabled:
        if (
            environment == "production"
            and os.getenv("CDSS_AGENT_MODE", "freeform") == "freeform"
        ):
            raise RuntimeError("CDSS_FREEFORM_DURABLE_STORE is required in production")
        return NullRunStore()

    database_url = (
        os.getenv("KAREOS_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    aes_key = os.getenv("LANGGRAPH_AES_KEY", "").encode("utf-8")
    if not database_url:
        raise RuntimeError(
            "KAREOS_DATABASE_URL or DATABASE_URL is required for agent persistence"
        )
    return RdsRunStore(database_url, aes_key)


__all__ = [
    "LeaseState",
    "NullRunStore",
    "RdsRunStore",
    "RunBusy",
    "RunCancelled",
    "RunStore",
    "build_run_store",
]

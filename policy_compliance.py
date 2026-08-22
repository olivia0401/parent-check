"""Policy-constrained access decisions with verifiable audit evidence.

This is a research prototype, not a replacement for a production policy
engine or a KMS. It models the three-party setting in the Newcastle project:
the data owner, the AI service, and the policy authority exchange a decision
without exposing the protected payload. Each decision is signed with Ed25519
and linked to the previous decision, making the local audit stream tamper-
evident. The private key must be replaced by KMS/HSM custody in production.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ALLOWED_PURPOSES = {"scam_check", "research_evaluation"}
PROTECTED_DATA_CLASSES = {"health", "identity", "financial"}


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    policy_id: str
    policy_version: str
    principal: str
    data_owner: str
    data_class: str
    purpose: str
    reason_code: str


class PolicyAuthority:
    """Small deterministic policy authority used by the prototype API."""

    def __init__(self, policy_id: str = "parent-check-access", version: str = "v1"):
        self.policy_id = policy_id
        self.version = version

    def decide(self, *, principal: str, data_owner: str, data_class: str, purpose: str) -> PolicyDecision:
        principal = principal.strip().lower()
        data_owner = data_owner.strip().lower()
        data_class = data_class.strip().lower()
        purpose = purpose.strip().lower()

        if not principal or not data_owner:
            reason = "missing_identity"
            decision = "deny"
        elif purpose not in ALLOWED_PURPOSES:
            reason = "purpose_not_allowed"
            decision = "deny"
        elif data_class in PROTECTED_DATA_CLASSES and principal != data_owner:
            reason = "owner_consent_required"
            decision = "deny"
        else:
            reason = "policy_satisfied"
            decision = "allow"

        return PolicyDecision(
            decision=decision,
            policy_id=self.policy_id,
            policy_version=self.version,
            principal=principal,
            data_owner=data_owner,
            data_class=data_class,
            purpose=purpose,
            reason_code=reason,
        )


class SignedAuditLedger:
    """Append-only, hash-linked Ed25519-signed decision evidence."""

    def __init__(self, private_key: Ed25519PrivateKey | None = None):
        self._private_key = private_key or Ed25519PrivateKey.generate()
        self._events: list[dict[str, Any]] = []
        self._lock = Lock()

    @property
    def public_key(self) -> str:
        raw = self._private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def append(self, decision: PolicyDecision) -> dict[str, Any]:
        with self._lock:
            previous_hash = self._events[-1]["event_hash"] if self._events else "GENESIS"
            payload = {
                "timestamp_ms": int(time.time() * 1000),
                "previous_hash": previous_hash,
                "decision": asdict(decision),
            }
            signature = self._private_key.sign(_canonical(payload))
            event = {
                **payload,
                "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
            }
            event["event_hash"] = hashlib.sha256(_canonical(event)).hexdigest()
            self._events.append(event)
            return event.copy()

    def verify(self) -> bool:
        previous_hash = "GENESIS"
        public_key = self._private_key.public_key()
        for event in self._events:
            signed_payload = {
                "timestamp_ms": event["timestamp_ms"],
                "previous_hash": event["previous_hash"],
                "decision": event["decision"],
            }
            if event["previous_hash"] != previous_hash:
                return False
            try:
                signature = base64.urlsafe_b64decode(event["signature"] + "==")
                public_key.verify(signature, _canonical(signed_payload))
            except (InvalidSignature, ValueError):
                return False
            unsigned_event = {k: v for k, v in event.items() if k != "event_hash"}
            if hashlib.sha256(_canonical(unsigned_event)).hexdigest() != event["event_hash"]:
                return False
            previous_hash = event["event_hash"]
        return True

    def events(self) -> list[dict[str, Any]]:
        return [event.copy() for event in self._events]

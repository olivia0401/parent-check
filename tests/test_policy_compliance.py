import app as app_module
from policy_compliance import PolicyAuthority, SignedAuditLedger


def test_protected_data_requires_owner_consent():
    decision = PolicyAuthority().decide(
        principal="ai-service", data_owner="alice", data_class="health", purpose="scam_check"
    )
    assert decision.decision == "deny"
    assert decision.reason_code == "owner_consent_required"


def test_allowed_owner_request_is_audited_and_verifiable():
    ledger = SignedAuditLedger()
    decision = PolicyAuthority().decide(
        principal="alice", data_owner="alice", data_class="health", purpose="scam_check"
    )
    event = ledger.append(decision)
    assert event["decision"]["decision"] == "allow"
    assert ledger.verify()
    assert ledger.public_key


def test_tampering_breaks_signature_or_chain():
    ledger = SignedAuditLedger()
    ledger.append(PolicyAuthority().decide(
        principal="alice", data_owner="alice", data_class="health", purpose="scam_check"
    ))
    ledger._events[0]["decision"]["decision"] = "deny"
    assert not ledger.verify()


def test_policy_api_returns_verifiable_evidence():
    client = app_module.app.test_client()
    response = client.post("/api/policy-check", json={
        "principal": "ai-service",
        "data_owner": "alice",
        "data_class": "health",
        "purpose": "scam_check",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["decision"] == "deny"
    assert body["audit_chain_valid"] is True
    assert body["audit_event"]["decision"]["reason_code"] == "owner_consent_required"


def test_ledger_is_bounded_and_window_still_verifies():
    ledger = SignedAuditLedger(max_events=3)
    decision = PolicyAuthority().decide(
        principal="alice", data_owner="alice", data_class="health", purpose="scam_check"
    )
    for _ in range(5):
        ledger.append(decision)
    assert len(ledger.events()) == 3
    assert ledger.verify()

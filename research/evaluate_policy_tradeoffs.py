"""Small reproducible benchmark for the policy-enforcement prototype.

It measures policy accuracy, protected-data exposure, and decision latency on
synthetic requests. It intentionally contains no personal data and no LLM
calls, so it can run in CI and serve as a baseline for future FL/DP/MPC work.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    from policy_compliance import PolicyAuthority
except ModuleNotFoundError:  # support `python research/evaluate_policy_tradeoffs.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from policy_compliance import PolicyAuthority


CASES = [
    {"principal": "alice", "owner": "alice", "class": "health", "purpose": "scam_check", "expected": "allow"},
    {"principal": "ai-service", "owner": "alice", "class": "health", "purpose": "scam_check", "expected": "deny"},
    {"principal": "alice", "owner": "alice", "class": "financial", "purpose": "unknown", "expected": "deny"},
    {"principal": "analyst", "owner": "analyst", "class": "public", "purpose": "research_evaluation", "expected": "allow"},
]


def run() -> dict[str, float | int | str]:
    authority = PolicyAuthority()
    start = time.perf_counter()
    results = [authority.decide(
        principal=case["principal"], data_owner=case["owner"],
        data_class=case["class"], purpose=case["purpose"]
    ) for case in CASES]
    elapsed_ms = (time.perf_counter() - start) * 1000
    correct = sum(result.decision == case["expected"] for result, case in zip(results, CASES))
    exposed = sum(
        result.decision == "allow" and result.data_class in {"health", "identity", "financial"}
        and result.principal != result.data_owner for result in results
    )
    return {
        "dataset": "synthetic-policy-v1",
        "cases": len(CASES),
        "policy_accuracy": round(correct / len(CASES), 4),
        "protected_data_exposure_rate": round(exposed / len(CASES), 4),
        "mean_decision_latency_ms": round(elapsed_ms / len(CASES), 4),
    }


if __name__ == "__main__":
    output = run()
    print(json.dumps(output, indent=2))
    out_path = Path(__file__).with_name("policy-tradeoff-baseline.json")
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

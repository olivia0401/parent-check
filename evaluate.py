# Runs the rule engine against tests/dataset.py and enforces a quality gate.
# Usage:
#   python evaluate.py            # report + gate (exits non-zero on regression)
#   python evaluate.py --no-gate  # report only, always exit 0 (local exploration)
#
# Missed scams (predicted "ok" for an actual scam) and false alarms (benign
# flagged) are reported separately - missing a scam is the bad failure mode,
# a false alarm is just annoying, so they're gated differently.
#
# The gate turns this from an informational script into a CI check that blocks a
# deploy when quality regresses. Thresholds are set just below current
# performance and can be overridden with EVAL_* env vars.

import os
import sys
from collections import defaultdict

from helpers import analyze_content
from tests.dataset import CASES

# --- Quality gate thresholds (env-overridable) ------------------------------
# Baseline when written: accuracy 97%, scam recall 100%, missed 0, false alarms 2.
MIN_ACCURACY = float(os.environ.get("EVAL_MIN_ACCURACY", "0.90"))
MIN_SCAM_RECALL = float(os.environ.get("EVAL_MIN_SCAM_RECALL", "0.95"))
MAX_MISSED_SCAMS = int(os.environ.get("EVAL_MAX_MISSED_SCAMS", "0"))
MAX_FALSE_ALARMS = int(os.environ.get("EVAL_MAX_FALSE_ALARMS", "4"))


def evaluate():
    """Run the engine over every case and return metrics + failing examples."""
    exact = 0
    missed_scam = []   # kind=scam, predicted "ok"  -> dangerous
    false_alarm = []   # kind=benign, predicted != "ok"
    under_warned = []  # warned, but a weaker level than ideal
    by_kind = defaultdict(lambda: {"n": 0, "warned": 0, "exact": 0})

    for case in CASES:
        predicted = analyze_content(case["text"], case["source"])["risk"]
        expected = case["expected"]
        kind = case["kind"]

        k = by_kind[kind]
        k["n"] += 1
        if predicted != "ok":
            k["warned"] += 1
        if predicted == expected:
            k["exact"] += 1
            exact += 1
        elif kind == "scam" and predicted == "ok":
            missed_scam.append((case, predicted))
        elif kind == "benign" and predicted != "ok":
            false_alarm.append((case, predicted))
        else:
            under_warned.append((case, predicted))

    total = len(CASES)
    scam = by_kind["scam"]
    return {
        "total": total,
        "exact": exact,
        "accuracy": exact / total if total else 0.0,
        "scam_recall": scam["warned"] / scam["n"] if scam["n"] else 0.0,
        "missed": len(missed_scam),
        "false_alarms": len(false_alarm),
        "under_warned": len(under_warned),
        "by_kind": by_kind,
        "missed_scam": missed_scam,
        "false_alarm": false_alarm,
        "under_warned_items": under_warned,
    }


def pct(a, b):
    return f"{(100 * a / b):.0f}%" if b else "—"


def report(m):
    scam = m["by_kind"]["scam"]
    health = m["by_kind"]["health"]
    benign = m["by_kind"]["benign"]

    print(f"Cases: {m['total']}")
    print(f"Exact accuracy:        {m['exact']}/{m['total']} = {pct(m['exact'], m['total'])}")
    print()
    print(f"Scam recall (warned):  {scam['warned']}/{scam['n']} = {pct(scam['warned'], scam['n'])}")
    print(f"  MISSED SCAMS (danger): {m['missed']}")
    print(f"Health warned:         {health['warned']}/{health['n']} = {pct(health['warned'], health['n'])}")
    kept = benign["n"] - m["false_alarms"]
    print(f"Benign kept clean:     {kept}/{benign['n']} = {pct(kept, benign['n'])}")
    print(f"  FALSE ALARMS:          {m['false_alarms']}")
    print(f"Warned but wrong level:  {m['under_warned']}")

    def show(title, items):
        if not items:
            return
        print("\n" + title)
        for case, predicted in items:
            snippet = case["text"][:46].replace("\n", " ")
            print(f"  expected={case['expected']:<7} got={predicted:<7} | {snippet}")

    show("MISSED SCAMS — slipped through as 'ok':", m["missed_scam"])
    show("FALSE ALARMS — benign flagged:", m["false_alarm"])
    show("WRONG LEVEL — warned, but not the ideal level:", m["under_warned_items"])


def gate(m):
    """Check metrics against thresholds. Return True if all pass."""
    checks = [
        ("exact accuracy", m["accuracy"] >= MIN_ACCURACY,
         f"{m['accuracy']:.1%} (min {MIN_ACCURACY:.0%})"),
        ("scam recall", m["scam_recall"] >= MIN_SCAM_RECALL,
         f"{m['scam_recall']:.1%} (min {MIN_SCAM_RECALL:.0%})"),
        ("missed scams", m["missed"] <= MAX_MISSED_SCAMS,
         f"{m['missed']} (max {MAX_MISSED_SCAMS})"),
        ("false alarms", m["false_alarms"] <= MAX_FALSE_ALARMS,
         f"{m['false_alarms']} (max {MAX_FALSE_ALARMS})"),
    ]
    print("\n--- Quality gate ---")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        all_ok = all_ok and ok
    print("GATE:", "PASS" if all_ok else "FAIL")
    return all_ok


if __name__ == "__main__":
    metrics = evaluate()
    report(metrics)
    if "--no-gate" not in sys.argv:
        if not gate(metrics):
            sys.exit(1)

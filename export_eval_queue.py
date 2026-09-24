"""Export this product's decisions as an annotation queue for the eval platform.

    python export_eval_queue.py --output path/to/queue.jsonl

Why this exists
---------------
The evidence-grounded metrics (groundedness, evidence precision, unsupported-
claim rate, source quality) need real model output paired with the evidence it
actually cited. This product produces exactly that: `analyze_content` returns a
risk verdict plus `reasons` — the specific signals that fired. A verdict is a
claim; each fired signal is a piece of cited evidence.

What the annotator then decides, and what no script can decide for them:

* Does each cited signal **genuinely support** this verdict, or did it merely
  match? "click" firing on a benign newsletter is a citation without support —
  precisely the unsupported-claim pattern the metrics exist to measure.
* How strong is each signal as evidence (1-5)? A `bit.ly` shortener in an
  unsolicited SMS is strong; the bare word "urgent" is weak.

Direction of the dependency is deliberate: the product exports a portable
`annotation-queue/v1` file, and the evaluation platform consumes it without
knowing anything about scams. Any other system that emits claims-with-citations
can produce the same format.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from helpers import analyze_content
from tests.dataset import CASES

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA = "annotation-queue/v1"


def build_queue() -> list[dict]:
    """One queue item per labelled case, carrying the engine's own citations."""
    items = []
    for index, case in enumerate(CASES):
        verdict = analyze_content(case["text"], case["source"])
        reasons = list(verdict.get("reasons") or [])
        items.append({
            "item_id": f"pc-{index:03d}",
            "text": case["text"],
            "channel": case["source"],
            # The labelled outcome, carried through so annotation can be
            # stratified and so a slice can be reported per outcome rather than
            # as one grand average.
            "stratum": f"{case['kind']}/{case['expected']}",
            "expected_risk": case["expected"],
            # The claim under evaluation, in the words a user would read.
            "claim": {
                "claim_id": "verdict",
                "text": f"This {case['source']} is {verdict['risk']}"
                        f" (category: {verdict.get('category') or 'none'})",
                "predicted_risk": verdict["risk"],
            },
            # Each fired signal is one candidate evidence item. The annotator
            # decides which of them actually carry the verdict.
            "evidence": [
                {"evidence_id": f"sig-{i}", "text": reason, "kind": "signal"}
                for i, reason in enumerate(reasons)
            ],
        })
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args(argv)

    items = build_queue()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"schema": SCHEMA, "source": "parent-check",
                             "items": len(items)}, ensure_ascii=False) + "\n")
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    uncited = sum(1 for i in items if not i["evidence"])
    strata: dict[str, int] = {}
    for item in items:
        strata[item["stratum"]] = strata.get(item["stratum"], 0) + 1

    print(f"Wrote {len(items)} items -> {args.output}")
    print(f"  strata: {dict(sorted(strata.items()))}")
    print(f"  verdicts with NO cited signal: {uncited}")
    if uncited:
        print("    ^ these are the interesting ones. A verdict with no evidence")
        print("      is either a correct call the engine cannot justify, or a")
        print("      guess — and the metrics cannot tell them apart without you.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Giskard scan of the scam-safety classifier.

The whole promise is "may raise caution, must never downgrade a scam to safe".
This points Giskard's scanner at analyze_content() to probe exactly that: can an
input be perturbed or a prompt injected so a dangerous message comes back as ok?
Writes an HTML report.

    python scan_giskard.py

The rule engine itself needs no key; only Giskard's probe-generating LLM does
(OPENAI_API_KEY, or GEMINI_API_KEY).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Scam + benign messages (bilingual, matching the app's real users).
_MESSAGES = [
    "点击链接输入验证码并转账，否则账户冻结",
    "Royal Mail: your parcel is held, pay the fee at http://royalmail-redelivery.com",
    "妈，我换了新号码，急用钱，先帮我打一点过来",
    "这款保健品包治百病，无副作用，限时半价",
    "HMRC: you are owed a tax refund, confirm your bank details to claim",
    "月季花叶子发黄怎么办，是不是浇水太多了",
    "I bought a new remote control for the TV at the weekend",
    "周末一起去公园散步吗，天气不错",
]


def _scanner_model():
    """Pick a Giskard scanner LLM from whatever key is available."""
    if os.environ.get("GISKARD_SCAN_MODEL"):
        return os.environ["GISKARD_SCAN_MODEL"]
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini/gemini-flash-lite-latest"
    return None


def main() -> int:
    try:
        import giskard
        import pandas as pd
    except ImportError:
        print("Giskard not installed. Run:  pip install -r requirements-qe.txt")
        return 0

    scanner = _scanner_model()
    if scanner is None:
        print("Set OPENAI_API_KEY (or GEMINI_API_KEY) — Giskard needs an LLM to "
              "generate adversarial probes.")
        return 0

    from helpers import analyze_content

    def predict(df: "pd.DataFrame") -> list[str]:
        outs = []
        for message in df["message"]:
            r = analyze_content(message, source="suspicious_msg")
            reasons = ", ".join(r["reasons"]) or "none"
            outs.append(f"risk={r['risk']}; category={r['category']}; signals={reasons}")
        return outs

    giskard.llm.set_llm_model(scanner)

    model = giskard.Model(
        model=predict,
        model_type="text_generation",
        name="ScamShield risk classifier",
        description=(
            "Given a message an elderly user received, returns a conservative "
            "risk verdict: risk=ok|caution|danger plus the matched scam/health "
            "signals. Safety contract: it may raise caution but must NEVER "
            "downgrade a scam or phishing message to risk=ok."
        ),
        feature_names=["message"],
    )
    dataset = giskard.Dataset(
        pd.DataFrame({"message": _MESSAGES}),
        name="scam-and-benign-messages",
    )

    print(f"Scanning the rule engine (scanner LLM: {scanner})...")
    report = giskard.scan(model, dataset)

    out = Path(__file__).resolve().parent / "giskard_scan_scamshield.html"
    report.to_html(str(out))
    print(f"Report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Reliability check for the IMAGE path (screenshot -> OCR -> scam pipeline).
#
# evaluate.py measures the text pipeline. The image route is "OCR the screenshot,
# then run that exact same pipeline", so its accuracy = OCR fidelity x pipeline
# accuracy. This script measures the whole chain end-to-end.
#
# It reuses the already-labelled cases in tests/dataset.py: each case's text is
# rendered to a PNG (a stand-in screenshot), OCR'd back to text via the real
# ocr.extract_text(), then scored. Labels come for free from the text dataset.
#
# Two numbers matter, and they answer different questions:
#   - OCR fidelity: did the image verdict match feeding the ORIGINAL text
#     straight in? This isolates "did OCR preserve the signal" from the pipeline.
#   - End-to-end vs expected labels: accuracy / scam recall / missed scams, the
#     same shape and gate as evaluate.py.
#
# OCR needs a live backend (Gemini vision or Azure Document Intelligence). With
# no key configured this exits 0 with a clear "skipped" message, mirroring how
# the app treats AI as an optional enhancement rather than a hard dependency.
#
# Usage:
#   python evaluate_images.py                 # render + OCR + score + gate
#   python evaluate_images.py --no-gate       # report only, always exit 0
#   python evaluate_images.py --limit 12      # quick subset (fewer OCR calls)
#   python evaluate_images.py --save-dir out  # also keep the rendered PNGs

import argparse
import io
import os
import sys
from collections import defaultdict

from helpers import analyze_content
from tests.dataset import CASES

# --- Quality gate thresholds (env-overridable) ------------------------------
# The image path runs strictly downstream of OCR, so these sit a little below the
# text-path gate. The first live run establishes the real baseline; tighten then.
MIN_E2E_ACCURACY = float(os.environ.get("EVAL_IMG_MIN_ACCURACY", "0.85"))
MIN_SCAM_RECALL = float(os.environ.get("EVAL_IMG_MIN_SCAM_RECALL", "0.90"))
MAX_MISSED_SCAMS = int(os.environ.get("EVAL_IMG_MAX_MISSED_SCAMS", "0"))
MIN_OCR_FIDELITY = float(os.environ.get("EVAL_IMG_MIN_OCR_FIDELITY", "0.90"))


# --- Rendering: text -> PNG "screenshot" ------------------------------------
def _load_font(size):
    """A font with both CJK and Latin glyphs. Falls back to PIL's default."""
    from PIL import ImageFont

    for path in (
        r"C:\Windows\Fonts\msyh.ttc",       # Microsoft YaHei (Windows)
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux/CI
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    """Greedy character-level wrap (works for CJK, which has no spaces)."""
    lines, line = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(line)
            line = ""
            continue
        trial = line + ch
        if draw.textlength(trial, font=font) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = ch
    lines.append(line)
    return lines


def render_png(text, width=720, pad=28, font_size=30, line_gap=12):
    """Render `text` as dark text on a white card and return PNG bytes."""
    from PIL import Image, ImageDraw

    font = _load_font(font_size)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _wrap(scratch, text, font, width - 2 * pad)
    line_h = font_size + line_gap
    height = 2 * pad + line_h * max(1, len(lines))

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        draw.text((pad, y), line, fill=(17, 24, 39), font=font)
        y += line_h

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- Evaluation -------------------------------------------------------------
def build_llm():
    """The app's LLM client, or None if no provider key is configured."""
    try:
        from ai.llm_client import LLMClient

        llm = LLMClient()
        return llm if getattr(llm, "available", False) else None
    except Exception:
        return None


def evaluate(cases, llm, save_dir=None):
    import ocr

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)

    exact = 0
    ocr_faithful = 0          # image verdict == verdict on the original text
    ocr_failures = []         # OCR could not read usable text back
    missed_scam = []          # kind=scam, image path predicted "ok" -> dangerous
    false_alarm = []          # kind=benign, image path predicted != "ok"
    by_kind = defaultdict(lambda: {"n": 0, "warned": 0, "exact": 0})

    for i, case in enumerate(cases):
        text, source = case["text"], case["source"]
        expected, kind = case["expected"], case["kind"]
        text_pred = analyze_content(text, source)["risk"]  # pure-text baseline

        png = render_png(text)
        if save_dir:
            with open(os.path.join(save_dir, f"{i:03d}_{kind}.png"), "wb") as fh:
                fh.write(png)

        res = ocr.extract_text(png, "image/png", llm)
        k = by_kind[kind]
        k["n"] += 1

        if not res["ok"]:
            ocr_failures.append((case, res["error"]))
            # An OCR miss on a scam is a real end-to-end miss, not a free pass.
            if kind == "scam":
                missed_scam.append((case, "ocr:" + res["error"]))
            continue

        img_pred = analyze_content(res["text"], source)["risk"]
        if img_pred != "ok":
            k["warned"] += 1
        if img_pred == expected:
            k["exact"] += 1
            exact += 1
        elif kind == "scam" and img_pred == "ok":
            missed_scam.append((case, img_pred))
        elif kind == "benign" and img_pred != "ok":
            false_alarm.append((case, img_pred))
        if img_pred == text_pred:
            ocr_faithful += 1

    total = len(cases)
    scam = by_kind["scam"]
    scanned = total - len(ocr_failures)  # cases where OCR returned usable text
    return {
        "total": total,
        "exact": exact,
        "accuracy": exact / total if total else 0.0,
        "ocr_fidelity": ocr_faithful / scanned if scanned else 0.0,
        "ocr_failures": ocr_failures,
        "scam_recall": scam["warned"] / scam["n"] if scam["n"] else 0.0,
        "missed": len(missed_scam),
        "false_alarms": len(false_alarm),
        "by_kind": by_kind,
        "missed_scam": missed_scam,
        "false_alarm": false_alarm,
    }


def pct(a, b):
    return f"{(100 * a / b):.0f}%" if b else "—"


def report(m):
    scam = m["by_kind"]["scam"]
    print(f"Cases (rendered + OCR'd):  {m['total']}")
    print(f"OCR read-back failures:    {len(m['ocr_failures'])}")
    print(f"End-to-end exact accuracy: {m['exact']}/{m['total']} = {pct(m['exact'], m['total'])}")
    scanned = m["total"] - len(m["ocr_failures"])
    faithful = round(m["ocr_fidelity"] * scanned)
    print(f"OCR fidelity (== text path): {faithful}/{scanned} = {pct(faithful, scanned)}")
    print()
    print(f"Scam recall (warned):      {scam['warned']}/{scam['n']} = {pct(scam['warned'], scam['n'])}")
    print(f"  MISSED SCAMS (danger):   {m['missed']}")
    print(f"  FALSE ALARMS:            {m['false_alarms']}")

    def show(title, items):
        if not items:
            return
        print("\n" + title)
        for case, got in items:
            snippet = case["text"][:46].replace("\n", " ")
            print(f"  expected={case['expected']:<7} got={got:<10} | {snippet}")

    show("MISSED SCAMS — slipped through the image path:", m["missed_scam"])
    show("FALSE ALARMS — benign screenshot flagged:", m["false_alarm"])
    show("OCR READ-BACK FAILURES:", m["ocr_failures"])


def gate(m):
    checks = [
        ("end-to-end accuracy", m["accuracy"] >= MIN_E2E_ACCURACY,
         f"{m['accuracy']:.1%} (min {MIN_E2E_ACCURACY:.0%})"),
        ("OCR fidelity", m["ocr_fidelity"] >= MIN_OCR_FIDELITY,
         f"{m['ocr_fidelity']:.1%} (min {MIN_OCR_FIDELITY:.0%})"),
        ("scam recall", m["scam_recall"] >= MIN_SCAM_RECALL,
         f"{m['scam_recall']:.1%} (min {MIN_SCAM_RECALL:.0%})"),
        ("missed scams", m["missed"] <= MAX_MISSED_SCAMS,
         f"{m['missed']} (max {MAX_MISSED_SCAMS})"),
    ]
    print("\n--- Image-path quality gate ---")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        all_ok = all_ok and ok
    print("GATE:", "PASS" if all_ok else "FAIL")
    return all_ok


def main():
    ap = argparse.ArgumentParser(description="Evaluate the screenshot/OCR scam path.")
    ap.add_argument("--no-gate", action="store_true", help="report only, always exit 0")
    ap.add_argument("--limit", type=int, default=0, help="only evaluate the first N cases")
    ap.add_argument("--save-dir", default=None, help="also write the rendered PNGs here")
    args = ap.parse_args()

    llm = build_llm()
    if llm is None:
        print("OCR not configured (no GEMINI_API_KEY / Azure Document Intelligence).")
        print("Skipping the image-path evaluation. Set a key to measure it.")
        return 0

    cases = CASES[: args.limit] if args.limit else CASES
    print(f"OCR backend available. Evaluating {len(cases)} rendered screenshots...\n")
    metrics = evaluate(cases, llm, save_dir=args.save_dir)
    report(metrics)
    if not args.no_gate and not gate(metrics):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Runs the engine against tests/dataset.py and prints accuracy stats.
# Usage: python evaluate.py
#
# Missed scams (predicted "ok" for an actual scam) and false alarms (benign
# flagged) are reported separately - missing a scam is the bad failure mode,
# a false alarm is just annoying, so they're not weighted the same.

from collections import defaultdict

from helpers import analyze_content
from tests.dataset import CASES


def main():
    exact = 0
    missed_scam = []  # kind=scam, predicted "ok"  -> dangerous
    false_alarm = []  # kind=benign, predicted != "ok"
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
    health = by_kind["health"]
    benign = by_kind["benign"]

    def pct(a, b):
        return f"{(100 * a / b):.0f}%" if b else "—"

    print(f"Cases: {total}")
    print(f"Exact accuracy:        {exact}/{total} = {pct(exact, total)}")
    print()
    print(
        f"Scam recall (warned):  {scam['warned']}/{scam['n']} = {pct(scam['warned'], scam['n'])}"
    )
    print(f"  MISSED SCAMS (danger): {len(missed_scam)}")
    print(
        f"Health warned:         {health['warned']}/{health['n']} = {pct(health['warned'], health['n'])}"
    )
    print(
        f"Benign kept clean:     {benign['n'] - len(false_alarm)}/{benign['n']} = {pct(benign['n'] - len(false_alarm), benign['n'])}"
    )
    print(f"  FALSE ALARMS:          {len(false_alarm)}")
    print(f"Warned but wrong level:  {len(under_warned)}")

    def show(title, items):
        if not items:
            return
        print("\n" + title)
        for case, predicted in items:
            snippet = case["text"][:46].replace("\n", " ")
            print(f"  expected={case['expected']:<7} got={predicted:<7} | {snippet}")

    show("MISSED SCAMS — slipped through as 'ok':", missed_scam)
    show("FALSE ALARMS — benign flagged:", false_alarm)
    show("WRONG LEVEL — warned, but not the ideal level:", under_warned)


if __name__ == "__main__":
    main()

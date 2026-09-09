"""Inventory every bounded quest goal and changes since the previous guide.

This supplements structural audit.py: a valid progress number is not proof of
the author's intended stopping point. Unverified boundaries remain visible here.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", type=Path, default=ROOT / "dist/guide.json")
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/quest-goal-audit.json")
    args = parser.parse_args()
    guide = json.loads(args.guide.read_text(encoding="utf-8"))
    previous = json.loads(args.previous.read_text(encoding="utf-8"))
    old = {s["id"]: s for section in previous["sections"] for s in section["steps"]}
    steps = [(section, s) for section in guide["sections"] for s in section["steps"]]
    changed = []
    goals = []
    for section, step in steps:
        if step != old[step["id"]]:
            fields = sorted(k for k in step.keys() | old[step["id"]].keys()
                            if step.get(k) != old[step["id"]].get(k))
            assert all(k.startswith("quest") for k in fields), (step["id"], fields)
            changed.append({"bank": section["title"], "id": step["id"], "text": step["text"], "fields": fields})
        if step.get("questStep") and re.search(r"\b(?:until|up to|to unlock|to access|by obtaining)\b", step["text"], re.I):
            status = ("explicit item goal" if step.get("questStopItems") else
                      "source-verified state goal" if step.get("questStopValue") or step.get("questStopCondition") else
                      "manual: unresolved" if step.get("questStopUnresolved") else
                      "existing inferred boundary: semantic review still needed")
            goals.append({"bank": section["title"], "id": step["id"], "text": step["text"],
                          "status": status, "quest": step["questHelper"],
                          "value": step.get("questStopValue", step.get("questDoneAt")), "panel": step.get("questDoneAtPanel")})
    assert guide["migrations"] == previous["migrations"]
    report = {"contentHash": guide["contentHash"], "stepsScanned": len(steps),
              "changedSteps": len(changed), "starts": sum(bool(s.get("questStartOnly")) for _, s in steps),
              "itemGoals": sum(bool(s.get("questStopItems")) for _, s in steps),
              "verifiedStateGoals": sum(s.get("questStopValue") is not None or s.get("questStopCondition") is not None for _, s in steps),
              "manualGoals": sum(bool(s.get("questStopUnresolved")) for _, s in steps),
              "changed": changed, "boundedGoals": goals}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for key in ("contentHash", "stepsScanned", "changedSteps", "starts", "itemGoals", "verifiedStateGoals", "manualGoals"):
        print(f"{key}: {report[key]}")
    print(f"bounded goals needing semantic review: {sum(g['status'].startswith('existing') for g in goals)}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

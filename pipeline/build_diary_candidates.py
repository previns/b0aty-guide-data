"""Pair the guide's diary-tagged steps with Quest Helper's task bits.

Writes build/diary_candidates.json -- a **review document**. Nothing here is
merged. A person reads it and writes the pairs they accept into
curated/diary_tasks.yaml, keyed by step id.

Why a human has to do this
--------------------------
The completion signal itself is exact: the game sets a bit, we read it. What is
not exact is which of our steps a given bit means. The guide says "Check
playtime on Hans"; Quest Helper's panel says "Learn Age from Hans". Only prose
connects them, and prose matching is the thing that broke the previous attempt.

The cost of being wrong is also asymmetric in the worst direction. A wrong
highlight draws nothing. A wrong auto-tick silently marks work as done that the
player never did, and they find out much later, having skipped it.

So the ranking below is a convenience for the reviewer, never an answer.
"""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# "Lumbridge Easy Diary" -> the LumbridgeEasy / lumbridgeanddraynor file stem.
# Quest Helper names some regions differently from the guide; these are the
# region words, matched case-insensitively against the file stem.
REGION_WORDS = {
    "lumbridge": "lumbridge",
    "draynor": "lumbridge",
    "varrock": "varrock",
    "falador": "falador",
    "ardougne": "ardougne",
    "desert": "desert",
    "fremennik": "fremennik",
    "kandarin": "kandarin",
    "karamja": "karamja",
    "kourend": "kourend",
    "morytania": "morytania",
    "western": "western",
    "wilderness": "wilderness",
}
TIERS = ("easy", "medium", "hard", "elite")


def tier_key(tag: str) -> tuple[str, str] | None:
    low = tag.lower()
    region = next((v for k, v in REGION_WORDS.items() if k in low), None)
    tier = next((t for t in TIERS if t in low), None)
    return (region, tier) if region and tier else None


def stem_key(stem: str) -> tuple[str, str] | None:
    low = re.sub(r"(?<!^)(?=[A-Z])", " ", stem).lower()
    region = next((v for k, v in REGION_WORDS.items() if k in low), None)
    tier = next((t for t in TIERS if t in low), None)
    return (region, tier) if region and tier else None


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--tasks", type=Path, default=REPO / "build" / "diary_tasks.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "diary_candidates.json")
    args = ap.parse_args()

    guide = json.loads(args.guide.read_text(encoding="utf-8"))
    tasks_doc = json.loads(args.tasks.read_text(encoding="utf-8"))

    by_tier: dict[tuple[str, str], list] = {}
    for stem, tasks in tasks_doc["tiers"].items():
        key = stem_key(stem)
        if key:
            by_tier.setdefault(key, []).extend(tasks)

    report = []
    matched_tier = 0
    for section in guide["sections"]:
        for step in section["steps"]:
            for tag in step.get("tags", []):
                if not tag.get("diary"):
                    continue
                key = tier_key(tag["tag"])
                pool = by_tier.get(key, []) if key else []
                if pool:
                    matched_tier += 1
                ranked = sorted(
                    (t for t in pool if t["title"]),
                    key=lambda t: -similarity(step["text"], t["title"]),
                )[:4]
                report.append({
                    "stepId": step["id"],
                    "section": section.get("title"),
                    "text": step["text"],
                    "diaryTag": tag["tag"],
                    "tierResolved": bool(pool),
                    # Ranked by string similarity purely to put the likely row
                    # first. The reviewer decides; a high score is not a match.
                    "candidates": [
                        {
                            "title": t["title"],
                            "varplayer": t["varplayer"],
                            "bit": t["bit"],
                            "similarity": round(similarity(step["text"], t["title"]), 3),
                        }
                        for t in ranked
                    ],
                })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    strong = sum(1 for r in report
                 if r["candidates"] and r["candidates"][0]["similarity"] >= 0.6)
    print(f"diary-tagged steps        {len(report):5}")
    print(f"  tier found in QH        {matched_tier:5}")
    print(f"  top candidate >= 0.60   {strong:5}   (a hint for the reviewer, not a match)")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

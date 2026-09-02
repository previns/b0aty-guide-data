"""Append reviewed diary rows to curated/diary_tasks.yaml.

A helper for a person, not a pipeline stage: the decisions in NEW are made by
reading each tier's full task list, and this only formats them and checks them
against the extracted data before they are written.

It refuses to write a step id the file already has, because appending a
duplicate key produces a YAML file that still parses -- last one wins -- while
carrying two contradictory answers. That happened once and was invisible until
the row count was compared against the line count.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# stepId -> bit. Each decided against the tier's FULL task list, never a ranking.
NEW: dict[str, int] = {
    # Desert Hard -- mapped completely
    "47469d28b4": 25, "3c52368ea0": 30, "dacc23d589": 26, "d857b0dc8c": 28,
    "ec624b7e93": 31, "7d711a7cca": 0, "6a9f0e1dd0": 1, "9ae9b685ca": 29,
    # Morytania Hard -- mapped completely
    "535c33024a": 1, "92d1975ebc": 28, "de295e9660": 27, "5d6683a425": 30,
    "eb23df1b8b": 2, "d5f893346c": 23, "a44ebfd9da": 24,
    # Western Province Hard -- mapped completely
    "8e7ae639f4": 30, "df582594a9": 4, "b1e0ac8ded": 29, "d6a3ac9f0c": 31,
    "8c20db3ae7": 25, "1399c10797": 0,
    # Kandarin Medium  (ALS is McGrubor's Woods; the lockpicks have no task)
    "43c14f7e58": 24, "c7530d2ea2": 12, "78c978705d": 14, "25910e3b3e": 23,
}

# Guide diary tag -> the Quest Helper file the tier's bits come from.
STEM: dict[str, str] = {
    "Desert Hard Diary": "DesertHard",
    "Morytania Hard Diary": "MorytaniaHard",
    "Western Province Hard Diary": "WesternHard",
    "Kandarin Medium Diary": "KandarinMedium",
}


def main() -> int:
    candidates = {c["stepId"]: c for c in json.loads(
        (REPO / "build" / "diary_candidates.json").read_text(encoding="utf-8"))}
    tiers = json.loads(
        (REPO / "build" / "diary_tasks.json").read_text(encoding="utf-8"))["tiers"]
    by_stem = {stem: {t["bit"]: (t["varplayer"], t["title"]) for t in tasks}
               for stem, tasks in tiers.items()}

    path = REPO / "curated" / "diary_tasks.yaml"
    existing = yaml.safe_load(path.read_text(encoding="utf-8"))["tasks"] or {}

    rows, problems = [], []
    for step_id, bit in NEW.items():
        if step_id in existing:
            problems.append(f"{step_id}: already in the file")
            continue
        candidate = candidates.get(step_id)
        if not candidate:
            problems.append(f"{step_id}: not a diary step in the current guide")
            continue
        stem = STEM.get(candidate["diaryTag"])
        entry = by_stem.get(stem, {}).get(bit) if stem else None
        if not entry:
            problems.append(f"{step_id}: {candidate['diaryTag']} has no bit {bit}")
            continue
        varplayer, title = entry
        rows.append((candidate["diaryTag"], step_id, varplayer, bit, title,
                     candidate["text"]))

    if problems:
        print("nothing written:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8").rstrip("\n")
    out, last_tag = [], None
    for tag, step_id, varplayer, bit, title, step_text in sorted(rows):
        if tag != last_tag:
            out.append(f"\n  # --- {tag} ---")
            last_tag = tag
        out.append(f"  # {step_text}")
        out.append(f"  {step_id}: {{varplayer: {varplayer}, bit: {bit}}}  # {title}")
    path.write_text(text + "\n" + "\n".join(out) + "\n", encoding="utf-8")

    after = yaml.safe_load(path.read_text(encoding="utf-8"))["tasks"]
    print(f"added {len(rows)} rows; file now has {len(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

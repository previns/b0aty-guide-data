"""Stage 3d: extract achievement-diary task completion bits.

Writes build/diary_tasks.json: every individual diary task Quest Helper knows,
with the VarPlayer and bit index the game sets when it is done.

Why this matters
----------------
The plugin auto-ticks only what the client can prove, which so far has meant
quests alone. Individual diary tasks are equally provable -- the game stores
them as bits in a per-diary VarPlayer -- but RuneLite's `Varbits` enum only
names the *tier* (DIARY_ARDOUGNE_EASY), not the tasks inside it. Quest Helper
carries the per-task indices:

    notHans = new VarplayerRequirement(VarPlayerID.LUMB_DRAY_ACHIEVEMENT_DIARY, false, 5);

and pairs each with a readable title through its side panel:

    PanelDetails hansSteps = new PanelDetails("Learn your Age from Hans", ...);
    hansSteps.setDisplayCondition(notHans);

Joining those two inside one file gives (tier, title, varplayer, bit). That is
an extraction, not a guess: both halves are literals in the same source file.

What this file does NOT do is decide which of *our* guide's steps a task
corresponds to. That is a prose judgement and belongs in curated/.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"

RE_VARP = re.compile(
    r"(\w+)\s*=\s*new\s+VarplayerRequirement\(\s*VarPlayerID\.(\w+)\s*,"
    r"\s*(?:false|true)\s*,\s*(\d+)\s*\)")
RE_PANEL = re.compile(
    r"(\w+)\s*=\s*new\s+PanelDetails\(\s*\"([^\"]+)\"", re.S)
RE_CONDITION = re.compile(r"(\w+)\.setDisplayCondition\(\s*(\w+)\s*\)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "diary_tasks.json")
    args = ap.parse_args()

    root = args.source / "src/main/java/com/questhelper/helpers/achievementdiaries"
    if not root.is_dir():
        print(f"no quest-helper diaries at {root}; writing an empty table")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"tiers": {}}), encoding="utf-8")
        return 0

    tiers: dict[str, list] = {}
    unnamed = 0
    for path in sorted(root.rglob("*.java")):
        text = path.read_text(encoding="utf-8", errors="replace")
        bits = {var: (vp, int(bit)) for var, vp, bit in RE_VARP.findall(text)}
        if not bits:
            continue
        panels = dict(RE_PANEL.findall(text))
        # panel variable -> the requirement that hides it once done
        condition = dict(RE_CONDITION.findall(text))

        tasks = []
        claimed = set()
        for panel_var, req_var in condition.items():
            if req_var in bits and panel_var in panels:
                varp, bit = bits[req_var]
                tasks.append({
                    "title": panels[panel_var],
                    "varplayer": varp,
                    "bit": bit,
                    "questHelperVar": req_var,
                })
                claimed.add(req_var)
        # A bit with no panel is still a real completion signal; keep it, named
        # only by Quest Helper's variable, so nothing is silently lost.
        for req_var, (varp, bit) in bits.items():
            if req_var not in claimed:
                tasks.append({
                    "title": None,
                    "varplayer": varp,
                    "bit": bit,
                    "questHelperVar": req_var,
                })
                unnamed += 1
        tasks.sort(key=lambda t: (t["varplayer"], t["bit"]))
        tiers[path.stem] = tasks

    out = {"source": "quest-helper (BSD 2-Clause)", "tiers": tiers}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")

    total = sum(len(v) for v in tiers.values())
    named = total - unnamed
    print(f"diary tiers      {len(tiers):5}")
    print(f"task bits        {total:5}")
    print(f"  with a title   {named:5}")
    print(f"  bit only       {unnamed:5}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

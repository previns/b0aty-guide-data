"""Stage 3e: per-quest scenery, for working out which staircase a step means.

Writes build/quest_objects.json: for each Quest Helper quest, every ObjectStep
it contains as (object ids, coordinate).

The problem this solves
-----------------------
"Go upstairs and talk to Duke Horacio [Rune Mysteries]" resolves to the Duke on
plane 1. Stood on plane 0 the player cannot reach him, so the plugin looks for
the way up -- and picking the *nearest* climbable object gets Lumbridge castle
wrong, because several staircases and ladders sit within a few tiles.

Quest Helper already knows the answer, because it had to solve the same problem:

    goUpToHoracio = new ObjectStep(this, ObjectID.SPIRALSTAIRS,
        new WorldPoint(3205, 3208, 0), "Talk to Duke Horacio on the first floor")
    talkToHoracio = new NpcStep(this, NpcID.DUKE_OF_LUMBRIDGE,
        new WorldPoint(3210, 3220, 1), ...)

Scoping by the quest the guide already tags is what makes the join safe. Within
one quest the candidates are few and the nearest one on another plane is the
right one; across the whole game it would not be.

The quest name maps to a directory by a fixed rewrite -- lowercase, drop spaces
and apostrophes -- not by similarity. A name that does not produce an existing
directory yields nothing.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"

RE_OBJ_STEP = re.compile(
    r"new\s+ObjectStep\s*\(\s*this\s*,\s*ObjectID\.([A-Z0-9_]+)\s*,\s*"
    r"new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
    re.S)


def quest_directory(name: str) -> str:
    """"Rune Mysteries" -> "runemysteries". A fixed rewrite, not a search."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--ids", type=Path, default=REPO / "build" / "ids.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "quest_objects.json")
    args = ap.parse_args()

    root = args.source / "src/main/java/com/questhelper/helpers"
    if not root.is_dir():
        print(f"no quest-helper helpers at {root}; writing an empty table")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"quests": {}}), encoding="utf-8")
        return 0

    object_ids = json.loads(args.ids.read_text(encoding="utf-8"))["object"]

    quests: dict[str, list] = {}
    for directory in sorted(p for p in root.rglob("*") if p.is_dir()):
        entries: list[dict] = []
        for path in sorted(directory.glob("*.java")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for constant, x, y, z in RE_OBJ_STEP.findall(text):
                if constant not in object_ids:
                    continue
                entry = {
                    "constant": constant,
                    "id": object_ids[constant],
                    "point": [int(x), int(y), int(z)],
                }
                if entry not in entries:
                    entries.append(entry)
        if entries:
            quests[directory.name] = entries

    out = {"source": "quest-helper (BSD 2-Clause)", "quests": quests}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")

    total = sum(len(v) for v in quests.values())
    print(f"quests with scenery  {len(quests):5}")
    print(f"object steps         {total:5}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

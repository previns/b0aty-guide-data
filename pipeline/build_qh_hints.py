"""Extract (description, WorldPoint) pairs from a Quest Helper checkout.

Output feeds `worklist.py` as **suggestions for a human**, and nothing else. It
must never be joined into the pipeline automatically.

Why not automatically
---------------------
Quest Helper's coordinates are excellent, but they are keyed by prose, not by
place. Matching a destination name against those descriptions means substring
search over free text, which fails in exactly the way that broke the previous
attempt:

  * "Burthorpe" appears in 27 descriptions carrying 19 distinct coordinates.
    Nothing in the data says which one "Teleport to Burthorpe" means.
  * "Ardy" matches "h-ardy- gout tubers".

A person looking at the candidate list resolves both of those in a second. A
script cannot, and would silently pick one.

Quest Helper is BSD 2-Clause; see NOTICE.md. Only coordinates and the
descriptions needed to identify them are read, and only into a review document.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"

STEP = re.compile(
    r"new\s+(?:Npc|Object|DetailedQuest|Item|Tile|Widget)Step\s*\((?P<body>.{0,600}?)\)\s*;",
    re.S,
)
WORLD_POINT = re.compile(r"new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
JAVA_STRING = re.compile(r'"([^"\\]{6,200})"')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="path to a quest-helper checkout")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "qh_hints.json")
    args = ap.parse_args()

    root = args.source / "src" / "main" / "java"
    if not root.is_dir():
        print(f"no quest-helper source at {root}; skipping (hints are optional)")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("{}", encoding="utf-8")
        return 0

    hints: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    files = list(root.rglob("*.java"))
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in STEP.finditer(text):
            body = match.group("body")
            points = WORLD_POINT.findall(body)
            strings = JAVA_STRING.findall(body)
            if points and strings:
                key = tuple(int(v) for v in points[0])
                description = strings[0].strip()
                if description not in hints[key]:
                    hints[key].append(description)

    payload = {
        "source": "quest-helper (BSD 2-Clause)",
        "files": len(files),
        "points": {
            f"{x},{y},{p}": descriptions[:4]
            for (x, y, p), descriptions in hints.items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(v) for v in hints.values())
    print(f"java files      {len(files)}")
    print(f"distinct points {len(hints)}")
    print(f"descriptions    {total}")
    print(f"\nwrote {args.out}  (suggestions only -- never merged automatically)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

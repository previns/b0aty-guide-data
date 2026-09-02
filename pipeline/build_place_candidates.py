"""Gather coordinate candidates for destinations the pipeline could not resolve.

Writes build/place_candidates.json, which is a **review document**. Nothing here
is merged into the guide: a human reads it and writes the entries they accept
into curated/places.yaml by hand.

Why this is allowed to do loose matching when the rest of the pipeline is not
------------------------------------------------------------------------------
The pipeline's rule is that a name resolves through an authority or not at all.
That rule protects the *shipped data*. This file ships nothing. It puts a short
list of possibilities in front of a person, exactly as worklist.py does, and the
person is the resolution step. Every candidate carries its source so that person
can tell a RuneLite enum from a guess.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def norm(name: str) -> str:
    """Lowercase, collapse whitespace, drop punctuation the guide is loose about."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def load_locations(enum_dir: Path) -> dict[str, list[dict]]:
    """Every named WorldPoint in RuneLite's world-map enums, keyed by normalised name.

    Reads the enum sources directly rather than the filtered YAML: the YAML keeps
    one canonical name per entry, but the enums also carry the teleport item and
    the in-game label, which is often the only thing that matches the guide's
    wording ("Games necklace -> Wintertodt").
    """
    index: dict[str, list[dict]] = defaultdict(list)
    entry = re.compile(
        r'\(([^()]*?"(?P<label>[^"]+)"[^()]*?)'
        r'new WorldPoint\(\s*(?P<x>\d+)\s*,\s*(?P<y>\d+)\s*,\s*(?P<z>\d+)\s*\)'
    )
    for path in sorted(enum_dir.glob("*.java")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in entry.finditer(text):
            head = m.group(1)
            labels = re.findall(r'"([^"]+)"', head)
            point = [int(m.group("x")), int(m.group("y")), int(m.group("z"))]
            # The last string before the WorldPoint is the destination; an
            # earlier one, when present, is the item or teleport that reaches it.
            dest = labels[-1]
            via = labels[-2] if len(labels) > 1 else None
            record = {
                "name": dest,
                "point": point,
                "via": via,
                "source": f"runelite/{path.stem}",
            }
            if record not in index[norm(dest)]:
                index[norm(dest)].append(record)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path,
                    default=REPO.parent / "b0aty-guide-plugin" / "src" / "main"
                    / "resources" / "guide.json")
    ap.add_argument("--locations", type=Path, default=REPO / "build" / "runelite")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "place_candidates.json")
    args = ap.parse_args()

    guide = json.loads(args.guide.read_text(encoding="utf-8"))
    locations = load_locations(args.locations)

    # Destination names with no coordinate, plus where they are used.
    uses: dict[str, list[str]] = defaultdict(list)
    resolved: set[str] = set()
    for section in guide["sections"]:
        for step in section["steps"]:
            dest = step.get("destination")
            if not dest:
                continue
            if dest.get("points"):
                resolved.add(dest["name"])
            else:
                uses[dest["name"]].append(step["text"])

    report = {}
    for name in sorted(uses, key=lambda n: (-len(uses[n]), n)):
        key = norm(name)
        exact = locations.get(key, [])
        # Suggestions only: a location whose name contains the destination as a
        # whole word. Deliberately loose -- a person filters these.
        near = []
        if not exact:
            pattern = re.compile(rf"\b{re.escape(key)}\b")
            for other, entries in locations.items():
                if pattern.search(other):
                    near.extend(entries)
        report[name] = {
            "occurrences": len(uses[name]),
            "sampleSteps": uses[name][:3],
            "exactEnumMatch": exact,
            "nearbyEnumMatches": near[:6],
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    exact_n = sum(1 for v in report.values() if v["exactEnumMatch"])
    near_n = sum(1 for v in report.values() if not v["exactEnumMatch"] and v["nearbyEnumMatches"])
    none_n = len(report) - exact_n - near_n
    print(f"destination names needing coordinates : {len(report)}")
    print(f"  exact RuneLite enum match           : {exact_n}")
    print(f"  near match, needs a human           : {near_n}")
    print(f"  no candidate at all                 : {none_n}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

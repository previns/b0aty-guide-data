"""Stage 3c: build build/atlas.json -- game IDs to the places they are found.

Reads Quest Helper's source and RuneLite's ID constants. Writes a map from a
numeric game ID to the coordinates that ID appears at, plus the item IDs behind
Quest Helper's named item collections.

Why this one IS safe to merge automatically, when qh_hints.py is not
---------------------------------------------------------------------
`build_qh_hints.py` keys Quest Helper's coordinates by the prose in its step
descriptions, so joining it to our data means substring-matching free text --
"Burthorpe" appears in 27 descriptions carrying 19 different coordinates, and
"Ardy" matches "h-ardy- gout tubers". That output is for a human to read.

This file never looks at prose. Quest Helper writes

    new NpcStep(this, NpcID.FATHER_AERECK, new WorldPoint(3243, 3206, 0), "...")

and `NpcID.FATHER_AERECK` is a RuneLite constant with a number. The wiki has
already told us, independently, that Father Aereck is NPC 3211. The join is
number to number. No name is compared at any point, so the rule the pipeline is
built on -- resolve through an authority, never through similarity -- holds:
this is simply a second authority, keyed the same way as the first.

An ID with several coordinates keeps all of them and is marked ambiguous. A
person or a proximity rule picks; the data does not pretend to know.

Quest Helper is BSD 2-Clause (see NOTICE.md). Only IDs and coordinates are read.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"

WP = r"new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
RE_NPC_STEP = re.compile(r"new\s+NpcStep\s*\(\s*this\s*,\s*NpcID\.([A-Z0-9_]+)\s*,\s*" + WP, re.S)
RE_OBJ_STEP = re.compile(r"new\s+ObjectStep\s*\(\s*this\s*,\s*ObjectID\.([A-Z0-9_]+)\s*,\s*" + WP, re.S)
# Enum constants in ItemCollections.java: NAME( ... ItemID.A, ItemID.B ... )
RE_COLLECTION = re.compile(r"\n\t([A-Z][A-Z0-9_]*)\s*\(\s*(.*?)\n\t\)", re.S)
RE_ITEM_CONST = re.compile(r"ItemID\.([A-Z0-9_]+)")


def scan_steps(root: Path, ids: dict) -> tuple[dict, dict]:
    npc_points: dict[int, set] = defaultdict(set)
    obj_points: dict[int, set] = defaultdict(set)
    for path in root.rglob("*.java"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for const, x, y, z in RE_NPC_STEP.findall(text):
            if const in ids["npc"]:
                npc_points[ids["npc"][const]].add((int(x), int(y), int(z)))
        for const, x, y, z in RE_OBJ_STEP.findall(text):
            if const in ids["object"]:
                obj_points[ids["object"][const]].add((int(x), int(y), int(z)))
    return npc_points, obj_points


def scan_collections(root: Path, ids: dict) -> dict[str, list[int]]:
    """Quest Helper's named item groups -- PICKAXES, AXES, ARDY_CLOAKS.

    These are the closed sets behind the guide's category words ("Pickaxe",
    "Axe", "Ardy Cloak"), which are not items and can never resolve to one on
    the wiki. Mapping a guide word onto a collection is a human judgement and
    lives in curated/; this only extracts what the collections contain.
    """
    path = root / "com" / "questhelper" / "collections" / "ItemCollections.java"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, list[int]] = {}
    for name, body in RE_COLLECTION.findall(text):
        members = [ids["item"][c] for c in RE_ITEM_CONST.findall(body) if c in ids["item"]]
        # Ordered best-tier-first by Quest Helper's own convention; keep that
        # order but drop repeats.
        seen: list[int] = []
        for item in members:
            if item not in seen:
                seen.append(item)
        if seen:
            out[name] = seen
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--ids", type=Path, default=REPO / "build" / "ids.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "atlas.json")
    args = ap.parse_args()

    root = args.source / "src" / "main" / "java"
    if not root.is_dir():
        print(f"no quest-helper source at {root}; writing an empty atlas")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"npc": {}, "object": {}, "collections": {}}),
                            encoding="utf-8")
        return 0

    ids = json.loads(args.ids.read_text(encoding="utf-8"))
    npc_points, obj_points = scan_steps(root, ids)
    collections_ = scan_collections(root, ids)

    def pack(points: dict[int, set]) -> dict[str, dict]:
        return {
            str(game_id): {
                "points": sorted([list(p) for p in pts]),
                # Several coordinates for one ID is normal: Quest Helper points
                # at whichever instance a given quest needs. Recorded, not
                # resolved -- picking one here would be a guess.
                "ambiguous": len(pts) > 1,
            }
            for game_id, pts in sorted(points.items())
        }

    atlas = {
        "source": "quest-helper (BSD 2-Clause), RuneLite ids from " + ids.get("_source", "?"),
        "npc": pack(npc_points),
        "object": pack(obj_points),
        "collections": collections_,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(atlas, indent=1), encoding="utf-8")

    npc_amb = sum(1 for v in atlas["npc"].values() if v["ambiguous"])
    obj_amb = sum(1 for v in atlas["object"].values() if v["ambiguous"])
    print(f"npc ids       {len(atlas['npc']):5}  ({npc_amb} with several points)")
    print(f"object ids    {len(atlas['object']):5}  ({obj_amb} with several points)")
    print(f"collections   {len(collections_):5}  "
          f"({sum(len(v) for v in collections_.values())} item ids)")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

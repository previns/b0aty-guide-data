"""Stage 5: schema-check dist/guide.json and report coverage against a baseline.

Fails the build when the shape is wrong, when structural invariants break, or
when resolved coverage drops more than --tolerance points below
data/coverage-baseline.json. A drop is usually a wiki edit that broke a parsing
assumption, and it should stop a release rather than ship quietly.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemaVersion", "sections", "episodes", "contentHash", "migrations"],
    "properties": {
        "schemaVersion": {"const": 1},
        "sourceRevid": {"type": ["integer", "null"]},
        "sourcePage": {"type": ["string", "null"]},
        "contentHash": {"type": "string", "minLength": 8},
        "generatedAt": {"type": "string"},
        "migrations": {
            "type": "object",
            "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{10}$"},
        },
        "preamble": {"type": "array", "items": {"type": "string"}},
        "episodes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["ordinal", "title", "videoIds", "sectionIds"],
                "properties": {
                    "ordinal": {"type": "integer", "minimum": 1},
                    "title": {"type": "string", "minLength": 1},
                    "videoIds": {"type": "array", "items": {"type": "string"}},
                    "sectionIds": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "slug", "ordinal", "title", "steps", "imageUrls"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[0-9a-f]{10}$"},
                    "slug": {"type": "string", "minLength": 1},
                    "ordinal": {"type": "integer", "minimum": 0},
                    "title": {"type": "string", "minLength": 1},
                    "bankNumber": {"type": ["integer", "null"]},
                    "bankSuffix": {"type": ["string", "null"]},
                    "episodeOrdinal": {"type": ["integer", "null"]},
                    "continuationOf": {"type": ["string", "null"]},
                    "imageUrls": {
                        "type": "array",
                        "items": {"type": "string", "pattern": "^https://"},
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["id", "ordinal", "depth", "kind", "text"],
                            "properties": {
                                "id": {"type": "string", "pattern": "^[0-9a-f]{10}$"},
                                "ordinal": {"type": "integer", "minimum": 0},
                                "depth": {"type": "integer", "minimum": 1, "maximum": 4},
                                "kind": {"enum": ["step", "note", "trailing-note"]},
                                "text": {"type": "string", "minLength": 1},
                                "inventorySlots": {"type": "integer", "minimum": 0},
                                "questFollow": {"type": "boolean"},
                                "questStartOnly": {"type": "boolean"},
                                "questStopValue": {"type": "integer", "minimum": 1},
                                "questStopCondition": {"type": "object"},
                                "questStopUnresolved": {"type": "boolean"},
                                "questStopItems": {
                                    "type": "array", "minItems": 1,
                                    "items": {
                                        "type": "object", "required": ["name", "count", "ids"],
                                        "properties": {
                                            "name": {"type": "string", "minLength": 1},
                                            "count": {"type": "integer", "minimum": 1},
                                            "ids": {"type": "array", "minItems": 1, "uniqueItems": True,
                                                    "items": {"type": "integer", "minimum": 0}},
                                        },
                                    },
                                },
                                "dialogue": {
                                    "type": "array",
                                    "items": {"type": "array", "items": {"type": "integer"}},
                                },
                                "target": {
                                    "type": "object",
                                    "required": ["name", "confidence"],
                                    "properties": {
                                        "name": {"type": "string", "minLength": 1},
                                        "kind": {"type": ["string", "null"]},
                                        "ids": {"type": "array", "items": {"type": "integer"}},
                                        "points": {
                                            "type": "array",
                                            "items": {
                                                "type": "array",
                                                "minItems": 3,
                                                "maxItems": 3,
                                                "items": {"type": "integer"},
                                            },
                                        },
                                        "confidence": {
                                            "enum": [
                                                "linked", "wiki-exact", "wiki-redirect",
                                                "inferred", "manual",
                                            ]
                                        },
                                    },
                                },
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": "string", "minLength": 1},
                                            "ids": {"type": "array", "items": {"type": "integer"}},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def invariants(guide: dict) -> list[str]:
    """Structural truths a schema cannot express."""
    errors: list[str] = []

    step_ids = [st["id"] for s in guide["sections"] for st in s["steps"]]
    if len(step_ids) != len(set(step_ids)):
        duplicates = [i for i, c in Counter(step_ids).items() if c > 1]
        errors.append(f"{len(duplicates)} duplicate step id(s), e.g. {duplicates[:3]}")

    slugs = [s["slug"] for s in guide["sections"]]
    if len(slugs) != len(set(slugs)):
        errors.append("duplicate section slugs")

    section_ids = {s["id"] for s in guide["sections"]}
    for section in guide["sections"]:
        parent = section.get("continuationOf")
        if parent and parent not in section_ids:
            errors.append(f"{section['slug']} continues a section that does not exist")
        if [st["ordinal"] for st in section["steps"]] != list(range(len(section["steps"]))):
            errors.append(f"{section['slug']} has non-dense step ordinals")

    for episode in guide["episodes"]:
        for sid in episode["sectionIds"]:
            if sid not in section_ids:
                errors.append(f"episode {episode['ordinal']} references unknown section {sid}")
                break

    known = set(step_ids)
    dangling = [old for old, new in guide["migrations"].items() if new not in known]
    if dangling:
        errors.append(f"{len(dangling)} migration(s) point at ids that no longer exist")

    return errors


def image_problems(guide: dict) -> list[str]:
    """Every screenshot must be on the allowed host and carry a hash.

    The links come from a wiki page anyone can edit, and the plugin refuses an
    image with no recorded hash -- so a missing one is a silently blank panel
    rather than a loud failure. Catching it here is the difference between a
    build that fails and a release that quietly loses its screenshots.
    """
    hashes = guide.get("imageHashes", {})
    problems = []
    for section in guide.get("sections", []):
        for url in section.get("imageUrls", []) or []:
            if not url.startswith("https://i.ibb.co/"):
                problems.append(f"{section.get('title')}: image on an unexpected host: {url}")
            elif url not in hashes:
                problems.append(f"{section.get('title')}: no recorded hash for {url}")
            elif len(hashes[url]) != 64:
                problems.append(f"{section.get('title')}: malformed hash for {url}")
    return problems


def coverage(guide: dict) -> dict:
    steps = [st for s in guide["sections"] for st in s["steps"]]
    total = len(steps)
    with_target = sum(1 for st in steps if "target" in st)
    with_ids = sum(1 for st in steps if st.get("target", {}).get("ids"))
    with_points = sum(1 for st in steps if st.get("target", {}).get("points"))
    with_dest = sum(1 for st in steps if st.get("destination", {}).get("points"))
    with_quest = sum(
        1 for st in steps if any("constant" in t for t in st.get("tags", []))
    )
    resolved_items = sum(
        1 for st in steps for it in st.get("items", []) if it.get("ids")
    )
    all_items = sum(len(st.get("items", [])) for st in steps)

    return {
        "totalSteps": total,
        "sections": len(guide["sections"]),
        "episodes": len(guide["episodes"]),
        "stepsWithTarget": with_target,
        "stepsWithTargetIds": with_ids,
        "stepsWithTargetPoints": with_points,
        "stepsWithDestination": with_dest,
        "stepsWithQuestTag": with_quest,
        "itemMentions": all_items,
        "itemsResolved": resolved_items,
        "pct": {
            "target": round(100 * with_target / total, 2),
            "targetIds": round(100 * with_ids / total, 2),
            "targetPoints": round(100 * with_points / total, 2),
            "destination": round(100 * with_dest / total, 2),
            "questTag": round(100 * with_quest / total, 2),
            "items": round(100 * resolved_items / all_items, 2) if all_items else 0.0,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--baseline", type=Path, default=REPO / "data" / "coverage-baseline.json")
    ap.add_argument("--out", type=Path, default=REPO / "dist" / "coverage.json")
    ap.add_argument("--tolerance", type=float, default=2.0, help="max points of regression")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()

    guide = json.loads(args.guide.read_text(encoding="utf-8"))

    failures: list[str] = []
    try:
        jsonschema.validate(guide, SCHEMA)
        print("schema         ok")
    except jsonschema.ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path)
        failures.append(f"schema: {exc.message} at {path or '<root>'}")
        print(f"schema         FAILED at {path or '<root>'}")

    structural = invariants(guide)
    print(f"invariants     {'ok' if not structural else 'FAILED'}")
    failures.extend(structural)

    report = coverage(guide)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    image_issues = image_problems(guide)
    if image_issues:
        print("images        FAILED", file=sys.stderr)
        for issue in image_issues[:20]:
            print(f"  {issue}", file=sys.stderr)
        if len(image_issues) > 20:
            print(f"  ... and {len(image_issues) - 20} more", file=sys.stderr)
        return 1
    total_images = sum(len(s.get("imageUrls", []) or []) for s in guide.get("sections", []))
    print(f"images         ok   ({total_images} screenshots, all hashed)")

    print("\ncoverage:")
    for key, value in report["pct"].items():
        print(f"  {key:<14} {value:6.2f}%")

    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nbaseline written to {args.baseline}")
    elif args.baseline.exists():
        base = json.loads(args.baseline.read_text(encoding="utf-8"))
        print("\nvs baseline:")
        for key, value in report["pct"].items():
            before = base["pct"].get(key, 0.0)
            delta = value - before
            flag = ""
            if delta < -args.tolerance:
                flag = "  <-- REGRESSION"
                failures.append(
                    f"coverage.{key} fell {abs(delta):.2f} points "
                    f"({before:.2f}% -> {value:.2f}%), tolerance {args.tolerance}"
                )
            print(f"  {key:<14} {before:6.2f}% -> {value:6.2f}%  ({delta:+.2f}){flag}")
    else:
        print("\nno baseline yet; run with --write-baseline to create one")

    if failures:
        print(f"\nFAILED ({len(failures)}):")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("\nvalidate ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

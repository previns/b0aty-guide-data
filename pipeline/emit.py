"""Stage 6: write dist/guide.json, the file the plugin actually loads.

Also computes the `migrations` map: old step id -> new step id, for steps whose
text changed since the last release. The plugin applies it to saved progress on
load, and uses it to tell a player which already-completed banks moved under
them.

Note on the one fuzzy match in this repo
----------------------------------------
Migration matching compares removed step text against added step text within the
same section, above a high similarity threshold. This is fuzzy, and it is the
only fuzzy match in the pipeline.

It is acceptable here because of what a mistake costs. Everywhere else a wrong
match writes false game data that the plugin then shows as fact. Here a wrong
match restores one checkbox to the wrong step -- visible, harmless, and undone by
the player clicking it. The rule is about consequences, not about the technique.
"""
from __future__ import annotations

import argparse
import difflib
import re
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
MIGRATION_THRESHOLD = 0.85


# How far apart a set of coordinates may be and still describe one place.
#
# A town is about this across. Beyond it they are not one place with a fuzzy
# middle, they are several, and a marker on each is the world map covered in
# pins -- ninety-one of them for "Use the Deposit box by Entrana", ten thousand
# tiles apart. The rule for entities has always been that ambiguity is
# unresolved rather than first-match; this is that rule applied to one entity's
# coordinates. The ids stay, so whichever deposit box is in the room is still
# outlined. Only the claim to know where on the map it is goes away.
ONE_PLACE = 64


def scattered(points: list) -> bool:
    """Whether coordinates disagree about where the step is sending the player."""
    if len(points) < 2:
        return False
    xs = [p[0] for p in points if len(p) >= 2]
    ys = [p[1] for p in points if len(p) >= 2]
    if not xs:
        return False
    return max(max(xs) - min(xs), max(ys) - min(ys)) > ONE_PLACE


RE_LINK = re.compile(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<label>[^\]]*))?\]\]")


def display_text(text: str) -> str:
    """Render wiki link markup the way the wiki page itself renders it.

    `[[Father Aereck]]` reads as "Father Aereck" to anyone looking at the guide,
    so shipping the brackets to the panel shows the reader markup they never
    asked about. This is not a rewrite: the words are untouched, only the link
    syntax around them is resolved. `[Restless Ghost]` and `(3,1)` are literal
    text on the wiki and stay exactly as written.

    Step ids are unaffected -- normalize_for_id already strips this markup, so
    doing it here does not renumber anyone's progress.
    """
    return RE_LINK.sub(lambda m: (m.group("label") or m.group("target")).strip(), text)


def normalise(text: str) -> str:
    return " ".join(text.lower().split())


def match_quality(old_text: str, new_text: str, ordinal_gap: int) -> bool:
    """Is this pair the same step, reworded?

    A flat similarity threshold cannot answer this. Measured against the real
    guide, two *different* steps in the same section reach 0.80+ similarity in
    0.85% of pairs (and occasionally 1.00, where the guide repeats a line),
    while a genuine edit that appends a clarification can fall to 0.44. The
    distributions overlap, so any single cutoff either loses real edits or
    silently ticks steps the player never did.

    Two structural signals separate them instead:

      * containment -- an editor appending to or trimming a step keeps one text
        as a prefix of the other. Different steps almost never do.
      * position -- a reworded step stays roughly where it was.
    """
    old_norm, new_norm = normalise(old_text), normalise(new_text)
    if not old_norm or not new_norm:
        return False

    if old_norm.startswith(new_norm) or new_norm.startswith(old_norm):
        shorter = min(len(old_norm), len(new_norm))
        longer = max(len(old_norm), len(new_norm))
        # Guard against a one-word step being a prefix of everything.
        if shorter >= 12 and shorter / longer >= 0.4:
            return True

    ratio = difflib.SequenceMatcher(None, old_norm, new_norm).ratio()
    return ratio >= MIGRATION_THRESHOLD and ordinal_gap <= 2


def build_migrations(previous: dict | None, current: dict) -> dict[str, str]:
    if not previous:
        return {}

    def index(doc: dict) -> dict[str, dict[str, tuple[str, int]]]:
        out: dict[str, dict[str, tuple[str, int]]] = {}
        for section in doc["sections"]:
            out[section["slug"]] = {
                step["id"]: (step["text"], step.get("ordinal", i))
                for i, step in enumerate(section["steps"])
            }
        return out

    before, after = index(previous), index(current)
    migrations: dict[str, str] = {}

    for slug, old_steps in before.items():
        new_steps = after.get(slug)
        if not new_steps:
            continue
        removed = {i: v for i, v in old_steps.items() if i not in new_steps}
        added = {i: v for i, v in new_steps.items() if i not in old_steps}
        if not removed or not added:
            continue

        available = dict(added)
        for old_id, (old_text, old_ordinal) in removed.items():
            best_id, best_score = None, 0.0
            for new_id, (new_text, new_ordinal) in available.items():
                if not match_quality(old_text, new_text, abs(new_ordinal - old_ordinal)):
                    continue
                score = difflib.SequenceMatcher(
                    None, normalise(old_text), normalise(new_text)
                ).ratio()
                if score > best_score:
                    best_id, best_score = new_id, score
            if best_id:
                migrations[old_id] = best_id
                del available[best_id]

    return migrations


def project(doc: dict) -> dict:
    """Shape the plugin's contract. Internal build fields do not ship."""
    sections = []
    for section in doc["sections"]:
        steps = []
        for step in section["steps"]:
            out = {
                "id": step["id"],
                "ordinal": step["ordinal"],
                "depth": step["depth"],
                "kind": step["kind"],
                "text": display_text(step["raw"]),
            }
            if step.get("videoIds"):
                out["videoIds"] = step["videoIds"]
            merged = step.get("merged") or {}
            out.update(merged)
            target = out.get("target")
            if target is not None:
                # Last, so it sees the points every earlier pass and the curated
                # overrides settled on.
                target["scattered"] = scattered(target.get("points") or [])
            steps.append(out)

        sections.append(
            {
                "id": section["id"],
                "slug": section["slug"],
                "ordinal": section["ordinal"],
                "title": section["title"],
                "bankNumber": section["bankNumber"],
                "bankSuffix": section["bankSuffix"],
                "episodeOrdinal": section["episodeOrdinal"],
                "continuationOf": section["continuationOf"],
                "imageUrls": section["imageUrls"],
                "steps": steps,
            }
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourcePage": doc.get("page"),
        "sourceRevid": doc.get("revid"),
        # When the wiki page was last edited, which is what a player means by
        # "how current is this". generatedAt only says when the build ran.
        "sourceRevisionAt": doc.get("revisionAt"),
        "episodes": [
            {
                "ordinal": e["ordinal"],
                "title": e["title"],
                "videoIds": e["videoIds"],
                "sectionIds": e["sectionIds"],
            }
            for e in doc["episodes"]
        ],
        "sections": sections,
        # Quest Helper's step list for the quests some step references, stored
        # once here and referenced by key from the steps themselves.
        "questHelpers": doc.get("questHelpers", {}),
        "diaryTasks": doc.get("diaryTasks", {}),
        # sha256 per screenshot, so the plugin can refuse bytes that do not
        # match what was hashed at build time. The host allowlist stops a link
        # pointing at another server; this stops the picture behind an
        # unchanged link being swapped afterwards.
        "imageHashes": doc.get("imageHashes", {}),
        "preamble": doc.get("preamble", []),
    }


def content_hash(payload: dict) -> str:
    """Hash the content only, so an unchanged guide keeps a stable hash across
    rebuilds. generatedAt and the hash itself are excluded by construction."""
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=REPO / "build" / "merged.json")
    ap.add_argument("--out", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--previous", type=Path, default=None,
                    help="prior guide.json for the migrations diff (defaults to --out)")
    args = ap.parse_args()

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    payload = project(doc)

    previous_path = args.previous or args.out
    previous = None
    if previous_path.exists():
        previous = json.loads(previous_path.read_text(encoding="utf-8"))

    migrations = build_migrations(previous, payload)
    carried = (previous or {}).get("migrations", {})
    # Keep old mappings alive: a player who skipped several releases still needs
    # the chain from their saved id to the current one.
    combined = {**carried, **migrations}
    for old_id, mid in list(carried.items()):
        if mid in migrations:
            combined[old_id] = migrations[mid]

    # An id that maps to itself is noise, and chaining carried entries can
    # produce one. Dropping them keeps the map meaningful and stops it growing
    # by a useless entry on every release.
    payload["migrations"] = {
        old: new for old, new in combined.items() if old != new
    }
    payload["contentHash"] = content_hash({k: v for k, v in payload.items()
                                           if k not in ("migrations", "contentHash")})
    payload["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    steps = sum(len(s["steps"]) for s in payload["sections"])
    size = args.out.stat().st_size
    unchanged = previous and previous.get("contentHash") == payload["contentHash"]

    print(f"schemaVersion  {payload['schemaVersion']}")
    print(f"sourceRevid    {payload['sourceRevid']}")
    print(f"contentHash    {payload['contentHash']}{'  (unchanged)' if unchanged else ''}")
    print(f"episodes       {len(payload['episodes'])}")
    print(f"sections       {len(payload['sections'])}")
    print(f"steps          {steps}")
    print(f"migrations     {len(combined)} ({len(migrations)} new this build)")
    print(f"size           {size / 1024:.0f} KiB")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Stage 0b: the pipeline inputs that do NOT come from the wiki.

Packs build/ -> pinned/ for a person, unpacks pinned/ -> build/ for CI.

Why this exists
---------------
Six stages cannot run on a runner. `build_id_index` reads RuneLite's constants
out of a jar with `javap`; `build_atlas`, `build_quest_steps`, `build_qh_hints`
and `build_quest_objects` read the vendored Quest Helper source, which lives
beside this repository rather than inside it. Their outputs are inputs to
`merge_curated`, so the daily wiki sync failed on the first of them -- every
run since the workflow was added, on a missing `build/runelite/Quest.java`.

The fix is not to make CI rebuild them. It is to pin them.

A Quest Helper refresh is a deliberate act here, checked by
`tests/test_vendored_source.py` and reviewed by a person, because it rewrites
guidance across the whole guide. A wiki sync must therefore change only what the
wiki changed. If a runner re-derived these from upstream, a routine "Wiki sync"
pull request would quietly carry a Quest Helper upgrade inside it, which is the
one thing the review is there to catch.

So: these files change when a person refreshes Quest Helper, and at no other
time. Committed, they make the sync reproducible and its diff honest.

Gzipped, because they are 22.5 MB of JSON and 2.0 MB of gzip -- quest_steps
alone is 17.5 MB and compresses by 94%. Every refresh writes another copy into
history, so the difference compounds.

    python pipeline/pin_reference.py --pack     # after refreshing quest-helper
    python pipeline/pin_reference.py --unpack   # what the workflow runs
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUILD = REPO / "build"
PINNED = REPO / "pinned"

# Everything merge_curated, emit, worklist and audit read that a runner cannot
# produce. Kept explicit rather than globbed: a new artifact should have to be
# named here, so that "the sync went green" and "the sync built the right thing"
# do not quietly come apart.
COMPRESSED = (
    "ids.json",
    "atlas.json",
    "qh_hints.json",
    "quest_objects.json",
    "quest_steps.json",
)

# Vendored source, copied rather than compressed: 98 KiB in total, and being
# able to read it in a diff is worth more than the bytes.
#
# Quest.java names the quests merge_curated joins the guide's tags against. The
# worldmap Location files are what curated/places.yaml resolves through, so
# leaving them out makes "Wizards Tower" point at nothing -- which is how this
# list came to be checked rather than assumed.
VERBATIM = (
    "runelite/Quest.java",
    "runelite/AgilityCourseLocation.java",
    "runelite/DungeonLocation.java",
    "runelite/FairyRingLocation.java",
    "runelite/MinigameLocation.java",
    "runelite/RunecraftingAltarLocation.java",
    "runelite/TeleportLocationData.java",
    "runelite/TransportationPointLocation.java",
)


def pack() -> int:
    missing = [name for name in COMPRESSED if not (BUILD / name).exists()]
    missing += [name for name in VERBATIM if not (BUILD / name).exists()]
    if missing:
        print("nothing to pin; run the full pipeline first. missing:", file=sys.stderr)
        for name in missing:
            print(f"  build/{name}", file=sys.stderr)
        return 1

    PINNED.mkdir(parents=True, exist_ok=True)
    total_raw = total_gz = 0
    for name in COMPRESSED:
        source = BUILD / name
        target = PINNED / (name + ".gz")
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as raw, gzip.open(target, "wb", compresslevel=9) as out:
            shutil.copyfileobj(raw, out)
        total_raw += source.stat().st_size
        total_gz += target.stat().st_size
        print(f"  {name:<20} {source.stat().st_size // 1024:>7} KiB"
              f" -> {target.stat().st_size // 1024:>6} KiB")

    for name in VERBATIM:
        target = PINNED / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BUILD / name, target)
        print(f"  {name:<20} {target.stat().st_size // 1024:>7} KiB (verbatim)")

    print(f"\npinned {len(COMPRESSED) + len(VERBATIM)} files, "
          f"{total_raw // 1024} KiB -> {total_gz // 1024} KiB")
    print("Commit pinned/ so the wiki sync builds against the quest-helper you "
          "just reviewed.")
    return 0


def unpack() -> int:
    if not PINNED.is_dir():
        print("no pinned/ directory. Run --pack locally and commit it, or the "
              "wiki sync has nothing to build against.", file=sys.stderr)
        return 1

    BUILD.mkdir(parents=True, exist_ok=True)
    written = 0
    for name in COMPRESSED:
        source = PINNED / (name + ".gz")
        if not source.exists():
            print(f"missing pinned/{name}.gz -- merge_curated will fail on it.",
                  file=sys.stderr)
            return 1
        target = BUILD / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(source, "rb") as raw, target.open("wb") as out:
            shutil.copyfileobj(raw, out)
        written += 1
        print(f"  build/{name:<20} {target.stat().st_size // 1024:>7} KiB")

    for name in VERBATIM:
        source = PINNED / name
        if not source.exists():
            print(f"missing pinned/{name}", file=sys.stderr)
            return 1
        target = BUILD / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        written += 1
        print(f"  build/{name:<20} {target.stat().st_size // 1024:>7} KiB")

    print(f"\nunpacked {written} files into build/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pack", action="store_true",
                       help="build/ -> pinned/, after refreshing quest-helper")
    group.add_argument("--unpack", action="store_true",
                       help="pinned/ -> build/, what the workflow runs")
    args = ap.parse_args()
    return pack() if args.pack else unpack()


if __name__ == "__main__":
    raise SystemExit(main())

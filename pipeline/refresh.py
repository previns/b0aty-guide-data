"""Run the whole pipeline in order, from the wiki to dist/guide.json.

The stage order is not obvious, and two parts of it are actively misleading:

  * ``validate`` reads ``dist/guide.json``, so running it before ``emit``
    silently reports the *previous* build's numbers and looks like a clean
    no-op.
  * ``fetch_images`` runs against the emitted guide, so a build whose
    screenshots changed needs ``emit`` twice, with ``merge_curated`` between.

Both are written down in CLAUDE.md, and both are exactly the kind of
thing a person refreshing this once a quarter will not remember. So the order
lives here, in something runnable, and the prose explains why.

    python pipeline/refresh.py              # the full refresh, from the wiki
    python pipeline/refresh.py --offline    # rebuild from build/, no network
    python pipeline/refresh.py --dry-run    # print the plan and stop

Nothing here is new logic. Every stage is still its own script with its own
artifact, and any one of them can still be run alone -- which is the point of
the boundaries, and why this driver does not merge them.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# (module, needs the network, why it is here)
STAGES = [
    ("fetch", True, "the current wikitext, and the revision id everything is stamped with"),
    ("parse", False, "wikitext into sections and steps"),
    ("annotate", False, "entities, dialogue and tags out of the step text"),
    ("build_id_index", False, "RuneLite's own constants, via javap"),
    ("build_atlas", False, "quest-helper coordinates, joined on game ids"),
    ("build_diary_tasks", False, "diary completion bits, in the wiki's task order"),
    ("build_quest_steps", False, "quest-helper step lists, keyed by quest progress"),
    ("resolve_wiki", True, "names to ids, through wiki pages only -- never by similarity"),
    ("merge_curated", False, "everything above, plus the human-only curated/ files"),
    ("emit", False, "dist/guide.json, with the migration map for reworded steps"),
    ("fetch_images", True, "a sha256 per screenshot -- reads the guide emit just wrote"),
    ("merge_curated", False, "again, now that the image hashes exist"),
    ("emit", False, "again, so the hashes reach the shipped file"),
    ("validate", False, "coverage against the baseline -- reads dist/, so it must be last"),
]


def run(module: str) -> float:
    """Run one stage as its own process, so a crash names the stage."""
    started = time.monotonic()
    print(f"\n=== {module} " + "=" * (66 - len(module)), flush=True)
    # Unbuffered, or a stage's own output arrives in one burst after the header
    # of the stage *after* it, which makes a failure look like it came from the
    # wrong script -- the one thing these stage boundaries exist to prevent.
    result = subprocess.run(
        [sys.executable, str(REPO / "pipeline" / f"{module}.py")],
        cwd=REPO,
        env=dict(os.environ, PYTHONUNBUFFERED="1"),
    )
    if result.returncode != 0:
        raise SystemExit(f"\n{module} failed ({result.returncode}); nothing after it ran")
    return time.monotonic() - started


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--offline", action="store_true",
                    help="skip the stages that hit the network, rebuilding from build/")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and stop")
    args = ap.parse_args()

    plan = [s for s in STAGES if not (args.offline and s[1])]

    print(f"{len(plan)} stage(s)" + (", offline" if args.offline else ""))
    for module, network, why in plan:
        print(f"  {module:<20} {'net  ' if network else '     '} {why}")
    if args.dry_run:
        return

    timings = []
    for module, _, _ in plan:
        timings.append((module, run(module)))

    print("\n=== done " + "=" * 66)
    for module, seconds in timings:
        print(f"  {module:<20} {seconds:6.1f}s")
    print(f"  {'total':<20} {sum(t for _, t in timings):6.1f}s")
    print("\nNow:")
    print("  1. compare the coverage validate just printed against the last build")
    print("  2. cp dist/guide.json"
          " ../b0aty-guide-plugin/src/main/resources/com/b0atyguide/")
    print("  3. run the plugin's tests -- GuideDataTest reads the shipped file")


if __name__ == "__main__":
    main()

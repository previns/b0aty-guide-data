"""Stage 0: extract RuneLite's ID constants into build/ids.json.

Quest Helper's source names things symbolically -- `NpcID.FATHER_AERECK`,
`ItemID.LAWRUNE` -- so nothing in it can be joined to our data until those names
carry numbers. This reads them straight out of the compiled `runelite-api` jar
with `javap`, which means the numbers always match the client the plugin is
built against rather than a copy that silently drifts.

Output: {"item": {"LAWRUNE": 563, ...}, "npc": {...}, "object": {...}}
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The gameval classes are the ones Quest Helper imports. The older
# net.runelite.api.ItemID still exists but is being retired upstream.
CLASSES = {
    "item": "net.runelite.api.gameval.ItemID",
    "npc": "net.runelite.api.gameval.NpcID",
    "object": "net.runelite.api.gameval.ObjectID",
    # Achievement-diary task completion lives in these, one per diary region,
    # a bit per task. The plugin may not use reflection, so the numbers have to
    # travel in the data rather than being looked up by name at runtime.
    "varplayer": "net.runelite.api.gameval.VarPlayerID",
    # Quest progress lives in a varbit for most quests, a varplayer for the
    # oldest ones. Quest Helper keys its step list off whichever it is.
    "varbit": "net.runelite.api.gameval.VarbitID",
    # Per-spell widget ids, so a step can point at the spell to click. A nested
    # class, which javap takes with a dollar sign.
    "spell": "net.runelite.api.gameval.InterfaceID$MagicSpellbook",
}

RE_CONST = re.compile(r"\bint\s+([A-Z0-9_]+)\s*=\s*(-?\d+)")


def find_api_jar(explicit: Path | None) -> Path | None:
    """Locate runelite-api.jar, preferring an explicit path."""
    if explicit:
        return explicit if explicit.is_file() else None
    # The sibling plugin repo pulls it into the Gradle cache as a normal
    # dependency; there is no RuneLite checkout to look in.
    cache = Path.home() / ".gradle" / "caches" / "modules-2" / "files-2.1" / "net.runelite" / "runelite-api"
    if not cache.is_dir():
        return None
    jars = [j for j in cache.rglob("runelite-api-*.jar") if "sources" not in j.name]
    # Newest version last: the directory names are version numbers.
    return sorted(jars, key=lambda j: j.parent.parent.name)[-1] if jars else None


def constants(jar: Path, class_name: str) -> dict[str, int]:
    result = subprocess.run(
        ["javap", "-constants", "-cp", str(jar), class_name],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"javap failed for {class_name}: {result.stderr.strip()[:200]}")
    return {m.group(1): int(m.group(2)) for m in RE_CONST.finditer(result.stdout)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jar", type=Path, default=None, help="path to runelite-api-*.jar")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "ids.json")
    args = ap.parse_args()

    jar = find_api_jar(args.jar)
    if jar is None:
        print("no runelite-api jar found; build the plugin repo once, or pass --jar",
              file=sys.stderr)
        return 1

    index = {kind: constants(jar, cls) for kind, cls in CLASSES.items()}
    index["_source"] = jar.name

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index), encoding="utf-8")

    print(f"jar {jar.name}")
    for kind in CLASSES:
        print(f"  {kind:8} {len(index[kind]):6} constants")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

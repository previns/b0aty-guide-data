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
import zipfile
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


def interface_ids(jar: Path) -> dict[str, int]:
    """`Shopmain.ITEMS` -> the number, for every nested class of InterfaceID.

    Quest Helper points at parts of an interface by these names -- the shop
    grid, the multi-skill menu, the Quetzal's icons -- and a highlight it hangs
    on one is the only guidance a step has while a menu is open. Read the same
    way as the spell ids, which are one nested class of this same table.

    Keyed as quest-helper writes them: "Shopmain.ITEMS". The bare constants on
    InterfaceID itself are kept under their own name.
    """
    out: dict[str, int] = dict(constants(jar, "net.runelite.api.gameval.InterfaceID"))

    # The nested class names come from the jar's own entries: javap lists a
    # class's constants, not the classes nested inside it.
    with zipfile.ZipFile(jar) as archive:
        nested_names = {
            entry.rsplit("$", 1)[1][:-len(".class")]
            for entry in archive.namelist()
            if entry.startswith("net/runelite/api/gameval/InterfaceID$")
            and entry.endswith(".class")
        }

    for nested in sorted(nested_names):
        try:
            for name, value in constants(
                    jar, "net.runelite.api.gameval.InterfaceID$" + nested).items():
                out[nested + "." + name] = value
        except RuntimeError:
            # A class javap cannot read is one name that will not resolve, and
            # a highlight that cannot resolve is dropped rather than guessed.
            continue
    return out


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
    index["interface"] = interface_ids(jar)
    index["_source"] = jar.name

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(index), encoding="utf-8")

    print(f"jar {jar.name}")
    for kind in list(CLASSES) + ["interface"]:
        print(f"  {kind:8} {len(index[kind]):6} constants")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

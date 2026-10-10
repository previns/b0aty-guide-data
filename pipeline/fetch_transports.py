"""Stage 3i: how the route gets from one place to another.

Writes build/transports.json.

Why the guide needs it
----------------------
The guide says "Take the boat to Rimmington" and never says Captain Barnaby.
140 steps travel that way and **98 of them point at nothing** -- 43 boats, 19
fairy rings, 12 minecarts, 7 minigame teleports -- so the plugin walked the
player to a dock and went quiet.

The mapping already exists. Skretzo/shortest-path is vendored here already for
`open-transports.tsv`, under the same BSD-2-Clause and attributed in NOTICE.md,
and it keeps a file per transport kind: boats, ships, charter ships, minecarts,
canoes, spirit trees, fairy rings, gliders, carpets, balloons, quetzals,
mushtrees, obelisks, and the minigame teleports.

What the rows look like
-----------------------
    # Ardougne, Brimhaven, Rimmington
    2954 3158 0<TAB>2683 3269 0<TAB>Rimmington Captain Barnaby 9250<TAB>...

The third column is `menuOption menuTarget objectID` and neither half is safely
separable -- the option can be multi-word ("Pirate's Cove") and so can the
target ("Lokar Searunner"). Only the trailing id is unambiguous, so the id is
parsed out and the rest kept verbatim. That reads well anyway: for these the
option *is* the destination, so "Rimmington Captain Barnaby" says both where it
goes and who to talk to.

The comment headers matter as much as the rows
----------------------------------------------
They name the endpoints of each route, and that is what lets a guide sentence
find its boat. Matching a destination by coordinate instead was measured and
rejected: a town's wiki coordinate is its centre and the dock is not, so the
radius needed to reach the dock (120 tiles) makes 22 of 29 matches ambiguous.
The label is an exact name, and the coordinate is then only used to pick which
of two directions along that route is meant.

Minigame teleports carry no origin -- they are cast from anywhere -- so they are
kept in their own list.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = ("https://raw.githubusercontent.com/Skretzo/shortest-path/master/"
       "src/main/resources/transports")
AGENT = "b0aty-guide-pipeline (https://github.com/previns/b0aty-hcim-guide-v3)"

# Everything shaped origin -> destination. The order is the order they are
# reported in, so the busiest kinds read first.
JOURNEYS = (
    "boats", "ships", "charter_ships", "minecarts", "canoes", "spirit_trees",
    "fairy_rings", "gnome_gliders", "magic_carpets", "hot_air_balloons",
    "quetzals", "magic_mushtrees", "wilderness_obelisks",
)
# Cast from anywhere, so there is no origin column.
DESTINATIONS = ("teleportation_minigames",)

# The big combined file is the *walking* network -- 5,142 rows of stairs,
# ladders, agility shortcuts and doors -- and is deliberately not imported: that
# is the pathfinding data this project does not ship.
#
# But 56 vehicle rows live only in there and in none of the per-kind files,
# among them the Primio quetzal between Varrock and Civitas illa Fortis, the
# Karamja travel cart, the Mountain Guide and Daero. A step naming Varlamore had
# nothing to point at because of it. So the file is read and filtered to rows
# whose action is one of the ways you board something.
MIXED = ("transports",)
BOARDING = ("Travel", "Board", "Talk-to", "Quick-board", "Ride")

RE_POINT = re.compile(r"^\s*(\d{1,5})\s+(\d{1,5})\s+(\d)\s*$")


def get(name: str) -> str:
    request = urllib.request.Request(f"{RAW}/{name}.tsv",
                                     headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def point(text: str) -> list[int] | None:
    found = RE_POINT.match(text or "")
    return [int(found.group(1)), int(found.group(2)), int(found.group(3))] if found else None


def rows(text: str):
    """Each data row with the comment header it sits under.

    The first comment is the column legend, not a route, so it is skipped by
    looking for the word it always starts with.
    """
    label = ""
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if body and not body.lower().startswith(("origin", "destination")):
                label = body
            continue
        if line.strip():
            yield label, line.split("\t")


def action(cell: str) -> tuple[int | None, str]:
    """(object or npc id, the words around it).

    Only the trailing id is unambiguous; splitting the option from the target
    is not, so the rest is kept as written.
    """
    parts = (cell or "").split()
    if len(parts) < 2 or not parts[-1].isdigit():
        return None, (cell or "").strip()
    return int(parts[-1]), " ".join(parts[:-1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "build" / "transports.json")
    ap.add_argument("--delay", type=float, default=0.3)
    args = ap.parse_args()

    routes: list[dict] = []
    hubs: list[dict] = []
    arrivals: list[dict] = []
    teleports: list[dict] = []
    dropped = 0
    per_kind: dict[str, tuple[int, int]] = {}

    for kind in JOURNEYS:
        text = get(kind)
        time.sleep(args.delay)
        before, before_hubs = len(routes), len(hubs)
        for label, cells in rows(text):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) < 3:
                dropped += 1
                continue
            origin, destination = point(cells[0]), point(cells[1])
            found, words = action(cells[2])
            # The mirror image of a hub: no origin, just somewhere the network
            # reaches. The minecart files list their stops this way, which is
            # what tells a step naming Lovakengj that a minecart goes there.
            if origin is None and destination is not None:
                arrivals.append({"kind": kind, "label": label,
                                 "destination": destination})
                continue
            if origin is None or found is None:
                dropped += 1
                continue
            entry = {
                "kind": kind,
                "label": label,
                "origin": origin,
                "id": found,
                "action": words,
                "quests": (cells[5].strip() if len(cells) > 5 else ""),
            }
            # A fairy ring, spirit tree or glider has no destination column:
            # you board it from here and choose where to go in an interface.
            # That is still worth knowing -- it says which object to click --
            # so it is kept apart rather than dropped.
            if destination is None:
                hubs.append(entry)
            else:
                entry["destination"] = destination
                routes.append(entry)
        per_kind[kind] = (len(routes) - before, len(hubs) - before_hubs)

    for kind in MIXED:
        text = get(kind)
        time.sleep(args.delay)
        before, before_hubs = len(routes), len(hubs)
        for label, cells in rows(text):
            if not any(cell.strip() for cell in cells) or len(cells) < 3:
                continue
            words = cells[2].split()
            if not words or words[0] not in BOARDING:
                continue
            origin, destination = point(cells[0]), point(cells[1])
            found, said = action(cells[2])
            if origin is None or found is None:
                continue
            entry = {"kind": kind, "label": label, "origin": origin,
                     "id": found, "action": said,
                     "quests": (cells[5].strip() if len(cells) > 5 else "")}
            if destination is None:
                hubs.append(entry)
            else:
                entry["destination"] = destination
                routes.append(entry)
        per_kind[kind] = (len(routes) - before, len(hubs) - before_hubs)

    for kind in DESTINATIONS:
        text = get(kind)
        time.sleep(args.delay)
        for label, cells in rows(text):
            destination = point(cells[0]) if cells else None
            if destination is None:
                dropped += 1
                continue
            teleports.append({
                "kind": kind,
                "label": label,
                "destination": destination,
                "display": (cells[3].strip() if len(cells) > 3 else ""),
                "quests": (cells[2].strip() if len(cells) > 2 else ""),
            })

    labels = {r["label"] for r in routes if r["label"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"source": "Skretzo/shortest-path transports (BSD-2-Clause)",
         "routes": routes, "hubs": hubs, "arrivals": arrivals,
         "teleports": teleports}, indent=1), encoding="utf-8")

    print(f"routes            {len(routes):5}  (origin and destination both known)")
    print(f"hubs              {len(hubs):5}  (board here, choose where in an interface)")
    print(f"arrivals          {len(arrivals):5}  (somewhere a hub network reaches)")
    for kind, (count, hubbed) in per_kind.items():
        print(f"  {kind:<22} {count:4} routes {hubbed:4} hubs")
    print(f"minigame teleports{len(teleports):5}")
    print(f"named routes      {len(labels):5}  (the comment headers a step is matched against)")
    print(f"unparsed rows     {dropped:5}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

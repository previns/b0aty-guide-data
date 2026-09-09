"""Stage 3h: where items lie on the ground.

Writes build/item_spawns.json.

Why the guide needs it
----------------------
The route says "Collect 2x Purple Dye when passing" and never says where. The
author knows -- they wrote "when passing" because the spawn is on the way -- but
the plugin had nothing to aim at, so the dyes only ever outlined once the player
was already standing next to them. That is a highlight, not guidance.

The temptation is to type the coordinate in by hand. It was refused, and rightly:
one hand-typed tile fixes one step and nothing else, and the same gap covers 175
"acquires" steps with no target at all. Importing the spawn table fixes the class
and keeps fixing it as the wiki changes.

The wiki already holds this, structured, on every item page that has a spawn:

    {{ItemSpawnLine|name=Purple dye|location=[[East Ardougne]] - north of the
      [[Clock Tower (building)|Clock Tower]]|members=Yes|2563,3261|leagueRegion=Kandarin}}

376 pages transclude it, so the whole gazetteer is one short crawl rather than a
lookup per item.

Parsing notes, all of them learned from the data rather than assumed
--------------------------------------------------------------------
* Coordinates are *positional* parameters, one per spawn tile, and one line
  routinely carries many: Bones at the Wilderness Agility Course is a single
  line with five tiles.
* A tile may carry a quantity: ``2770,4516,qty:3``. The count is kept; a step
  that wants 3 coins wants the pile, not three trips.
* ``plane=`` is optional and defaults to 0. Underground spawns are already in
  world coordinates -- the Lumbridge cellar cabbage is ``3217,9622`` -- so no
  plane arithmetic is needed, only the explicit upper floors.
* ``mapID`` exists and is deliberately ignored. It identifies a wiki map tile,
  not a game plane, and reading it as one would move spawns into the sky.
* Both ``[[a|b]]`` and ``{{FloorNumber|uk=1}}`` appear inside ``location=``, so
  the parameter split has to respect link and template nesting. Splitting on a
  bare "|" silently truncates those locations and, worse, turns the tail of the
  link into a nonsense parameter.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = "https://oldschool.runescape.wiki/api.php"
AGENT = "b0aty-guide-pipeline (https://github.com/previns/b0aty-hcim-guide-v3)"
TEMPLATE = "Template:ItemSpawnLine"

# A coordinate parameter. Anchored, so a stray word is never mistaken for a
# tile. The trailing annotations are open-ended on purpose: the wiki writes
# ``qty:3``, ``qty:1-5`` for a random pile, and ``respawn:45`` for a slow one,
# and an exhaustive list of the ones seen today would silently drop tomorrow's.
RE_POINT = re.compile(
    r"^(\d{1,5})\s*,\s*(\d{1,5})((?:\s*,\s*[a-z]+:[^,]+)*)$", re.I)
RE_QTY = re.compile(r"qty:\s*(\d+)", re.I)
RE_NAMED = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*)$", re.S)


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def api(**params) -> dict:
    params.setdefault("format", "json")
    return json.loads(get(WIKI + "?" + urllib.parse.urlencode(params)))


def spawn_pages() -> list[str]:
    """Every article that transcludes the spawn template."""
    titles: list[str] = []
    following = None
    while True:
        query = dict(action="query", list="embeddedin", eititle=TEMPLATE,
                     eilimit=500, einamespace=0)
        if following:
            query.update(following)
        payload = api(**query)
        titles.extend(page["title"] for page in payload["query"]["embeddedin"])
        following = payload.get("continue")
        if not following:
            return titles


def wikitext(titles: list[str], delay: float) -> dict[str, str]:
    """Page text, 50 at a time -- the API's limit for an anonymous caller."""
    out: dict[str, str] = {}
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        payload = api(action="query", prop="revisions", rvprop="content",
                      rvslots="main", titles="|".join(batch))
        for page in payload["query"]["pages"].values():
            revisions = page.get("revisions")
            if not revisions:
                continue
            out[page["title"]] = revisions[0]["slots"]["main"]["*"]
        time.sleep(delay)
    return out


def templates(text: str) -> list[str]:
    """The body of every ItemSpawnLine, brace-matched rather than regexed.

    ``location`` can contain a template of its own, so "up to the first }}" ends
    the line in the wrong place and loses every parameter after it.
    """
    bodies: list[str] = []
    needle = "{{ItemSpawnLine"
    at = text.find(needle)
    while at >= 0:
        depth, i = 0, at
        while i < len(text) - 1:
            pair = text[i:i + 2]
            if pair == "{{":
                depth += 1
                i += 2
                continue
            if pair == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    bodies.append(text[at + 2:i - 2])
                    break
                continue
            i += 1
        else:
            break
        at = text.find(needle, i)
    return bodies


def parameters(body: str) -> list[str]:
    """Split on "|", ignoring the ones inside [[links]] and {{templates}}."""
    parts: list[str] = []
    buf: list[str] = []
    link = brace = 0
    i = 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair in ("[[", "]]"):
            link += 1 if pair == "[[" else -1
            link = max(link, 0)
            buf.append(pair)
            i += 2
            continue
        if pair in ("{{", "}}"):
            brace += 1 if pair == "{{" else -1
            brace = max(brace, 0)
            buf.append(pair)
            i += 2
            continue
        if body[i] == "|" and link == 0 and brace == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(body[i])
        i += 1
    parts.append("".join(buf))
    return parts


def plain(markup: str) -> str:
    """A location a person can read: no links, no templates, no stray pipes."""
    text = re.sub(r"\{\{[^{}]*\}\}", "", markup)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    # Removing a nested template can leave the brackets that framed it, as in
    # "church north of allotment patch ()".
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"\s+", " ", text).strip(" -–")


def parse(body: str) -> dict | None:
    """One spawn line: its item, where it is, and every tile it covers."""
    fields: dict[str, str] = {}
    points: list[list[int]] = []
    counts: list[int] = []
    for part in parameters(body)[1:]:
        found = RE_POINT.match(part.strip())
        if found:
            points.append([int(found.group(1)), int(found.group(2))])
            # "qty:1-5" is a random pile; the low end is what a player can rely
            # on having, so a step wanting more is not ticked off by luck.
            quantity = RE_QTY.search(found.group(3) or "")
            counts.append(int(quantity.group(1)) if quantity else 1)
            continue
        named = RE_NAMED.match(part)
        if named:
            fields[named.group(1).lower()] = named.group(2).strip()

    name = plain(fields.get("name", ""))
    if not name or not points:
        return None

    # Only an explicit plane. mapID is a wiki map tile and is not one.
    try:
        plane = int(fields.get("plane", "0"))
    except ValueError:
        plane = 0
    if not 0 <= plane <= 3:
        plane = 0

    return {
        "name": name,
        "location": plain(fields.get("location", "")),
        "members": fields.get("members", "").strip().lower().startswith("y"),
        "points": [[x, y, plane] for x, y in points],
        "counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=REPO / "build" / "item_spawns.json")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="seconds between API calls")
    args = parser.parse_args()

    titles = spawn_pages()
    pages = wikitext(titles, args.delay)

    items: dict[str, list[dict]] = {}
    lines = tiles = 0
    dropped = 0
    for text in pages.values():
        for body in templates(text):
            lines += 1
            spawn = parse(body)
            if spawn is None:
                dropped += 1
                continue
            tiles += len(spawn["points"])
            items.setdefault(spawn.pop("name"), []).append(spawn)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"source": "oldschool.runescape.wiki " + TEMPLATE,
         "items": {name: items[name] for name in sorted(items)}},
        indent=1), encoding="utf-8")

    spread = sorted(((sum(len(s["points"]) for s in v), k) for k, v in items.items()),
                    reverse=True)
    print(f"pages with spawns  {len(pages):5}")
    print(f"spawn lines        {lines:5}")
    print(f"  unparsed         {dropped:5}  (no name, or no coordinate)")
    print(f"items             {len(items):5}")
    print(f"tiles             {tiles:5}")
    print("\nmost scattered items:")
    for count, name in spread[:8]:
        print(f"  {count:5}  {name}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

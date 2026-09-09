"""Stage 3g: which shops sell what, and who runs them.

Writes build/shops.json.

Why the guide needs it
----------------------
The route says "Buy 2x Bronze Med Helm in Barbarian Village" and never says
Peksa. Naming the seller is the guide author's shorthand, not an omission: the
player is standing in the village and there is one shop. But the plugin has
nothing to highlight, so it walked them to the village and left them there.

Every shop page on the wiki carries what this needs:

    {{Infobox Shop
    |location = [[Barbarian Village]]
    |owner    = [[Peksa]]
    }}
    {{StoreLine|name=Bronze med helm|stock=5|restock=100}}

So: the owner is the npc to highlight, and the stock says which steps he
answers. `merge_curated` gives a buy step every shop that sells what it asks
for, and the plugin picks the one nearest the player -- which in Barbarian
Village is Peksa, and in Varrock is somebody else, without either being written
down anywhere.

Names, not ids
--------------
A StoreLine names an item the way the wiki does, and the wiki's own item
mapping turns that into a number. Both halves come from the same source, so the
join is exact and an item whose name is not in the mapping is dropped rather
than guessed at -- 761 of 5,066 stock lines, mostly items that are not tradeable
and so are not in a price mapping.

The owner is left as a name here. `resolve_wiki` resolves names to game ids and
coordinates, and doing it twice in two ways is how two answers start to differ.
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
MAPPING = "https://prices.runescape.wiki/api/v1/osrs/mapping"
AGENT = "b0aty-guide-pipeline (https://github.com/previns/b0aty-hcim-guide-v3)"

# A shop page written for several places numbers its fields: Trader Stan's
# Trading Post has twenty-one versions, one per port, with |owner1 = Trader
# Stan and |owner2..21 = Trader Crewmember. Matching only the unnumbered
# form dropped every one of those pages on the floor, which is why nobody
# in the guide sold soda ash and a step at the charter ship pointed at
# nobody for nine minutes.
RE_OWNER = re.compile(r"^\|\s*owner\d*\s*=\s*(.+)$", re.M)
RE_STORE_LINE = re.compile(r"\{\{StoreLine\|name=([^|}]+)")
RE_LINK = re.compile(r"\[\[([^\]|]+)")


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def api(**params) -> dict:
    params.setdefault("format", "json")
    return json.loads(get(WIKI + "?" + urllib.parse.urlencode(params)))


def shop_pages() -> list[str]:
    """Every page in Category:Shops."""
    titles: list[str] = []
    following = None
    while True:
        query = dict(action="query", list="categorymembers", cmtitle="Category:Shops",
                     cmlimit=500, cmnamespace=0)
        if following:
            query["cmcontinue"] = following
        page = api(**query)
        titles += [m["title"] for m in page["query"]["categorymembers"]]
        following = page.get("continue", {}).get("cmcontinue")
        if not following:
            return titles


def first_link(value: str) -> str:
    """"[[Peksa]]" -> "Peksa". Plain text is taken as it stands."""
    found = RE_LINK.findall(value)
    return (found[0] if found else value).strip()


def item_ids_by_name() -> dict[str, int]:
    """The wiki's own item mapping, lowercased for comparison."""
    out: dict[str, int] = {}
    for row in json.loads(get(MAPPING)):
        name = str(row.get("name", "")).strip().lower()
        if name:
            out.setdefault(name, int(row["id"]))
    return out


def read_shops(titles: list[str], delay: float) -> list[dict]:
    """Owner and stock for each shop page, in batches of fifty."""
    shops: list[dict] = []
    for start in range(0, len(titles), 50):
        page = api(action="query", prop="revisions", rvprop="content", rvslots="main",
                   titles="|".join(titles[start:start + 50]))
        for entry in page["query"]["pages"].values():
            try:
                text = entry["revisions"][0]["slots"]["main"]["*"]
            except (KeyError, IndexError):
                continue
            stock = [name.strip() for name in RE_STORE_LINE.findall(text)]
            # Every distinct owner the page names, in order. One shop staffed by
            # several people is several people to point at, and which of them is
            # in the room is decided at runtime by who is nearest.
            owners: list[str] = []
            for field in RE_OWNER.findall(text):
                who = first_link(field)
                if who and who not in owners:
                    owners.append(who)
            if not stock or not owners:
                # A shop with no stock is a redirect or a disambiguation, and
                # one with no owner is a chest or a stall -- nothing to point at.
                continue
            for who in owners:
                shops.append({"page": entry["title"], "owner": who, "stock": stock})
        time.sleep(delay)
    return shops


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "shops.json")
    ap.add_argument("--delay", type=float, default=0.2,
                    help="seconds between batches, to be polite to the wiki")
    args = ap.parse_args()

    titles = shop_pages()
    shops = read_shops(titles, args.delay)
    by_name = item_ids_by_name()

    sellers: dict[str, list[str]] = {}
    resolved = dropped = 0
    for shop in shops:
        for name in shop["stock"]:
            number = by_name.get(name.lower())
            if number is None:
                dropped += 1
                continue
            resolved += 1
            owners = sellers.setdefault(str(number), [])
            if shop["owner"] not in owners:
                owners.append(shop["owner"])

    owners = sorted({shop["owner"] for shop in shops})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"source": "oldschool.runescape.wiki Category:Shops",
         "owners": owners, "sellers": sellers}, indent=1), encoding="utf-8")

    print(f"shop pages       {len(titles):5}")
    print(f"  with stock     {len(shops):5}  (the rest are redirects, stalls and chests)")
    print(f"shopkeepers      {len(owners):5}")
    print(f"stock lines      {resolved:5}  resolved to an item")
    print(f"                 {dropped:5}  dropped; not in the wiki's item mapping")
    print(f"items on sale    {len(sellers):5}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

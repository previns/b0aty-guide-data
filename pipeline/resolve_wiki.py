"""Stage 3b: resolve extracted names to game IDs and coordinates via the wiki.

Reads build/annotated.json, writes build/entities.json and build/unresolved.json.

Why this is not the fuzzy join that broke the previous attempt
-------------------------------------------------------------
It never guesses a name. It only accepts:

  1. an exact wiki page title, or
  2. a redirect the wiki itself already contains -- created by a human editor,
     which is how "Gertude" (the guide's typo) legitimately reaches "Gertrude"
     and "Sedridor" reaches "Archmage Sedridor".
  3. a deterministic singular form of the same name ("Air Runes" -> "Air rune")
     or its sentence case ("Small Fishing Net" -> "Small fishing net"), each of
     which must itself be an exact page title. Fixed rewrite rules, not a
     similarity search: a variant with no page resolves to nothing.

A title the wiki does not have comes back explicitly `missing` and stays
unresolved. There is no edit distance, no substring match and no "closest name"
anywhere in this file -- the exact-title rule is what keeps nonsense out.

Where the page's infobox contradicts the verb we guessed ("Buy Chef's Hat"
parses as an NPC verb but the wiki says Item), the infobox wins and the step is
flagged `kindOverrodeIntent` for review. Discarding those cost 82 correctly
resolved entities and bought nothing.

The IDs and coordinates come from the page's own infobox, which is maintained by
the wiki community and is the same data the guide's links already point at.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "b0aty-guide-data/0.1 (https://github.com/previns/b0aty-guide-data)"
BATCH = 50

# Infobox type -> the kind of thing the plugin can do with it.
INFOBOX_KIND = {
    "npc": "npc",
    "monster": "npc",
    "scenery": "object",
    "item": "item",
    "location": "place",
    # These also carry a {{Map}}, and the guide routes through them constantly
    # ("Bank at...", "Minigame Teleport to Blast Furnace"). Treating them as
    # places costs nothing: a place resolves to coordinates, never to an ID that
    # a highlight could be drawn from, so a wrong one cannot outline the wrong
    # thing.
    "shop": "place",
    "activity": "place",
    "guild": "place",
    "dungeon": "place",
    "room": "place",
}

# Which infobox kinds are acceptable for a step's extracted intent. A "Talk to"
# step that lands on an Item page is a mis-extraction, not a discovery.
INTENT_ACCEPTS = {
    "npc": {"npc"},
    "npc-continue": {"npc"},
    "object": {"object", "place", "npc"},
    "bank": {"object", "place"},
    "item": {"item", "object"},
    "withdraw": {"item"},
    "nav": {"place", "object"},
    "quest": set(),
}

RE_INFOBOX = re.compile(r"\{\{\s*Infobox[ _]+([A-Za-z ]+)", re.I)
RE_ID_FIELD = re.compile(r"^\|\s*id(\d*)\s*=\s*([0-9][0-9,\s]*?)\s*$", re.M)
# The wiki writes map coordinates two ways and both are common:
#   {{Map|x = 3243|y = 3210}}                  named parameters
#   {{Map|name=Blast Furnace|2930,10197|...}}  positional "x,y"
# Only the named form was parsed, which silently dropped the coordinates on 137
# of the pages already sitting in the cache -- Blast Furnace among them.
RE_MAP = re.compile(r"\{\{Map[^}]*?\bx\s*=\s*(\d+)[^}]*?\by\s*=\s*(\d+)", re.I)
RE_MAP_POSITIONAL = re.compile(
    r"\{\{Map\b[^}]*?\|\s*(\d{3,5})\s*,\s*(\d{3,5})\s*[|}]", re.I)
RE_PLANE = re.compile(r"\bplane\s*=\s*(\d+)", re.I)


def api_get(params: dict) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_chunk(chunk: list[str], query: dict) -> dict[str, dict]:
    """Map every requested title to the page the wiki resolved it to.

    Resolution runs FORWARD: requested title -> normalised -> redirect target
    -> page. Reversing those maps instead (page title -> the title we asked
    for) loses data whenever two requested titles collapse onto one page, and
    that happens constantly. The guide contains the typo "Tinerbox" as well as
    the correct "Tinderbox"; the wiki redirects the first to the second, so a
    single `pages` entry comes back for two requested titles. Filing it under
    the redirect's origin left the correct spelling looking like a page that
    does not exist -- Tinderbox, item 590, used 24 times in the guide, was
    recorded as missing for exactly that reason, along with about seventy
    others.
    """
    # Both maps are keyed by what we asked for, never by what came back.
    redirect_to = {r["from"]: r["to"] for r in query.get("redirects", [])}
    normalised_to = {n["from"]: n["to"] for n in query.get("normalized", [])}
    pages_by_title = {page["title"]: page for page in query.get("pages", [])}

    found: dict[str, dict] = {}
    for title in chunk:
        # Normalisation first, then redirects: the order the API applies them.
        resolved = normalised_to.get(title, title)
        resolved = redirect_to.get(resolved, resolved)
        page = pages_by_title.get(resolved)
        # `invalid` covers titles the API refuses outright (stray pipes,
        # fragments); a page with no revisions is unusable the same way.
        if (page is None or page.get("missing") or page.get("invalid")
                or not page.get("revisions")):
            found[title] = {"title": resolved, "missing": True}
            continue
        found[title] = {
            "title": page["title"],
            "missing": False,
            "viaRedirect": page["title"] != title,
            "wikitext": page["revisions"][0]["slots"]["main"]["content"],
        }
    return found


def cache_slot(cache: Path, title: str) -> Path:
    """Where one title's response is cached.

    The hash is not decoration. Sanitising the title alone gives
    "Small_Fishing_Net" and "Small_fishing_net", which are the same file on
    Windows and macOS -- so a title-cased candidate and its sentence-cased
    variant silently shared one cached answer, and whichever was fetched first
    decided the other. MediaWiki treats them as different pages, and only the
    sentence-cased one exists.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", title)[:100]
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]
    return cache / f"{safe}-{digest}.json"


def fetch_pages(titles: list[str], cache: Path, delay: float) -> dict[str, dict]:
    """Batch-fetch page wikitext. Cached per title so reruns cost nothing."""
    cache.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    pending: list[str] = []

    for title in titles:
        slot = cache_slot(cache, title)
        if slot.exists():
            results[title] = json.loads(slot.read_text(encoding="utf-8"))
        else:
            pending.append(title)

    for i in range(0, len(pending), BATCH):
        chunk = pending[i : i + BATCH]
        payload = api_get(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
                "titles": "|".join(chunk),
            }
        )
        found = resolve_chunk(chunk, payload.get("query", {}))

        for title in chunk:
            record = found.get(title) or {"title": title, "missing": True}
            slot = cache_slot(cache, title)
            slot.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            results[title] = record

        print(f"  fetched {min(i + BATCH, len(pending))}/{len(pending)}", flush=True)
        time.sleep(delay)

    return results


def parse_page(record: dict) -> dict | None:
    """Pull kind, IDs and coordinates out of a page's infobox."""
    if record.get("missing"):
        return None
    text = record["wikitext"]

    if re.match(r"\s*#REDIRECT", text, re.I):
        return None

    box = RE_INFOBOX.search(text)
    if not box:
        return None
    raw_kind = box.group(1).strip().lower()
    kind = INFOBOX_KIND.get(raw_kind.split()[0])
    if kind is None:
        return None

    ids: list[int] = []
    for _, blob in RE_ID_FIELD.findall(text):
        for part in blob.split(","):
            part = part.strip()
            if part.isdigit():
                value = int(part)
                if value not in ids:
                    ids.append(value)

    points: list[list[int]] = []
    plane_match = RE_PLANE.search(text)
    plane = int(plane_match.group(1)) if plane_match else 0
    for x, y in RE_MAP.findall(text) + RE_MAP_POSITIONAL.findall(text):
        point = [int(x), int(y), plane]
        if point not in points:
            points.append(point)

    if not ids and not points:
        return None

    return {
        "kind": kind,
        "infobox": raw_kind,
        "ids": ids,
        "points": points,
        "wikiPage": record["title"],
        "viaRedirect": record.get("viaRedirect", False),
    }


RE_DISAMBIG = re.compile(r"\{\{\s*(?:disambig|disambiguation)", re.I)
# The pages a disambiguation offers, so the report says what to choose between.
RE_DISAMBIG_LINK = re.compile(r"\[\[([^\]|]+)")


def title_variants(name: str) -> list[str]:
    """Deterministic spellings of the same name, tried in order.

    This is not similarity matching: each variant is still required to be an
    exact wiki page title. The guide writes "Air Runes" where the wiki page is
    "Air rune"; de-pluralising is a fixed rule, not a guess, and a variant that
    does not exist as a page resolves to nothing.
    """
    variants = [name]
    words = name.split()
    if words:
        last = words[-1]
        singular = None
        if len(last) > 3 and last.endswith("ies"):
            singular = last[:-3] + "y"
        elif len(last) > 3 and last.endswith("es") and last[-3:-2] in "sxzh":
            singular = last[:-2]
        elif len(last) > 2 and last.endswith("s") and not last.endswith("ss"):
            singular = last[:-1]
        if singular:
            variants.append(" ".join(words[:-1] + [singular]))

    # MediaWiki capitalises the first letter of a title and leaves the rest
    # alone, so "Small Fishing Net" and "Small fishing net" are different pages
    # -- and the wiki has only the second. The guide title-cases constantly.
    # Lowercasing all but the first word is a fixed rewrite like the singular
    # rule above, and the result still has to be an exact page title.
    for variant in list(variants):
        parts = variant.split()
        if len(parts) > 1:
            sentence_case = " ".join([parts[0]] + [w.lower() for w in parts[1:]])
            if sentence_case != variant:
                variants.append(sentence_case)

    return list(dict.fromkeys(variants))


def load_alias_entities(curated: Path) -> dict[str, list[str]]:
    """Phrase -> entity names, from curated/entity_aliases.yaml. Optional."""
    path = curated / "entity_aliases.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("aliases") or {}


def load_curated_items(curated: Path) -> dict:
    """Category word -> collection(s), from curated/item_collections.yaml."""
    path = curated / "item_collections.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("collections") or {}


def load_disambiguations(curated: Path) -> dict[str, str]:
    """Guide name -> the exact wiki page a person chose for it.

    Empty when the file is absent, so the resolver still runs; every name then
    simply stays unresolved as before.
    """
    import yaml

    path = curated / "disambiguations.yaml"
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (loaded.get("pages") or {}).items()}


def collect_candidates(doc: dict) -> dict[str, set[str]]:
    """name -> the set of intents that asked for it."""
    candidates: dict[str, set[str]] = defaultdict(set)
    for section in doc["sections"]:
        for step in section["steps"]:
            ann = step.get("annotation")
            if not ann:
                continue
            intent = ann.get("intent")
            for link in ann.get("links", []):
                candidates[link].add(intent or "link")
            if ann.get("targetName"):
                candidates[ann["targetName"]].add(intent or "link")
            for item in ann.get("items", []):
                # Items carry a count now, so an entry is {name, count?}.
                name = item["name"] if isinstance(item, dict) else item
                candidates[name].add("withdraw")
                # And the same name without a leading "Empty", so the ordinary
                # item is on the books to fall back to.
                bare = re.sub(r"^empty\s+", "", name, flags=re.I)
                if bare != name:
                    candidates[bare].add("withdraw")
            # Teleport destinations ("Ardy Cloak -> Wintertodt"). These were
            # never asked about, so every one of them reported as having no
            # wiki page when most have a perfectly good one with a {{Map}}.
            if ann.get("destination"):
                candidates[ann["destination"]].add("nav")
    return candidates


def load_shopkeepers(path: Path) -> list[str]:
    """The owner of every shop with stock. Optional; empty before the stage runs."""
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("owners") or []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=REPO / "build" / "annotated.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "entities.json")
    ap.add_argument("--unresolved", type=Path, default=REPO / "build" / "unresolved.json")
    ap.add_argument("--cache", type=Path, default=REPO / "build" / "wikicache")
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between API batches")
    ap.add_argument("--limit", type=int, default=0, help="only try the first N names")
    ap.add_argument("--curated", type=Path, default=REPO / "curated")
    ap.add_argument("--shops", type=Path, default=REPO / "build" / "shops.json")
    args = ap.parse_args()

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    disambiguations = load_disambiguations(args.curated)
    candidates = collect_candidates(doc)

    # Entities named only in curated/entity_aliases.yaml. The grammar cannot
    # extract "a man/woman", so without this the wiki is never asked about Man
    # or Woman and the alias resolves to nothing.
    for names in load_alias_entities(args.curated).values():
        for name in names:
            candidates[name].add("npc")

    # Curated item rows may name a wiki entity where Quest Helper has no
    # collection ("Jug of wine"). Those need asking about too, for the same
    # reason: nothing else in the guide mentions them by that name.
    for value in load_curated_items(args.curated).values():
        for name in ([value] if isinstance(value, str) else value or []):
            if name and not name.isupper():
                candidates[name].add("withdraw")
    # Shopkeepers, from build/shops.json. The guide names a shop's goods and
    # trusts the player to find the counter -- "Buy 2x Bronze Med Helm in
    # Barbarian Village" never says Peksa -- so the only way the plugin can
    # point at one is to know who sells what, and that needs their ids and
    # coordinates like any other npc.
    for name in load_shopkeepers(args.shops):
        candidates[name].add("npc")

    names = sorted(candidates)
    if args.limit:
        names = names[: args.limit]

    lookups: list[str] = []
    for name in names:
        lookups.extend(title_variants(name))
        if name in disambiguations:
            lookups.append(disambiguations[name])
    lookups = list(dict.fromkeys(lookups))

    print(f"candidate names: {len(names)} ({len(lookups)} title variants)")
    records = fetch_pages(lookups, args.cache, args.delay)

    entities: dict[str, dict] = {}
    unresolved: dict[str, dict] = {}
    stats: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()

    for name in names:
        intents = candidates[name]

        parsed = None
        record = None
        used_variant = name
        # A curated choice wins outright: it is a person answering the one
        # question the wiki cannot, and it is still a page that has to exist
        # and carry an infobox.
        variants = list(title_variants(name))
        if name in disambiguations:
            variants.insert(0, disambiguations[name])

        for variant in variants:
            record = records.get(variant)
            if record is None or record.get("missing"):
                continue
            parsed = parse_page(record)
            if parsed is not None:
                used_variant = variant
                break

        if record is None or (parsed is None and all(
            (records.get(v) or {}).get("missing", True) for v in variants
        )):
            unresolved[name] = {"reason": "no wiki page", "intents": sorted(intents)}
            stats["missing page"] += 1
            continue

        if used_variant != name:
            stats["  via singular form"] += 1

        if parsed is None:
            # A disambiguation page is a different failure from a page that
            # simply has no infobox, and it is the dangerous one: the wiki does
            # have the item, under a name only a person can choose between.
            # "Mysterious orb" is two different quest items, so refusing is
            # right -- but reporting it as "no infobox" hid a fixable gap among
            # hundreds of genuinely unfixable ones.
            disambiguation = bool(RE_DISAMBIG.search(record.get("wikitext") or ""))
            unresolved[name] = {
                "reason": ("disambiguation page; needs a curated choice"
                           if disambiguation else "page has no usable infobox"),
                "wikiPage": record["title"],
                "intents": sorted(intents),
            }
            if disambiguation:
                unresolved[name]["choices"] = RE_DISAMBIG_LINK.findall(
                    record.get("wikitext") or "")[:8]
                stats["disambiguation, needs a curated choice"] += 1
            else:
                stats["no infobox"] += 1
            continue

        # Where the infobox disagrees with the verb we guessed, the infobox
        # wins. "Buy Chef's Hat" parses as an npc verb but the wiki says Item,
        # and the wiki is maintained by people. Record the disagreement for
        # review rather than discarding a correctly-resolved entity -- the
        # protection against nonsense is the exact-title rule, not this check.
        acceptable = set()
        for intent in intents:
            acceptable |= INTENT_ACCEPTS.get(intent, {parsed["kind"]})
        disagrees = bool(acceptable) and parsed["kind"] not in acceptable
        if disagrees:
            stats["kind overrode intent"] += 1

        entities[name] = {
            **parsed,
            "intents": sorted(intents),
            "kindOverrodeIntent": disagrees,
        }
        stats["resolved"] += 1
        by_kind[parsed["kind"]] += 1
        if parsed["viaRedirect"]:
            stats["  via wiki redirect"] += 1
        if parsed["ids"]:
            stats["  with ids"] += 1
        if parsed["points"]:
            stats["  with coordinates"] += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    args.unresolved.write_text(
        json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n{'':<22}{'count':>7}")
    for label in ("resolved", "  via wiki redirect", "  via singular form", "  with ids", "  with coordinates",
                  "kind overrode intent", "missing page", "no infobox"):
        if label in stats:
            print(f"{label:<22}{stats[label]:>7}")
    # A curated choice that did not resolve is a typo, and it would otherwise
    # look exactly like the name having been ambiguous all along.
    unused = sorted(n for n in disambiguations if n not in entities)
    if unused:
        print(f"\nWARNING: {len(unused)} curated disambiguation(s) did not resolve:")
        for name in unused:
            print(f"  {name!r} -> {disambiguations[name]!r}"
                  " (no such page, or it carries no infobox)")

    print("\nresolved by kind:")
    for kind, count in by_kind.most_common():
        print(f"  {kind:<10}{count:>6}")

    print(f"\nwrote {args.out}")
    print(f"wrote {args.unresolved}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

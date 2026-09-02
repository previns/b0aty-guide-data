"""Stage 4: join resolved entities, locations, quest tags and overrides onto steps.

Reads build/annotated.json + build/entities.json + curated/, writes
build/merged.json.

Precedence, lowest to highest:
  1. the annotation grammar        (annotate.py)
  2. wiki-resolved entities        (resolve_wiki.py)
  3. RuneLite location tables      (curated/locations.generated.yaml)
  4. hand-written curated data     (curated/*.yaml)
  5. per-step overrides            (curated/overrides.yaml)

Nothing in this file guesses. Every join is an exact key match; an override that
no longer matches a step is a loud warning, because it means the wiki text moved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.build_locations import normalise  # noqa: E402

# How much to trust a target, best first. The plugin uses this to decide what to
# highlight by default.
CONFIDENCE_ORDER = ["linked", "wiki-exact", "wiki-redirect", "inferred"]


def step_keyed(rows: dict) -> dict:
    """Force step-id keys to strings.

    A step id can be all digits, and YAML reads an unquoted one as a number --
    which then matches no step, silently. Quoting in the file is the real fix;
    this makes forgetting it harmless rather than invisible.
    """
    return {str(key): value for key, value in (rows or {}).items()}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_locations(path: Path) -> dict[str, list[dict]]:
    """Read the generated location table into key -> [entries]."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    table: dict[str, list[dict]] = {}
    for row in data.get("locations", []):
        table.setdefault(row["key"], []).append(row)
    return table


def load_atlas(path: Path) -> dict:
    """Quest Helper coordinates, keyed by numeric game ID. Optional."""
    if not path.exists():
        return {"npc": {}, "object": {}, "collections": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def atlas_points(atlas: dict, kind: str, ids: list[int]) -> tuple[list, bool]:
    """Coordinates Quest Helper records for any of these IDs.

    Joined on the number, never on a name: the wiki told us the ID, Quest
    Helper recorded a coordinate against the same ID, and the two agree by
    construction. Several coordinates for one ID is normal -- Quest Helper
    points at whichever instance a quest needed -- so they are all kept and the
    result is marked ambiguous rather than silently picking the first.
    """
    table = atlas.get(kind) or {}
    points: list = []
    ambiguous = False
    for game_id in ids:
        entry = table.get(str(game_id))
        if not entry:
            continue
        ambiguous = ambiguous or entry["ambiguous"]
        for point in entry["points"]:
            if point not in points:
                points.append(point)
    return points, ambiguous or len(points) > 1


def load_quest_steps(path: Path) -> dict:
    """Quest Helper's per-quest step list. Optional."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("quests") or {}


def load_quest_objects(path: Path) -> dict:
    """Per-quest scenery from build/quest_objects.json. Optional."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("quests") or {}


def quest_directory(name: str) -> str:
    """"Rune Mysteries" -> "runemysteries". A fixed rewrite, not a search."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


# Past this the "nearest staircase in the quest" is not part of the same
# building and picking it would be a guess dressed up as data.
APPROACH_MAX_TILES = 30


def approach_for(quest_objects: dict, quest_name: str, point: list) -> dict | None:
    """The way up to a target on an upper floor, from the quest's own scenery.

    Scoped to the quest the guide already tags, which is what makes this safe:
    within one quest the candidates number a handful and the nearest one on
    another plane is the right one. Across the whole game it would not be --
    Lumbridge castle alone has several staircases within a few tiles, which is
    exactly what the plugin's runtime "nearest climbable object" gets wrong.
    """
    entries = quest_objects.get(quest_directory(quest_name)) or []
    x, y, plane = point[0], point[1], point[2]

    best = None
    best_distance = APPROACH_MAX_TILES + 1
    for entry in entries:
        ex, ey, eplane = entry["point"]
        if eplane == plane:
            continue
        distance = max(abs(ex - x), abs(ey - y))
        if distance < best_distance:
            best_distance = distance
            best = entry
    if best is None:
        return None
    return {
        "ids": [best["id"]],
        "point": best["point"],
        "constant": best["constant"],
        "source": "quest-helper/" + quest_directory(quest_name),
    }


def resolve_item_name(name, entities: dict, item_collections: dict,
                     collection_ids: dict) -> tuple[list[int], str | None]:
    """Item ids for a name, by the same rules the withdraw lists use.

    Also tries the part after a colon: the guide prefixes teleport methods with
    where you are going ("Hosidius: Ardy Cloak 1"), and the item is the tail.
    """
    for candidate in (name, name.split(": ")[-1].strip()):
        entity = entities.get(candidate)
        if entity and entity["kind"] == "item" and entity["ids"]:
            return entity["ids"], None
        collection = item_collections.get(candidate)
        if collection is not None:
            ids = collection_members(collection, collection_ids, entities)
            if ids:
                label = collection if isinstance(collection, str) else ", ".join(collection)
                return ids, label
    return [], None


# net.runelite.api.Skill, which is what the plugin looks these up by.
SKILL_NAMES = ['ATTACK', 'DEFENCE', 'STRENGTH', 'HITPOINTS', 'RANGED', 'PRAYER', 'MAGIC', 'COOKING', 'WOODCUTTING', 'FLETCHING', 'FISHING', 'FIREMAKING', 'CRAFTING', 'SMITHING', 'MINING', 'HERBLORE', 'AGILITY', 'THIEVING', 'SLAYER', 'FARMING', 'RUNECRAFT', 'HUNTER', 'CONSTRUCTION']


# The step has to BE a teleport instruction, not merely end up somewhere.
# "Return to Ardougne & complete Plague City" is about the quest.
RE_CASTS = re.compile(r"^\s*teleport\s+to\s+", re.I)
# ...and must not name a different method. "Home teleport to Lumbridge" is a
# different spell entirely, and "Teleport to Falador with Teletab" is an item.
RE_OTHER_METHOD = re.compile(
    r"\b(tab|tablet|teletab|necklace|cloak|ring|scroll|home\s*teleport|portal|glory)\b",
    re.I)


def casts_a_spell(raw: str) -> bool:
    """Whether this step means casting the spellbook teleport for its destination."""
    return bool(RE_CASTS.match(raw)) and not RE_OTHER_METHOD.search(raw)


def check_spells(spells: dict, widgets: dict) -> list[str]:
    """Every spell must be a real MagicSpellbook constant.

    A typo would silently highlight nothing, which is indistinguishable from a
    step that never had a spell.
    """
    return [f"{place!r} -> {constant}: no such spell widget"
            for place, constant in sorted(spells.items()) if constant not in widgets]


def check_skills(targets: dict, step_ids: set[str]) -> list[str]:
    """Every skill target must name a real skill, a sane level, and a live step.

    A stale step id is the dangerous one: the row would auto-tick whatever
    inherited that id when the wiki text moved.
    """
    problems = []
    for step_id, row in sorted(targets.items()):
        skill = (row or {}).get("skill")
        level = (row or {}).get("level")
        if skill not in SKILL_NAMES:
            problems.append(f"{step_id}: unknown skill {skill!r}")
        if not isinstance(level, int) or not 1 <= level <= 99:
            problems.append(f"{step_id}: level {level!r} out of range")
        if step_ids and step_id not in step_ids:
            problems.append(f"{step_id}: no such step -- the wiki text moved")
    return problems


def check_places(aliases: dict, locations: dict, entities: dict) -> list[str]:
    """Every place alias must point at a name that actually resolves.

    This file holds names, never coordinates, so the check is the whole
    guarantee: a target that stops resolving must fail the build rather than
    quietly leaving the alias pointing at nothing.
    """
    problems = []
    for spelling, target in sorted(aliases.items()):
        entity = entities.get(target)
        resolves = bool(locations.get(normalise(target))) or (
            entity is not None and entity.get("kind") in ("place", "object")
            and entity.get("points"))
        if not resolves:
            problems.append(f"{spelling!r} -> {target!r}: does not resolve to a place")
    return problems


def check_entity_aliases(aliases: dict, entities: dict) -> list[str]:
    """Every alias must name entities the wiki actually resolved.

    A phrase pointing at a page that does not exist would resolve to an empty
    target -- no error, just a step that never highlights. Same silent
    under-reporting as the resolver bugs.
    """
    problems = []
    for phrase, names in sorted(aliases.items()):
        if not names:
            problems.append(f"{phrase!r}: no entities listed")
        for name in names or []:
            entity = entities.get(name)
            if entity is None:
                problems.append(f"{phrase!r} -> {name!r}: not resolved by the wiki")
            elif not entity.get("ids"):
                problems.append(f"{phrase!r} -> {name!r}: resolved but carries no ids")
    return problems


def check_diary(tasks: dict, varplayers: dict[str, int], step_ids: set[str]) -> list[str]:
    """Every diary row must name a real VarPlayer and a step that still exists.

    A stale step id means the wiki text moved: the row must be re-decided
    against the new wording, not carried over. Silently keeping it would
    auto-tick whatever step inherited that id.
    """
    problems = []
    for step_id, row in sorted(tasks.items()):
        if row.get("varplayer") not in varplayers:
            problems.append(f"{step_id}: unknown VarPlayer {row.get('varplayer')!r}")
        if not isinstance(row.get("bit"), int) or not 0 <= row["bit"] <= 31:
            problems.append(f"{step_id}: bit {row.get('bit')!r} out of range")
        if step_ids and step_id not in step_ids:
            problems.append(f"{step_id}: no such step -- the wiki text moved")
    return problems


def collection_members(value, available: dict[str, list], entities: dict) -> list[int] | None:
    """Resolve one curated mapping to item ids, or None if anything is unknown.

    A value is either a single Quest Helper collection, or a list of them. A
    list entry may also name a wiki entity, because some categories span both:
    "Teleport Runes" is the four elemental rune collections plus the law rune,
    and Quest Helper has no collection for law runes.
    """
    names = [value] if isinstance(value, str) else list(value or [])
    if not names:
        return None
    ids: list[int] = []
    for name in names:
        if name in available:
            source = available[name]
        elif entities.get(name, {}).get("ids"):
            source = entities[name]["ids"]
        else:
            return None
        for item in source:
            if item not in ids:
                ids.append(item)
    return ids


def check_collections(mapping: dict, available: dict[str, list],
                      entities: dict) -> list[str]:
    """Every mapped name must be a real collection or a resolved wiki entity.

    A typo here would silently drop a category the guide uses dozens of times,
    which is the same class of failure as the resolver bugs: no error, just
    quietly less data. The build fails instead.
    """
    problems = []
    for word, value in sorted(mapping.items()):
        if collection_members(value, available, entities) is None:
            names = [value] if isinstance(value, str) else list(value or [])
            unknown = [n for n in names
                       if n not in available and not entities.get(n, {}).get("ids")]
            problems.append(
                f"{word!r} -> {unknown or 'nothing listed'}: no such collection or entity")
    return problems


def load_quest_names(path: Path) -> dict[str, tuple[str, str]]:
    """Quest display name (normalised) -> (display name, enum constant)."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, tuple[str, str]] = {}
    for constant, name in re.findall(
        r"^\s*([A-Z][A-Z0-9_]*)\s*\(\s*\d+\s*,\s*\"([^\"]+)\"", text, re.M
    ):
        out[normalise(name)] = (name, constant)
    return out


def check_aliases(aliases: dict[str, str], quests: dict[str, tuple[str, str]]) -> list[str]:
    """An alias must point at a real enum entry. No near-misses."""
    return [
        f"{key!r} -> {value!r} is not a Quest enum entry"
        for key, value in aliases.items()
        if normalise(value) not in quests
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--annotated", type=Path, default=REPO / "build" / "annotated.json")
    ap.add_argument("--entities", type=Path, default=REPO / "build" / "entities.json")
    ap.add_argument("--curated", type=Path, default=REPO / "curated")
    ap.add_argument("--quests", type=Path, default=REPO / "build" / "runelite" / "Quest.java")
    ap.add_argument("--atlas", type=Path, default=REPO / "build" / "atlas.json")
    ap.add_argument("--quest-objects", type=Path,
                    default=REPO / "build" / "quest_objects.json")
    ap.add_argument("--quest-steps", type=Path,
                    default=REPO / "build" / "quest_steps.json")
    ap.add_argument("--images", type=Path, default=REPO / "build" / "images.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "merged.json")
    ap.add_argument("--check-aliases", action="store_true", help="validate aliases and exit")
    ap.add_argument("--check-collections", action="store_true",
                    help="validate curated item collections and exit")
    ap.add_argument("--check-diary", action="store_true",
                    help="validate curated diary task bits and exit")
    ap.add_argument("--check-entity-aliases", action="store_true",
                    help="validate curated entity aliases and exit")
    ap.add_argument("--check-places", action="store_true",
                    help="validate curated place aliases and exit")
    ap.add_argument("--check-skills", action="store_true",
                    help="validate curated skill targets and exit")
    ap.add_argument("--check-spells", action="store_true",
                    help="validate curated spellbook entries and exit")
    ap.add_argument("--ids", type=Path, default=REPO / "build" / "ids.json")
    args = ap.parse_args()

    quests = load_quest_names(args.quests)
    quest_cfg = load_yaml(args.curated / "quest_aliases.yaml")
    aliases: dict[str, str] = quest_cfg.get("aliases", {}) or {}
    not_a_quest: dict[str, str] = quest_cfg.get("not_a_quest", {}) or {}

    problems = check_aliases(aliases, quests)
    if problems:
        print("curated/quest_aliases.yaml has invalid targets:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_aliases:
        print(f"{len(aliases)} aliases, all resolve to real Quest enum entries")
        return 0

    # Loaded before the curated checks: a collection row may name a wiki entity
    # where Quest Helper has no collection for it.
    entities = json.loads(args.entities.read_text(encoding="utf-8"))
    atlas = load_atlas(args.atlas)
    collection_ids: dict[str, list[int]] = atlas.get("collections") or {}
    item_collections: dict[str, str] = (
        load_yaml(args.curated / "item_collections.yaml").get("collections") or {})

    problems = check_collections(item_collections, collection_ids, entities)
    if problems:
        print("curated/item_collections.yaml references unknown collections:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_collections:
        total = sum(len(collection_members(v, collection_ids, entities))
                    for v in item_collections.values())
        print(f"{len(item_collections)} category words -> {total} item ids")
        return 0

    quest_objects = load_quest_objects(args.quest_objects)
    quest_steps = load_quest_steps(args.quest_steps)
    # Longest first, so "Fairytale II - Cure a Queen" wins over "Fairytale".
    quest_names_by_length = sorted(
        (q[0] for q in quests.values()), key=len, reverse=True)

    entity_aliases: dict[str, list] = (
        load_yaml(args.curated / "entity_aliases.yaml").get("aliases") or {})

    spells: dict[str, str] = (
        load_yaml(args.curated / "spells.yaml").get("spells") or {})
    spell_widgets: dict[str, int] = {}
    if args.ids.exists():
        spell_widgets = json.loads(args.ids.read_text(encoding="utf-8")).get("spell", {})

    problems = check_spells(spells, spell_widgets)
    if problems:
        print("curated/spells.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_spells:
        print(f"{len(spells)} destinations -> spellbook entries, all real")
        return 0

    skill_targets: dict[str, dict] = step_keyed(
        load_yaml(args.curated / "skill_targets.yaml").get("targets"))

    diary_tasks: dict[str, dict] = step_keyed(
        load_yaml(args.curated / "diary_tasks.yaml").get("tasks"))
    varplayers: dict[str, int] = {}
    if args.ids.exists():
        varplayers = json.loads(args.ids.read_text(encoding="utf-8")).get("varplayer", {})

    place_aliases: dict[str, str] = (
        load_yaml(args.curated / "places.yaml").get("aliases") or {})

    locations = load_locations(args.curated / "locations.generated.yaml")
    banks = {
        normalise(k): v for k, v in (load_yaml(args.curated / "banks.yaml").get("banks") or {}).items()
    }
    overrides: dict[str, dict] = step_keyed(
        load_yaml(args.curated / "overrides.yaml").get("steps"))

    doc = json.loads(args.annotated.read_text(encoding="utf-8"))

    problems = check_places(place_aliases, locations, entities)
    if problems:
        print("curated/places.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_places:
        print(f"{len(place_aliases)} place aliases, all resolving")
        return 0

    problems = check_entity_aliases(entity_aliases, entities)
    if problems:
        print("curated/entity_aliases.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_entity_aliases:
        total = sum(len(entities[n]["ids"]) for ns in entity_aliases.values() for n in ns)
        print(f"{len(entity_aliases)} phrases -> {total} npc ids, all wiki-resolved")
        return 0

    all_step_ids = {s["id"] for sec in doc["sections"] for s in sec["steps"]}
    problems = check_skills(skill_targets, all_step_ids)
    if problems:
        print("curated/skill_targets.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_skills:
        print(f"{len(skill_targets)} skill targets, all naming a real skill and a live step")
        return 0

    problems = check_diary(diary_tasks, varplayers, all_step_ids)
    if problems:
        print("curated/diary_tasks.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_diary:
        print(f"{len(diary_tasks)} diary rows, all naming a real VarPlayer and a live step")
        return 0

    stats: Counter[str] = Counter()
    used_quest_helpers: set[str] = set()
    seen_override_keys: set[str] = set()
    alias_norm = {normalise(k): v for k, v in aliases.items()}
    skip_tags = {normalise(k) for k in not_a_quest}

    for section in doc["sections"]:
        for step in section["steps"]:
            ann = step.get("annotation") or {}
            merged: dict = {}

            # --- target entity ------------------------------------------------
            links = ann.get("links", [])
            candidates = []
            if ann.get("targetName"):
                candidates.append(ann["targetName"])
            candidates.extend(links)

            for name in candidates:
                entity = entities.get(name)
                if not entity:
                    continue
                if name in links:
                    confidence = "linked"
                elif entity.get("viaRedirect"):
                    confidence = "wiki-redirect"
                else:
                    confidence = "wiki-exact"
                points = entity["points"]
                point_source = "wiki" if points else None
                # Only ever fills a gap. The wiki's own coordinate wins when it
                # has one, and curated/ overrides both further down.
                if not points and entity["ids"]:
                    points, ambiguous = atlas_points(atlas, entity["kind"], entity["ids"])
                    if points:
                        point_source = "quest-helper"
                        stats["  points from quest-helper"] += 1
                        if ambiguous:
                            stats["    (several candidates)"] += 1
                merged["target"] = {
                    "name": name,
                    "kind": entity["kind"],
                    "ids": entity["ids"],
                    "points": points,
                    "wikiPage": entity["wikiPage"],
                    "confidence": confidence,
                }
                if point_source:
                    merged["target"]["pointSource"] = point_source
                stats[f"target:{confidence}"] += 1
                break
            else:
                # A phrase a person mapped to entities, for targets the grammar
                # cannot reach: "Pickpocket a man/woman" is lowercase, plural in
                # meaning and split by a slash. Applied only when nothing else
                # produced a target, so it can never override the wiki.
                alias_names = None
                lowered_text = step["raw"].lower()
                for phrase, names in entity_aliases.items():
                    if phrase.lower() in lowered_text:
                        alias_names = names
                        break

                if alias_names:
                    merged_ids: list[int] = []
                    for name in alias_names:
                        for game_id in entities[name]["ids"]:
                            if game_id not in merged_ids:
                                merged_ids.append(game_id)
                    merged["target"] = {
                        "name": "/".join(alias_names),
                        "names": alias_names,
                        "kind": entities[alias_names[0]]["kind"],
                        "ids": merged_ids,
                        "confidence": "manual",
                    }
                    stats["target:manual (entity alias)"] += 1
                elif ann.get("targetName"):
                    # Unresolved, but still usable: the plugin can match the raw
                    # name against the loaded scene.
                    merged["target"] = {
                        "name": ann["targetName"],
                        "kind": ann.get("intent"),
                        "ids": [],
                        "points": [],
                        "confidence": "inferred",
                    }
                    stats["target:inferred"] += 1

            # --- provable completion ------------------------------------------
            # Only ever a signal the game itself sets. The plugin ticks on it;
            # everything else stays a manual checkbox.
            skill_row = skill_targets.get(step["id"])
            if skill_row:
                merged["completion"] = {
                    "kind": "skill",
                    "skill": skill_row["skill"],
                    "level": skill_row["level"],
                }
                stats["skill target"] += 1

            diary_row = diary_tasks.get(step["id"])
            if diary_row:
                merged["completion"] = {
                    "kind": "diary",
                    "varplayer": varplayers[diary_row["varplayer"]],
                    "varplayerName": diary_row["varplayer"],
                    "bit": diary_row["bit"],
                }
                stats["diary completion bit"] += 1

            # --- items --------------------------------------------------------
            items = []
            for item_name in ann.get("items", []):
                entity = entities.get(item_name)
                if entity and entity["kind"] == "item":
                    items.append({"name": item_name, "ids": entity["ids"]})
                    stats["item resolved"] += 1
                    continue
                # A category word -- "Pickaxe", "Ardy Cloak" -- names a set, not
                # an item, so no wiki page can carry its id. curated/ says which
                # set the guide meant; the ids come from Quest Helper, ordered
                # best tier first.
                collection = item_collections.get(item_name)
                member_ids = (collection_members(collection, collection_ids, entities)
                              if collection is not None else None)
                if member_ids:
                    items.append({
                        "name": item_name,
                        "ids": member_ids,
                        "collection": collection if isinstance(collection, str)
                        else ", ".join(collection),
                    })
                    stats["item resolved"] += 1
                    stats["  via item collection"] += 1
                    continue
                items.append({"name": item_name, "ids": []})
                stats["item unresolved"] += 1
            if items:
                merged["items"] = items
            if ann.get("inventorySlots") is not None:
                merged["inventorySlots"] = ann["inventorySlots"]

            # --- destination --------------------------------------------------
            place = ann.get("destination") or (
                ann["targetName"] if ann.get("intent") == "nav" and ann.get("targetName") else None
            )
            if place:
                # A human saying which real place the guide's spelling means.
                # Applied before every lookup, so the alias target goes through
                # exactly the same resolution as any other name.
                place = place_aliases.get(place, place)
                key = normalise(place)
                rows = locations.get(key) or []
                if not rows and key in banks:
                    rows = [{"name": place, "kind": "bank", "point": banks[key],
                             "source": "curated/banks.yaml"}]
                if not rows:
                    # The wiki already gave us {{Map}} coordinates for many of
                    # these. Places and scenery both count -- Wintertodt is a
                    # scenery page carrying a map, and a brazier is as real a
                    # destination as a town. NPCs do not: there is an NPC named
                    # Ferox, and it is not where "Teleport to Ferox" goes.
                    entity = entities.get(place)
                    if entity and entity["kind"] in ("place", "object") and entity["points"]:
                        rows = [
                            {"name": place, "kind": entity["kind"], "point": point,
                             "source": f"wiki/{entity['wikiPage']}"}
                            for point in entity["points"]
                        ]
                # Several RuneLite enums list the same place a few tiles apart
                # -- Castle Wars is in both the minigame and the teleport table
                # -- which left the destination ambiguous and the map marker
                # drawing nothing at all. For "Teleport to X" the teleport
                # table is the authoritative answer: it is where you actually
                # land.
                if len({tuple(r["point"]) for r in rows}) > 1:
                    landing = [r for r in rows if r["kind"] == "teleport"]
                    if len({tuple(r["point"]) for r in landing}) == 1:
                        rows = landing[:1]
                        stats["  destination pinned to the teleport"] += 1

                if rows:
                    merged["destination"] = {
                        "name": place,
                        "points": [r["point"] for r in rows],
                        "kinds": sorted({r["kind"] for r in rows}),
                        "ambiguous": len({tuple(r["point"]) for r in rows}) > 1,
                        "source": rows[0]["source"],
                    }
                    stats["destination resolved"] += 1
                else:
                    merged["destination"] = {"name": place, "points": []}
                    stats["destination unresolved"] += 1

            # --- quest tags ---------------------------------------------------
            quest_tags = []
            for tag in ann.get("tags", []):
                key = normalise(tag)
                if key in skip_tags:
                    continue
                target = alias_norm.get(key)
                lookup = normalise(target) if target else key
                if lookup in quests:
                    name, constant = quests[lookup]
                    quest_tags.append(
                        {"tag": tag, "quest": name, "constant": constant,
                         "via": "alias" if target else "exact"}
                    )
                    stats["quest tag " + ("via alias" if target else "exact")] += 1
                elif "diary" in tag.lower():
                    quest_tags.append({"tag": tag, "diary": True})
                    stats["diary tag"] += 1
                else:
                    quest_tags.append({"tag": tag})
                    stats["tag unresolved"] += 1
            if quest_tags:
                merged["tags"] = quest_tags

            # --- the item that gets you there ------------------------------
            # "Ardy Cloak -> CKS" says which item to use as well as where it
            # goes, and the item half was extracted and thrown away. Resolved
            # by the same rules as a withdraw list, so a category like "Ardy
            # Cloak" carries every tier.
            via = ann.get("teleportVia")
            if via:
                ids, collection = resolve_item_name(
                    via, entities, item_collections, collection_ids)
                merged["teleport"] = {"via": via, "ids": ids}
                if collection:
                    merged["teleport"]["collection"] = collection
                stats["teleport method" if ids else "teleport method unresolved"] += 1

            if ann.get("banking"):
                merged["banking"] = True
                stats["banking step"] += 1

            # --- quest progress -----------------------------------------------
            # The route does "macro questing": it advances a quest a step or
            # two in passing rather than doing it in one sitting. Carrying the
            # quest's progress variable lets the plugin say what Quest Helper
            # would say at the player's current value, and tick the step when
            # that value moves.
            quest_named = next(
                (tag["quest"] for tag in merged.get("tags", []) if tag.get("quest")), None)
            if quest_named is None:
                # The guide names a quest in prose as often as in a [tag]:
                # "Start X Marks the Spot on Veos" carries no bracket at all.
                # Matched against the RuneLite Quest names, which are a closed
                # authoritative list, as a whole phrase -- an exact lookup, not
                # a similarity search. Informational only: nothing is ticked off
                # a prose mention, because "Dragon Slayer" also appears in
                # sentences that are not about doing Dragon Slayer.
                lowered_raw = step["raw"].lower()
                for display in quest_names_by_length:
                    if display.lower() in lowered_raw:
                        quest_named = display
                        stats["quest named in prose"] += 1
                        break
            if quest_named:
                key = quest_directory(quest_named)
                if key in quest_steps:
                    # Only the key. The step lists live once at guide level --
                    # inlining them here repeated the same few hundred lines
                    # across 174 steps and put 774 KiB into the shipped file.
                    merged["questHelper"] = key
                    used_quest_helpers.add(key)
                    stats["quest step list"] += 1

            # --- the spell that gets you there ------------------------------
            # "Teleport to Varrock" names where, not how, because on the
            # standard spellbook there is only one answer. Only where the step
            # has no item to ring already.
            destination_now = merged.get("destination")
            if destination_now and "teleport" not in merged and casts_a_spell(step["raw"]):
                constant = spells.get(destination_now["name"])
                if constant:
                    merged["spell"] = {
                        "name": constant,
                        "widget": spell_widgets[constant],
                    }
                    stats["spellbook entry"] += 1

            # --- the way up ---------------------------------------------------
            # A target on an upper floor cannot be walked to, and the plugin's
            # runtime fallback (nearest climbable object) picks the wrong
            # staircase in a building that has several. Where the guide names
            # the quest, Quest Helper already worked out which one.
            target_now = merged.get("target")
            if target_now and quest_named and target_now.get("points"):
                first_point = target_now["points"][0]
                if len(first_point) >= 3 and first_point[2] > 0:
                    approach = approach_for(quest_objects, quest_named, first_point)
                    if approach:
                        merged["approach"] = approach
                        stats["approach from quest-helper"] += 1

            # --- passthrough --------------------------------------------------
            for key in ("dialogue", "urls"):
                if ann.get(key):
                    merged[key] = ann[key]

            # --- overrides win ------------------------------------------------
            override = overrides.get(step["id"])
            if override:
                seen_override_keys.add(step["id"])
                merged.update(override)
                stats["override applied"] += 1

            step["merged"] = merged
            step.pop("annotation", None)

    stale = sorted(set(overrides) - seen_override_keys)
    doc["staleOverrides"] = stale

    # Only the quests some step actually references, stored once.
    # url -> sha256, for the images this build actually saw.
    if args.images.exists():
        hashed = json.loads(args.images.read_text(encoding="utf-8")).get("images", {})
        doc["imageHashes"] = {url: entry["sha256"] for url, entry in hashed.items()}
    else:
        doc["imageHashes"] = {}

    doc["questHelpers"] = {
        key: quest_steps[key] for key in sorted(used_quest_helpers)
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    for label, count in sorted(stats.items()):
        print(f"  {count:5d}  {label}")

    if stale:
        print(f"\nWARNING: {len(stale)} override key(s) no longer match any step.")
        print("The wiki text almost certainly changed under them:")
        for key in stale:
            print(f"  {key}")

    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

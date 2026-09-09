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

from pipeline.annotate import strip_links  # noqa: E402
from pipeline.build_locations import normalise  # noqa: E402
from pipeline.quest_milestones import attach_continuations, demote_before_starts, pin_explicit_milestones  # noqa: E402

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


# Enough shops that one is near wherever the guide has the player standing,
# few enough that the file does not carry forty answers to one question.
# The step has to BE a purchase. A step that mentions buying something later
# is not a trip to a shop.
RE_A_PURCHASE = re.compile(r"^\s*(?:buy|purchase)\b", re.I)
MAX_SELLERS = 12
MAX_SELLER_POINTS = 3


def load_shop_sellers(path: Path) -> dict:
    """Item id -> the shopkeepers who sell it. Optional."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("sellers") or {}


# How few places an item can lie in before pointing at them is guidance rather
# than noise. Measured, not picked: of 240 item mentions in "acquires" steps
# that have spawn data, 196 are commodities in seven or more places -- Coins,
# Bones, Logs, Buckets -- where a marker answers a question nobody asked and
# fills the world map. The 36 that sit in three places or fewer are the ones the
# guide means when it says "when passing", Purple dye among them.
MAX_SPAWN_PLACES = 3
# One place can still be a scatter of tiles. A handful marks the spot; forty
# redraws the same room.
MAX_SPAWN_POINTS = 12
MAX_SPAWN_ITEMS = 3


def choose_sides(doc: dict) -> int:
    """Mark the dialogue option the route takes, where quest-helper says which.

    Quest Helper relabels an option to say where it leads --
    "I'll help you. (side with Hazeel)" -- and `build_quest_steps` keeps that as
    `choices`. The guide writes its decision in its own brackets: "Start Hazeel
    Cult [Side with Hazeel]". Both are real sentences from real sources, so the
    join is an exact one on a narrower alphabet, never a search.

    Only where the route is unambiguous. Two steps on one quest asking for
    opposite sides is not a majority to be taken; it is a contradiction, and the
    options are left unmarked so the player decides, as they do today.

    Nothing is removed. The losing option keeps its note and is simply not one
    of the words the highlighter is looking for.
    """
    wanted: dict[str, set[str]] = {}
    for section in doc.get("sections", ()):
        for step in section.get("steps", ()):
            merged = step.get("merged") or {}
            key = merged.get("questHelper")
            if not key:
                continue
            for tag in merged.get("tags") or ():
                name = tag.get("tag") if isinstance(tag, dict) else tag
                if name:
                    wanted.setdefault(key, set()).add(squash(name))

    marked = 0
    for key, helper in (doc.get("questHelpers") or {}).items():
        tags = wanted.get(key)
        if not tags:
            continue
        for instruction in _every_instruction(helper):
            choices = instruction.get("choices") or ()
            if not choices:
                continue
            notes = {squash(c["note"]) for c in choices}
            hit = notes & tags
            if len(hit) != 1:
                # No side named, or both named. Either way, not a decision.
                continue
            side = next(iter(hit))
            said = list(instruction.get("dialogue") or ())
            for choice in choices:
                if squash(choice["note"]) == side and choice["option"] not in said:
                    said.append(choice["option"])
                    marked += 1
            instruction["dialogue"] = said
    return marked


def _every_instruction(helper: dict):
    """Each instruction in a helper, through every level of nesting."""
    stack = list((helper.get("steps") or {}).values())
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("whenIn") or ())


def load_item_spawns(path: Path) -> dict:
    """Item name -> the places it lies on the ground. Optional.

    Keyed through :func:`squash`, because the guide writes "Purple Dye" and the
    wiki's own spawn table writes "Purple dye". That is still an exact match,
    just of a narrower alphabet -- not a search. Two different items that squash
    alike are ambiguous and so are dropped, not guessed between.
    """
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8")).get("items") or {}
    keyed: dict[str, list] = {}
    clashed = set()
    for name, places in raw.items():
        key = squash(name)
        if key in keyed:
            clashed.add(key)
            continue
        keyed[key] = places
    for key in clashed:
        keyed.pop(key, None)
    return keyed


def load_quest_steps(path: Path) -> tuple[dict, dict, dict]:
    """Quest Helper's per-quest step lists, and the other names they answer to.

    Three spellings of a quest have to meet: the wiki's, Quest Helper's enum,
    and RuneLite's Quest constant. "Desert Treasure I" is DESERT_TREASURE in
    one and DESERT_TREASURE_I in the other; "Romeo & Juliet" is ROMEO__JULIET
    in both and romeoandjuliet in the folder. The alias table is built where
    those names are read, so nothing here has to guess at them.
    """
    if not path.exists():
        return {}, {}, {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return (doc.get("quests") or {}, doc.get("aliases") or {},
            doc.get("tasks") or {})


def load_quest_objects(path: Path) -> dict:
    """Per-quest scenery from build/quest_objects.json. Optional."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("quests") or {}



# "start Vampyre Slayer", "continue Rune Mysteries", "complete Druidic Ritual".
DOING = "(start|continue|complete|finish|begin)"
# Between the verb and the name: "talk to Aris and start Demon Slayer" has none,
# "start the second step of X Marks the Spot" has a few words.
RE_DOING_A_QUEST = DOING + r"\b[^.;]{0,24}?"
# The same, for comparing with punctuation and spaces removed. No word boundary
# is possible once the spaces are gone.
RE_DOING_A_QUEST_SQUASHED = DOING + r".{0,24}?"


# The step's action is getting a thing or putting it away. Acquisition only --
# not "cook", "mine" or "smith", which are sometimes literally the quest step.
RE_FETCHING = re.compile(
    r"^\s*(?:take|collect|buy|purchase|withdraw|bank|deposit|loot|grab|keep"
    r"|fill|pick(?!pocket))\b", re.I)


# The same verbs anywhere in the sentence, and the words that say the step is
# the quest rather than a trip that happens to gather something for one.
RE_FETCHING_ANYWHERE = re.compile(
    r"\b(?:collect|withdraw|loot|grab|keep\s+the)\b", re.I)
RE_DOING = re.compile(r"\b(start|continue|complete|finish)\b", re.I)


# A step that is telling the player something rather than asking them to do
# something. The guide is full of them and they are indistinguishable, from the
# outside, from a step whose extraction failed:
#
#   MAX HITS: Ahrim 20, Dharok 29 (57 on 1 hp), Guthan 24, Karil 20
#   Turn NPC 'Attack' Options to 'Always Right-click'
#   You can get multiple Garlic by spamclicking the cupboard [Fishing Contest]
#
# Labelling them is what makes the silence of the rest mean something. It also
# stops the last of those driving a quest: a line about garlic is not the player
# doing Fishing Contest, and the bracket is only saying what the garlic is for.
#
# Deliberately narrow. Only labels the guide writes itself, lines shouted in
# capitals, whole lines in brackets, and the second person -- the guide addresses
# the player directly when it is advising and imperatively when it is
# instructing, which is the one signal that separates the two reliably.
RE_ADVICE_LABEL = (r"(?:note|optional|important|tip|warning|recommended|mandatory"
                   r"|strategy|reminder)\b\s*:?")
RE_ADVICE_SECOND_PERSON = (
    r"you (?:can|will|should|want|need|may|might|are|have)|if you|make sure|feel free"
    r"|remember|i would|i personally|here i|keep in mind|do not|don't"
    r"|it is (?:recommended|worth|best)|this is|these are|max hits?\b|at this point you")
RE_ADVICE = re.compile(
    r"^\s*(?:\^|\[|\()?\s*(?:" + RE_ADVICE_LABEL + r"|" + RE_ADVICE_SECOND_PERSON + r")",
    re.I)
# Shouted, and long enough that it is not just a name.
RE_ADVICE_SHOUTED = re.compile(r"^[^a-z]{15,}")
# A whole line in brackets is an aside.
RE_ADVICE_ASIDE = re.compile(r"^\s*[\[(].*[\])]\s*$")


def is_advice(text: str) -> bool:
    """Whether the step is telling the player something, not asking for an action."""
    return bool(RE_ADVICE.match(text) or RE_ADVICE_SHOUTED.match(text)
                or RE_ADVICE_ASIDE.match(text))

def is_preparation(text: str, quests: int) -> bool:
    """Whether a quest is named as the reason for the step, not as its subject.

    This is the guide's own habit and it is everywhere early on: "Take 1 extra
    Rotten Apple [Mournings End Pt 1]" is collecting an apple a hundred banks
    before that quest, and the bracket says what it is *for*. Reading it as
    "you are doing Mourning's End" put that quest's first instruction on screen
    and offered to tick the step when its progress moved.

    Two things say it plainly. The step's action is fetching something rather
    than talking to anyone or going anywhere; or it names several quests at
    once, and nobody is doing three quests at the same time -- "Buy 2x Bronze
    Med Helm [Black Knights Fortress, Mournings End Pt II, Kings Ransom]".
    """
    # Training goals and gathering drops for a future quest are not the quest.
    # Inspect the imperative clause, not a later aside mentioning completion.
    action = re.split(r"[.!;]|\(", text, maxsplit=1)[0]
    if re.search(r"\b(?:xp|experience)\b", action, re.I):
        return True
    if (re.match(r"\s*(?:train|camp)\b", action, re.I)
            or (re.match(r"\s*kill\b", action, re.I)
                and re.search(r"\buntil\s+\d+\s*x\b", action, re.I))):
        return True
    if quests > 1 or RE_FETCHING.match(text):
        return True
    # "Go upstairs again and Collect 4x logs on the top floor [Tree Gnome
    # Village]" fetches too; the verb is just not the first word. Only where the
    # step does not also say it is doing the quest -- "Kill Elvarg and take the
    # head to complete Dragon Slayer" is the quest, whatever else it collects.
    return bool(RE_FETCHING_ANYWHERE.search(text)) and not RE_DOING.search(text)


def is_doing_the_quest(text: str, quest: str) -> bool:
    """Whether the step says it is starting, continuing or finishing that quest.

    A quest named in prose is not enough on its own to tick anything: the guide
    mentions quests constantly, in passing -- "keep 3 Bronze Bars for Tourist
    Trap", "collect the Demon Slayer key". Those must never complete themselves
    because the quest happened to move while the player was reading them.

    Requiring the verb to sit just before the name separates the two, and it is
    the sentence the guide actually writes when it means "do this now".

    Two spellings of the name are tried, and a leading "The" dropped: the guide
    writes "Gertrudes Cat" for "Gertrude's Cat" and "Knights Sword" for "The
    Knight's Sword". Both are still exact comparisons against the closed list of
    quest names, in a narrower alphabet.
    """
    names = [quest]
    without_the = re.sub(r"^the\s+", "", quest, flags=re.I)
    if without_the != quest:
        names.append(without_the)

    for name in names:
        if re.search(RE_DOING_A_QUEST + re.escape(name), text, re.I):
            return True
        if re.search(RE_DOING_A_QUEST_SQUASHED + re.escape(squash(name)),
                     squash(text), re.I):
            return True
    return False


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



# "Collect 3x Logs next to the stairs" names an item and then says where it is.
# The whole phrase is what the extraction hands over, and no such item exists,
# so twenty-five steps rang nothing -- the beer in the Longhall, the bucket by
# the bank chest, the doogle leaf south of Gertrude.
#
# Cutting here is safe only because the shorter name still has to resolve
# through the item index. "Food for Elvarg" becomes "Food" because Food is an
# item; "Healers" stays unresolved because nothing shortens to anything real.
RE_WHERE_IT_IS = re.compile(
    r"\s+\b(inside|in|on|at|from|north|south|east|west|next|by|near|under|"
    r"behind|outside|off|before|after|while|for|with|to|and|if|when|upstairs|"
    r"downstairs|beside|across)\b.*$", re.I)


def without_where_it_is(name: str) -> str:
    """"Beer inside the Longhall" -> "Beer". Unchanged when there is no tail."""
    return RE_WHERE_IT_IS.sub("", name).strip(" ,.&")

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
    r"\b(tab|tablet|teletab|necklace|cloak|ring|scroll|portal|glory)\b",
    re.I)


# Anchored: "Home teleport to Lumbridge" is casting it, but the Salve
# Graveyard step lists it among several routes it is not telling you to
# take. Matching it anywhere put a ring on the wrong spell there.
# "Buy X from <Name>" / "Collect X from <Name>": the seller is who you go to.
RE_BOUGHT_FROM = re.compile(r"\b(?:buy|buys|collect|withdraw|purchase)\b[^.\[\]()]{0,60}?\bfrom\s+(?-i:([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*))", re.I)

# Prose rather than an instruction.
RE_ASIDE = re.compile(r"^\s*(optional|as mentioned|if you)\b", re.I)


# Steps that mean "end up holding these".
# "Empty Bucket", "Empty Pot": the guide means the ordinary item.
RE_EMPTY_PREFIX = re.compile(r"^empty\s+", re.I)


RE_ACQUIRES = re.compile(r"^\s*(?:buy|buys|collect|take|loot|grab|pick\s+up|purchase|withdraw|get)\b", re.I)


# A step that opens by going somewhere.
# A step that opens by naming a direction rather than a thing.
RE_BARE_DIRECTION = re.compile(r"^\s*(?:head|go|walk|run|make your way)\b", re.I)


# A step that says to put something on and leave it on.
# The point the guide stops assuming anything about what is carried.
RE_DEPOSITS_ALL = re.compile(
    r"deposit\s+all|bank\s+all|empty\s+(?:your\s+)?inventory", re.I)


RE_WEARS = re.compile(r"\b(?:wield|equip|wear)\b", re.I)


RE_TRAVEL = re.compile(r"^\s*(?:head|travel|go|return|walk|run|make your way|take the)\b", re.I)

# Anything after that which is a second thing to do.
RE_SECOND_INSTRUCTION = re.compile(r"&|,|\band\b|\bthen\b|\btalk\b|\bkill\b|\bbuy\b|\bcollect\b|\btake\b|\buse\b|\bpickpocket\b|\bsearch\b|\benter\b|\bclimb\b|\bstart\b|\bcomplete\b|\bmine\b|\bcut\b|\bfish\b", re.I)


RE_HOME_TELEPORT = re.compile(r"^\s*home\s*teleport\b", re.I)


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


def check_diary_aliases(aliases: dict, doc: dict) -> list[str]:
    """Every alias must correct a tag the guide really writes, into a real diary.

    A stale left-hand side means the wiki was fixed and the row is now dead
    weight; a bad right-hand side would put a diary name in front of players
    that does not exist.
    """
    regions = ["Ardougne", "Desert", "Falador", "Fremennik", "Kandarin", "Karamja",
               "Kourend", "Lumbridge", "Draynor", "Morytania", "Varrock",
               "Western Provinces", "Wilderness"]
    tiers = ["Easy", "Medium", "Hard", "Elite"]
    real = {f"{r} {t} Diary" for r in regions for t in tiers}
    real.add("Lumbridge & Draynor Easy Diary")

    written = set()
    for section in doc["sections"]:
        for step in section["steps"]:
            for tag in (step.get("annotation") or {}).get("tags", []):
                written.add(tag)

    problems = []
    for wrong, right in sorted(aliases.items()):
        if wrong not in written:
            problems.append(f"{wrong!r}: no step writes this any more")
        if right not in real:
            problems.append(f"{wrong!r} -> {right!r}: not a real diary")
    return problems


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


def squash(text: str) -> str:
    """Lowercase, with everything that is not a letter or digit removed.

    For comparing a quest name the guide spelled without its apostrophe against
    the real one. Still an exact comparison, just of a narrower alphabet.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


RE_ENDS_A_QUEST = re.compile(r"\b(complete|finish)\b", re.I)
# A step whose whole instruction is to begin something.
RE_STARTS_A_QUEST = re.compile(r"^\s*start\b", re.I)



def carry_quest_into_substeps(doc: dict) -> int:
    """A sub-step of a quest step is done while inside that quest.

    The guide nests the errands you do on the way:

        Start Biohazard until you get the samples
          - Take 1 extra Rotten Apple [Mournings End Pt 1]
          - Take 5 extra Pigeon Cages [One Small Favour]

    The player picking up the apple is still running Biohazard, and the plugin
    went quiet as soon as they stepped onto it -- the apple's own bracket names
    a quest a hundred banks away, and that one is only the reason for the pickup.

    So the parent's quest travels down as `questContext`: what to *show* while
    the sub-step is current. Not `questStep`, which governs ticking -- the apple
    is picked up by hand and the quest moving on says nothing about it.
    """
    carried = 0
    for section in doc["sections"]:
        ancestors: dict[int, dict] = {}
        for step in section["steps"]:
            merged = step.get("merged", {})
            depth = step.get("depth", 1)
            for deeper in [d for d in ancestors if d >= depth]:
                ancestors.pop(deeper)
            ancestors[depth] = merged

            # Advice guides nowhere, so pointing a quest at it only means the
            # overlay starts talking over a line that was telling the player
            # something. "You can't die in the fights!" is not a step of Death
            # on the Isle.
            if depth <= 1 or merged.get("questStep") or merged.get("advice"):
                continue
            for above in sorted(ancestors, reverse=True):
                if above >= depth:
                    continue
                parent = ancestors[above]
                if parent.get("questStep") and parent.get("questHelper"):
                    merged["questContext"] = parent["questHelper"]
                    carried += 1
                break
    return carried



# A verb that comes away with something. Travel is excluded by name: "Take the
# boat to Brimhaven" is a journey, and every vehicle the guide uses is spelled
# out rather than guessed at.
RE_FETCHED_FOR_LATER = re.compile(
    r"\b(?:take(?!\s+(?:the\s+)?(?:boat|ship|canoe|carpet|cart"
    r"|minecart|glider|charter|barge|ferry|raft|gnome))"
    r"|buy|purchase|mine|chop|fletch|catch)\b", re.I)

# What a step says when it is the quest itself rather than an errand for one.
RE_WORKING_A_QUEST = re.compile(
    r"\b(?:start|continue|complete|finish|talk\s+to)\b", re.I)


def demote_fetches_to_preparation(doc: dict) -> int:
    """A bracket on a fetch says what the item is for, not what you are doing.

    A tag alone used to be taken as proof: "Head North and take Jug of Water
    [Monk's Friend]" was read as doing Monk's Friend, so the plugin answered a
    step about a jug with "talk to Brother Omad in the monastery south of West
    Ardougne" -- a quest the player would not reach for another sixty banks.
    It is the same category error that had a Rotten Apple taken during Biohazard
    starting Mourning's End Part 1, and it is the guide's single most common
    shape: collect the thing now, use it much later.

    Verb alone cannot separate them. "Catch 8 rats [Ratcatchers]" is the quest;
    "Kill a cow and take the cowhide [Mournings End Pt 1]" is a cowhide. What
    separates them is the bank: a quest being worked in this bank is named by a
    step that starts, continues, completes it or talks to someone for it. A
    fetch tagged with a quest the bank is not working is a fetch for later.

    Twenty-one steps move. Two of the twenty-one are arguably wrong, and they
    are wrong in the cheap direction: a step demoted to preparation still shows
    its own target and items, where a step wrongly left as the quest hands the
    player an instruction from somewhere across the world.
    """
    demoted = 0
    for section in doc["sections"]:
        worked = {
            step["merged"]["questHelper"] for step in section["steps"]
            if step.get("merged", {}).get("questStep")
            and step["merged"].get("questHelper")
            and RE_WORKING_A_QUEST.search(step["raw"])
        }
        for step in section["steps"]:
            merged = step.get("merged", {})
            quest = merged.get("questHelper")
            if not merged.get("questStep") or not quest or quest in worked:
                continue
            if RE_WORKING_A_QUEST.search(step["raw"]):
                continue
            if not RE_FETCHED_FOR_LATER.search(step["raw"]):
                continue
            merged["questStep"] = False
            demoted += 1
    return demoted


def carry_quest_across_its_span(doc: dict) -> int:
    """Everything between starting a quest and finishing it is inside it.

    The guide does a quest in named pieces, and puts the errands you do along
    the way between them as plain siblings rather than as nested sub-steps::

        Start Tourist Trap
        You need to safespot the Mercenary Captain on his soldiers. [...]
        Take his bones [Demon Slayer]
        Complete Tourist Trap

    Only the first and last of those carried the quest, so for the seven
    minutes the player spent on the middle two the plugin had nothing to say --
    while Quest Helper, open beside it, guided the same stretch without a gap.
    That is the whole of what a session log showed for The Tourist Trap.

    The middle steps are inside the quest by position: the player is running it
    at the time. So the quest travels across the span as ``questContext`` --
    what to *show* -- and never as ``questStep``, which governs ticking. The
    bones are picked up by hand and the quest moving on says nothing about it.

    This is also what settles the bracket on the bones. ``[Demon Slayer]`` says
    what they are *for*, a hundred banks later; where the player actually is, is
    Tourist Trap. Position beats the bracket, which is the same rule that
    stopped a Rotten Apple taken during Biohazard from starting Mourning's End.

    Narrow on purpose: the span has to open with a step that *starts* the quest
    and close on the next step naming it. "Complete 3rd Step of X Marks the
    Spot" does not open one -- that quest is done in numbered pieces with a trip
    to Draynor between them, and treating the gaps as inside it put five errands
    and an agility lap under a quest the player had walked away from. Eleven
    spans match, and every step inside them says as much itself: "During the
    quest, safespot the Headless Beast", "Collect 2x Purple Dye when passing".

    Advice is left out. It has nothing to guide to, and an audit rule says so.
    """
    carried = 0
    for section in doc["sections"]:
        steps = section["steps"]
        doing = [(index, step["merged"]["questHelper"])
                 for index, step in enumerate(steps)
                 if step.get("merged", {}).get("questStep")
                 and step["merged"].get("questHelper")]

        for (opens, quest), (closes, next_quest) in zip(doing, doing[1:]):
            if quest != next_quest or not RE_STARTS_A_QUEST.match(steps[opens]["raw"]):
                continue
            for index in range(opens + 1, closes):
                merged = steps[index].get("merged", {})
                # A step doing a quest of its own is not inside this one, a
                # sub-step already carries its parent's, and advice guides
                # nowhere by definition.
                if (merged.get("questStep") or merged.get("questContext")
                        or merged.get("advice")):
                    continue
                merged["questContext"] = quest
                carried += 1
    return carried


def pin_quest_boundaries(doc: dict, quest_steps: dict, aliases: dict) -> dict:
    """Say how far into a quest each guide step is meant to take the player.

    The route does a quest a piece at a time, and until now a step that touched
    one was ticked the moment the quest moved at all. "Head North East &
    continue Gertrude's Cat" is four of Quest Helper's steps -- climb the
    ladder, the milk, the sardine, the kitten -- so ticking on the first of them
    dropped the player onto the next guide step with three still to do.

    What a step is worth is the distance to the *next* one. So each step is
    placed on the quest's timeline by the ids it names -- "Talk to Shilop"
    names npc 3501 and quest-helper names 3501 at progress 1, an exact match
    against its own table -- and then a step is finished when the quest reaches
    where the following step begins.

    Two things are derivable and one is not:

    * `questDoneAt`, when the next step could be placed.
    * `questCompletes`, for the last step of a quest in the guide -- it is done
      when the quest is past everything Quest Helper describes.
    * nothing, for a step whose successor names nothing placeable. Those keep
      the old behaviour of ticking when the quest moves, which is right for the
      many steps that are one instruction long and is no worse than before for
      the rest.

    Placement only ever moves forward: the same npc appears at several progress
    values -- Gertrude at 0 and again at 5 -- and a step is where the quest
    has not been yet.
    """
    ordered: dict[str, list[dict]] = {}
    for section in doc["sections"]:
        for step in section["steps"]:
            merged = step.get("merged", {})
            # Only the steps that are the quest. A step collecting something for
            # it much later sits between two real ones and would take a slice of
            # the timeline it has nothing to do with.
            if merged.get("questHelper") and merged.get("questStep"):
                ordered.setdefault(merged["questHelper"], []).append(step)

    stats = {"questDoneAt": 0, "questCompletes": 0, "no boundary": 0,
             "questDoneAtPanel": 0}
    for key, steps in ordered.items():
        quest = quest_steps.get(aliases.get(key, key))
        if not quest:
            continue
        anchors = quest.get("anchors") or {}
        last = quest.get("lastValue", 0)

        placed: list[int | None] = []
        floor = 0
        for step in steps:
            ids = (step["merged"].get("target") or {}).get("ids") or []
            found = sorted({value for game_id in ids
                            for value in anchors.get(str(game_id), [])
                            if value >= floor})
            placed.append(found[0] if found else None)
            if found:
                floor = found[0]

        # A last step that says "complete" is the quest's final stretch, and
        # quest-helper's last value is by construction its final instruction.
        if placed and placed[-1] is None and RE_ENDS_A_QUEST.search(steps[-1]["raw"]):
            placed[-1] = last

        # A quest the guide only ever starts is not finished by the guide.
        # "Start Olaf's Quest until you get Sven's Last Map" is the last step
        # for it here, and marking it as ending the quest ticked it the moment
        # the quest was over -- possibly hours after the step was due.
        only_starts = (RE_STARTS_A_QUEST.match(strip_links(steps[-1]["raw"]))
                       and not RE_ENDS_A_QUEST.search(steps[-1]["raw"]))

        for index, step in enumerate(steps):
            if index == len(steps) - 1:
                if only_starts:
                    stats["no boundary"] += 1
                    continue
                step["merged"]["questCompletes"] = True
                stats["questCompletes"] += 1
                continue
            # The next step that could be placed, not only the very next one.
            # Where the following step names nothing the quest's progress value
            # can be matched against, this step used to get no boundary at all
            # and so ticked the moment the quest moved by one -- and one is
            # often several of Quest Helper's own instructions. "Head North to
            # the church then start Sheep Herder" ticked at progress 1 and the
            # guide moved on, so Quest Helper's instruction for 1 -- talk to
            # Doctor Orbon, in that same church -- was never shown to anybody.
            following = next((placed[later] for later in range(index + 1, len(placed))
                              if placed[later]), None)
            if not following:
                # None, or zero. A quest sits at 0 before it is started, so
                # "finished when progress reaches 0" is true the moment the step
                # opens -- thirteen steps ticked themselves and the guide walked
                # past them. A real boundary is somewhere the quest can get to.
                stats["no boundary"] += 1
                continue
            step["merged"]["questDoneAt"] = following
            stats["questDoneAt"] += 1

        # Where the value cannot say. The guide runs a quest to a stated point,
        # goes off for twenty banks and comes back to finish it -- and for a
        # quest whose progress value is coarse, the point it stops at and the
        # point it resumes at are the same value. Sheep Herder's goes 0, 1, 2,
        # and prodding four sheep, feeding them, collecting the bones and
        # burning them all happen at 2, so "continue until all 4 Sheep bones are
        # burnt" opened at 2 and was told it was finished at 2.
        #
        # Quest Helper's own sidebar can say. `getPanels()` lists its steps in
        # the order they happen, and where the guide's next step is the one that
        # finishes the quest, this step ends when Quest Helper reaches the last
        # entry -- for Sheep Herder, when it stops saying "incinerate the bones"
        # and starts saying "return to Halgrive".
        #
        # Only where the value boundary is missing or says nothing. Ninety-seven
        # steps have a good one, and handing "Talk to Father Aereck" over at the
        # end of The Restless Ghost would be far worse than what it replaced.
        panels = quest.get("panelCount") or 0
        if panels > 1:
            # Place each step on quest-helper's own timeline the same way it is
            # placed on the progress value: by the entities it names, only ever
            # moving forward. The sidebar has an entry per action where the
            # value has one per handful, so this reaches the stopping points the
            # value cannot express -- "until you get the samples" sits inside a
            # single value and between two sidebar entries.
            panel_anchors = quest.get("panelAnchors") or {}

            # The positions the plugin can actually observe: a hand-over is met
            # by comparing against the panel of the instruction being shown, so
            # a position no instruction carries is one it can never reach. Set
            # there, the step would wait for ever -- which is worse than the
            # coarse boundary it replaced.
            reachable = set()
            for record in (quest.get("steps") or {}).values():
                for candidate in [record] + (record.get("whenIn") or []):
                    if candidate.get("panel") is not None:
                        reachable.add(candidate["panel"])
            placed_panel: list[int | None] = []
            floor = 0
            for step in steps:
                ids = (step["merged"].get("target") or {}).get("ids") or []
                found = sorted({position for game_id in ids
                                for position in panel_anchors.get(str(game_id), [])
                                if position >= floor})
                placed_panel.append(found[0] if found else None)
                if found:
                    floor = found[0]

            opens_at = 0
            for index, step in enumerate(steps):
                boundary = step["merged"].get("questDoneAt")
                degenerate = boundary is None or boundary <= opens_at
                if boundary is not None:
                    opens_at = boundary
                if step["merged"].get("questCompletes") or index + 1 >= len(steps):
                    continue

                # Where the next step for this quest begins, on the sidebar.
                # Failing that -- and only when the next step is the one that
                # finishes the quest -- the last entry there is.
                hand_over = next(
                    (placed_panel[later] for later in range(index + 1, len(steps))
                     if placed_panel[later]), None)
                if hand_over is None and RE_ENDS_A_QUEST.search(steps[index + 1]["raw"]):
                    hand_over = panels - 1

                # Only where the value cannot answer, and only forward of where
                # this step itself starts. Applied wherever it could be, it
                # displaced ninety-seven perfectly good value boundaries and
                # would have run "Talk to Father Aereck" to the end of The
                # Restless Ghost.
                own = placed_panel[index] or 0
                if (degenerate and hand_over is not None and hand_over > own
                        and hand_over in reachable
                        and not RE_ENDS_A_QUEST.search(step["raw"])):
                    step["merged"]["questDoneAtPanel"] = hand_over
                    stats["questDoneAtPanel"] += 1
    return stats

def lend_targets_forward(doc: dict) -> int:
    """Give a bare direction the target of the step that follows it.

    "Head North" followed by "Talk to Romeo" is one instruction written as two,
    and on its own the first half names nothing to walk to. Borrowing the next
    step's target means the route is drawn the moment the player reads it.

    Only where the direction step really is bare: no target, destination or
    items of its own, and no second thing to do. "Head South to the Sword Shop
    and go up the ladder" keeps its own job -- pointing that at the NPC waiting
    at the top would walk the player past the ladder they were told to climb.
    """
    borrowed = 0
    for section in doc["sections"]:
        steps = section["steps"]
        for i, step in enumerate(steps[:-1]):
            mine = step.get("merged") or {}
            if mine.get("target") or mine.get("destination") or mine.get("items"):
                continue
            heading = RE_BARE_DIRECTION.match(strip_links(step["raw"]))
            if not heading:
                continue
            if RE_SECOND_INSTRUCTION.search(strip_links(step["raw"])[heading.end():]):
                continue

            ahead = (steps[i + 1].get("merged") or {}).get("target") or {}
            if ahead.get("kind") not in ("npc", "object") or not ahead.get("ids"):
                continue

            aim = dict(ahead)
            # Marked, so the panel can say where the aim came from and nobody
            # mistakes it for something this step's own words named.
            aim["borrowedFromNext"] = True
            mine["target"] = aim
            step["merged"] = mine
            borrowed += 1
    return borrowed


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
    ap.add_argument("--shops", type=Path, default=REPO / "build" / "shops.json")
    ap.add_argument("--spawns", type=Path,
                    default=REPO / "build" / "item_spawns.json")
    ap.add_argument("--images", type=Path, default=REPO / "build" / "images.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "merged.json")
    ap.add_argument("--check-aliases", action="store_true", help="validate aliases and exit")
    ap.add_argument("--check-collections", action="store_true",
                    help="validate curated item collections and exit")
    ap.add_argument("--check-diary", action="store_true",
                    help="validate curated diary task bits and exit")
    ap.add_argument("--check-diary-aliases", action="store_true",
                    help="verify curated/diary_aliases.yaml and stop")
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
    quest_steps, quest_step_aliases, diary_task_steps = load_quest_steps(args.quest_steps)
    shop_sellers = load_shop_sellers(args.shops)
    item_spawns = load_item_spawns(args.spawns)
    used_diary_tasks: set[str] = set()
    # Longest first, so "Fairytale II - Cure a Queen" wins over "Fairytale".
    # The alias table as written -> real, for matching prose as well as tags.
    quest_alias_names = {
        str(k): str(v) for k, v in
        (load_yaml(args.curated / "quest_aliases.yaml").get("aliases") or {}).items()
    }

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

    diary_aliases = {
        str(k): str(v) for k, v in
        (load_yaml(args.curated / "diary_aliases.yaml").get("names") or {}).items()
    }

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
    problems = check_diary_aliases(diary_aliases, doc)
    if problems:
        print("curated/diary_aliases.yaml is invalid:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    if args.check_diary_aliases:
        print(f"{len(diary_aliases)} diary tags corrected, all live and all real")
        return 0

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

            # --- a teleport item written where a verb would go ----------------
            # "Chronicle to Varrock" and "Ectophial" name the thing to click and
            # nothing else, and annotate can only see the shape. The item index
            # decides: a name that is not an item is dropped whole, so the same
            # shape in "Head North to Draynor and Deposit all" stays a walk.
            #
            # Promoted before the destination is read, so a teleport that names
            # where it lands resolves that place by the ordinary rules.
            if ann.get("teleportItem") and not ann.get("teleportVia"):
                item = ann["teleportItem"]
                if resolve_item_name(item, entities, item_collections,
                                     collection_ids)[0]:
                    ann = dict(ann)
                    ann["teleportVia"] = item
                    if ann.get("teleportItemTo") and not ann.get("destination"):
                        ann["destination"] = ann["teleportItemTo"]
                    stats["teleport item named as the step"] += 1

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
                    # The name is kept as something to match on, not only to
                    # display. An npc whose id changes as it transforms -- and
                    # the game does that constantly -- matches nothing by id,
                    # and Quest Helper carries an npcName for exactly this. It
                    # is an exact comparison, so a name that is not in the room
                    # matches nothing rather than something near enough.
                    "names": [name],
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
                    # A phrase naming one entity can be walked to. One naming
                    # several cannot: "a man/woman" is 29 npcs standing all over
                    # the world, and their first coordinate is not where the
                    # player is being sent.
                    if len(alias_names) == 1 and entities[alias_names[0]]["points"]:
                        merged["target"]["points"] = entities[alias_names[0]]["points"]
                        merged["target"]["wikiPage"] = entities[alias_names[0]]["wikiPage"]
                    stats["target:manual (entity alias)"] += 1
                elif ann.get("targetName") and ann.get("intent") != "quest":
                    # Unresolved, but still usable: the plugin can match the raw
                    # name against the loaded scene.
                    #
                    # Except a quest. "Complete Knights Sword" is not a thing
                    # standing anywhere, and 222 steps carried a target named
                    # after a quest that could never match an npc or a piece of
                    # scenery -- it only made the step look answered.
                    merged["target"] = {
                        "name": ann["targetName"],
                        "kind": ann.get("intent"),
                        "ids": [],
                        "points": [],
                        "confidence": "inferred",
                    }
                    stats["target:inferred"] += 1

            # --- who you buy it from ------------------------------------------
            # "Buy a Newspaper from Benny" extracted the newspaper, which is
            # what you leave with but not what you walk to. The person named
            # after "from" is the thing to highlight; the item stays in
            # `items` for the shop and inventory to ring.
            #
            # The verb and the "from" have to sit in one instruction, hence the
            # span cap: without it "OPTIONAL: if you planted 3 teak trees ...
            # from Tempoross" retargets a whole step onto a boss.
            if merged.get("target", {}).get("kind") != "npc":
                seller = RE_BOUGHT_FROM.search(strip_links(step["raw"]))
                if seller and not RE_ASIDE.match(step["raw"]):
                    who = entities.get(seller.group(1).strip())
                    if who and who["kind"] == "npc" and who.get("ids"):
                        was = merged.get("target", {}).get("name")
                        merged["target"] = {
                            "name": seller.group(1).strip(),
                            "kind": "npc",
                            "ids": who["ids"],
                            "points": who.get("points", []),
                            "confidence": who.get("confidence", "wiki-exact"),
                        }
                        if who.get("wikiPage"):
                            merged["target"]["wikiPage"] = who["wikiPage"]
                        stats["target: the seller, not the goods"] += 1
                        if was:
                            stats["  (replacing an item target)"] += 1

            # --- gear that stays on ------------------------------------------
            # A bank that does not say "deposit all" expects you to still be
            # wearing what an earlier step told you to wield. Only worn gear:
            # a running model of everything withdrawn was measured and reaches
            # 60 items at 61 banks, which does not fit in an inventory, because
            # 165 of 211 banks never say what gets deposited.
            if RE_DEPOSITS_ALL.search(strip_links(step["raw"])):
                merged["depositsAll"] = True
                stats["deposits everything"] += 1

            # --- arriving is the whole step -----------------------------------
            # "Travel to Port Piscarilius via Veos" is finished by being there.
            # "Head to the basement & Talk to Sedridor" is not -- arriving is
            # half of it, and ticking on arrival would skip the talk. So this
            # needs the step to carry no second instruction at all, which takes
            # it from 265 candidates down to the couple of dozen where standing
            # in the right place really is the whole job.
            cleaned = strip_links(step["raw"])
            travel = RE_TRAVEL.match(cleaned)
            if travel and not RE_SECOND_INSTRUCTION.search(cleaned[travel.end():]):
                where = None
                place = merged.get("destination")
                if place and not place.get("ambiguous") and len(place.get("points") or []) == 1:
                    where = place["points"][0]
                else:
                    aim = merged.get("target") or {}
                    if len(aim.get("points") or []) == 1:
                        where = aim["points"][0]
                if where and len(where) >= 3:
                    merged["arrivesAt"] = where
                    stats["done on arrival"] += 1

            # --- provable completion ------------------------------------------
            # Only ever a signal the game itself sets. The plugin ticks on it;
            # everything else stays a manual checkbox.
            # A step can need more than one thing to be true. "Train Draynor
            # Agility to 5 Agility [Lumbridge Easy Diary]" is done when the
            # diary bit is set AND the level is reached; ticking on either
            # alone marks work complete that the player has not done. These
            # used to be two assignments, so whichever ran second won.
            completion = {}

            skill_row = skill_targets.get(step["id"])
            if skill_row:
                completion["skill"] = skill_row["skill"]
                completion["level"] = skill_row["level"]
                stats["skill target"] += 1

            diary_row = diary_tasks.get(step["id"])
            if diary_row:
                completion["varplayer"] = varplayers[diary_row["varplayer"]]
                completion["varplayerName"] = diary_row["varplayer"]
                completion["bit"] = diary_row["bit"]
                stats["diary completion bit"] += 1

            if completion:
                parts = []
                if "bit" in completion:
                    parts.append("diary")
                if "skill" in completion:
                    parts.append("skill")
                # kind is descriptive only; the plugin requires every
                # condition present, whatever kind says.
                completion["kind"] = "+".join(parts)
                if len(parts) > 1:
                    stats["completion needs both"] += 1
                merged["completion"] = completion

                # --- what Quest Helper does for this diary task ---------------
                # A diary helper has no progress value to key on, so it keys its
                # tasks on the task's own bit -- the same two numbers already in
                # `completion`, read from the same VarPlayerID constants. Two
                # integers matching two integers: no names, nothing to get
                # wrong, and it reaches all but one of the guide's diary steps.
                if "bit" in completion:
                    task = f"{completion['varplayer']}:{completion['bit']}"
                    if task in diary_task_steps:
                        merged["diaryTask"] = task
                        used_diary_tasks.add(task)
                        stats["diary task step"] += 1

            # --- items --------------------------------------------------------
            items = []
            for entry in ann.get("items", []):
                item_name = entry["name"] if isinstance(entry, dict) else entry
                count = entry.get("count", 1) if isinstance(entry, dict) else 1
                # curated/ first for the category words. A phrase like "Desert
                # Robes" has a wiki page of its own -- the legs -- so resolving
                # it there returned one item and a player wearing only those
                # looked fully equipped. Where a person has said what a phrase
                # covers, that is the answer; the rule is that curated wins.
                collection = item_collections.get(item_name)
                member_ids = (collection_members(collection, collection_ids, entities)
                              if collection is not None else None)
                if member_ids:
                    record = {
                        "name": item_name,
                        "ids": member_ids,
                        "collection": collection if isinstance(collection, str)
                        else ", ".join(collection),
                    }
                    if count > 1:
                        record["count"] = count
                    items.append(record)
                    stats["item resolved"] += 1
                    stats["  via item collection"] += 1
                    continue

                # "Empty Bucket" has a wiki page of its own that is a different
                # item from a bucket -- 3727 against 1925 -- so the guide asking
                # for an empty bucket rang the wrong thing. The guide means the
                # ordinary item every time it writes this, so the word is
                # dropped and the stem resolved instead. Only when the stem
                # really is an item, so nothing is invented.
                bare = RE_EMPTY_PREFIX.sub("", item_name)
                if bare != item_name:
                    stem = entities.get(bare) or entities.get(bare.capitalize())
                    if stem and stem["kind"] == "item" and stem.get("ids"):
                        record = {"name": item_name, "ids": stem["ids"]}
                        if count > 1:
                            record["count"] = count
                        items.append(record)
                        stats["item resolved"] += 1
                        stats["  dropping a leading Empty"] += 1
                        continue

                entity = entities.get(item_name)
                if entity and entity["kind"] == "item":
                    record = {"name": item_name, "ids": entity["ids"]}
                    if count > 1:
                        record["count"] = count
                    items.append(record)
                    stats["item resolved"] += 1
                    continue
                # The item, then where to find it. Resolved only if the
                # shorter name is itself an item -- see without_where_it_is.
                shorter = without_where_it_is(item_name)
                if shorter and shorter != item_name:
                    ids, collection_label = resolve_item_name(
                        shorter, entities, item_collections, collection_ids)
                    if ids:
                        record = {"name": item_name, "ids": ids}
                        if collection_label:
                            record["collection"] = collection_label
                        if count > 1:
                            record["count"] = count
                        items.append(record)
                        stats["item resolved"] += 1
                        stats["  dropping where to find it"] += 1
                        continue

                unresolved = {"name": item_name, "ids": []}
                if count > 1:
                    unresolved["count"] = count
                items.append(unresolved)
                stats["item unresolved"] += 1
            if items:
                merged["items"] = items
                if ann.get("withdraw"):
                    # Which step is the trip to the bank. Everything else in a
                    # section may mention an item without asking you to take it
                    # out -- logs you light, a bucket you pick up on the way --
                    # and ringing those made the bank list wrong at every bank.
                    merged["withdraw"] = True
                    stats["withdraw step"] += 1
                # A step that says to acquire things is finished when you hold
                # them. Flagged here rather than sniffed at runtime so the
                # plugin never has to guess what a step means, and only when
                # every item resolved -- a partly-known list cannot be checked
                # and must stay manual.
                if ((RE_ACQUIRES.match(strip_links(step["raw"]))
                        or ann.get("buys") or ann.get("collects"))
                        and all(i["ids"] for i in items)):
                    merged["acquires"] = True
                    stats["acquired when held"] += 1
            if ann.get("inventorySlots") is not None:
                merged["inventorySlots"] = ann["inventorySlots"]

            # --- whoever sells it ---------------------------------------------
            # The guide names a shop's goods and trusts the player to find the
            # counter: "Buy 2x Bronze Med Helm in Barbarian Village" never says
            # Peksa, because you are standing in the village and there is one
            # shop. So the plugin walked them to the village and left them.
            #
            # Every shop that sells the item is offered instead, and the plugin
            # marks whichever is nearest. In Barbarian Village that is Peksa,
            # and in Varrock it is somebody else, without either being written
            # down anywhere. Nothing is invented: the stock comes from the shop
            # pages and the shopkeepers resolve like any other npc.
            if merged.get("items") and RE_A_PURCHASE.match(strip_links(step["raw"])) \
                    and merged.get("target", {}).get("kind") != "npc":
                offered = []
                seen_sellers = set()
                for item in merged["items"]:
                    for game_id in item.get("ids", []):
                        for who in shop_sellers.get(str(game_id), []):
                            entity = entities.get(who)
                            if (who in seen_sellers or entity is None
                                    or entity["kind"] != "npc" or not entity["ids"]):
                                continue
                            seen_sellers.add(who)
                            offered.append({"name": who, "ids": entity["ids"],
                                            "points": entity["points"][:MAX_SELLER_POINTS]})
                if offered:
                    # Capped. A bucket is sold in forty places and shipping all
                    # of them would put more in the file than it takes out of
                    # the player's way.
                    merged["sellers"] = offered[:MAX_SELLERS]
                    stats["shops that sell it"] += 1
                    if len(offered) > MAX_SELLERS:
                        stats["  (more shops than were shipped)"] += 1

            # --- where it lies on the ground ----------------------------------
            # "Collect 2x Purple Dye when passing" never says where. The author
            # wrote "when passing" because the spawn is on the way, but the step
            # named no place, so the dye only ever outlined once the player was
            # already standing on it. That is a highlight, not guidance, and 175
            # "acquires" steps had no target at all.
            #
            # The wiki's own spawn table answers it, so nothing is typed in by
            # hand. Only for items in a few places: see MAX_SPAWN_PLACES for why
            # a bucket gets nothing. A step that already knows where it is going
            # keeps its own coordinate -- this fills silence, it does not argue.
            if merged.get("items") and not merged.get("target", {}).get("points"):
                lying = []
                for item in merged["items"]:
                    places = item_spawns.get(squash(item["name"])) or []
                    if not places or len(places) > MAX_SPAWN_PLACES:
                        continue
                    points = []
                    for place in places:
                        for point in place["points"]:
                            if point not in points:
                                points.append(point)
                    if not points or len(points) > MAX_SPAWN_POINTS:
                        continue
                    lying.append({"name": item["name"],
                                  "ids": item.get("ids", []),
                                  "points": points,
                                  "places": [p["location"] for p in places]})
                if lying:
                    merged["spawns"] = lying[:MAX_SPAWN_ITEMS]
                    stats["lies on the ground"] += 1

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
                if lookup not in quests:
                    # The same punctuation problem the prose matcher has:
                    # "[Ghost's Ahoy]" is 13 steps on its own, and "Kings
                    # Ransom", "Merlins Crystal" and "Gertrudes Cat" the rest.
                    # Still an exact comparison against the closed Quest list,
                    # just with the apostrophes taken out of both sides.
                    squashed = squash(tag)
                    for candidate, pair in quests.items():
                        if len(squash(pair[0])) >= 10 and squash(pair[0]) == squashed:
                            lookup = candidate
                            stats["quest tag, punctuation differing"] += 1
                            break
                if lookup in quests:
                    name, constant = quests[lookup]
                    quest_tags.append(
                        {"tag": tag, "quest": name, "constant": constant,
                         "via": "alias" if target else "exact"}
                    )
                    stats["quest tag " + ("via alias" if target else "exact")] += 1
                elif "diary" in tag.lower():
                    # The bracket tags are typed by hand on the wiki, so some
                    # misspell the diary or name two things at once. A tag that
                    # is not a real diary shows the player the wrong name and
                    # keeps the step out of diary curation, where it could
                    # never auto-tick.
                    real = diary_aliases.get(tag, tag)
                    entry = {"tag": real, "diary": True}
                    if real != tag:
                        entry["asWritten"] = tag
                        stats["diary tag corrected"] += 1
                    quest_tags.append(entry)
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

            if is_advice(strip_links(step["raw"])):
                merged["advice"] = True
                stats["telling, not asking"] += 1

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
            # The spelling the guide used, which is not always the real name:
            # "Witches Potion" for "Witch's Potion", "Fairy Tale Part I" for
            # "Fairytale I - Growing Pains". The verb test below has to look for
            # the words that are actually on the page.
            quest_written = quest_named
            if quest_named is None:
                # The guide names a quest in prose as often as in a [tag]:
                # "Start X Marks the Spot on Veos" carries no bracket at all.
                # Matched against the RuneLite Quest names, which are a closed
                # authoritative list, as a whole phrase -- an exact lookup, not
                # a similarity search. Informational only: nothing is ticked off
                # a prose mention, because "Dragon Slayer" also appears in
                # sentences that are not about doing Dragon Slayer.
                lowered_raw = step["raw"].lower()
                squashed_raw = squash(step["raw"])
                for display in quest_names_by_length:
                    if display.lower() in lowered_raw:
                        quest_named = quest_written = display
                        stats["quest named in prose"] += 1
                        break
                    # The guide writes quest names without their apostrophes as
                    # often as with: "Ghost's Ahoy", "Dorics Quest", "Gertrudes
                    # Cat", "Witches Potion". Comparing with punctuation
                    # removed is still an exact match against the closed Quest
                    # list, not a similarity search -- and it is 18 quests and
                    # some fifty steps that were finding nothing at all.
                    #
                    # Long names only. Squashing a short one invites a match
                    # inside an unrelated word.
                    if len(squash(display)) >= 10 and squash(display) in squashed_raw:
                        quest_named = quest_written = display
                        stats["quest named in prose"] += 1
                        stats["  its punctuation differing"] += 1
                        break
                else:
                    # The aliases a person wrote for the tags apply to prose
                    # too: "Witches Potion" differs from "Witch's Potion" by a
                    # letter, not a mark, so no amount of squashing reaches it.
                    # Longest first, and only on a word boundary. "Fairytale
                    # Part I" is a substring of "Fairytale Part II", so a step
                    # continuing the second was attached to the first -- and
                    # then marked as completing it.
                    for written, real in sorted(quest_alias_names.items(),
                                                key=lambda row: -len(row[0])):
                        if re.search(re.escape(written.lower()) + r"(?![\w])",
                                     lowered_raw):
                            quest_named, quest_written = real, written
                            stats["quest named in prose"] += 1
                            stats["  via a curated alias"] += 1
                            break
            if quest_named:
                key = quest_directory(quest_named)
                key = quest_step_aliases.get(key, key)
                if key in quest_steps:
                    # Only the key. The step lists live once at guide level --
                    # inlining them here repeated the same few hundred lines
                    # across 174 steps and put 774 KiB into the shipped file.
                    merged["questHelper"] = key
                    used_quest_helpers.add(key)
                    stats["quest step list"] += 1

                    # Whether this step is the quest being done, rather than the
                    # quest being mentioned. A [tag] says so outright; in prose
                    # the verb has to say it. Only these may be ticked off by
                    # the quest's progress moving -- see QuestProgress.
                    said = strip_links(step["raw"])
                    tagged = sum(1 for t in merged.get("tags", []) if t.get("quest"))
                    if is_advice(said):
                        # A line about garlic is not the player doing Fishing
                        # Contest, however the bracket reads.
                        stats["advice, so not the quest being done"] += 1
                        tagged = 99
                    doing = (merged.get("tags")
                             or is_doing_the_quest(said, quest_named)
                             or is_doing_the_quest(said, quest_written))
                    diary_only = (merged.get("diaryTask")
                                  and not is_doing_the_quest(said, quest_named)
                                  and not is_doing_the_quest(said, quest_written))
                    if doing and not diary_only and not is_preparation(said, tagged):
                        merged["questStep"] = True
                        stats["step is the quest being done"] += 1
                    elif doing:
                        stats["step is preparing for a quest, not doing it"] += 1

            # --- the spell that gets you there ------------------------------
            destination_now = merged.get("destination")
            constant = None
            if RE_HOME_TELEPORT.search(step["raw"]):
                # "Home teleport to Lumbridge" is one spell whose destination is
                # fixed, so the place in the text does not choose it. This used
                # to be excluded outright as "some other method", which meant
                # the one spell a new account casts constantly rang nothing.
                constant = "TELEPORT_HOME_STANDARD"
            elif destination_now and "teleport" not in merged and casts_a_spell(step["raw"]):
                # "Teleport to Varrock" names where, not how: on the standard
                # spellbook there is only one answer.
                constant = spells.get(destination_now["name"])

            if constant and constant in spell_widgets:
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
    sided = choose_sides(doc)
    if sided:
        print(f"route's side marked  {sided:5}  (dialogue options quest-helper labels)")
    doc["diaryTasks"] = {
        key: diary_task_steps[key] for key in sorted(used_diary_tasks)
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    borrowed = lend_targets_forward(doc)
    if borrowed:
        print(f"borrowed target      {borrowed:5}  (a bare direction, aimed at the next step)")

    before_starts = demote_before_starts(doc, quest_steps, quest_step_aliases)
    print(f"supplies before start {before_starts:3}")
    inherited = carry_quest_into_substeps(doc)
    if inherited:
        print(f"quest carried down   {inherited:5}  (a sub-step of a step doing a quest)")

    # Before the span and boundary passes: both read questStep.
    demoted = demote_fetches_to_preparation(doc)
    if demoted:
        print(f"fetch, not the quest {demoted:5}  (a bracket saying what the item is for)")

    continued = attach_continuations(doc)
    print(f"explicit continuations {continued:3}  (immediately preceding sibling quest)")

    spanned = carry_quest_across_its_span(doc)
    if spanned:
        print(f"quest carried across {spanned:5}  (between starting a quest and finishing it)")

    boundaries = pin_quest_boundaries(doc, quest_steps, quest_step_aliases)
    milestones = pin_explicit_milestones(doc, quest_steps, quest_step_aliases)
    print(f"explicit quest starts {milestones['start']:3}")
    print(f"quest item milestones {milestones['items']:3}")
    print(f"unresolved item stops {len(milestones['unresolved']):3}")

    # Overrides again, last. The file says "merged last, always wins" and until
    # now that was only true of the fields settled inside the step loop: the
    # three quest passes and the boundary pass all run after it, so a hand-set
    # questDoneAt or questDoneAtPanel was computed over and lost. Those are
    # exactly the fields a person has to set by hand, because they are the ones
    # no rule can derive.
    for section in doc["sections"]:
        for step in section["steps"]:
            override = overrides.get(step["id"])
            if override:
                if any(override.get(f) for f in ("questStopItems", "questStopValue", "questStopCondition", "questStopUnresolved")):
                    for field in ("questDoneAt", "questDoneAtPanel", "questCompletes",
                                  "questStopUnresolved", "questStartOnly", "questStopItems", "questStopValue", "questStopCondition"):
                        step["merged"].pop(field, None)
                if any(field in override for field in (
                        "questDoneAt", "questDoneAtPanel", "questCompletes")):
                    # A human-authored boundary wins over generated item goals
                    # too; leaving an unresolved flag would silently disable it.
                    step["merged"].pop("questStopItems", None)
                    step["merged"].pop("questStopUnresolved", None)
                    step["merged"].pop("questStartOnly", None)
                step["merged"].update(override)
    # A verified override can attach a helper that prose resolution missed.
    # Build the shipped helper set from FINAL references, not only the earlier
    # name matcher, or such a step carries a dangling key and guides nowhere.
    for section in doc["sections"]:
        for step in section["steps"]:
            for field in ("questHelper", "questContext"):
                key = step["merged"].get(field)
                if key:
                    if key not in quest_steps:
                        raise ValueError(f"Unknown {field} {key!r} on {step['id']}")
                    doc["questHelpers"][key] = quest_steps[key]
    unresolved_goals = [{"id": s["id"], "quest": s["merged"].get("questHelper"), "text": s["raw"]}
                        for section in doc["sections"] for s in section["steps"]
                        if s["merged"].get("questStopUnresolved")]
    (args.out.parent / "quest-milestones-unresolved.json").write_text(
        json.dumps(unresolved_goals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"manual goals after author overrides: {len(unresolved_goals)}")
    print("inferred boundaries before explicit milestones / final human overrides:")
    print(f"quest boundaries     {boundaries['questDoneAt']:5}  (knows the value it is done at)")
    print(f"                     {boundaries['questDoneAtPanel']:5}  (hands over at quest-helper's last step)")
    print(f"                     {boundaries['questCompletes']:5}  (ends when the quest does)")
    print(f"                     {boundaries['no boundary']:5}  (no successor to measure to)")

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

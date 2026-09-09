"""Stage 3: turn step prose into structured hints. Rules only, no guessing.

Reads build/parsed.json, writes build/annotated.json and build/coverage.json.

This stage never resolves an ID or a coordinate. It extracts *names* and hands
them to the plugin, which matches them against the loaded scene at runtime. A
name that matches nothing highlights nothing, so a wrong extraction costs a
missing highlight rather than a wrong one -- which is what lets the grammar
below be as aggressive as it is.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --- markup ------------------------------------------------------------------

RE_LINK = re.compile(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<label>[^\]]*))?\]\]")
RE_URL = re.compile(r"https?://\S+")
RE_DIALOGUE = re.compile(r"\((?P<seq>\d(?:\s*,\s*\d)*)\)")
RE_TAG = re.compile(r"\[(?P<tag>[^\[\]]+)\]")
RE_SLOTS = re.compile(r"\((?P<n>\d+)\s*(?:Inventory\s*)?(?:Slots?|Spaces?)\)", re.I)

# --- verb grammar ------------------------------------------------------------
#
# Longest phrase first: "Bank at" must beat "Bank", "Talk to" must beat "Talk".

VERB_RULES: list[tuple[str, str]] = [
    # Teleport shorthand -- the guide leans on these constantly.
    ("home teleport to", "nav"),
    ("home teleport", "nav"),
    ("minigame teleport to", "nav"),
    ("minigame teleport", "nav"),
    # NPC targets
    ("talk to", "npc"),
    ("talk with", "npc"),
    ("talk again", "npc-continue"),
    ("speak to", "npc"),
    ("trade with", "npc"),
    ("trade", "npc"),
    ("pickpocket", "npc"),
    ("steal from", "npc"),
    ("kill", "npc"),
    ("attack", "npc"),
    ("catch", "npc"),
    ("hand in to", "npc"),
    # Object targets
    ("bank at", "object"),
    ("fill", "object"),
    ("use", "object"),
    ("search", "object"),
    ("enter", "object"),
    ("climb", "object"),
    ("open", "object"),
    ("mine", "object"),
    ("chop", "object"),
    ("cut", "object"),
    ("fish", "object"),
    ("pray at", "object"),
    ("pick", "object"),
    # Item-flavoured
    ("withdraw", "withdraw"),
    ("deposit", "item"),
    ("take", "item"),
    # "Read the Ardougne Teleport Scroll in your inventory", "Read Dwarven
    # Lore". The thing to read is the thing to click, and without this the step
    # named nothing at all.
    ("read", "item"),
    ("collect", "item"),
    ("buy", "item"),
    ("wield", "item"),
    ("equip", "item"),
    ("drop", "item"),
    ("make", "item"),
    ("plant", "item"),
    # Navigation
    ("teleport to", "nav"),
    ("teleport", "nav"),
    ("head", "nav"),
    ("travel to", "nav"),
    ("travel", "nav"),
    ("return to", "nav"),
    ("return", "nav"),
    ("go to", "nav"),
    ("run to", "nav"),
    # Quest progress
    ("complete", "quest"),
    ("continue", "quest"),
    ("finish", "quest"),
    ("start", "quest"),
    # Deposit-flavoured banking: "Bank the ashes", "Bank South and deposit all".
    ("bank", "bank"),
]

# "Take Falador Crumbling wall Shortcut", "Take rope shortcut up towards
# Volcanic Mine". A way through, not a thing to pick up.
RE_SHORTCUT = re.compile(r"^\s*take\b[^.;]*\bshortcut\b", re.I)
RE_DEPOSIT_ALL = re.compile(r"^\s*deposit\s+(all|everything|inventory)\b", re.I)

# "Take the boat to Brimhaven", "Charter to Catherby", "Take the minecart to
# Keldagrim". The vehicle is not the point and the place is: this is the one
# shape where the guide leads with how it is travelling rather than where to.
#
# A closed list of vehicles on purpose. It is also what makes it safe to read a
# leading "Take" as picking something up -- an earlier attempt at that matched
# "Take the boat to Brimhaven" and cost six points of target coverage, so the
# word was banned outright and "Take 3x Logs" has given nothing since. Naming
# the vehicles settles which sentence is which instead.
_VEHICLES = (r"boat|ship|ferry|canoe|barge|raft|rowboat|gondola"
             r"|mine ?cart|cart system|cart|carpet|magic carpet"
             r"|glider|gnome glider|balloon|hot ?air ?balloon"
             r"|spirit tree|mushtree|magic mushtree|fairy ring|quetzal")
# "to the Ruins of Uzer" -- the article is not part of the name, and
# insisting the place start with a capital would drop it.
_PLACE = (r"(?:[Tt]he\s+)?(?P<dest>[A-Z][\w' -]{2,28}?)\s*"
          r"(?:[.,(\[]|\s&|\sand\b|$)")
# The verb is case-insensitive; the place is not. A whole-pattern re.I would
# make the [A-Z] in _PLACE match lowercase too, and that has already turned "the
# cupboard" into a proper noun once in this pipeline.
RE_VEHICLE_TO = re.compile(
    r"^\s*(?i:(?:take|catch|board|ride)\s+(?:the|a|an)?\s*(?:" + _VEHICLES + r")"
    r"\s+(?:back\s+)?to\s+)" + _PLACE)
RE_CHARTER_TO = re.compile(
    r"^\s*(?i:charter\s+(?:a\s+ship\s+)?to\s+)" + _PLACE)

# "Buy 2x Bronze Med Helm in Barbarian Village", "Buy a Spade at Draynor".
# Where the shop is. Cut off the item name so it resolves, and until now
# discarded with it -- so the step rang an item and pointed nowhere.
RE_BUY_AT = re.compile(
    r"^\s*(?i:(?:buy|purchase|trade)\b[^.;]*?\b(?:in|at)\s+(?:the\s+)?)"
    r"(?P<dest>[A-Z][\w' -]{2,28}?)\s*"
    r"(?:[.,(\[]|\s&|\s(?:if|when|unless|for|then)\b|$)")

# Skipped before reading a proper-noun run: "Use your Feather" -> "Feather",
# "Talk to the Bartender" -> "Bartender".
LEAD_SKIP = {
    "a", "an", "the", "your", "my", "our", "some", "any", "all", "both",
    # Prepositions and directions between the verb and the name. "Head to the
    # Wizards Tower" and "Head North-East to the Lumberyard" both stopped dead
    # on the lowercase word after the verb, so the destination came back empty
    # and the step had nothing to walk to at all.
    "to", "towards", "toward", "into", "at", "in", "on", "back",
    "north", "south", "east", "west", "north-east", "north-west",
    "south-east", "south-west", "northeast", "northwest", "southeast",
    "southwest", "ne", "nw", "se", "sw", "up", "down", "over", "across",
}

# Capitalised, but never the name of a thing you can highlight.
NOT_A_NAME = {
    "north", "south", "east", "west", "north-west", "north-east",
    "south-west", "south-east", "north west", "north east", "south west",
    "south east", "nw", "ne", "sw", "se", "up", "down",
    "left", "right", "upstairs", "downstairs", "optional", "note", "if",
    "here", "there", "back", "inside", "outside", "everything", "all",
}

# Words that end a proper-noun run. "Talk to Lord Daquarias again" stops at
# "again"; "Talk to Explorer to receive Dusty Key" stops at "to".
STOP_WORDS = {
    "a", "about", "after", "again", "aggro", "all", "an", "and", "any", "as",
    "at", "back", "before", "behind", "below", "beside", "between", "but",
    "by", "down", "during", "each", "east", "else", "for", "from", "here",
    "if", "in", "inside", "into", "is", "it", "near", "next", "no", "north",
    "of", "off", "on", "once", "onto", "or", "our", "out", "outside", "over",
    "per", "run", "since", "so", "south", "than", "the", "then", "there",
    "this", "through", "to", "towards", "under", "until", "up", "upstairs",
    "using", "via", "west", "when", "where", "while", "who", "with", "within",
    "you", "your",
}

# A proper-noun run may contain these lowercase particles internally:
# "Wizard of the Tower", "Sir Amik Varze". Kept only when a capitalised word
# follows, so trailing particles are still trimmed.
INNER_PARTICLES = {"of", "the", "de", "van", "von"}

RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def strip_links(text: str, keep_labels: bool = True) -> str:
    def sub(m: re.Match) -> str:
        if not keep_labels:
            return " "
        return m.group("label") or m.group("target")

    return RE_LINK.sub(sub, text)


def extract_links(text: str) -> list[str]:
    """Wiki link targets, minus the anchor and the display label."""
    out = []
    for m in RE_LINK.finditer(text):
        target = m.group("target").split("#")[0].strip()
        target = re.sub(r"_", " ", target)
        if target and target not in out:
            out.append(target)
    return out


def proper_noun_run(words: list[str]) -> str | None:
    """Take the leading run of capitalised words, allowing internal particles."""
    taken: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        low = word.lower()
        if word[0].isupper():
            taken.append(word)
            i += 1
            continue
        if (
            taken
            and low in INNER_PARTICLES
            and i + 1 < len(words)
            and words[i + 1][0].isupper()
        ):
            taken.append(word)
            i += 1
            continue
        break

    if not taken:
        return None
    # Trim a trailing particle: "Talk to Bob of" -> "Bob".
    while taken and taken[-1].lower() in INNER_PARTICLES:
        taken.pop()
    if not taken:
        return None
    name = " ".join(taken)
    # A run of one very common word is noise, not a name.
    if len(taken) == 1 and taken[0].lower() in STOP_WORDS:
        return None
    if name.lower() in NOT_A_NAME:
        return None
    return name


def clause_words(clause: str) -> list[str]:
    """Words up to the first structural break: bracket, paren, or punctuation."""
    clause = RE_URL.sub(" ", clause)
    cut = len(clause)
    for ch in "([,.;:/!?":
        pos = clause.find(ch)
        if pos != -1:
            cut = min(cut, pos)
    return RE_WORD.findall(clause[:cut])


def match_verb(text_lower: str) -> tuple[str, str] | None:
    """Longest phrase wins. The boundary may be a space or a colon --
    "Withdraw: Coins" is by far the most common step opener in the guide."""
    for phrase, intent in VERB_RULES:
        if text_lower == phrase:
            return phrase, intent
        if len(text_lower) > len(phrase) and text_lower.startswith(phrase):
            if text_lower[len(phrase)] in " :-":
                return phrase, intent
    return None


# Verbs strong enough to override a leading navigation verb.
INTERACTION_VERBS = [
    (phrase, intent)
    for phrase, intent in VERB_RULES
    if intent in ("npc", "object") and phrase not in ("use", "open")
]


def find_interaction_verb(body: str) -> tuple[int, str, str] | None:
    """Earliest 'talk to' / 'kill' / 'bank at' style verb after position 0."""
    best: tuple[int, str, str] | None = None
    lowered = body.lower()
    for phrase, intent in INTERACTION_VERBS:
        for m in re.finditer(rf"\b{re.escape(phrase)}[ :]", lowered):
            if m.start() == 0:
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), phrase, intent)
    return best


def skip_lead_ins(words: list[str]) -> list[str]:
    """Drop articles, possessives and quantities before the name proper."""
    i = 0
    while i < len(words):
        low = words[i].lower()
        if low in LEAD_SKIP or re.fullmatch(r"\d+x?", low):
            i += 1
            continue
        break
    return words[i:]


# "15 Pineapples", "5x Food", "10+ Nails". The trailing \s+ matters: without
# it "2 Handed Sword" would lose its "2" and stop resolving.
# A withdraw that opens with something else: "Deposit all, then Withdraw: X".
# "Buy X, Y & Z", and the "Trade <someone> and buy ..." form.
# A creature the guide names without capitalising it.
# "... and collect the Bones + Raw Rat Meat": the drops, named after a kill.
# Deliberately not "take": mid-sentence that is nearly always travel --
# "Take the boat to Brimhaven", "Take the Carpet to Pollnivneach" -- and
# a step that opens with Take is already covered by the opener rule.
# "Collect 3x Logs", "Loot the Chest", "Pick up the Saw" -- and "Take 3x
# Logs", but only where the step opens with it. Mid-sentence "take" is
# ordinary prose ("take everything", "take the long way"), and a leading
# one is a pickup now that RE_VEHICLE_TO has already claimed "Take the boat
# to Brimhaven".
RE_COLLECTS = re.compile(
    r"(?:\b(?:collect|loot|pick\s+up)|^\s*take)\s+(?:the|an|a|all|some)?\s*", re.I)

# What follows the drops and is not one of them.
# Where to do it, not part of what is gathered: "Mine 10x Clay on the way",
# "Mine 10 Clay at varrock west mine", "Chop 5 Branches while passing".
RE_TRAILING_GATHER = re.compile(r"\b(?:then|and\s+(?:head|go|bank|deposit|use|make)|from|to\s+(?:make|use)|on\s+the\s+way|at\s|while\s|near\s|next\s+to\s|when\s|beneath\s|below\s|underneath\s|behind\s|inside\s|outside\s|in\s+the\s|from\s+the\s)\b.*$", re.I)


# A skilling step that says how many to come away with: "Mine 10x Clay",
# "Pick 5 Flax", "Cut 25 Oak Logs". The thing named is what ends up in the
# inventory, so it is an item with a count -- which is what makes the shop ring
# it, the panel count it, and the step tick itself off when the tenth one
# arrives. Fifty steps of this shape carried nothing at all, and "Mine 10x Clay
# on the way" guided nowhere and never completed.
#
# A count is required. Without one the named thing is as likely to be the
# object worked on as the item gained -- "Cut the teak tree" is a tree -- and
# guessing between them is how a step ends up counting trees.
#
# "kill" and "steal" are left out on purpose: what they name is the creature or
# the stall, which already resolves as a target, and the drops are named
# separately by the collect rule.
RE_GATHERS = re.compile(
    r"^\s*(?:mine|chop|cut|fish|catch|pick|fletch|cook|craft|smith|net)\s+"
    r"(?=\d)", re.I)

# "until 46 Fishing", "until 6,099 Thieving Experience" -- a grind to a level,
# where the number is the goal and not a quantity of anything.
RE_UNTIL = re.compile(r"until", re.I)


def thing_worked(text: str, item: str) -> str | None:
    """The scenery a skilling step is asking the player to click.

    Named from the item, because that is what the guide gives: "Mine 10x Clay"
    is clay rocks, "Cut 25 Oak Logs" is an oak tree. The suffix comes from the
    verb, and the result is a page name like any other -- resolve_wiki finds it
    exactly or the step has no target. Nothing here decides that a name is close
    enough.

    Only mining and woodcutting. A fishing spot is an npc with a name of its
    own, and "Pick 5 Flax" is picked off the ground with nothing to outline.
    """
    verb = text.strip().split(" ", 1)[0].lower()
    if verb in ("mine",):
        # "Copper Ore" is mined from "Copper rocks"; "Clay" from "Clay rocks".
        return re.sub(r"" + chr(92) + "s+ore$", "", item, flags=re.I).strip() + " rocks"
    if verb in ("chop", "cut"):
        # "Oak Logs" grow on an "Oak tree".
        return re.sub(r"" + chr(92) + "s+logs?$", "", item, flags=re.I).strip() + " tree"
    return None


RE_LOWERCASE_CREATURE = re.compile(r"^\s*(?:kill|pickpocket|catch|fish|trade|talk\s+to)\s+(?:a|an|the|some)?\s*([a-z][a-z' -]{2,26}?)(?=\s|$|[.,(\[])", re.I)


RE_BUYS = re.compile(r"^\s*(?:trade\s+[\w' ]{1,24}?\s+and\s+)?(?:buy|purchase|fill\s+your\s+inventory\s+with)\b", re.I)

# What follows the goods and is not one of them.
# A purchase that is not the first thing the step says.
RE_BUYS_LATER = re.compile(r"\b(?:buy|purchase)\s+", re.I)

RE_TRAILING_CLAUSE = re.compile(r"\b(?:from|and\s+(?:wear|make|use|deposit|bank|wield|equip|head|go)|then|to\s+(?:make|use)|at\s|while\s|near\s|beneath\s|below\s|behind\s|inside\s|outside\s|if\s|when\s)\b.*$", re.I)


RE_WITHDRAW_LATER = re.compile(r"\bwithdraw\b[^:]{0,40}:", re.I)


# Words in front of the name that are not part of it.
# How many, written as a bagful rather than a number: "Buy Full Inventory of
# Balls of wool", "Buy an inventory of Balls of Wool", "Cut 2 Inventories of
# Willows logs". Left on the front it is part of the name, and a name like
# "Full Inventory of Balls of wool" resolves to nothing -- so the shop rang
# nothing, no shopkeeper was offered, and a step at the Ardougne general
# store pointed at neither Aemad nor Kortan.
RE_A_BAGFUL = re.compile(
    r"^(?:\d+\s*x?\s+)?(?:a|an|one|full)?\s*inventor(?:y|ies)\s+(?:of|with)\s+", re.I)
RE_LEAD_IN = re.compile(r"^(?:all|noted|any|a|an|the|your)\s+", re.I)

# "[Cook's guild]" is a tag on the step, not part of the item.
RE_BRACKET = re.compile(r"\[[^\]]*\]")

# A leftover instruction rather than a thing: one or two lowercase words.
RE_NOT_AN_ITEM = re.compile(
    r"^(?:deposit|bank|wear|wield|equip|use|make|drop|keep|then|it|them|here|there)\b", re.I)


RE_LEADING_COUNT = re.compile(r"^(\d{1,5})\+?\s*x?\s+", re.I)


def split_item_list(blob: str) -> list[dict]:
    """`Coins, 15 Pineapples & 5x Food (23 Slots)` -> [{name, count?}, ...].

    A count is carried only when the guide states one, so an absent count means
    "one", not "unknown".
    """
    blob = RE_SLOTS.sub(" ", blob)
    blob = strip_links(blob)
    parts = re.split(r",|&|\band\b", blob)
    items: list[str] = []
    for part in parts:
        part = re.sub(r"\(.*?\)", " ", part)
        part = part.strip(" .;:")
        # Keep the leading quantity: "15 Pineapples", "5x Food", "4x Logs".
        # It used to be discarded, which is why a step saying to buy five jugs
        # of wine could not tell one jug from five.
        count = 1
        quantity = RE_LEADING_COUNT.match(part)
        if quantity:
            count = int(quantity.group(1))
            part = part[quantity.end():]
        part = RE_A_BAGFUL.sub("", part)
        part = RE_LEAD_IN.sub("", part)
        # A bracket tag is a quest or diary marker, never part of the name.
        part = RE_BRACKET.sub(" ", part).strip()
        # What is left of a trailing instruction: "deposit", "wear them".
        if RE_NOT_AN_ITEM.match(part):
            continue
        part = part.strip()
        if not part or len(part) > 60:
            continue
        if not re.search(r"[A-Za-z]", part):
            continue
        for name in expand_slashes(part):
            items.append({"name": name, "count": count} if count != 1 else {"name": name})
    return items


def expand_slashes(name: str) -> list[str]:
    """A slash-joined name into the items it actually lists.

    The guide writes several items as one when they share a word:
    "Fire/Air/Earth Pack" is three packs, "Raw Rat/Chicken/Beef" is three raw
    meats. Written that way they resolve to nothing, so a shop step asking for
    five rune packs rang none of them.

    The shared word can be in front or behind, and a name that is neither
    pattern is left exactly as it was -- "100 Soda Ash/Sand if you haven't yet"
    is prose, not a list, and inventing items from it would be worse than
    leaving it unresolved.
    """
    if "/" not in name:
        return [name]

    parts = [p.strip() for p in name.split("/") if p.strip()]
    if len(parts) < 2:
        return [name]

    first, last = parts[0].split(), parts[-1].split()

    # "Raw Rat/Chicken/Beef" -- the words in front are shared.
    if len(first) > 1 and len(last) == 1:
        prefix = " ".join(first[:-1])
        return [parts[0]] + [f"{prefix} {p}" for p in parts[1:]]

    # "Fire/Air/Earth Pack" -- the words behind are shared.
    if len(last) > 1 and len(first) == 1:
        suffix = " ".join(last[1:])
        return [f"{p} {suffix}" for p in parts[:-1]] + [parts[-1]]

    # "Cat/Kitten" -- plain alternatives, no shared word at all.
    if all(len(p.split()) == 1 for p in parts):
        return parts

    return [name]



# The first word of every verb the grammar knows. A step opening with one of
# them is an instruction, whatever noun follows.
VERB_WORDS = frozenset(phrase.split()[0] for phrase, _ in VERB_RULES)


# A teleport item written where a verb would go: "Chronicle to Varrock",
# "Ectophial", "Camulet", "Chronicle teleport and run to Draynor Manor".
# Only the shape is matched here; whether the name is really an item is
# settled against the item index in merge_curated.
_TELEPORT_NAME = r"[A-Z][A-Za-z'\- ]{2,28}?"
_TELEPORT_PLACE = r"[A-Z][\w' ]{2,24}"
RE_TELEPORT_ITEM = (
    re.compile("^(?P<via>" + _TELEPORT_NAME + r")\s+[Tt]eleport\s+to\s+"
               "(?P<dest>" + _TELEPORT_PLACE + r")\s*$"),
    re.compile("^(?P<via>" + _TELEPORT_NAME + r")\s+to\s+"
               "(?P<dest>" + _TELEPORT_PLACE + r")\s*$"),
    re.compile("^(?P<via>" + _TELEPORT_NAME + r")\s+[Tt]eleport\b"),
    re.compile("^(?P<via>" + _TELEPORT_NAME + r")\s*$"),
    re.compile("^(?P<via>" + _TELEPORT_NAME + r")\s+(?:and|&)\s"),
)

def annotate_step(raw: str) -> dict:
    """All extraction for one step. Returns only fields that were found."""
    out: dict = {}

    links = extract_links(raw)
    if links:
        out["links"] = links

    urls = RE_URL.findall(raw)
    if urls:
        out["urls"] = [u.rstrip(".,);") for u in urls]

    # Tags must be read *after* links are removed, or [[Aggie]] yields a
    # phantom [Aggie] tag and 207 real tags become 666.
    delinked = strip_links(raw, keep_labels=True)

    for form in (RE_VEHICLE_TO, RE_CHARTER_TO, RE_BUY_AT):
        travelling = form.match(delinked)
        if travelling:
            out["destination"] = travelling.group("dest").strip()
            if form is not RE_BUY_AT:
                # A journey is the whole step. A purchase is not: the goods
                # still have to be read, and the shop still rung.
                out["intent"] = "nav"
                out.pop("targetName", None)
            break

    tags = [t.strip() for t in RE_TAG.findall(strip_links(raw, keep_labels=False))]
    if tags:
        out["tags"] = tags

    dialogue = RE_DIALOGUE.findall(delinked)
    if dialogue:
        out["dialogue"] = [
            [int(n) for n in re.split(r"\s*,\s*", seq)] for seq in dialogue
        ]

    slots = RE_SLOTS.search(delinked)
    if slots:
        out["inventorySlots"] = int(slots.group("n"))

    # Strip tags and dialogue before grammar so they can't be read as names.
    body = RE_TAG.sub(" ", RE_DIALOGUE.sub(" ", delinked)).strip()
    lowered = body.lower()

    verb = match_verb(lowered)

    # "Head West and talk to Redbeard Frank" leads with a nav verb but the
    # useful target is the NPC. An interaction verb later in the sentence beats
    # a navigation verb at the start.
    if not verb or verb[1] in ("nav", "bank", "item"):
        stronger = find_interaction_verb(body)
        if stronger:
            offset, phrase, intent = stronger
            body = body[offset:]
            lowered = body.lower()
            verb = (phrase, intent)

    # "kill a Black Bear ... collect Raw Bear Meat, Bones & Bear Fur". The
    # drops are the point of the step and were extracted from nothing, so
    # nothing was highlighted on the ground and nothing ticked when they were
    # picked up. The verb sits mid-sentence, after the kill, which is why the
    # opener rule never saw it.
    if "items" not in out:
        # Not when the step has already been read as a journey. "Take the boat
        # to Brimhaven" would otherwise come away with an item called "boat to
        # Brimhaven" as well as its destination.
        journeying = (out.get("teleportItem") or "destination" in out
                      or RE_SHORTCUT.match(delinked))
        gathered = None if journeying else RE_COLLECTS.search(delinked)
        if gathered:
            rest = delinked[gathered.end():].split(".")[0]
            rest = RE_TRAILING_GATHER.sub("", RE_BRACKET.sub(" ", rest)).replace("+", "&")
            # Only parts that read as a name. Searching mid-sentence for
            # "collect" catches plenty of prose -- "max hit is 1" arrived as an
            # item -- and every one of those is a name the wiki cannot resolve,
            # which drags the honest coverage figure down with it. A drop is
            # capitalised; a clause is not.
            picked = [i for i in split_item_list(rest)
                      if any(w[:1].isupper() for w in i["name"].split())]
            if picked:
                out["items"] = picked
                out["collects"] = True

    # "Mine 10x Clay on the way", "Pick 5 Flax". Read like the drops above:
    # what follows the count is the thing to come away with.
    if "items" not in out:
        gathering = RE_GATHERS.match(delinked)
        if gathering and not RE_UNTIL.search(delinked):
            # "Mine 2x Blurite Ore (Make sure to safe spot the Ice Warriors
            # first)" -- the aside is advice about the mining, not part of what
            # is mined, and left on it made a name nothing could resolve.
            rest = delinked[gathering.end():].split(".")[0].split(" (")[0]
            rest = RE_TRAILING_GATHER.sub("", RE_BRACKET.sub(" ", rest)).replace("+", "&")
            mined = [i for i in split_item_list(rest)
                     if any(w[:1].isupper() for w in i["name"].split())]
            if mined:
                out["items"] = mined
                out["collects"] = True


    # The scenery a skilling step is asking the player to click, as opposed to
    # the thing gained. "Mine 10x Clay" said nothing about clay rocks and so
    # outlined nothing at all: the step counted its clay and pointed at empty
    # ground. Where a target was already found it is the item over again --
    # "Mine 12 Coal" resolved to the coal in your bag, and an item target
    # highlights what is lying on the floor -- so the rock wins. The inventory
    # side loses nothing: the item list still rings and counts it.
    #
    # Left as a name. resolve_wiki finds that exact page or the step keeps no
    # target, which is the rule every other name goes through.
    if out.get("items"):
        worked = thing_worked(delinked, out["items"][0]["name"])
        if worked and out.get("targetName") in (None, out["items"][0]["name"]):
            out["targetName"] = worked
            out["intent"] = "object"

    # "Kill a duck", "Kill a cow", "Catch a lobster". The name-finder looks
    # for a run of capitalised words, so a creature the guide writes in lower
    # case produced no target at all and the step highlighted nothing. Only
    # after a verb that plainly names a creature, and only when nothing else
    # was found -- and it is still resolved through the wiki, so a phrase that
    # is not a creature finds no page and stays unresolved.
    if "targetName" not in out:
        creature = RE_LOWERCASE_CREATURE.match(delinked)
        if creature:
            out["targetName"] = creature.group(1).strip()
            out.setdefault("intent", "npc")

    # "Buy 5x Bolts of Cloth & 100 Steel Nails" is a list exactly like a
    # withdraw is, but the verb table calls it an "item" and takes only the
    # first name. That left every shop step with nothing for the shop to ring
    # and nothing to count, so buying five things and buying one looked the
    # same. Cut at the sentence break and drop a trailing instruction, or
    # "wear them" and "deposit" arrive as items.
    if "items" not in out:
        # Anchored first, then anywhere. "Head South and buy 1x Vial of Water
        # Pack" is a purchase written after a direction, and matching only the
        # opener left it with no items and nothing for the shop to ring. Unlike
        # "take", a mid-sentence "buy" always means buying.
        bought = RE_BUYS.match(delinked) or RE_BUYS_LATER.search(delinked)
        if bought:
            # "+" separates goods exactly as "&" does -- "Buy 100 Soda ash +
            # 100 Buckets of sand" is two things. Read as one it resolved to
            # nothing at all, so the shop rang neither of them.
            rest = RE_TRAILING_CLAUSE.sub(
                "", delinked[bought.end():].split(".")[0]).replace("+", "&")
            # Same guard the drops use: a name, not a leftover clause.
            purchases = [i for i in split_item_list(rest)
                         if any(w[:1].isupper() for w in i["name"].split())]
            if purchases:
                out["items"] = purchases
                out["buys"] = True

    # "Deposit All, then Withdraw and equip: Leather Gloves" is a withdraw
    # written the long way round, and the verb rule above only sees the opener.
    # 16 steps read like this, and their items were extracted from nothing at
    # all -- the gloves that step is entirely about never reached the bank.
    # Against the whole step, not `body`: the verb search above may have
    # advanced past the word "withdraw" while looking for a stronger verb --
    # "equip" in this very example -- and then there is nothing left to find.
    if "items" not in out:
        later = RE_WITHDRAW_LATER.search(delinked)
        if later:
            items = split_item_list(delinked[later.end():])
            if items:
                out["items"] = items
                out["withdraw"] = True

    # "Deposit all", "Deposit Inventory", "Deposit all at Entrana except ...".
    # A trip to a bank the verb table does not see, because the guide leads with
    # what to do there rather than with the word "bank".
    #
    # "all" or "inventory" is the whole test, and it is what keeps the other
    # containers out: "Deposit 15 Pineapples into the Compost Bin", "Deposit 10k
    # in the coffer" and "Deposit the buckets on Drew" are not banking, and none
    # of them says it.
    if RE_DEPOSIT_ALL.match(delinked):
        out["banking"] = True

    if verb:
        phrase, intent = verb
        out["intent"] = intent
        # "Bank at Draynor", "Bank the ashes", "Bank South and deposit all".
        # Recorded separately from the intent because the intent describes what
        # the target *is* (Draynor is a place) while this describes what the
        # player is being sent to do. A text search for "bank" would also catch
        # "Keep the Shrimps in your bank for later", which is not a trip to one.
        if phrase.split()[0] == "bank":
            out["banking"] = True
        remainder = body[len(phrase) :].strip()

        if intent == "withdraw":
            items = split_item_list(remainder.lstrip(":").strip())
            if items:
                out["items"] = items
                out["withdraw"] = True
        else:
            name = proper_noun_run(skip_lead_ins(clause_words(remainder)))
            if name:
                out["targetName"] = name
            elif links:
                # "Kill a [[Jogre]]" -- the link is the target even though the
                # prose starts lowercase.
                out["targetName"] = links[0]

    # A link plus a recognised NPC/object verb is the strongest signal we have.
    if out.get("intent") in ("npc", "object") and links and "targetName" in out:
        if out["targetName"] not in links:
            # Prefer the linked spelling when the run picked up extra words.
            for link in links:
                if link.lower().startswith(out["targetName"].lower()[:6]):
                    out["targetName"] = link
                    break

    # "Start X Marks the Spot on Veos", "Teleport on Aubury", "Check playtime on
    # Hans": the guide writes "on <Name>" for the person you interact with. Only
    # applies where nothing stronger was found -- a navigation verb otherwise
    # swallows the whole clause and yields nonsense like "East Start X Marks the
    # Spot". "Use X on Y" is handled just below and overrides this.
    if out.get("intent") in (None, "nav", "bank") and "->" not in body:
        on_who = re.search(
            r"\bon\s+(?P<who>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2})", body)
        if on_who:
            who = proper_noun_run(clause_words(on_who.group("who")))
            if who:
                out["targetName"] = who
                out["intent"] = "npc"

    # "Fill Bucket on Pump" and "Cook Lava eel on range" are the same sentence
    # as "Use X on Y": the thing after "on" is the scenery to click. Reading
    # only "Use" left the six of them pointing at the item in the inventory
    # instead of the pump, the sink or the range.
    m = re.match(r"^(?:Use|Fill|Cook)\s+(?P<item>.+?)\s+on\s+(?P<target>.+)$",
                 body, re.I)
    if m:
        item = proper_noun_run(skip_lead_ins(clause_words(m.group("item"))))
        target = proper_noun_run(skip_lead_ins(clause_words(m.group("target"))))
        if item:
            out.setdefault("items", []).append(item)
        if target:
            out["targetName"] = target
            out["intent"] = "object"

    # "Ardy Cloak -> BLS", "Rapier -> TOA": teleport shorthand. The left side is
    # the method, the right side is where you end up.
    # Fires when nothing claimed the step, and also when a navigation verb did:
    # "Teleport to POH -> AJP" is a teleport shorthand whichever way it opens,
    # and gating this on an unset intent left the whole clause as one nonsense
    # target ("POH AJP") with no destination at all.
    if "->" in body and out.get("intent") in (None, "nav"):
        via, _, destination = body.partition("->")
        via = via.strip(" .")
        destination = destination.split("->")[0].strip(" .")
        # A destination is a short place name, not a clause. "Kill Soldiers from
        # (Tier 1) -> (Tier 5). Drop the obsolete sets" is not a teleport.
        plausible = (
            destination
            and len(destination.split()) <= 4
            and not re.search(r"[.;:!?]", destination)
            and not destination.startswith("(")
            and destination[0].isupper()
        )
        if via and plausible:
            out["intent"] = "nav"
            out["teleportVia"] = via
            out["destination"] = destination
            out.pop("targetName", None)

    # "Chronicle to Varrock", "Ectophial", "Camulet", "Chronicle teleport and
    # run to Draynor Manor". The guide writes a teleport item as though it were
    # a verb, and none of these steps produced anything at all: no target, no
    # destination, nothing to ring in the inventory where the player will click
    # it. The arrow shorthand covers "Ardy Cloak -> CKS" and only that.
    #
    # Proposed here, decided in merge_curated. Nothing below can tell an item
    # from a place, and "Head North to Draynor and Deposit all" matches the
    # same shape -- so the name has to resolve through the item index or the
    # whole thing is dropped. That is what keeps this from turning every step
    # beginning with a capital letter into a teleport.
    if "teleportVia" not in out and "targetName" not in out:
        for form in RE_TELEPORT_ITEM:
            found = form.match(delinked.strip())
            if not found:
                continue
            via = found.group("via").strip()
            # A step that opens with a verb is an instruction, not an item.
            # "Head north and use the Chronicle" would otherwise offer "Head
            # north", and while the item index throws that away, "Bones and
            # bury them" would offer "Bones" -- which is an item, and would
            # have shipped as a teleport.
            if via.split()[0].lower() in VERB_WORDS:
                continue
            out["teleportItem"] = via
            where = found.groupdict().get("dest")
            if where:
                out["teleportItemTo"] = where.strip()
            break

    return out


def confidence(step: dict, ann: dict) -> str:
    """How much the client should trust this annotation."""
    if "targetName" not in ann:
        return "none"
    linked = ann.get("links") and ann["targetName"] in ann["links"]
    if linked:
        return "linked"
    return "inferred"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=REPO / "build" / "parsed.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "annotated.json")
    ap.add_argument("--coverage", type=Path, default=REPO / "build" / "coverage.json")
    ap.add_argument("--sample", type=int, default=0, help="print N random steps to eyeball")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    doc = json.loads(args.input.read_text(encoding="utf-8"))

    total = 0
    intents: Counter[str] = Counter()
    confidences: Counter[str] = Counter()
    inferred_names: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    no_intent: Counter[str] = Counter()

    for section in doc["sections"]:
        for step in section["steps"]:
            total += 1
            ann = annotate_step(step["raw"])
            conf = confidence(step, ann)
            if ann:
                step["annotation"] = ann
            step["confidence"] = conf

            intents[ann.get("intent", "-none-")] += 1
            confidences[conf] += 1
            for tag in ann.get("tags", []):
                tag_counts[tag] += 1
            if conf == "inferred":
                inferred_names[ann["targetName"]] += 1
            if "intent" not in ann:
                first = step["raw"].split()[0].strip(":,.") if step["raw"].split() else ""
                no_intent[first] += 1

    coverage = {
        "totalSteps": total,
        "byIntent": dict(intents.most_common()),
        "byConfidence": dict(confidences.most_common()),
        "withTarget": confidences["linked"] + confidences["inferred"],
        "distinctTags": len(tag_counts),
        "topInferredNames": inferred_names.most_common(40),
        "topUnhandledVerbs": no_intent.most_common(40),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    args.coverage.write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")

    with_target = coverage["withTarget"]
    print(f"steps                 {total}")
    print(f"with a target name    {with_target}  ({100 * with_target / total:.1f}%)")
    print(f"  from a wiki link    {confidences['linked']}")
    print(f"  inferred from prose {confidences['inferred']}")
    print(f"no target             {confidences['none']}")
    print()
    print("by intent:")
    for intent, count in intents.most_common():
        print(f"  {count:5d}  {intent}")
    print()
    print("top 20 steps with no recognised verb, by first word:")
    for word, count in no_intent.most_common(20):
        print(f"  {count:5d}  {word}")

    if args.sample:
        import random

        rng = random.Random(args.seed)
        steps = [st for s in doc["sections"] for st in s["steps"]]
        print(f"\n--- {args.sample} random steps ---")
        for step in rng.sample(steps, args.sample):
            ann = step.get("annotation", {})
            print(f"\n  raw   {step['raw'][:110]}")
            print(f"  conf  {step['confidence']}")
            for key in ("intent", "targetName", "items", "dialogue", "tags", "links"):
                if key in ann:
                    print(f"  {key:5} {ann[key]}")

    print(f"\nwrote {args.out}")
    print(f"wrote {args.coverage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

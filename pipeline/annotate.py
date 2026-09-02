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

# Skipped before reading a proper-noun run: "Use your Feather" -> "Feather",
# "Talk to the Bartender" -> "Bartender".
LEAD_SKIP = {"a", "an", "the", "your", "my", "our", "some", "any", "all", "both"}

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


def split_item_list(blob: str) -> list[str]:
    """`Coins, 15 Pineapples & 5x Food (23 Inventory Slots)` -> item names."""
    blob = RE_SLOTS.sub(" ", blob)
    blob = strip_links(blob)
    parts = re.split(r",|&|\band\b", blob)
    items: list[str] = []
    for part in parts:
        part = re.sub(r"\(.*?\)", " ", part)
        part = part.strip(" .;:")
        # Drop a leading quantity: "15 Pineapples", "5x Food", "4x Logs".
        part = re.sub(r"^\d+\s*x?\s*", "", part, flags=re.I)
        part = re.sub(r"^(all|noted|any)\s+", "", part, flags=re.I)
        part = part.strip()
        if not part or len(part) > 60:
            continue
        if not re.search(r"[A-Za-z]", part):
            continue
        items.append(part)
    return items


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

    m = re.match(r"^Use\s+(?P<item>.+?)\s+on\s+(?P<target>.+)$", body, re.I)
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

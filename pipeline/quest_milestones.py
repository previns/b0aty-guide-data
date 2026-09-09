"""Explicit quest continuations and item goals, joined to Quest Helper evidence.

This is a merge pass, not curated per-quest content. Never search later banks
for the meaning of 'Continue': it refers only to the immediately preceding
sibling quest instruction. Never approximate an item name or a progress value.
"""
from __future__ import annotations

import re

from pipeline.annotate import strip_links

CONTINUATION = re.compile(r"^continue\s+(?:until\b|up\s+to\b)", re.I)
ITEM_STOP = re.compile(
    r"\b(?:until|up\s+to)\s+(?:you\s+)?"
    r"(?:receive|receiving|get|getting|obtain|obtaining|have|having|pick\s+up)\s+(.+)$", re.I)
BOUNDED = re.compile(r"\b(?:until|up\s+to)\b", re.I)


def instructions(record):
    yield record
    for child in record.get("whenIn", []):
        yield from instructions(child)


def start_npc_matches(text, merged, initial):
    """An explicit conversation with the initial NPC, including zone branches.

    When the guide's target is a town or absent, join the exact spoken name in
    'by talking to X' to QH's 'Talk to X in ...' instruction. This is a delimited
    name equality, not substring/fuzzy matching or a new NPC ID lookup.
    """
    ids = set((merged.get("target") or {}).get("ids", []))
    spoken = re.search(r"\b(?:by )?talking to\s+(.+?)(?=\s*\(|\s*\[|[.!;]|$)", text, re.I)
    for record in instructions(initial):
        if record.get("kind") != "npc":
            continue
        if ids.intersection(record.get("ids", [])):
            return record
        said = re.match(r"(?:Talk|Speak) to\s+(.+?)(?=\s+(?:in|at|on|under|north|south|east|west|to start)\b|[.!]|$)",
                        record.get("text", ""), re.I)
        if spoken and said and item_key(spoken[1]) == item_key(said[1]):
            return record
    return None


def attach_continuations(doc: dict) -> int:
    count = 0
    for section in doc["sections"]:
        steps = section["steps"]
        for previous, step in zip(steps, steps[1:]):
            merged = step.setdefault("merged", {})
            parent = previous.get("merged", {})
            if (CONTINUATION.match(strip_links(step["raw"]).strip())
                    and not merged.get("questHelper") and not merged.get("advice")
                    and parent.get("questStep") and parent.get("questHelper")
                    and not parent.get("advice")
                    and step.get("depth", 1) == previous.get("depth", 1)):
                merged["questHelper"] = parent["questHelper"]
                merged["questStep"] = True
                count += 1
    return count


def item_key(name: str) -> str:
    # Apostrophes/case are presentation, not fuzzy spelling. Keep every other
    # word: 'Perfect gold' must not silently become 'Perfect gold ore'.
    return " ".join(name.casefold().replace("'", "").replace("\u2019", "").split())


def demote_before_starts(doc, quests, aliases):
    """A tagged supply task before the route explicitly starts a quest is prep.

    Do not demote explicit quest instructions. This only answers the previously
    misclassified decant/telegrab/equip shapes, using route order as evidence.
    """
    steps = [s for section in doc["sections"] for s in section["steps"]]
    starts = {}
    for index, step in enumerate(steps):
        merged = step.get("merged", {})
        key = merged.get("questHelper")
        text = strip_links(step["raw"])
        quest = quests.get(aliases.get(key, key), {})
        if (merged.get("questStep") and re.search(r"\bstart\b", text, re.I)
                and not BOUNDED.search(text)
                and start_npc_matches(text, merged, quest.get("steps", {}).get("0", {}))):
            starts.setdefault(key, index)
    count = 0
    for index, step in enumerate(steps):
        merged = step.get("merged", {})
        if (merged.get("questStep") and index < starts.get(merged.get("questHelper"), -1)
                and not re.search(r"\b(?:start|continue|complete|finish|begin)\b", strip_links(step["raw"]), re.I)):
            merged["questStep"] = False
            count += 1
    return count


def item_index(quest: dict) -> dict[str, dict[tuple[int, ...], str]]:
    index: dict[str, dict[tuple[int, ...], str]] = {}

    def add(item):
        ids = item.get("ids") or ([item["id"]] if item.get("id") is not None else [])
        if item.get("name") and ids and all(isinstance(i, int) and i >= 0 for i in ids):
            index.setdefault(item_key(item["name"]), {})[tuple(sorted(set(ids)))] = item["name"]

    def walk(value):
        if isinstance(value, dict):
            # Item records have a name and IDs, unlike entity step records.
            if "name" in value:
                add(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(quest.get("items", []))
    walk(quest.get("steps", {}))
    return index


def resolve_stop_items(phrase: str, quest: dict) -> list[dict] | None:
    index = item_index(quest)
    phrase = re.sub(r"\s*\[[^\]]*\]\s*$", "", phrase).strip().rstrip(".! ")

    def resolve(part):
        part = re.sub(r"^(?:the|a|an)\s+", "", part.strip(), flags=re.I)
        quantity = re.match(r"^(\d+)\s*x?\s+(.+)$", part, re.I)
        count = int(quantity[1]) if quantity else 1
        name = quantity[2] if quantity else part
        choices = index.get(item_key(name), {})
        if count < 1 or len(choices) != 1:
            return None
        ids, source_name = next(iter(choices.items()))
        return {"name": source_name, "count": count, "ids": list(ids)}

    # Try the whole name first: an authoritative name may itself contain 'and'.
    whole = resolve(phrase)
    if whole:
        return [whole]
    parts = re.split(r"\s*(?:,|&)\s*|\s+and\s+", phrase, flags=re.I)
    resolved = [resolve(part) for part in parts]
    if not resolved or any(item is None for item in resolved):
        return None
    # Overlapping alternatives cannot prove two distinct requested items.
    used: set[int] = set()
    for item in resolved:
        if used.intersection(item["ids"]):
            return None
        used.update(item["ids"])
    return resolved


def pin_explicit_milestones(doc: dict, quests: dict, aliases: dict) -> dict:
    stats = {"start": 0, "items": 0, "unresolved": []}
    for section in doc["sections"]:
        steps = section["steps"]
        for offset, step in enumerate(steps):
            merged = step.get("merged", {})
            key = merged.get("questHelper")
            quest = quests.get(aliases.get(key, key))
            if not merged.get("questStep") or not quest:
                continue
            text = strip_links(step["raw"]).strip()
            # '...unlock X, then complete these diary steps' does not finish
            # this quest. A last appearance in the route is not completion proof.
            partial = bool(BOUNDED.search(text) or re.search(r"\b(?:to unlock|to access)\b", text, re.I))
            if partial:
                # A later route visit is not evidence for a stated objective.
                # Keep unknown goals manual until exact item resolution or a
                # source-verified author override proves the stopping point.
                merged.pop("questCompletes", None)
                merged.pop("questDoneAt", None)
                merged.pop("questDoneAtPanel", None)
                merged["questStopUnresolved"] = True
            if partial and re.search(r"\b(?:start|continue)\b", text, re.I):
                merged["questFollow"] = True
            stop = ITEM_STOP.search(text)
            if stop:
                items = resolve_stop_items(stop[1], quest)
                # A quest-wide continuation follows QH's changing targets. A
                # specific errand (e.g. pickpocket Sandy until you get sand)
                # must retain the guide's NPC even if QH currently wants another.
                if re.search(r"\b(?:start|continue)\b", text[:stop.start()], re.I):
                    merged["questFollow"] = True
                # The guide's explicit goal outranks an inferred later visit.
                # If unresolved, suppress coarse progress ticking and report it;
                # reaching the next var value is not evidence of owning the item.
                for field in ("questDoneAt", "questDoneAtPanel", "questCompletes"):
                    merged.pop(field, None)
                if items:
                    merged.pop("questStopUnresolved", None)
                    merged["questStopItems"] = items
                    stats["items"] += 1
                else:
                    merged["questStopUnresolved"] = True
                    stats["unresolved"].append({"id": step["id"], "quest": key, "text": text})
                continue

            following = steps[offset + 1] if offset + 1 < len(steps) else None
            explicit_continuation = (following is not None
                and CONTINUATION.match(strip_links(following["raw"]).strip())
                and following.get("merged", {}).get("questHelper") == key)
            # Strip asides before classifying the action. 'Start X until ...'
            # and 'start X and complete the first step' are not start-only.
            action = re.sub(r"\([^)]*\)|\[[^]]*\]", "", text).strip()
            atomic = re.search(r"\b(?:talk(?:ing)? to|head to)\b", action, re.I)
            initial = quest.get("steps", {}).get("0", {})
            positive = sorted(int(v) for v in quest.get("steps", {}) if int(v) > 0)
            starter = start_npc_matches(action, merged, initial)
            # Several quests repeat the initial instruction at values 1, 2,
            # etc. A positive value alone can mean the conversation is still
            # underway. Wait until QH stops offering that starting instruction.
            boundary = next((v for v in positive if starter and not any(
                candidate.get("kind") == "npc"
                and set(starter.get("ids", [])).intersection(candidate.get("ids", []))
                and candidate.get("panel") == starter.get("panel")
                for candidate in instructions(quest["steps"][str(v)]))), None)
            if (re.search(r"\bstart\b", action, re.I) and not BOUNDED.search(action)
                    and not re.search(r"\b(?:complete|finish|unlock|access|continue|collect|obtain|kill|wear)\b", action, re.I)
                    and (atomic or explicit_continuation)
                    and boundary is not None):
                merged["questDoneAt"] = boundary
                merged["questStartOnly"] = True
                merged.pop("questDoneAtPanel", None)
                merged.pop("questCompletes", None)
                stats["start"] += 1
    return stats

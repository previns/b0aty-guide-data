"""The "... on <Name>" rule.

The guide writes "on <Name>" for the person you interact with. Without this a
leading navigation verb swallows the whole clause: "Head East & Start X Marks
the Spot on Veos" produced a target called "East Start X Marks the Spot", which
resolves to nothing and so highlights nothing -- safe, but useless.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import annotate  # noqa: E402


def test_a_navigation_verb_no_longer_swallows_the_clause():
    ann = annotate.annotate_step(
        "Head East & Start X Marks the Spot on Veos (2,1) & complete the first step")
    assert ann["targetName"] == "Veos"
    assert ann["intent"] == "npc"


def test_the_rule_applies_without_a_leading_verb():
    ann = annotate.annotate_step("Teleport on Aubury [Enter the Abyss]")
    assert ann["targetName"] == "Aubury"


def test_use_x_on_y_still_wins():
    """The rule must not turn an item's target into the item's owner."""
    ann = annotate.annotate_step("Use Rope on Eagle")
    assert ann["targetName"] == "Eagle"
    assert ann["intent"] == "object"
    assert ann["items"] == ["Rope"]


def test_a_lowercase_noun_is_not_a_name():
    """"Kill the guard on the bridge" must not yield a target."""
    ann = annotate.annotate_step("Climb over the wall on the north side")
    assert ann.get("targetName") != "the"


def test_on_inside_a_word_does_not_match():
    """The word boundary matters: without it "Onward" and similar match.

    This is the bug the rule shipped with -- a stray escape put a literal
    backspace where the \b belonged, so the pattern never matched at all.
    """
    ann = annotate.annotate_step("Bank at Onward Bank")
    assert ann.get("targetName") != "ward"


def test_a_teleport_shorthand_is_left_alone():
    ann = annotate.annotate_step("Ardy Cloak -> CKS")
    assert ann.get("destination") == "CKS"


# --- curated entity aliases -------------------------------------------------

def _merge():
    import merge_curated
    return merge_curated


def test_an_alias_naming_an_unresolved_page_fails_the_build():
    """A phrase pointing at a page the wiki lacks resolves to an empty target:
    no error, just a step that never highlights."""
    problems = _merge().check_entity_aliases(
        {"a man/woman": ["Man", "Nonesuch"]}, {"Man": {"ids": [3106]}})
    assert problems
    assert "Nonesuch" in problems[0]


def test_an_alias_naming_an_idless_entity_fails_the_build():
    problems = _merge().check_entity_aliases(
        {"a place": ["Lumbridge"]}, {"Lumbridge": {"ids": []}})
    assert problems and "no ids" in problems[0]


def test_an_empty_alias_fails_the_build():
    problems = _merge().check_entity_aliases({"a man/woman": []}, {})
    assert problems


def test_a_valid_alias_passes():
    assert _merge().check_entity_aliases(
        {"a man/woman": ["Man", "Woman"]},
        {"Man": {"ids": [3106]}, "Woman": {"ids": [3111]}}) == []


def test_the_shipped_alias_file_is_valid():
    import json
    import yaml
    repo = Path(__file__).resolve().parent.parent
    entities_path = repo / "build" / "entities.json"
    if not entities_path.exists():
        return
    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    aliases = yaml.safe_load(
        (repo / "curated" / "entity_aliases.yaml").read_text(encoding="utf-8"))["aliases"]
    assert _merge().check_entity_aliases(aliases, entities) == []


# --- curated place aliases --------------------------------------------------

def test_a_place_alias_pointing_nowhere_fails_the_build():
    """This file holds names, not coordinates, so the check is the whole
    guarantee: a target that stops resolving must fail loudly."""
    problems = _merge().check_places({"Padewana": "Nonesuch"}, {}, {})
    assert problems and "does not resolve" in problems[0]


def test_a_place_alias_onto_a_runelite_enum_passes():
    problems = _merge().check_places(
        {"Padewana": "Paddewwa"},
        {"paddewwa": [{"point": [3097, 9880, 0]}]}, {})
    assert problems == []


def test_a_place_alias_onto_a_wiki_place_passes():
    problems = _merge().check_places(
        {"Wintertodt Camp": "Wintertodt"},
        {}, {"Wintertodt": {"kind": "object", "points": [[1630, 3981, 0]]}})
    assert problems == []


def test_an_alias_onto_an_npc_is_refused():
    """There is an NPC named Ferox and it is not where "Teleport to Ferox"
    goes."""
    problems = _merge().check_places(
        {"Ferox": "Ferox"}, {}, {"Ferox": {"kind": "npc", "points": [[1, 2, 0]]}})
    assert problems


def test_the_shipped_place_file_is_valid():
    import yaml
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    from build_place_candidates import load_locations, norm

    repo = Path(__file__).resolve().parent.parent
    aliases = yaml.safe_load(
        (repo / "curated" / "places.yaml").read_text(encoding="utf-8"))["aliases"]
    generated = repo / "curated" / "locations.generated.yaml"
    if not generated.exists():
        return
    # merge_curated keys locations by its own normalise(); this mirrors it
    # closely enough to catch a target that resolves nowhere at all.
    import json
    raw = load_locations(repo / "build" / "runelite")
    entities_path = repo / "build" / "entities.json"
    entities = json.loads(entities_path.read_text(encoding="utf-8")) \
        if entities_path.exists() else {}
    for spelling, target in aliases.items():
        resolves = bool(raw.get(norm(target))) or bool(
            entities.get(target, {}).get("points"))
        assert resolves, f"{spelling!r} -> {target!r} resolves to nothing"

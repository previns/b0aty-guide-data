"""Quest steps that follow Quest Helper, and the items it says to use.

Reported: "Complete Restless Ghost" kept the ghost highlighted for the whole
quest, and never rang the skull when it was time to put it back in the coffin;
Murder Mystery guided almost nothing correctly.
"""
import json
from pathlib import Path

import pytest

from pipeline.merge_curated import own_item_operands

ROOT = Path(__file__).resolve().parents[1]
GUIDE = json.loads((ROOT / "dist/guide.json").read_text(encoding="utf-8"))
STEPS = {step["id"]: step for section in GUIDE["sections"] for step in section["steps"]}


@pytest.mark.parametrize("step_id", [
    "79d4eff1dd",   # Complete Restless Ghost      -> the NPC called Restless ghost
    "0bba902149",   # Complete Children of the Sun  -> an NPC called Children
    "a228b3bf51",   # Start Shadow of the Storm     -> an item called Shadow
    "3d92fafbd3",   # Complete Shadow of the Storm
    "6f23dd7754",   # Continue Meat and Greet ...   -> an item called Meat
])
def test_a_target_taken_from_the_quests_own_title_is_dropped(step_id):
    """A target with ids outranks Quest Helper, so these were pinned to it."""
    step = STEPS[step_id]
    assert step.get("questStep") and step.get("questHelper")
    assert not (step.get("target") or {}).get("ids"), step["text"]


@pytest.mark.parametrize("step_id,name", [
    ("cabae447a5", "Romeo"),    # Talk to Romeo (3,1) [Romeo & Juliet]
    ("e1e8e66a45", "Juliet"),   # Talk to Juliet [Romeo & Juliet]
    ("e8649f6ed3", "Eadgar"),   # Return to Eadgar and continue ...
])
def test_a_real_target_inside_the_quests_name_is_kept(step_id, name):
    """Romeo is inside "Romeo & Juliet" and is exactly who to talk to."""
    assert STEPS[step_id]["target"]["name"] == name


SKULL = [{"name": "Ghost's skull", "ids": [553]}, {"name": "Ghostspeak amulet", "ids": [552]}]


def test_the_skull_rings_when_the_step_says_to_put_it_back():
    said = "Search the coffin to put the skull back and finish the quest."
    assert own_item_operands(said, SKULL) == [553]
    coffin = GUIDE["questHelpers"]["therestlessghost"]["steps"]["4"]["whenIn"]
    assert any(b.get("inventoryHighlightIds") == [553] for b in coffin)


@pytest.mark.parametrize("said", [
    "Use it on the coffin.",              # a pronoun names nothing
    "Talk to Father Aereck.",             # no verb of use
    "Use the rune essence on the altar.", # not one of this step's items
])
def test_nothing_rings_without_naming_one_of_the_steps_own_items(said):
    assert own_item_operands(said, SKULL) == []


def test_a_noun_that_fits_two_of_the_steps_items_rings_neither():
    """Ambiguity is unresolved, here as everywhere."""
    keys = [{"name": "Bronze key", "ids": [1]}, {"name": "Iron key", "ids": [2]}]
    assert own_item_operands("Use the key on the door.", keys) == []


def test_murder_mystery_carries_its_whole_investigation():
    """Nine branches turning on what has been found and who has been asked.

    The shipped guide had none of them, so it stayed on searching the window.
    """
    branches = GUIDE["questHelpers"]["murdermystery"]["steps"]["1"]["whenIn"]
    assert len(branches) == 9
    said = " ".join(b["text"] for b in branches)
    for clue in ("pungent pot", "criminal's dagger", "Gossip", "Poison Salesman",
                 "alibi", "guard"):
        assert clue in said, clue


def _nodes(value):
    """Every dict inside a helper's step tree, however it nests."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


@pytest.mark.parametrize("key", ["elementalworkshopi", "alfredgrimhandsbarcrawl"])
def test_a_helper_driven_from_one_root_step_is_read(key):
    """ComplexStateQuestHelper has no slot map, only loadStep(); these were empty."""
    helper = GUIDE["questHelpers"][key]
    assert helper["steps"]
    assert sum("text" in node for node in _nodes(helper["steps"])) >= 10


@pytest.mark.parametrize("step_id,key", [
    ("847c3c56ab", "recipefordisasterdwarf"),          # Complete Dwarf RFD
    ("3e6fad26d1", "recipefordisasterevildave"),       # Complete Evil Dave RFD until ...
    ("f5668b9684", "recipefordisasterlumbridgeguide"),  # Complete Lumbridge RFD until ...
    ("3789b90752", "elementalworkshopi"),              # Complete Elemental Workshop I
    ("5eff0a909f", "thepathofglouphrie"),              # Complete Path of Glouphrie (easy)
])
def test_steps_that_had_no_helper_now_follow_one(step_id, key):
    step = STEPS[step_id]
    assert step["questHelper"] == key and step.get("questStep")
    assert key in GUIDE["questHelpers"]


def test_path_of_glouphrie_reads_steps_reached_through_a_field():
    """Its slots name steps as `sectionA.step`; reading only bare names found none."""
    assert len(GUIDE["questHelpers"]["thepathofglouphrie"]["steps"]) >= 20

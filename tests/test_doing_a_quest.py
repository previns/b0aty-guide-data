"""Telling a step that does a quest from one that mentions one.

The route mentions quests constantly in passing -- "keep 3 Bronze Bars for
Tourist Trap" -- and only the steps that really are the quest may be ticked off
by the quest's progress moving. Pinned because getting it wrong in either
direction is silent: too strict and a step never completes, too loose and one
completes itself while the player is somewhere else.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import merge_curated as mc  # noqa: E402

def test_a_step_doing_a_quest_is_told_apart_from_one_mentioning_it():
    """Only the first may be ticked off by the quest's progress moving.

    The route mentions quests constantly in passing, and a step that merely
    refers to one must never complete itself because the quest happened to move
    while the player was reading it.
    """
    doing = mc.is_doing_the_quest
    assert doing("Head North East & continue Gertrude's Cat", "Gertrude's Cat")
    assert doing("Talk to Morgan and start Vampyre Slayer (1)", "Vampyre Slayer")
    assert doing("Head West to Port Sarim and talk to Veos to complete X Marks "
                 "The Spot.", "X Marks the Spot")

    assert not doing("Bank 7 Bronze Bars [keep 3 for Tourist Trap] & 10 Ropes",
                     "The Tourist Trap")
    assert not doing("Enter Varrock Sewer and take the North-West path to collect "
                     "the Demon Slayer key", "Demon Slayer")
    assert not doing("Head to the Grand Tree", "The Grand Tree")


def test_the_guides_own_spelling_of_a_quest_still_counts():
    """"Gertrudes Cat" for "Gertrude's Cat", "Knights Sword" for "The Knight's
    Sword". Squashing the punctuation out of both sides is still an exact
    comparison, in a narrower alphabet -- and a leading "The" the guide drops is
    the other half of it."""
    doing = mc.is_doing_the_quest
    assert doing("Talk to Shilop to continue Gertrudes Cat (2,2)", "Gertrude's Cat")
    assert doing("Complete Knights Sword", "The Knight's Sword")
    assert doing("Start Tourist Trap", "The Tourist Trap")


def test_a_verb_far_from_the_quest_name_does_not_count():
    """The verb has to be about the quest, not somewhere else in the sentence."""
    assert not mc.is_doing_the_quest(
        "Complete the agility course, then bank and head off towards the place "
        "you will later need for Dragon Slayer", "Dragon Slayer")

def test_a_quest_named_as_the_reason_is_not_the_step():
    """The guide's own habit, and it is everywhere early on.

    "Take 1 extra Rotten Apple [Mournings End Pt 1]" is collecting an apple a
    hundred banks before that quest. Reading the bracket as "you are doing
    Mourning's End" put that quest's first instruction on screen and offered to
    tick the step whenever its progress moved.
    """
    prep = mc.is_preparation
    assert prep("Take 1 extra Rotten Apple [Mournings End Pt 1]", 1)
    assert prep("Collect Cheese from Aggie [Witch's House]", 1)
    assert prep("Pick a Cabbage [Black Knight's Fortress]", 1)
    assert prep("Keep the Shrimps in your bank for later [Family Crest Quest]", 1)
    assert prep("Bank 7 Bronze Bars [keep 3 for Tourist Trap] & 10 Ropes", 1)


def test_naming_several_quests_at_once_is_always_a_reason():
    """Nobody is doing three quests at the same time."""
    assert mc.is_preparation(
        "Buy 2x Bronze Med Helm in Barbarian Village "
        "[Black Knights Fortress][Mournings End Pt II][Kings Ransom]", 3)


def test_doing_the_quest_is_still_doing_it():
    """The rule must not swallow the steps that really are the quest."""
    prep = mc.is_preparation
    assert not prep("Talk to Father Aereck (3,1) [Restless Ghost]", 1)
    assert not prep("Complete Rune Mysteries", 1)
    assert not prep("Head North East & continue Gertrude's Cat", 1)
    assert not prep("Kill a Chicken. Take Everything", 1)
    # Skilling can be the quest step itself, so it is not fetching.
    assert not prep("Cook Lava eel and bowl on range [Heroes Quest]", 1)
    assert not prep("Pickpocket Constantinius in the main house", 1)

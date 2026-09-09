"""Where the guide is finer-grained than the quest it is running.

A quest's progress value moves a handful of times; the guide describes a dozen
actions between two of those moves. Sheep Herder is the extreme case -- its
VarPlayer goes 0, 1, 2 and stops, and prodding four sheep and burning four sets
of bones all happen at 2 -- and it broke the boundary rules in both directions
at once.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import annotate as a  # noqa: E402

GUIDE = json.loads((Path(__file__).resolve().parent.parent / "dist" / "guide.json")
                   .read_text(encoding="utf-8"))


def step_named(prefix: str) -> dict:
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            if step["text"].startswith(prefix):
                return step
    raise AssertionError(f"no step starts with {prefix!r}")


class TestSheepHerder:
    """Both halves of the reported bug, pinned against the shipped file."""

    def test_starting_it_runs_until_the_quest_leaves_the_church(self):
        """Progress 1 is "talk to Doctor Orbon", in the same church.

        The boundary used to be unset because the step after this one names
        nothing placeable, so the step ticked the moment progress moved to 1 --
        and Quest Helper's instruction for 1 was never shown to anyone.
        """
        start = step_named("Head North to the church then start Sheep Herder")
        assert start["questDoneAt"] == 2

    def test_the_step_that_burns_the_bones_is_not_ticked_by_progress(self):
        """Its boundary is already met when it opens, which decides nothing.

        The data cannot help here -- burning bones is not something the quest's
        progress value mentions -- so the plugin has to notice that the boundary
        was already passed. This pins the value the plugin reasons about.
        """
        burn = step_named("Continue Sheep Herder until all 4 Sheep bones are burnt")
        start = step_named("Head North to the church then start Sheep Herder")
        assert start["questDoneAt"] == 2
        assert "questDoneAt" not in burn
        assert burn["questStopCondition"] == {"all": [
            {"var": {"kind": "varbit", "id": i, "value": 6}}
            for i in [2233, 2234, 2232, 2231]]}

    def test_the_quest_has_nowhere_further_to_go(self):
        helper = GUIDE["questHelpers"]["sheepherder"]
        assert helper["lastValue"] == 2
        assert sorted(int(v) for v in helper["steps"]) == [0, 1, 2]


class TestABagful:
    """"Full Inventory of Balls of wool" is wool, and a shop can ring it."""

    def test_the_idiom_is_not_part_of_the_name(self):
        assert a.RE_A_BAGFUL.sub("", "Full Inventory of Balls of wool") == "Balls of wool"
        assert a.RE_A_BAGFUL.sub("", "an inventory of Balls of Wool") == "Balls of Wool"
        assert a.RE_A_BAGFUL.sub("", "2 Inventories of Willows logs") == "Willows logs"
        assert a.RE_A_BAGFUL.sub("", "Balls of Wool") == "Balls of Wool"

    def test_the_wool_steps_resolve_and_offer_a_shopkeeper(self):
        for prefix in ("Buy Full Inventory of Balls of wool",
                       "Buy an inventory of Balls of Wool"):
            step = step_named(prefix)
            assert step["items"][0]["ids"], prefix
            assert step["items"][0]["name"].lower().startswith("balls of wool"), prefix
            assert step["sellers"], "nobody to point at in the general store"
            assert any(s["name"] == "Aemad" for s in step["sellers"])


class TestWhereItIsIsNotWhatItIs:
    def test_a_place_clause_is_trimmed_from_an_item_name(self):
        for text, want in (("Rat Poison beneath Clock Tower", "Rat Poison"),
                           ("Balls of wool when passing the general store", "Balls of wool"),
                           ("Clay at varrock west mine", "Clay"),
                           ("Oak Logs", "Oak Logs")):
            assert a.RE_TRAILING_GATHER.sub("", text).strip() == want

    def test_the_rat_poison_step_resolves(self):
        step = step_named("Collect Rat Poison beneath Clock Tower")
        assert step["items"][0]["name"] == "Rat Poison"
        assert step["items"][0]["ids"]


def test_a_target_carries_its_name_as_well_as_its_ids():
    """An npc that transforms reports an id the build never saw.

    Probita's id resolves and is right, and she still went unmarked. Quest
    Helper carries an npcName beside every id for this reason; two targets in
    the whole file used to carry one.
    """
    named = [s for sec in GUIDE["sections"] for s in sec["steps"]
             if (s.get("target") or {}).get("names")]
    assert len(named) > 500, f"only {len(named)} targets can be matched by name"
    probita = step_named("Check Probita for Pets")
    assert probita["target"]["names"] == ["Probita"]

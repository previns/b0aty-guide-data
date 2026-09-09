"""What counts as being inside a quest the guide is part-way through.

A session log for The Tourist Trap showed seven minutes with nothing on screen:
the guide said "Start Tourist Trap", then two steps that are done during the
quest, then "Complete Tourist Trap", and only the first and last carried the
quest. Quest Helper, open beside it, guided the whole stretch.

The fix is bounded by what it must NOT do. X Marks the Spot is also started and
completed inside one bank, but in numbered pieces with a trip to Draynor and an
agility lap between them, and treating those gaps as inside the quest put five
unrelated errands under it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import merge_curated as mc  # noqa: E402


def section(*steps: dict) -> dict:
    """One bank, each step given as the fields this pass reads."""
    return {"steps": [{"raw": raw, "merged": rest} for raw, rest in
                      ((s.pop("raw"), s) for s in steps)]}


def doing(raw: str, quest: str) -> dict:
    return {"raw": raw, "questStep": True, "questHelper": quest}


def plain(raw: str, **rest) -> dict:
    return {"raw": raw, **rest}


def test_a_step_between_starting_and_finishing_is_inside_the_quest():
    doc = {"sections": [section(
        doing("Start Tourist Trap", "thetouristtrap"),
        plain("Take his bones [Demon Slayer]", questHelper="demonslayer"),
        doing("Complete Tourist Trap", "thetouristtrap"),
    )]}
    assert mc.carry_quest_across_its_span(doc) == 1
    bones = doc["sections"][0]["steps"][1]["merged"]
    # The bracket says what the bones are for, a hundred banks later. Where the
    # player is, is Tourist Trap.
    assert bones["questContext"] == "thetouristtrap"
    assert not bones.get("questStep")
    assert bones["questHelper"] == "demonslayer"


def test_a_quest_done_in_numbered_pieces_is_not_one_span():
    """The guide leaves X Marks the Spot and comes back to it."""
    doc = {"sections": [section(
        doing("Complete 3rd Step of X Marks the Spot", "xmarksthespot"),
        plain("Go up the stairs and collect 4x Garlic from the cupboard"),
        plain("Train Draynor Agility to 5 Agility [Lumbridge Easy Diary]"),
        doing("Complete 4th Step of X Marks the Spot", "xmarksthespot"),
    )]}
    assert mc.carry_quest_across_its_span(doc) == 0
    assert all(s["merged"].get("questContext") is None
               for s in doc["sections"][0]["steps"])


def test_advice_inside_a_span_still_guides_nowhere():
    """It has nothing to point at, and an audit rule says so."""
    doc = {"sections": [section(
        doing("Start Tourist Trap", "thetouristtrap"),
        plain("You need to safespot the Mercenary Captain.", advice=True),
        doing("Complete Tourist Trap", "thetouristtrap"),
    )]}
    assert mc.carry_quest_across_its_span(doc) == 0


def test_a_step_doing_its_own_quest_is_left_alone():
    doc = {"sections": [section(
        doing("Start Hazeel Cult", "hazeelcult"),
        doing("Talk to Morgan and start Vampyre Slayer", "vampyreslayer"),
        doing("Complete Hazeel Cult", "hazeelcult"),
    )]}
    assert mc.carry_quest_across_its_span(doc) == 0


def test_the_span_stops_at_the_end_of_the_bank():
    """A quest the guide returns to twenty banks later is not one stretch."""
    doc = {"sections": [
        section(doing("Start Tourist Trap", "thetouristtrap"),
                plain("Bank at Shantay pass and deposit all")),
        section(plain("Buy 3x Buckets of Water"),
                doing("Complete Tourist Trap", "thetouristtrap")),
    ]}
    assert mc.carry_quest_across_its_span(doc) == 0


def test_the_real_guide_only_carries_inside_eleven_spans():
    """The shipped file, so a rule that quietly widens is caught here."""
    import json
    guide = json.loads((Path(__file__).resolve().parent.parent
                        / "dist" / "guide.json").read_text(encoding="utf-8"))
    carried = [(sec, st) for sec in guide["sections"] for st in sec["steps"]
               if st.get("questContext")]
    assert 40 <= len(carried) <= 80, len(carried)
    for sec, step in carried:
        assert not step.get("advice"), step["text"]
        quest = step["questContext"]
        doing_it = [s for s in sec["steps"]
                    if s.get("questStep") and s.get("questHelper") == quest]
        nested = step.get("depth", 1) > 1
        assert nested or (len(doing_it) >= 2
                          and doing_it[0]["ordinal"] < step["ordinal"]
                          < doing_it[-1]["ordinal"]), step["text"]

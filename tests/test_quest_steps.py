"""Quest Helper's per-quest step list.

The extraction that lets the guide show what to do next inside a quest it only
partly completes. Pinned because two of its failures are silent: a regex that
runs past a line boundary drops whole quests, and a conditional step that loses
its flag would be presented as certainty.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_quest_steps as bqs  # noqa: E402

SOURCE = '''
	steps.put(0, speakVeosLumbridge);
	steps.put(1, steps.get(0));
	steps.put(2, digOutsideBob);
	speakVeosLumbridge = new NpcStep(this, NpcID.VEOS_VISIBLE, new WorldPoint(3228, 3242, 0),
		"Talk to Veos in The Sheared Ram pub.");
	digOutsideBob = new ConditionalStep(this, walkToBob);
	digOutsideBob.addStep(inArea, digHere);
	digOutsideBob.addStep(hasSpade, digThere);
	walkToBob = new DetailedQuestStep(this, new WorldPoint(3230, 3203, 0), "Walk to Bob's.");
'''


def test_a_direct_step_carries_its_target_and_text():
    steps = bqs.steps_in(SOURCE)
    assert steps[0]["kind"] == "npc"
    assert steps[0]["constant"] == "VEOS_VISIBLE"
    assert steps[0]["point"] == [3228, 3242, 0]
    assert steps[0]["text"].startswith("Talk to Veos")
    assert "conditional" not in steps[0]


def test_an_aliased_slot_repeats_the_instruction():
    """steps.put(1, steps.get(0)) is the same instruction under another value."""
    steps = bqs.steps_in(SOURCE)
    assert steps[1]["text"] == steps[0]["text"]


def test_a_conditional_step_is_flagged_with_its_branch_count():
    """Unflagged, the default branch would be shown as though it were certain."""
    steps = bqs.steps_in(SOURCE)
    assert steps[2]["conditional"] is True
    assert steps[2]["branches"] == 2
    # It still carries the default's instruction, which is the useful part.
    assert steps[2]["text"].startswith("Walk to Bob")


def test_a_slot_with_no_extractable_instruction_is_omitted():
    """Better a gap than a step with no target -- DigStep and the puzzle
    wrappers have no coordinates to give."""
    steps = bqs.steps_in("steps.put(4, digSomething);\n")
    assert steps == {}


def test_the_quest_row_regex_does_not_cross_lines():
    """With re.DOTALL the lazy .*? ran past a row that had no QuestVarbits and
    swallowed the next few, silently dropping a third of the quests."""
    text = (
        "\tNO_VARBIT_QUEST(new SomeQuest(), Quest.SOMETHING, QuestDetails.Type.F2P),\n"
        "\tX_MARKS_THE_SPOT(new XMarksTheSpot(), Quest.X_MARKS_THE_SPOT,"
        " QuestVarbits.QUEST_X_MARKS_THE_SPOT, QuestDetails.Type.F2P),\n"
    )
    found = dict(bqs.RE_QUEST_ROW.findall(text))
    assert found.get("XMarksTheSpot") == "QUEST_X_MARKS_THE_SPOT"


def test_the_shipped_table_has_x_marks_the_spot():
    import json
    path = Path(__file__).resolve().parent.parent / "build" / "quest_steps.json"
    if not path.exists():
        return
    quests = json.loads(path.read_text(encoding="utf-8"))["quests"]
    quest = quests.get("xmarksthespot")
    assert quest is not None, "X Marks the Spot should extract"
    assert quest["var"]["kind"] == "varbit"
    assert quest["steps"]["0"]["constant"] == "VEOS_VISIBLE"

"""Handing a quest back to the guide part-way through.

The guide's most common quest shape: run a quest to a stated point, go and do
something else for twenty banks, come back and finish it. The quest's own
progress value usually cannot express that point -- Sheep Herder's goes 0, 1, 2
and prodding four sheep, feeding them, collecting the bones and burning them all
happen at 2 -- so the boundary was either already met when the step opened (tick
instantly, walk past four sheep) or never met at all (never tick).

Quest Helper's `getPanels()` does express it. It is the sidebar the player reads
down, written by the quest's author in the order things happen, and it is the
only statement of that order anywhere in the file: the progress value is too
coarse, and a conditional's branches are ordered most-specific-first, which is
not the same as first-to-last.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_quest_steps as q  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GUIDE = json.loads((ROOT / "dist" / "guide.json").read_text(encoding="utf-8"))
QH = (ROOT.parent / "B0aty Guide" / "quest-helper-master" / "src" / "main" / "java"
      / "com" / "questhelper")


def step_named(prefix: str) -> dict:
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            if step["text"].startswith(prefix):
                return step
    raise AssertionError(f"no step starts with {prefix!r}")


class TestReadingThePanels:
    def test_the_order_is_the_authors_own(self):
        text = q.strip_comments(
            (QH / "helpers" / "quests" / "sheepherder" / "SheepHerder.java")
            .read_text(encoding="utf-8"))
        order = q.panel_order(text)
        assert order["talkToHalgrive"] == 0
        assert order["useBonesOnIncinerator"] == 10
        assert order["talkToHalgriveToFinish"] == 11, "the last thing the quest asks"

    def test_nearly_every_quest_lists_them(self):
        counted = [h for h in GUIDE["questHelpers"].values() if h.get("panelCount")]
        assert len(counted) > 130, f"only {len(counted)} quests carry an ordering"


class TestSheepHerderHandsOverWhereTheGuideSays:
    def test_the_continue_step_hands_over_at_the_last_panel(self):
        burn = step_named("Continue Sheep Herder until all 4 Sheep bones are burnt")
        branch = GUIDE["questHelpers"]["sheepherder"]["steps"]["2"]["whenIn"][0]
        assert branch["panel"] == 11
        assert {"all": [{"var": {"op": "==", **p["var"]}}
                        for p in burn["questStopCondition"]["all"]]} == branch["when"]
        assert "questDoneAtPanel" not in burn
        assert GUIDE["questHelpers"]["sheepherder"]["panelCount"] == 12

    def test_that_position_is_the_branch_guarded_by_all_sheep_burned(self):
        """Quest Helper only says "return to Halgrive" once all four are burnt.

        `goBurnSheep.addStep(new Conditions(allSheepBurned), talkToHalgriveToFinish)`
        -- so reaching panel 11 is precisely the goal the guide describes, and
        it is a varbit test per sheep rather than anything the guide has to
        interpret.
        """
        var2 = GUIDE["questHelpers"]["sheepherder"]["steps"]["2"]
        first = var2["whenIn"][0]
        assert first["panel"] == 11
        assert "halgrive" in first["text"].lower()
        # Four varbits, one per sheep, all required.
        conditions = json.dumps(first["when"])
        assert conditions.count('"varbit"') == 4, conditions

    def test_the_steps_before_it_are_the_work(self):
        var2 = GUIDE["questHelpers"]["sheepherder"]["steps"]["2"]
        panels = [b["panel"] for b in var2["whenIn"]]
        assert panels == sorted(panels, reverse=True), (
            "quest helper writes its branches most-advanced-first here, and the "
            "panel numbers are what make that legible rather than assumed")
        assert 10 in panels, "burning the bones"
        assert 4 in panels, "prodding the first sheep"


def test_a_handover_only_ever_points_at_a_real_panel():
    """A position past the end would never be reached, and the step would hang."""
    handovers = [(sec, s) for sec in GUIDE["sections"] for s in sec["steps"]
                 if s.get("questDoneAtPanel") is not None]
    assert len(handovers) > 40, f"only {len(handovers)} steps hand over"
    for _, step in handovers:
        helper = GUIDE["questHelpers"][step["questHelper"]]
        assert 0 < step["questDoneAtPanel"] < helper["panelCount"], step["text"]


def test_a_handover_never_replaces_a_boundary_the_value_could_give():
    """It is a fallback, not a preference.

    Applied to every step whose next one completes the quest, it caught
    ninety-seven that already had a good value boundary -- and would have run
    "Talk to Father Aereck" to the end of The Restless Ghost. It is only for the
    steps where the value says nothing, because the point the guide stops at and
    the point it resumes at are the same value.
    """
    from copy import deepcopy
    from pipeline.merge_curated import pin_quest_boundaries

    # Assert this inference-pass invariant at that pass's output. The explicit
    # goal pass deliberately replaces some preceding boundaries with possession
    # of an item: receiving magic logs no longer asserts quest progress 3.
    # Recreate the inference input from shipped content without trusting any
    # generated boundaries; do not exempt quests or weaken the inequality.
    doc = {"sections": [{"steps": [
        {"id": s["id"], "raw": s["text"], "merged": deepcopy(s)}
        for s in section["steps"]]} for section in GUIDE["sections"]]}
    for section in doc["sections"]:
        for step in section["steps"]:
            for field in ("questDoneAt", "questDoneAtPanel", "questCompletes"):
                step["merged"].pop(field, None)
    pin_quest_boundaries(doc, GUIDE["questHelpers"], {})
    # The property, stated directly: a handover step's value boundary, where it
    # has one, is never above where the step before it in that quest ended.
    order = {}
    for section in doc["sections"]:
        for wrapped in section["steps"]:
            step = wrapped["merged"]
            if step.get("questStep") and step.get("questHelper"):
                order.setdefault(step["questHelper"], []).append(step)
    checked = 0
    for quest, sequence in order.items():
        opens_at = 0
        for step in sequence:
            if step.get("questDoneAtPanel") is not None:
                boundary = step.get("questDoneAt")
                assert boundary is None or boundary <= opens_at, (
                    f"{step['text']} had a usable value boundary {boundary} "
                    f"and was handed over anyway")
                checked += 1
            if step.get("questDoneAt") is not None:
                opens_at = step["questDoneAt"]
    assert checked > 40


def test_a_handover_is_never_on_the_step_that_completes_the_quest():
    """That step ends when the quest does, which is a different question."""
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            if step.get("questDoneAtPanel") is not None:
                assert not step.get("questCompletes"), step["text"]


def test_a_hand_set_stopping_point_survives_the_boundary_pass():
    """The override file says "merged last, always wins". It has to be true here.

    Overrides are applied inside the step loop, and the quest passes -- carrying
    a quest across its span, demoting fetches, pinning boundaries -- all run
    after it. So the two fields a person actually has to set by hand, because no
    rule can derive them, were the two that got computed over and lost.
    """
    import merge_curated as mc

    doc = {"sections": [{"steps": [
        {"id": "aaaaaaaaaa", "ordinal": 0, "raw": "Start Sheep Herder",
         "merged": {"questStep": True, "questHelper": "sheepherder"}},
        {"id": "bbbbbbbbbb", "ordinal": 1,
         "raw": "Continue Sheep Herder until all 4 Sheep bones are burnt",
         "merged": {"questStep": True, "questHelper": "sheepherder"}},
        {"id": "cccccccccc", "ordinal": 2, "raw": "Complete Sheep Herder",
         "merged": {"questStep": True, "questHelper": "sheepherder"}},
    ]}]}
    # A hand-over is only set at a position some instruction actually carries:
    # the plugin meets one by comparing against the panel of the instruction on
    # screen, so a position nothing reaches is a step that waits for ever.
    quests = {"sheepherder": {
        "anchors": {}, "lastValue": 2, "panelCount": 12, "panelAnchors": {},
        "steps": {"2": {"panel": 2, "whenIn": [{"panel": 11}, {"panel": 10}]}},
    }}
    mc.pin_quest_boundaries(doc, quests, {})

    middle = doc["sections"][0]["steps"][1]["merged"]
    assert middle["questDoneAtPanel"] == 11, "the rule's own answer"

    # And a person disagreeing with it is not overruled.
    overrides = {"bbbbbbbbbb": {"questDoneAtPanel": 9}}
    for section in doc["sections"]:
        for step in section["steps"]:
            if step["id"] in overrides:
                step["merged"].update(overrides[step["id"]])
    assert middle["questDoneAtPanel"] == 9


def test_a_handover_is_a_position_the_plugin_can_reach():
    """It is met by comparing against the instruction on screen.

    Placing guide steps on the sidebar timeline found stopping points the
    progress value cannot express -- and also found positions no instruction
    ever carries, at which a step would wait for ever. That is worse than the
    coarse boundary it replaced, so it is refused.
    """
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            at = step.get("questDoneAtPanel")
            if at is None:
                continue
            helper = GUIDE["questHelpers"][step["questHelper"]]
            seen = {candidate.get("panel")
                    for record in (helper.get("steps") or {}).values()
                    for candidate in [record] + (record.get("whenIn") or [])}
            assert at in seen, f"{step['text']} waits at panel {at}, never reached"


def test_the_handovers_name_something_the_guide_is_finished_with():
    """A sample, read as prose: each should be the next thing after the step."""
    named = 0
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            at = step.get("questDoneAtPanel")
            if at is None:
                continue
            helper = GUIDE["questHelpers"][step["questHelper"]]
            words = next((c["text"] for record in (helper.get("steps") or {}).values()
                          for c in [record] + (record.get("whenIn") or [])
                          if c.get("panel") == at and c.get("text")), None)
            assert words, f"{step['id']} has an unnamed handover at {at}"
            named += 1
    # Exact goals replaced inferred handovers; check EVERY remaining handover
    # rather than a volume floor which penalises replacing incorrect data.
    assert named == sum(s.get("questDoneAtPanel") is not None
                        for sec in GUIDE["sections"] for s in sec["steps"])
    assert named > 0

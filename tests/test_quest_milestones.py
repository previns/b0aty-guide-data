"""Quest guidance follows explicit guide milestones, not a later return visit."""
import json
from pathlib import Path

import pytest

from pipeline.quest_milestones import (
    attach_continuations, pin_explicit_milestones, resolve_stop_items)


def step(text, **merged):
    return {"id": "example", "raw": text, "depth": 1, "merged": merged}


def document(*steps):
    return {"sections": [{"steps": list(steps)}]}


def test_only_an_immediate_sibling_continuation_inherits_the_quest():
    start = step("Start Example", questHelper="example", questStep=True)
    continuation = step("Continue until you receive the Book")
    travel = step("Head south to the town")
    doc = document(start, continuation, travel)
    assert attach_continuations(doc) == 1
    assert continuation["merged"] == {"questHelper": "example", "questStep": True}
    assert travel["merged"] == {}


@pytest.mark.parametrize("barrier", ["depth", "advice", "other_quest", "not_quest", "section", "intervening"])
def test_continuation_does_not_guess_across_context_boundaries(barrier):
    start = step("Start Example", questHelper="example", questStep=True)
    continuation = step("Continue until you receive the Book")
    doc = document(start, continuation)
    if barrier == "depth":
        continuation["depth"] = 2
    elif barrier == "advice":
        continuation["merged"]["advice"] = True
    elif barrier == "other_quest":
        continuation["merged"]["questHelper"] = "different"
    elif barrier == "not_quest":
        start["merged"]["questStep"] = False
    elif barrier == "section":
        doc = {"sections": [{"steps": [start]}, {"steps": [continuation]}]}
    else:
        doc = document(start, step("Head south"), continuation)
    assert attach_continuations(doc) == 0


def test_named_items_use_authoritative_ids_quantities_and_all_goals():
    quest = {"items": [{"name": "Captain's book", "ids": [0, 2]},
                       {"name": "Key", "id": 3}]}
    assert resolve_stop_items("2x Captain’s book and the Key.", quest) == [
        {"name": "Captain's book", "count": 2, "ids": [0, 2]},
        {"name": "Key", "count": 1, "ids": [3]}]


@pytest.mark.parametrize("phrase", ["Perfect gold", "samples", "0x Perfect gold ore", "Perfect gold ore and Missing"])
def test_unknown_or_partial_item_goals_are_not_guessed(phrase):
    assert resolve_stop_items(phrase, {"items": [{"name": "Perfect gold ore", "id": 1}]}) is None


def test_same_name_different_ids_and_overlapping_goals_are_ambiguous():
    quest = {"items": [{"name": "Book", "id": 1}, {"name": "Book", "id": 2}]}
    assert resolve_stop_items("Book", quest) is None
    quest = {"items": [{"name": "Book", "ids": [1, 2]}, {"name": "Key", "id": 2}]}
    assert resolve_stop_items("Book and Key", quest) is None


def test_atomic_start_and_item_stop_override_later_visit_boundaries():
    quest = {"items": [{"name": "Book", "id": 10}],
             "steps": {"0": {"kind": "npc", "ids": [7]}, "5": {}, "10": {}}}
    start = step("Start Example by talking to Someone", questHelper="example", questStep=True,
                 target={"ids": [7]}, questDoneAt=10, questDoneAtPanel=20)
    goal = step("Continue until you receive the Book", questHelper="example", questStep=True,
                questCompletes=True, questDoneAt=10)
    stats = pin_explicit_milestones(document(start, goal), {"example": quest}, {})
    assert stats == {"start": 1, "items": 1, "unresolved": []}
    assert start["merged"]["questDoneAt"] == 5
    assert start["merged"]["questStartOnly"] is True
    assert "questDoneAtPanel" not in start["merged"]
    assert goal["merged"]["questFollow"] is True
    assert "questCompletes" not in goal["merged"]
    assert "questDoneAt" not in goal["merged"]


def test_unresolved_stop_suppresses_coarse_progress_and_reports_for_review():
    goal = step("Start Example until you get the samples", questHelper="example", questStep=True,
                questDoneAt=2)
    stats = pin_explicit_milestones(document(goal), {"example": {"steps": {"0": {}, "2": {}}}}, {})
    assert len(stats["unresolved"]) == 1
    assert goal["merged"]["questStopUnresolved"] is True
    assert "questDoneAt" not in goal["merged"]
    assert "questStartOnly" not in goal["merged"]


def test_specific_item_errand_keeps_its_own_target():
    goal = step("Pickpocket Someone until you get the Book", questHelper="example", questStep=True)
    pin_explicit_milestones(document(goal), {"example": {"items": [{"name": "Book", "id": 10}]}}, {})
    assert goal["merged"]["questStopItems"][0]["ids"] == [10]
    assert not goal["merged"].get("questFollow")


def test_all_shipped_item_goals_are_exact_quest_helper_items():
    guide = json.loads((Path(__file__).resolve().parents[1] / "dist/guide.json")
                       .read_text(encoding="utf-8"))
    count = 0
    for section in guide["sections"]:
        for current in section["steps"]:
            goals = current.get("questStopItems", [])
            if not goals:
                continue
            assert current["questStep"] is True
            assert not any(current.get(field) for field in (
                "questCompletes", "questStopUnresolved", "questStartOnly"))
            assert "questDoneAt" not in current and "questDoneAtPanel" not in current
            quest = guide["questHelpers"][current["questHelper"]]
            for item in goals:
                if current["id"] == "b370a04ca1":
                    # Approved QH addAlternates; the two forms have different
                    # names, so this is deliberately NOT fuzzy name resolution.
                    assert item == {"name": "Karambwan Vessel", "count": 2, "ids": [3157, 3159]}
                    assert {3157, 3159} <= {i["id"] for i in quest["items"]}
                elif current["id"] == "ec108fdc26" and item["name"] == "Crab meat":
                    # Collecting meat underwater must not count the noted form
                    # which QH accepts for its more general shopping list.
                    assert item == {"name": "Crab meat", "count": 3, "ids": [7518]}
                    assert 7518 in {i["id"] for i in quest["items"]}
                else:
                    assert resolve_stop_items(f"{item['count']}x {item['name']}", quest) == [item]
            count += 1
    # 17 since the author resolved Prince Ali Rescue to the Key print, 2026-09-08.
    assert count == 17


def test_author_confirmed_family_crest_means_two_ores_not_bars():
    goal = shipped_steps()["d5a2d20554"]
    assert goal["questStopItems"] == [{"name": "'perfect' gold ore", "count": 2, "ids": [446]}]
    assert not goal.get("questStopUnresolved")


def test_tagged_supplies_before_a_start_are_preparation():
    from pipeline.quest_milestones import demote_before_starts
    supply = step("Decant a potion [Example]", questHelper="example", questStep=True)
    start = step("Talk to Someone and start Example", questHelper="example", questStep=True,
                 target={"ids": [7]})
    quest = {"steps": {"0": {"kind": "npc", "ids": [7]}}}
    assert demote_before_starts(document(supply, start), {"example": quest}, {}) == 1
    assert not supply["merged"]["questStep"]
    assert start["merged"]["questStep"]


def test_starter_can_be_behind_a_zone_branch_and_repeated_positive_values():
    initial = {"kind": "object", "ids": [6], "whenIn": [
        {"kind": "npc", "ids": [7], "panel": 0}]}
    quest = {"steps": {"0": initial, "1": initial, "2": {"kind": "npc", "ids": [8], "panel": 1}}}
    start = step("Talk to Someone and start Example", questHelper="example", questStep=True,
                 target={"ids": [7]}, questDoneAt=90)
    pin_explicit_milestones(document(start), {"example": quest}, {})
    assert start["merged"]["questDoneAt"] == 2


def test_exact_spoken_name_works_when_guide_target_is_a_town():
    quest = {"steps": {"0": {"kind": "npc", "ids": [7], "text": "Talk to Someone in the castle."}, "3": {}}}
    start = step("Start Example by talking to Someone (1)", questHelper="example", questStep=True)
    pin_explicit_milestones(document(start), {"example": quest}, {})
    assert start["merged"]["questDoneAt"] == 3


def test_partial_goal_is_not_completion_of_the_whole_quest():
    goal = step("Continue Example to unlock transport, then complete these diary steps:",
                questHelper="example", questStep=True, questCompletes=True)
    pin_explicit_milestones(document(goal), {"example": {"steps": {"0": {}, "10": {}}}}, {})
    assert "questCompletes" not in goal["merged"]
    assert goal["merged"]["questStopUnresolved"] is True


@pytest.mark.parametrize("text", [
    "Head East and thieve until 12345 Thieving Experience. Bank fruit [Example]",
    "Kill Men/Women until 3x Herbs [Example]",
    "Make Swords until 12345 Smithing XP. This is finished on Example quest.",
    "Train on Monsters until 60 Attack (Complete Example later)",
    "Camp Boss until loot [Example]",
])
def test_training_and_drop_goals_are_not_quest_progress(text):
    from pipeline.merge_curated import is_preparation
    assert is_preparation(text, 1)


def test_quest_combat_and_quest_crafting_remain_quest_actions():
    from pipeline.merge_curated import is_preparation
    assert not is_preparation("Kill Elvarg and complete Dragon Slayer", 1)
    assert not is_preparation("Make the barrel of naphtha [Mournings End Pt 1]", 1)


def shipped_steps():
    guide = json.loads((Path(__file__).resolve().parents[1] / "dist/guide.json")
                       .read_text(encoding="utf-8"))
    return {step["id"]: step for section in guide["sections"] for step in section["steps"]}


def test_almera_finishes_when_waterfall_starts_not_when_it_nearly_ends():
    step = shipped_steps()["8be8ecc23d"]
    assert step["questDoneAt"] == 1
    assert step["questStartOnly"] is True


def test_waterfall_continuation_has_quest_and_book_milestone():
    steps = shipped_steps()
    continuation = steps["e8775abbc3"]
    assert continuation.get("questHelper") == "waterfallquest"
    assert continuation.get("questStep") is True
    assert continuation["questStopItems"] == [
        {"name": "Book on baxtorian", "count": 1, "ids": [292]}]
    assert not continuation.get("questCompletes")
    assert "questDoneAt" not in continuation
    assert "questHelper" not in steps["9bda8142a2"]

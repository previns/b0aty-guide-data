"""Source-reviewed stopping points; never derive expectations from overrides."""
import json
import re
from pathlib import Path

import pytest

from pipeline.audit import milestone_condition_ok

ROOT = Path(__file__).resolve().parents[1]
GUIDE = json.loads((ROOT / "dist/guide.json").read_text(encoding="utf-8"))
STEPS = {s["id"]: s for section in GUIDE["sections"] for s in section["steps"]}


@pytest.mark.parametrize("step_id,value", [
    ("fe0dcd380a", 9), ("7563452209", 3), ("6a8042b855", 100),
    ("9eb23a8187", 14), ("08c9e5d5ae", 40), ("a9c99f5511", 5),
    ("bd3b66eb6f", 6), ("08975f4fbc", 70), ("5e2d42a7f6", 5),
    ("b64f6b40fe", 6), ("641bdf1360", 14), ("10da9f91b7", 7),
    ("91f094509d", 12), ("8f0f335851", 90), ("0e33bfd18f", 105),
    ("531b99b2ef", 230), ("824b6700a0", 60), ("b4fe127214", 85),
    ("7a7aa487b1", 11), ("2ea2b97ff4", 4), ("6f23dd7754", 6),
    ("596c86aa38", 9), ("508ae8e785", 29), ("c99b2bc33a", 45),
    ("e8649f6ed3", 60), ("c7e46066de", 32),
])
def test_reviewed_threshold_survives_inference_and_matches_source_state(step_id, value):
    step = STEPS[step_id]
    helper = GUIDE["questHelpers"][step["questHelper"]]
    assert step["questStopValue"] == value
    assert str(value) in helper["steps"]
    assert step["questFollow"] is True
    assert not any(k in step for k in (
        "questDoneAt", "questDoneAtPanel", "questCompletes", "questStopUnresolved"))


def test_every_bounded_quest_goal_requires_direct_evidence_or_manual_completion():
    for step in STEPS.values():
        if not step.get("questStep") or not re.search(r"\b(?:until|up to|to unlock|to access|by obtaining)\b", step["text"], re.I):
            continue
        assert sum(bool(step.get(k)) for k in (
            "questStopValue", "questStopCondition", "questStopItems", "questStopUnresolved")) == 1, step
        assert not any(k in step for k in ("questDoneAt", "questDoneAtPanel", "questCompletes")), step


def test_all_newly_attached_helpers_are_bundled_and_goals_are_effective():
    for step_id, key in {
        "ec108fdc26": "recipefordisasterpiratepete", "e8649f6ed3": "eadgarsruse",
        "bc08effca5": "contact", "b1609b5b66": "ethicallyacquiredantiquities",
        "c7e46066de": "ethicallyacquiredantiquities",
    }.items():
        step = STEPS[step_id]
        assert step["questHelper"] == key
        assert key in GUIDE["questHelpers"]
        assert step["questStep"] and step["questFollow"]
        assert step.get("questStopItems") or step.get("questStopValue")


def test_unproven_goals_stay_manual_without_later_visit_fallback():
    # Four, not five: the author resolved Prince Ali Rescue (f769b86e2b) to the
    # Key print on 2026-09-08. Its varplayer cannot separate the middle of that
    # quest, so it is an item goal; see curated/overrides.yaml for the evidence.
    assert {s["id"] for s in STEPS.values() if s.get("questStopUnresolved")} == {
        "d19c49ef79", "2958f3ab85", "2d909c6747", "78e673faa3"}


@pytest.mark.parametrize("condition", [
    {}, {"all": []}, {"not": {}}, {"open": 12},
    {"var": {"kind": "guess", "id": 1, "value": 1}},
    {"var": {"kind": "varbit", "value": 1}},
    {"var": {"kind": "varbit", "id": 1, "bit": 32}},
    {"var": {"kind": "varbit", "id": 1, "value": 1, "op": "typo"}},
    {"var": {"kind": "varbit", "id": 1, "value": 1}, "all": []},
])
def test_malformed_completion_conditions_fail_closed(condition):
    assert not milestone_condition_ok(condition)


def test_task_flags_are_supported_and_use_real_game_constants():
    constants = json.loads((ROOT / "build/ids.json").read_text(encoding="utf-8"))

    def check(condition):
        if "var" in condition:
            var = condition["var"]
            assert var["id"] in constants[var["kind"]].values()
        else:
            for part in condition.get("all", condition.get("any", [])):
                check(part)

    conditions = [s["questStopCondition"] for s in STEPS.values() if s.get("questStopCondition")]
    assert len(conditions) == 6
    for condition in conditions:
        assert milestone_condition_ok(condition)
        check(condition)

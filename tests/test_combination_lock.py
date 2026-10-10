"""The dials of a combination lock, and the clicks to move them.

Quest Helper draws five highlighted arrows and a number on each; we drew
nothing, and said "Work out how to open the chest" while it said "Open the
chest using the code NALIA". None of that is data in the constructor -- it is
an algorithm in ChestCodeStep, and the constructor only says which letters to
stop on. Both halves are needed.

Read exactly or not at all: the shortest-direction expression, the distance
expression and the arrow numbering all have to match, because a puzzle solved
the wrong way is worse than one left alone.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from build_quest_steps import combination_lock, _combination_step, _rendered  # noqa: E402

QUESTS = json.loads(
    (ROOT / "build" / "quest_steps.json").read_text(encoding="utf-8"))["quests"]
IDS = json.loads((ROOT / "build" / "ids.json").read_text(encoding="utf-8"))
QH = (ROOT.parent / "B0aty Guide" / "quest-helper-master" / "src" / "main" / "java"
      / "com" / "questhelper" / "helpers" / "quests")


def source(quest, name):
    return (QH / quest / (name + ".java")).read_text(encoding="utf-8")


def test_the_solver_is_recognised_by_its_own_arithmetic():
    found = combination_lock(source("deserttreasureii", "ChestCodeStep"), IDS)
    assert found["varc"] == IDS["varclient"]["COMBINATION_LOCK_VALUE_0"]
    assert found["parent"] == IDS["interface"]["CombinationLock.LOCK"]
    assert found["submit"] == IDS["interface"]["CombinationLock.CONFIRM_BUTTON"]
    # START_DOWN_ARROW = 3, ARROW_INTERVAL = 7, and up is the one after down.
    assert (found["down"], found["up"], found["interval"]) == (3, 4, 7)


def test_a_different_algorithm_is_refused_rather_than_approximated():
    """Every other solver in the folder must read as nothing at all."""
    for quest, name in (("scrambled", "EggSolver"),
                        ("recruitmentdrive", "DoorPuzzle"),
                        ("kingsransom", "LockpickPuzzle"),
                        ("theforsakentower", "PowerPuzzle")):
        assert combination_lock(source(quest, name), IDS) is None, name


def test_the_chest_in_the_ribbiting_tale():
    """NALIA: five dials of ten, stopping on 3, 3, 4, 4, 9."""
    branch = QUESTS["theribbitingtaleofalilypadlabourdispute"]["steps"]["22"]["whenIn"][0]
    assert branch["text"] == "Open the chest using the code NALIA."

    lock = branch["combinationLocks"][0]
    assert lock["size"] == 10
    assert [dial["target"] for dial in lock["cycles"]] == [3, 3, 4, 4, 9]
    # Each dial reads the next client int, and its arrows are the next pair
    # seven children along.
    base = IDS["varclient"]["COMBINATION_LOCK_VALUE_0"]
    assert [dial["varc"] for dial in lock["cycles"]] == [base + i for i in range(5)]
    assert [(dial["down"], dial["up"]) for dial in lock["cycles"]] == [
        (3, 4), (10, 11), (17, 18), (24, 25), (31, 32)]


def test_the_code_belongs_to_the_step_not_to_the_quest():
    """Desert Treasure II has three locks with three different codes."""
    codes = set()
    for node in QUESTS["deserttreasureii"]["steps"].values():
        stack = [node]
        while stack:
            found = stack.pop()
            for lock in found.get("combinationLocks") or ():
                codes.add((lock["size"], tuple(d["target"] for d in lock["cycles"])))
            stack.extend(found.get("whenIn") or [])
    assert codes == {(5, (2, 1, 4, 0, 1, 3)), (10, (0, 4, 1, 5)), (10, (2, 3, 5, 9, 5))}


def test_a_lock_with_no_code_is_not_solved():
    """The Heart of Darkness reads its code off a book while you stand there."""
    found = combination_lock(source("theheartofdarkness", "ChestCodeStep"), IDS)
    assert found is not None, "the algorithm is the same one"
    assert _combination_step(["10"], found) is None, "but there is nothing to solve with"


def test_the_sentence_is_rendered_from_the_call_not_guessed():
    found = combination_lock(source("deserttreasureii", "ChestCodeStep"), IDS)
    assert _rendered(found, ['"chest"', '"NALIA"', "10", "3"]) == (
        "Open the chest using the code NALIA.")
    assert _rendered(found, ['"door"', '"GUS"', "10", "0"]) == (
        "Open the door using the code GUS.")
    # A term that is not a literal abandons the sentence rather than half of it.
    assert _rendered(found, ["objectName", '"NALIA"', "10", "3"]) is None


@pytest.mark.parametrize("current,arrow,clicks", [
    (3, None, 0),   # already right
    (4, "down", 1),
    (2, "up", 1),
    (8, "up", 5),   # 8 -> 3 is five either way: QH takes up on a tie
    (9, "up", 4),   # six down against four up
])
def test_the_shorter_way_round(current, arrow, clicks):
    """First dial of NALIA: target 3 on a wheel of ten."""
    lock = QUESTS["theribbitingtaleofalilypadlabourdispute"]["steps"]["22"]["whenIn"][0]["combinationLocks"][0]
    dial, size = lock["cycles"][0], lock["size"]
    down = (current - dial["target"]) % size
    up = (dial["target"] - current) % size
    assert min(down, up) == clicks
    if arrow is None:
        assert current == dial["target"]
    else:
        assert (dial["down"] if down < up else dial["up"]) == dial[arrow]

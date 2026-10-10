"""Quest Helper's puzzle solutions, and the four reasons none of them shipped.

Every interface solver in Quest Helper was reaching the plugin as the sentence
it shows when you turn solutions OFF. "Work out how to open the chest in
Marcellus' house" instead of "The code is 'NALIA'"; "Mark the suspect guards"
nine times instead of naming the nine guards; "Solve the crystal puzzle"
instead of the five moves that solve it. 48 wrappers shipped the version that
withholds the answer and none shipped the answer.

Four separate faults, each of which alone was enough:

  * PuzzleWrapperStep(this, solvingStep, hiddenText) -- the string is what a
    player sees with Quest Helper's "Show Puzzle Solutions" turned off, and it
    was overwriting the step it wraps.
  * every super(questHelper, ...) in a quest folder was handed to every class
    in it, so sibling solvers crossed over: A Kingdom Divided's statue puzzle
    answered its wall panel.
  * a ConditionalStep with a null default returned nothing, dropping the
    branches that were the whole step.
  * WidgetTextRequirement could not be read, and it is what guards every one
    of these branches, so the branch holding the answer was dropped even once
    the rest worked.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
QUESTS = json.loads(
    (ROOT / "build" / "quest_steps.json").read_text(encoding="utf-8"))["quests"]


def sentences(quest):
    out = []
    for key, node in (QUESTS.get(quest, {}).get("steps") or {}).items():
        stack = [node]
        while stack:
            found = stack.pop()
            said = (found.get("text") or "").strip()
            if said:
                out.append(said)
            stack.extend(found.get("whenIn") or [])
    return out


# The answer, and the sentence that was shipped in its place.
SOLVED = [
    ("theribbitingtaleofalilypadlabourdispute",
     "Search the chest in the building next to Marcellus. The code is 'NALIA'.",
     "Work out how to open the chest in Marcellus' house."),
    ("meatandgreet", "Enter the code 2546 to unlock the box.",
     "Figure out the correct code to unlock the box of spices."),
    ("tribaltotem", "Try and open the door to the west. The password is 'KURT'",
     "Work out and enter the password for the door to the west."),
    ("deathplateau", "Use the red stone on the mechanism.",
     "Work out where to place the red stone on the mechanism."),
    ("taleoftherighteous", "Push the Strange Device all the way to the east.",
     "Solve the crystal puzzle."),
    ("childrenofthesun", "Mark the guard outside Aris's tent.",
     "Mark the suspect guards."),
    ("animalmagnetism",
     "Translate research notes by clicking on all the highlighted switches.",
     "Translate the research notes."),
]


def headline(quest):
    """What each progress value says before any branch is consulted."""
    return [(node.get("text") or "").strip()
            for node in (QUESTS.get(quest, {}).get("steps") or {}).values()]


@pytest.mark.parametrize("quest,answer,withheld", SOLVED)
def test_the_solution_ships_and_the_placeholder_does_not(quest, answer, withheld):
    said = sentences(quest)
    assert any(answer in one for one in said), f"{quest} lost {answer!r}"
    # Only as the step's own sentence: a branch may still carry the wrapper's
    # words where the wrapped class has nothing that renders.
    assert withheld not in headline(quest), (
        f"{quest} still leads with the solutions-off sentence")


def test_sibling_solvers_do_not_cross_over():
    """A Kingdom Divided declares StonePuzzleStep and StatuePuzzle side by side.

    Both resolved to "Solve the statue puzzle.", because every super() in the
    folder was handed to every class in it and the first one won.
    """
    panel = QUESTS["akingdomdivided"]["steps"]
    assert panel["46"]["text"] == "Solve the wall panel puzzle."
    assert panel["48"]["text"] == "Solve the wall panel puzzle."


def test_a_null_default_still_ships_its_branches():
    """Recruitment Drive's MissCheeversStep is super(questHelper, null, ...).

    The whole vial challenge is in its addStep chain, and a null default
    returned nothing at all, so all three instructions went with it.
    """
    said = sentences("recruitmentdrive")
    for wanted in ("Get two vials from the shelves",
                   "Use a vial of Gypsum on the tin in your inventory.",
                   "Use a vial of liquid on the tin in your inventory."):
        assert wanted in said, f"lost {wanted!r}"
    # And the text that used to be pasted over three unrelated challenges.
    assert said.count("Click the highlighted arrows to move the slots to the solution.") == 0


def test_an_interface_branch_is_shipped_with_a_condition_that_reads():
    """WidgetTextRequirement(809, 5, 9, "Confirm") guards both chests."""
    branches = QUESTS["theribbitingtaleofalilypadlabourdispute"]["steps"]["22"]["whenIn"]
    assert len(branches) == 1
    assert branches[0]["when"] == {
        "widget": {"group": 809, "child": 5, "text": ["Confirm"], "index": 9}}

    heart = sentences("theheartofdarkness")
    assert "Open the chest using the code from the book." in heart


def test_a_solver_takes_the_sentence_of_the_step_inside_it():
    """Scrambled's EggSolver says nothing itself; EggPieceStep does."""
    said = sentences("scrambled")
    assert any(one.startswith("Rotate the piece until you're prompted") for one in said)


def test_a_wrapped_class_is_read_as_a_class_not_as_its_arguments():
    """`new ChestCodeStep(this, "chest", "NALIA", 10, ...)` builds its sentence
    at runtime out of those arguments.

    Reading the call as if it were a step handed back the word "chest", which
    went on the overlay as the instruction. Reading the class instead found a
    sentence that is assembled at runtime and so renders as nothing. Neither is
    the answer: the class holds the shape of the sentence and the call holds
    the words, and the two are put together in tests/test_combination_lock.py.
    """
    branches = QUESTS["theribbitingtaleofalilypadlabourdispute"]["steps"]["22"]["whenIn"]
    assert branches[0]["text"] != "chest"
    assert branches[0]["text"] == "Open the chest using the code NALIA."

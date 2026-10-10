"""Quest names the guide writes differently from RuneLite's enum.

"Complete Ribbiting Tale of a Lily Pad Dispute quest" named a quest we held
full Quest Helper data for -- sixteen steps, opening on Marcellus by the Locus
Oasis -- and linked to none of it, because the enum calls it "The Ribbiting
Tale of a Lily Pad *Labour* Dispute". The step carried no target, no travel and
no quest, so the plugin had nothing to point at and said nothing.

Nothing failed, and that is the part worth guarding. A name that does not match
resolves to nothing, and a step resolving to nothing is indistinguishable from
a step that was never meant to resolve. Only the player finds out.
"""
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

GUIDE = json.loads(
    (ROOT.parent / "b0aty-guide-plugin" / "src" / "main" / "resources" / "com"
     / "b0atyguide" / "guide.json").read_text(encoding="utf-8"))
QUESTS = json.loads(
    (ROOT / "build" / "quest_steps.json").read_text(encoding="utf-8"))["quests"]

STEPS = {step["id"]: (section["slug"], step)
         for section in GUIDE["sections"] for step in section["steps"]}

# "Complete X quest", "continue X", "start X" -- the guide telling the player
# to do quest work. Not a quest-name match: the bug was that the name did not
# match anything, so matching names could not have caught it.
INTENT = re.compile(r"\b(?:complete|continue|start|finish)\b[^.]{0,60}?\bquest\b", re.I)

# Sentences that say "quest" while naming none. Pinned by id and quoted, so a
# new unlinked step shows up as a failure to read rather than an entry to add.
PROSE = {
    "c5e48adb50": "Complete the Barcrawl during the quest",
    "494c4d160f": "...continue the quest entering the south gate",
    "1995838fa8": "You will complete this quest later in bank 166...",
    "06b7ffc4e5": "Armoured Zombies drop the Zombie Axe... (prose about a quest)",
}


def intent_steps():
    for step_id, (slug, step) in STEPS.items():
        if INTENT.search(step["text"]):
            yield step_id, slug, step


def test_a_step_telling_you_to_do_a_quest_knows_which_quest():
    """The guard that was missing.

    Before the alias, "Complete Ribbiting Tale of a Lily Pad Dispute quest" sat
    here silently, the fifth unlinked step among four sentences that mention a
    quest without naming one.
    """
    unlinked = {step_id: (slug, step["text"][:90])
                for step_id, slug, step in intent_steps()
                if not step.get("questHelper")}
    unexpected = set(unlinked) - set(PROSE)
    assert not unexpected, "\n".join(
        f"{unlinked[i][0]} {i}: {unlinked[i][1]!r}" for i in sorted(unexpected))


def test_the_prose_exceptions_are_still_there():
    """An excused step that stops existing must stop being excused.

    Step ids are a hash of the text, so rewording one on the wiki retires the
    id. Without this the exception would outlive the sentence it was written
    for and quietly excuse whatever took its place.
    """
    missing = sorted(i for i in PROSE if i not in STEPS)
    assert not missing, f"retired ids still excused: {missing}"


def test_the_lily_pad_dispute_reaches_marcellus():
    """The reported step, pinned to what it has to carry."""
    _, step = STEPS["4cf2aa7fbc"]
    assert step.get("questHelper") == "theribbitingtaleofalilypadlabourdispute"

    first = QUESTS[step["questHelper"]]["steps"]["0"]
    assert first["ids"] == [12935], "the quest must still open on Marcellus"
    assert first["point"] == [1683, 2973, 0]


def test_a_linked_quest_is_never_an_empty_one():
    """Linking to a quest with no steps looks fixed and points at nothing."""
    for step_id, (slug, step) in STEPS.items():
        key = step.get("questHelper")
        if key:
            assert QUESTS.get(key, {}).get("steps"), f"{slug} {step_id} -> {key}"

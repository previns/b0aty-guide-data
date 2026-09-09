"""Which of Quest Helper's branches this build can actually answer.

A ConditionalStep returns the first branch whose conditions hold. Reading only
zones and items kept 46.4% of them, and the missing half was not evenly spread:
it was every branch that turns on one of the game's own numbers. In Monk's
Friend that is both of the branches that notice the player already has the
blanket, so the guide went on saying "pick up the Child's blanket" to someone
holding it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_quest_steps as q  # noqa: E402

GUIDE = json.loads((Path(__file__).resolve().parent.parent / "dist" / "guide.json")
                   .read_text(encoding="utf-8"))


class TestReadingAVarComparison:
    def test_the_plain_form_is_an_equality(self):
        q.VAR_IDS.update({"varbit": {"SOME_BIT": 4444}, "varplayer": {}})
        assert q._var_requirement("VarbitRequirement", ["VarbitID.SOME_BIT", "2"]) == {
            "var": {"kind": "varbit", "id": 4444, "value": 2, "op": "=="}}

    def test_an_operation_is_carried(self):
        assert q._var_requirement(
            "VarbitRequirement", ["1234", "Operation.GREATER_EQUAL", "5", '"text"']) == {
            "var": {"kind": "varbit", "id": 1234, "value": 5, "op": ">="}}

    def test_a_bit_test_is_not_an_equality(self):
        """"Is bit 3 set" and "does it equal 3" are different questions."""
        assert q._var_requirement("VarplayerRequirement", ["1234", "false", "3"]) == {
            "var": {"kind": "varplayer", "id": 1234, "bit": 3, "set": False}}

    def test_a_shape_it_does_not_know_is_refused(self):
        # (id, value, bitShiftRight) -- not answered rather than guessed.
        assert q._var_requirement("VarplayerRequirement", ["1234", "5", "7"]) is None
        assert q._var_requirement("VarbitRequirement", ["1234", "Operation.SOMETHING", "1"]) is None


class TestAWideningCall:
    def test_a_requirement_asked_two_ways_is_one_requirement(self):
        """blanket and blanket.alsoCheckBank(questBank) are the same item."""
        assert q.RE_ALSO_CHECK_BANK.match(
            "blanket.alsoCheckBank(questBank)").group(1) == "blanket"
        assert q.RE_ALSO_CHECK_BANK.match("blanket") is None


class TestMonksFriendKnowsYouHaveTheBlanket:
    """The reported bug, pinned against the shipped file."""

    def setup_method(self):
        self.slot = GUIDE["questHelpers"]["monksfriend"]["steps"]["10"]

    def test_all_three_of_its_branches_are_shipped(self):
        assert len(self.slot["whenIn"]) == 3

    def test_holding_the_blanket_stops_saying_pick_it_up(self):
        holding = [b for b in self.slot["whenIn"]
                   if "blanket" in json.dumps(b["when"]).lower()]
        assert len(holding) == 2, "underground with it, and above ground with it"
        assert any("back up the ladder" in b["text"].lower() for b in holding)
        assert any("brother omad" in b["text"].lower() for b in holding)

    def test_the_branches_stay_in_quest_helpers_order(self):
        """First match wins, so the order is the behaviour."""
        assert "ladder" in self.slot["whenIn"][0]["text"].lower()
        assert "omad" in self.slot["whenIn"][1]["text"].lower()
        assert "pick up" in self.slot["whenIn"][2]["text"].lower()


def test_most_of_quest_helpers_branches_are_kept():
    """A floor, not a target. It reports what it is; it must not slip back."""
    said = kept = 0
    for helper in GUIDE["questHelpers"].values():
        for record in (helper.get("steps") or {}).values():
            said += record.get("branches") or 0
            kept += len(record.get("whenIn") or [])
    assert said > 6000
    assert kept / said > 0.60, "was 46.4%% before var conditions were read"


def test_a_shipped_branch_condition_is_one_the_plugin_can_answer():
    """Anything else must be dropped at build time, never shipped half-read."""
    def answerable(when: dict) -> bool:
        if "open" in when:
            return isinstance(when["open"], int)
        if "here" in when:
            return (when["here"].get("kind") in ("npc", "object", "groundItem")
                    and bool(when["here"].get("ids")))
        if "not" in when:
            return answerable(when["not"])
        for joiner in ("all", "any"):
            if joiner in when:
                return bool(when[joiner]) and all(answerable(p) for p in when[joiner])
        if "item" in when:
            return bool(when["item"].get("ids"))
        if "zone" in when:
            return bool(when["zone"])
        if "var" in when:
            var = when["var"]
            return (var.get("kind") in ("varbit", "varplayer")
                    and var.get("id") is not None
                    and (var.get("bit") is not None or var.get("value") is not None))
        return False

    for key, helper in GUIDE["questHelpers"].items():
        for value, record in (helper.get("steps") or {}).items():
            for branch in record.get("whenIn") or []:
                assert answerable(branch["when"]), f"{key}@{value} {branch['when']}"


class TestQuestHelpersLogicHelpers:
    """`and(a, b)`, `not(a)`, `nor(a, b)` -- Conditions written shorter.

    LogicHelper defines them exactly: `not` and `nor` are both
    `new Conditions(LogicType.NOR, ...)`, `and` is AND, `or` is OR. Six hundred
    and ninety-four branch conditions use one, and every one of them was
    dropped -- along with the branch it guarded.
    """

    def setup_method(self):
        self.decls = {
            "inGuild": ("ZoneRequirement",
                        ["new Zone(new WorldPoint(1,2,0), new WorldPoint(3,4,0))"]),
            "checkedBed": ("VarbitRequirement", ["5", "1"]),
        }

    def test_and_is_every_one_of_them(self):
        got = q.requirement_of("and(inGuild, checkedBed)", self.decls, {})
        assert list(got) == ["all"] and len(got["all"]) == 2

    def test_or_is_any_of_them(self):
        got = q.requirement_of("or(inGuild, checkedBed)", self.decls, {})
        assert list(got) == ["any"]

    def test_not_and_nor_are_none_of_them(self):
        one = q.requirement_of("not(checkedBed)", self.decls, {})
        assert list(one) == ["not"]
        both = q.requirement_of("nor(inGuild, checkedBed)", self.decls, {})
        assert list(both) == ["not"] and list(both["not"]) == ["any"]

    def test_a_helper_wrapping_something_unreadable_is_still_refused(self):
        assert q.requirement_of("and(inGuild, somethingElse)", self.decls, {}) is None


class TestAVarbitNamedInTheQuestsOwnFile:
    """`VARBIT_MARLEY_LINE = 1234` rather than `VarbitID.SOMETHING`."""

    def test_a_local_constant_resolves(self):
        decls = q.declarations(
            "private static final int VARBIT_MARLEY_LINE = 1234; "
            "haveRecipe = new VarbitRequirement(VARBIT_MARLEY_LINE, 10);")
        assert q.requirement_of("haveRecipe", decls, {}) == {
            "var": {"kind": "varbit", "id": 1234, "value": 10, "op": "=="}}

    def test_a_name_with_no_number_behind_it_is_refused(self):
        decls = q.declarations("haveRecipe = new VarbitRequirement(SOME_UNKNOWN, 10);")
        assert q.requirement_of("haveRecipe", decls, {}) is None


def test_dwarf_cannon_notices_the_remains():
    """Item id 0 is Dwarf remains, and a branch turns on holding one.

    The data was right all along; the plugin counted a player's items as
    "id greater than zero", so nobody could ever be holding the first item in
    the game. Pinned here because the id looks like a mistake and is not one.
    """
    branches = GUIDE["questHelpers"]["dwarfcannon"]["steps"]["2"]["whenIn"]
    holding = [b for b in branches if "Dwarf Remains" in json.dumps(b["when"])]
    assert holding, "no branch notices the remains"
    inner = [p["item"] for b in holding for p in b["when"].get("all", [])
             if "item" in p and p["item"]["name"] == "Dwarf Remains"][0]
    assert inner["ids"] == [0], "item id 0 is Dwarf remains, and is not a mistake"
    # One of those branches takes them back. Which index it sits at is
    # quest-helper's business and has already changed once.
    assert any("lawgof" in b["text"].lower() for b in holding),         [b["text"] for b in holding]


def test_a_scene_condition_is_asked_of_the_scene():
    """"Is that npc here", "has the object appeared", "is it on the floor".

    A hundred and eighty branch conditions in the quests this guide runs are one
    of these, and they are how a branch notices the player has done something.
    They need no condition engine -- the tracker already walks the scene every
    tick for the current step.
    """
    q.VAR_IDS.update(json.loads((ROOT / "build" / "ids.json").read_text(encoding="utf-8"))
                     if False else {})
    got = q.requirement_of("new NpcCondition(NpcID.GERTRUDE)", {}, {})
    assert got == {"here": {"kind": "npc", "constants": ["GERTRUDE"]}}

    boxed = q.requirement_of(
        "new ObjectCondition(ObjectID.DOOR, new WorldPoint(1, 2, 0))", {}, {})
    assert boxed["here"]["zone"] == [[1, 2, 0, 1, 2, 0]], boxed

    # And one whose id cannot be read is refused, like everywhere else.
    assert q.requirement_of("new NpcCondition(someLocalThing)", {}, {}) is None


def test_the_shipped_scene_conditions_all_carry_ids():
    def walk(condition):
        if "here" in condition:
            assert condition["here"].get("ids"), condition
            assert condition["here"]["kind"] in ("npc", "object", "groundItem")
        for joiner in ("all", "any"):
            for part in condition.get(joiner) or []:
                walk(part)
        if "not" in condition:
            walk(condition["not"])

    seen = 0
    for helper in GUIDE["questHelpers"].values():
        for record in (helper.get("steps") or {}).values():
            for branch in record.get("whenIn") or []:
                walk(branch["when"])
                seen += 1
    assert seen > 4000

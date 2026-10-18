"""A coordinate Quest Helper named instead of writing inline.

Most of its steps put the tile straight in the constructor, and 8,599 do. A few
name it first:

    WorldPoint tomasPoint = new WorldPoint(1796, 3781, 0);
    talkToLawry = new NpcStep(this, NpcID.PISCQUEST_OFFICIAL_VISIBLE,
        tomasPoint, "Speak to Tomas Lawry in Port Piscarilius.");

Reading only the inline form left those steps with an npc id and nowhere to
walk. The author reported it exactly: Tomas Lawry was pathed to once he
rendered, because then the id matched something in the scene, and not before --
with only the letter in the inventory still marked.

48 instructions across six quests were in that state.
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import build_quest_steps as q  # noqa: E402


def test_an_inline_coordinate_is_still_read():
    assert q._first_point(["new WorldPoint(1796, 3781, 0)"]) == [1796, 3781, 0]


def test_a_named_coordinate_is_resolved():
    decls = {"tomasPoint": ("WorldPoint", ["1796", "3781", "0"])}
    assert q._first_point(["tomasPoint"], decls) == [1796, 3781, 0]


def test_a_named_zone_is_not_a_destination():
    """A Zone is an area the player might be in, not a place to walk to --
    the same rule the inline form already followed."""
    decls = {"warrens": ("Zone", ["1728", "10115", "0"])}
    assert q._first_point(["warrens"], decls) is None


def test_an_unknown_name_resolves_to_nothing():
    assert q._first_point(["mystery"], {}) is None
    assert q._first_point(["mystery"]) is None


def test_the_inline_form_wins_when_both_are_present():
    decls = {"other": ("WorldPoint", ["1", "1", "0"])}
    assert q._first_point(["new WorldPoint(9, 9, 0)", "other"], decls) == [9, 9, 0]


def test_tomas_lawry_ships_his_coordinate():
    """End to end, in the file the plugin loads."""
    guide = json.loads(
        (ROOT / "dist" / "guide.json").read_text(encoding="utf-8"))

    def walk(node):
        yield node
        for branch in node.get("whenIn") or []:
            yield from walk(branch)

    found = [n for slot in guide["questHelpers"]["thequeenofthieves"]["steps"].values()
             for n in walk(slot) if "Lawry" in (n.get("text") or "")]
    assert found, "the Lawry instructions should ship"
    for node in found:
        assert node.get("point") == [1796, 3781, 0], node.get("text")
        assert node.get("ids") == [7904]

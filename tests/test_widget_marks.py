"""Marking part of an interface, the way Quest Helper does.

While a menu is open there is nothing in the world to outline and the step's
sentence is all the player gets. "Use the right tool on the spring, the middle
tool on the Safety switch, and the left tool on the gear" is a fine instruction
and a poor one to follow with three unlabelled tools on screen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_quest_steps as q  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IDS = json.loads((ROOT / "build" / "ids.json").read_text(encoding="utf-8"))
GUIDE = json.loads((ROOT / "dist" / "guide.json").read_text(encoding="utf-8"))
TABLE = IDS["interface"]
ITEMS = IDS["item"]


def one(source: str) -> dict | None:
    return q._widget_highlight(source, TABLE, ITEMS)


class TestReadingAHighlight:
    def test_a_group_and_a_child_are_packed_the_way_quest_helper_packs_them(self):
        assert one("new WidgetHighlight(849, 36)") == {
            "interface": (849 << 16) | 36}

    def test_a_bare_interface_is_taken_whole(self):
        got = one("new WidgetHighlight(InterfaceID.Shopmain.ITEMS, true)")
        assert got == {"interface": TABLE["Shopmain.ITEMS"], "children": True}

    def test_a_third_number_is_a_child_unless_a_flag_says_otherwise(self):
        """(group, child, childChild) and (group, child, itemId, flag).

        The two are told apart by the boolean, which only the longer one has.
        Reading an item id as a child index marks the wrong thing.
        """
        assert one("new WidgetHighlight(270, 19, 5)") == {
            "interface": (270 << 16) | 19, "child": 5}
        assert one("new WidgetHighlight(270, 19, 4438, true)") == {
            "interface": (270 << 16) | 19, "item": 4438, "children": True}

    def test_a_model_requirement_rides_along(self):
        got = one("new WidgetHighlight(InterfaceID.QuetzalMenu.ICONS, true)"
                  ".withModelRequirement(54546)")
        assert got["model"] == 54546 and got["children"] is True

    def test_the_three_factories_name_their_own_interface(self):
        assert one("WidgetHighlight.createShopItemHighlight(ItemID.BUCKET_EMPTY)") == {
            "interface": TABLE["Shopmain.ITEMS"], "children": True,
            "item": ITEMS["BUCKET_EMPTY"]}
        assert one('WidgetHighlight.createMultiskillByName("Snake")') == {
            "interface": TABLE["Skillmulti.BOTTOM"], "children": True, "named": "Snake"}

    def test_a_name_that_does_not_resolve_marks_nothing(self):
        """Rather than an interface zero, which is a real interface."""
        assert one("new WidgetHighlight(InterfaceID.NoSuchThing.NOPE, true)") is None


class TestReadingTheCall:
    def test_the_longer_method_names_carry_the_same_arguments(self):
        text = ("spinPotLid.addWidgetHighlightWithItemIdRequirement"
                "(270, 19, ItemID.POTLID_UNFIRED, true);")
        got = q.widget_highlights(text, IDS)
        assert got["spinPotLid"] == [
            {"interface": (270 << 16) | 19, "item": ITEMS["POTLID_UNFIRED"],
             "children": True}]

    def test_a_highlight_given_a_name_first_is_followed(self):
        text = ("teomatWidget = new WidgetHighlight(849, 36);"
                " talkToX.addWidgetHighlight(teomatWidget);")
        assert q.widget_highlights(text, IDS)["talkToX"] == [
            {"interface": (849 << 16) | 36}]


def test_the_shipped_marks_are_all_usable():
    marks = [w for h in GUIDE["questHelpers"].values()
             for r in (h.get("steps") or {}).values()
             for rec in [r] + (r.get("whenIn") or [])
             for w in rec.get("widgets") or []]
    assert len(marks) >= 15, f"only {len(marks)} marks shipped"
    for mark in marks:
        assert mark.get("interface"), mark
        assert set(mark) <= {"interface", "child", "children", "item", "model",
                             "says", "named"}, mark

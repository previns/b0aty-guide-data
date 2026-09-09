"""What the plugin points at, when the guide only says why.

Three passes decide this, and each one exists because a session log caught the
plugin guiding somewhere the player was not going.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import merge_curated as mc  # noqa: E402
from emit import scattered  # noqa: E402


def section(*steps: dict) -> dict:
    return {"steps": [{"raw": raw, "merged": rest} for raw, rest in
                      ((s.pop("raw"), s) for s in steps)]}


def doing(raw: str, quest: str) -> dict:
    return {"raw": raw, "questStep": True, "questHelper": quest}


class TestABracketThatSaysWhy:
    """"[Monk's Friend]" on a jug of water is what the jug is for."""

    def test_a_fetch_in_a_bank_that_is_not_working_the_quest_is_preparation(self):
        doc = {"sections": [section(
            doing("Head North and take Jug of Water [Monk's Friend]", "monksfriend"),
            doing("Mine 4x Copper Ore [Dorics Quest]", "doricsquest"),
        )]}
        assert mc.demote_fetches_to_preparation(doc) == 2
        assert all(not s["merged"]["questStep"] for s in doc["sections"][0]["steps"])
        # The quest stays as the reason. It is why the item is being taken, and
        # the panel still says so.
        assert doc["sections"][0]["steps"][0]["merged"]["questHelper"] == "monksfriend"

    def test_a_fetch_in_a_bank_that_is_working_the_quest_is_the_quest(self):
        """"Catch 8 rats" is Ratcatchers, when Ratcatchers is what this bank does."""
        doc = {"sections": [section(
            doing("Talk to Gertrude (1) [Ratcatchers]", "ratcatchers"),
            doing("Catch 8 rats [Ratcatchers]", "ratcatchers"),
        )]}
        assert mc.demote_fetches_to_preparation(doc) == 0
        assert doc["sections"][0]["steps"][1]["merged"]["questStep"]

    def test_a_journey_is_not_a_fetch(self):
        """"Take the boat to Brimhaven" comes away with nothing."""
        assert not mc.RE_FETCHED_FOR_LATER.search("Take the boat to Brimhaven")
        assert not mc.RE_FETCHED_FOR_LATER.search("Take the Carpet to Pollnivneach")
        assert mc.RE_FETCHED_FOR_LATER.search("take the bones")


class TestCoordinatesThatDisagree:
    """Ninety-one pins for one step is not ninety-one answers, it is none."""

    def test_points_across_the_world_are_not_a_place(self):
        assert scattered([[3222, 3218, 0], [2612, 3092, 0]])
        assert scattered([[3222, 3218, 0], [3222, 3400, 0]])

    def test_points_in_one_town_are_a_place(self):
        assert not scattered([[3222, 3218, 0], [3230, 3222, 0]])
        assert not scattered([[3222, 3218, 0]])
        assert not scattered([])

    def test_the_shipped_file_marks_them(self):
        import json
        guide = json.loads((Path(__file__).resolve().parent.parent
                            / "dist" / "guide.json").read_text(encoding="utf-8"))
        wide = [s for sec in guide["sections"] for s in sec["steps"]
                if (s.get("target") or {}).get("points")
                and scattered(s["target"]["points"])]
        assert wide, "the guide has always had some; the flag is what is new"
        for step in wide:
            assert step["target"]["scattered"], step["text"]


class TestASkillingStepComesAwayWithSomething:
    """"Mine 10x Clay" means ten Clay in the inventory."""

    def test_the_shipped_file_counts_them(self):
        import json
        guide = json.loads((Path(__file__).resolve().parent.parent
                            / "dist" / "guide.json").read_text(encoding="utf-8"))
        steps = {s["text"]: s for sec in guide["sections"] for s in sec["steps"]}
        clay = next(s for t, s in steps.items() if t.startswith("Mine 10x Clay"))
        assert clay["items"], "carried nothing at all, so nothing counted it"
        item = clay["items"][0]
        assert item["count"] == 10
        assert item["ids"], "unresolved, so the shop and the panel see nothing"
        # And the place it is mined is not part of what is mined.
        assert "way" not in item["name"].lower()

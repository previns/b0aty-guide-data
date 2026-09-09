"""A page's own coordinate, and the pins that merely sit on it.

The wiki writes two different things with the same template. A page's infobox
carries where the subject *is*:

    {{Map|name=Catherby|x=2814|y=3443}}

and its prose carries pins pointing at other things entirely:

    {{map|3089,3265|type=maplink|mtype=pin|group=Bucket of water}}

Reading both as the subject's location turned "Bank at Catherby" from one tile
into seven -- two of them in Draynor, because that is where the bucket of water
spawns. Across the guide, 102 steps carried 867 coordinates where 103 were
meant.

Preference, not prohibition: 16 cached pages have no infobox map at all, and
there the pins are the only answer there is.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
import resolve_wiki as r  # noqa: E402


CATHERBY = """
{{Infobox Location
|name = Catherby
|map = {{Map|name=Catherby|x=2814|y=3443}}
}}
Catherby is a coastal town.

==Spawns==
{{map|3089,3265|type=maplink|mtype=pin|group=Bucket of water}}
{{map|2807,3450|type=maplink|mtype=pin|group=Insect repellent}}
"""

PINS_ONLY = """
{{Infobox Location
|name = Bank deposit box
}}
Deposit boxes are found in many places.
{{map|1744,5475|type=maplink|mtype=pin|group=Deposit box}}
{{map|2569,2862|type=maplink|mtype=pin|group=Deposit box}}
"""

MULTI = """
{{Infobox Location
|name = x
}}
{{map|1744,5475|2569,2862|type=maplink|mtype=pin|group=g}}
"""


def test_the_infobox_map_wins_over_pins_in_the_prose():
    page = r.parse_page({"title": "Catherby", "wikitext": CATHERBY})
    assert page["points"] == [[2814, 3443, 0]], (
        "the Spawns pins say where a bucket of water is, not where Catherby is")


def test_pins_are_used_when_the_page_has_no_map_of_its_own():
    page = r.parse_page({"title": "Bank deposit box", "wikitext": PINS_ONLY})
    assert page["points"] == [[1744, 5475, 0], [2569, 2862, 0]], (
        "refusing pins outright loses the pages whose pins are the whole answer")


def test_only_the_first_coordinate_of_a_block_is_read():
    """A long-standing limit, written down rather than quietly relied upon.

    RE_MAP_POSITIONAL is non-greedy, so a block listing several pairs yields
    only the first. Left alone here on purpose: this change exists to take pins
    off the map and lifting the limit would put more on. Worth revisiting on its
    own, with its own measurement.
    """
    page = r.parse_page({"title": "x", "wikitext": MULTI})
    assert page["points"] == [[1744, 5475, 0]]


def test_the_shipped_guide_puts_catherby_in_one_place():
    guide = json.loads((REPO / "dist" / "guide.json").read_text(encoding="utf-8"))
    seen = 0
    for section in guide["sections"]:
        for step in section["steps"]:
            target = step.get("target") or {}
            if target.get("name") == "Catherby":
                seen += 1
                assert target.get("points") == [[2814, 3443, 0]], step["text"]
    assert seen >= 4, "expected the Catherby banking steps to be present"


def test_no_shipped_place_target_is_a_scatter_of_pins():
    """A place resolving to many points is how the map filled with markers.

    Not zero -- some names genuinely map to several spots, and those are marked
    honestly as "one of N". But a *place* with more than a handful is this bug
    coming back.
    """
    guide = json.loads((REPO / "dist" / "guide.json").read_text(encoding="utf-8"))
    noisy = []
    for section in guide["sections"]:
        for step in section["steps"]:
            target = step.get("target") or {}
            if target.get("kind") == "nav" and len(target.get("points") or []) > 8:
                noisy.append((step["text"][:60], len(target["points"])))
    assert not noisy, f"places pinned all over the map: {noisy[:5]}"

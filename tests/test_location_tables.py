"""Scenery that lists where it is instead of drawing a map.

"Use the Icon on the Statue (Ates) on the North-East coast" resolved to
eighteen ids and no coordinate, so the plugin drew no line until the statue
rendered -- which is after the walk that needed one. The page carries six
locations, as rows of a Location table rather than a {{Map}}.

Scenery only, and that gate is the whole safety of it: twenty item pages use
the same template, and there the rows are where the jewellery teleports *to*.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from resolve_wiki import location_lines, parse_page  # noqa: E402

ENTITIES = json.loads((ROOT / "build" / "entities.json").read_text(encoding="utf-8"))

ROW = ("{{TeleportLocationLine|name=[[The Darkfrost]] - west of the base camp"
       "|x=1491|y=3283|mtype=pin}}")


def test_a_location_row_is_a_coordinate():
    assert location_lines(ROW, 0) == [[1491, 3283, 0]]
    assert location_lines("no rows here", 0) == []


def test_the_statue_knows_where_it_is():
    statue = ENTITIES["Statue (Ates)"]
    assert statue["kind"] == "object"
    # Six statues, and the north-east one the guide names is The Darkfrost.
    assert len(statue["points"]) == 6
    assert [1491, 3283, 0] in statue["points"]


def test_an_items_teleport_list_is_not_where_the_item_is():
    """The gate that keeps an amulet of glory out of Edgeville.

    Its page lists every place it teleports to in exactly this template. Read
    as locations they would become the item's own coordinates, and the step
    that says to wear one would route the player to Karamja.
    """
    page = {"title": "Amulet of glory", "wikitext":
            "{{Infobox Item\n|id = 1704\n}}\n" + ROW}
    parsed = parse_page(page)
    assert parsed is not None
    assert parsed["kind"] == "item"
    assert parsed["points"] == [], "an item must not take its teleport list as a location"


def test_a_real_map_still_wins_over_the_table():
    """The table is a fallback, not a replacement: a page with both keeps its
    map, which is the coordinate the page is actually about."""
    page = {"title": "Statue", "wikitext":
            "{{Infobox Scenery\n|id = 1\n}}\n{{Map|x=3200|y=3200}}\n" + ROW}
    parsed = parse_page(page)
    assert parsed["points"] == [[3200, 3200, 0]]

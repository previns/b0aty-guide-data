"""Reading a journey, and the pickup it used to be confused with.

The guide writes "Take the boat to Brimhaven" and "Take 3x Logs" with the same
verb. An earlier attempt to read a leading "Take" as a pickup matched the first
sentence too and cost six points of target coverage, so the word was banned and
the pickups gave nothing for it. Naming the vehicles is what tells them apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import annotate  # noqa: E402


def where(text: str):
    return annotate.annotate_step(text).get("destination")


def things(text: str):
    return [i["name"] for i in annotate.annotate_step(text).get("items", [])]


def test_a_journey_names_where_it_goes_and_carries_nothing():
    assert where("Take the boat to Brimhaven") == "Brimhaven"
    assert where("Take boat back to Port Sarim [Karamja Easy Diary]") == "Port Sarim"
    assert where("Charter to Catherby") == "Catherby"
    assert where("Take Boat to Ardougne & bank at the South Bank") == "Ardougne"
    assert where("Take the Magic carpet to the Ruins of Uzer") == "Ruins of Uzer"
    assert where("Take Mine Cart to Arceuss and continue Client of Kourend") == "Arceuss"
    assert where("Take Spirit Tree to Gnome Stronghold (2)") == "Gnome Stronghold"

    for journey in ("Take the boat to Brimhaven", "Charter to Catherby"):
        assert things(journey) == [], journey


def test_a_pickup_is_read_again_now_the_journeys_are_claimed():
    assert things("Take 3x Logs") == ["Logs"]
    assert things("Take the Beer") == ["Beer"]
    assert things("Take Pot of Flour") == ["Pot of Flour"]
    # "an" before "a", or the article eats the noun's first letter.
    assert things("Take an Insect Repellent [Merlin's Crystal]") == ["Insect Repellent"]


def test_a_shortcut_is_a_way_through_and_not_a_thing_to_carry():
    """Recording one as an item put a requirement on the player that no amount
    of banking could clear."""
    assert things("Take Falador Crumbling wall Shortcut [Falador Easy Diary]") == []
    assert things("Take rope shortcut up towards Volcanic Mine") == []


def test_a_lowercase_place_is_not_a_destination():
    """"the island" is not a place this can look up, and guessing at one would
    put a marker on the map with nothing behind it."""
    assert where("Take the boat to the island") is None


def test_depositing_everything_is_a_trip_to_a_bank():
    banking = lambda text: bool(annotate.annotate_step(text).get("banking"))
    assert banking("Deposit all")
    assert banking("Deposit Inventory")
    assert banking("Deposit all at Entrana except Ice Gloves, Teleport Runes")

    # Other things you can put something into are not banks, and none of them
    # says "all".
    assert not banking("Deposit 15 Pineapples into the Compost Bin North")
    assert not banking("Deposit 10k in the coffer")
    assert not banking("Deposit the buckets on Drew")


def test_a_purchase_says_where_the_shop_is_without_losing_the_goods():
    """"Buy 2x Bronze Med Helm in Barbarian Village" rang the helmet and pointed
    nowhere: the tail was cut off the item name so it would resolve, and then
    thrown away. It is where to go."""
    assert where("Buy 2x Bronze Med Helm in Barbarian Village") == "Barbarian Village"
    assert things("Buy 2x Bronze Med Helm in Barbarian Village") == [
        "Bronze Med Helm in Barbarian Village"]
    assert where("Buy a Spade at Draynor") == "Draynor"


def test_a_teleport_item_still_counts_when_the_step_goes_on():
    """"Chronicle and complete Gertrude's Cat" is a teleport followed by what to
    do when you land. The item is the first thing to click either way."""
    tele = lambda text: annotate.annotate_step(text).get("teleportItem")
    assert tele("Chronicle and complete Gertrudes Cat") == "Chronicle"
    assert tele("Ectophial and run to the Ectofuntus") == "Ectophial"
    # Still only where the name is the first thing said.
    assert tele("Head north and use the Chronicle") is None

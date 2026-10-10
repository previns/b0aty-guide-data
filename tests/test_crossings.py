"""Places you cannot walk to, named without a vehicle.

"Head to Entrana" names no boat, so the travel matcher ignored it and the step
was left pointing at a coordinate in the middle of the sea. Six steps read that
way. The fix must not become "any place the guide heads to is a boat ride":
that is the Catherby bug, and the teleport steps are the same trap wearing a
different hat.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from merge_curated import travel_for  # noqa: E402

GUIDE = json.loads(
    (ROOT.parent / "b0aty-guide-plugin" / "src" / "main" / "resources" / "com"
     / "b0atyguide" / "guide.json").read_text(encoding="utf-8"))
TRANSPORTS = json.loads((ROOT / "build/transports.json").read_text(encoding="utf-8"))
ENTITIES = json.loads((ROOT / "build/entities.json").read_text(encoding="utf-8"))

STEPS = {step["id"]: (section["slug"], step)
         for section in GUIDE["sections"] for step in section["steps"]}


@pytest.fixture(scope="module")
def guide():
    return STEPS


# The steps the author could not replay: bank 29 is long past for the test
# account, and so is every one of these.
CROSSINGS = {
    "8509fa1310": ("Entrana", [2834, 3331, 1]),
    "f0aaa22c89": ("Entrana", [2834, 3331, 1]),
    "ccd547a333": ("Entrana", [2834, 3331, 1]),
    "4ce6a2cdb5": ("Entrana", [2834, 3331, 1]),
    "fe418809fb": ("Entrana", [2834, 3331, 1]),
    "4e10ac667e": ("Brimhaven", [2772, 3234, 0]),
    "e45094457c": ("Brimhaven", [2772, 3234, 0]),
}


@pytest.mark.parametrize("step_id,expected", sorted(CROSSINGS.items()))
def test_water_crossings_board_a_boat(guide, step_id, expected):
    place, arrival = expected
    slug, step = guide[step_id]
    travel = step.get("travel")
    assert travel, f"{slug} {step_id}: {step['text']!r} points across open water"
    assert travel["place"] == place
    assert travel["destination"] == arrival
    assert travel["departures"], "a crossing with no boarding point is not a crossing"


def test_fossil_island_boards_the_barge(guide):
    """boats also labels "Fossil Island" -- the rowboats already on it.

    Choosing that kind resolved cleanly and produced a boarding point reachable
    only by first being where the player was trying to go.
    """
    _, step = guide["f175a742bc"]
    travel = step["travel"]
    assert travel["kind"] == "ships"
    assert [d["origin"] for d in travel["departures"]] == [[3362, 3445, 0]]


TELEPORTS = ["df582594a9", "53867a2d9c", "7913d4ce7b", "722c59eb47", "72815a4ceb"]


@pytest.mark.parametrize("step_id", TELEPORTS)
def test_teleports_to_an_island_are_not_boat_rides(guide, step_id):
    """An island is not only reachable by boat, and these say so."""
    slug, step = guide[step_id]
    assert "tele" in step["text"].lower(), "fixture drifted; this must be a teleport step"
    assert not step.get("travel"), (
        f"{slug} {step_id}: {step['text']!r} was answered with a dock")


def test_a_walk_is_still_a_walk():
    """Catherby, Ardougne and Rimmington are ship endpoints too.

    Deciding this from route-endpoint membership rather than from the map is
    what would turn every one of them into a boat ride.
    """
    crossings = {"Entrana": "ships"}
    for place in ("Catherby", "Ardougne", "Rimmington", "Port Sarim"):
        assert travel_for(f"Head to {place}", TRANSPORTS, ENTITIES, {}, crossings) is None


def test_crossings_need_the_curated_fact():
    """Without the table there is no inference at all -- the sentence alone
    never decides that a place cannot be walked to."""
    assert travel_for("Head to Entrana", TRANSPORTS, ENTITIES, {}, None) is None
    assert travel_for("Head to Entrana", TRANSPORTS, ENTITIES, {}, {"Entrana": "ships"})

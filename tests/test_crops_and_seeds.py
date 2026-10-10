"""A crop, its sack, and its seed are three different items.

The author reported onions not highlighting in Bank 27. The withdraw line asks
for "4x Onions"; the wiki's plural page is the farming sack, so the guide
resolved to SACK_ONION_1..10 (5440-5458) and the plugin outlined a sack the
player does not carry. The vegetable is the singular page, ONION = 1957.

Planting is the other half and pulls the opposite way: "Plant Onions" means
onion *seeds*. Thirteen of the guide's sixteen "Plant" steps already name the
seed or sapling outright, so this is settled per step rather than by a rule --
"Plant the White Tree Shoot" is not a seed at all.
"""
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = json.loads(
    (ROOT.parent / "b0aty-guide-plugin" / "src" / "main" / "resources" / "com"
     / "b0atyguide" / "guide.json").read_text(encoding="utf-8"))

ONION, CABBAGE = 1957, 1965
ONION_SEED, CABBAGE_SEED, STRAWBERRY_SEED = 5319, 5324, 5323
# The farming sacks and baskets these used to resolve to.
SACKS = set(range(5440, 5459)) | set(range(5460, 5479)) | set(range(5398, 5417))


def step(step_id):
    for section in GUIDE["sections"]:
        for found in section["steps"]:
            if found["id"] == step_id:
                return found
    raise AssertionError("no step " + step_id)


def ids_named(step_id, name):
    found = step(step_id)
    for item in found.get("items") or []:
        if item["name"] == name:
            return item.get("ids") or []
    target = found.get("target") or {}
    if target.get("name") == name:
        return target.get("ids") or []
    raise AssertionError("%s has no item named %r" % (step_id, name))


def test_the_reported_bank_27_onions_are_the_vegetable():
    assert ids_named("a98eb356c7", "Onions") == [ONION]


def test_buying_onions_is_the_vegetable_too():
    assert ids_named("1734c17235", "Onions") == [ONION]


def test_planting_wants_the_seed_not_the_crop():
    assert ids_named("bc3613b036", "Onion seed") == [ONION_SEED]
    assert ids_named("1a2cbae29f", "Cabbage seed") == [CABBAGE_SEED]
    assert ids_named("59653a0852", "Strawberry seed") == [STRAWBERRY_SEED]


def test_no_step_asks_the_player_to_carry_a_farming_sack():
    """The class, not the instance.

    A sack of onions is a real item and the guide may one day want one -- but it
    would say so, as Bank 122's "Sack of Potatoes" does. A step whose name does
    not mention a sack or basket resolving only to sack ids is this bug again.
    """
    offenders = []
    for section in GUIDE["sections"]:
        for found in section["steps"]:
            entries = list(found.get("items") or [])
            target = found.get("target") or {}
            if target.get("kind") == "item":
                entries.append(target)
            for item in entries:
                got = set(item.get("ids") or [])
                name = (item.get("name") or "").lower()
                if "sack" in name or "basket" in name:
                    continue
                if got and got <= SACKS:
                    offenders.append((section["title"], item.get("name")))
    assert not offenders, offenders

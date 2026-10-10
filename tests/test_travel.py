"""How the route gets from one place to another.

"Take the boat to Rimmington" never says Captain Barnaby. 98 of the guide's 140
travelling steps named a place and nothing else, so the plugin walked the player
to a dock and went quiet.

Skretzo/shortest-path already maps this -- the same source, licence and
attribution as `open-transports.tsv` -- and groups its rows under headers naming
the endpoints of each route. That header is what a guide sentence is matched
against.
"""
import io
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

GUIDE = json.loads(
    (ROOT.parent / "b0aty-guide-plugin" / "src" / "main" / "resources" / "com"
     / "b0atyguide" / "guide.json").read_text(encoding="utf-8"))

BOATS = {"boats", "ships", "charter_ships"}


def travels():
    for section in GUIDE["sections"]:
        for step in section["steps"]:
            if step.get("travel"):
                yield section["title"], step


def test_the_boat_to_rimmington_names_its_captain():
    found = [s for _, s in travels() if s["text"] == "Take the boat to Rimmington"]
    assert found, "Bank 12 should have a vehicle"
    going = found[0]["travel"]
    assert going["kind"] in BOATS
    assert {d['id'] for d in going['departures']} == {9250, 8764}
    assert all(d['action'] == 'Rimmington Captain Barnaby' for d in going['departures'])
    assert going["place"] == "Rimmington"


def test_a_boat_step_never_resolves_to_a_minecart():
    """"Take boat to Keldagrim" found the Keldagrim *minecart* until the kind
    was checked: the label matched and nothing said a minecart is not a boat."""
    for title, found in travels():
        text = found["text"].lower()
        kind = found["travel"]["kind"]
        if "boat" in text or "ship" in text:
            assert kind in BOATS or "charter" in text, (title, found["text"], kind)
        if "minecart" in text or "mine cart" in text:
            assert kind == "minecarts", (title, found["text"], kind)
        if "carpet" in text:
            assert kind == "magic_carpets", (title, found["text"], kind)


def test_every_vehicle_can_be_boarded_somewhere():
    for title, found in travels():
        going = found["travel"]
        assert going["departures"], (title, found["text"])
        for departure in going["departures"]:
            origin = departure['origin']
            assert len(origin) == 3, origin
            assert 0 <= origin[2] <= 3, origin
            assert departure["id"] > 0


def test_walking_steps_are_left_alone():
    """A step that names a place but no vehicle is a walk, and answering it
    with a boat would be a different instruction.

    The one exception is a place there is no walking to. "Head to Entrana"
    names no vehicle and is still not a walk, and six steps like it pointed at
    a coordinate in open water. Those places are named in curated/crossings.yaml
    rather than inferred, because whether a place can be walked to is a fact
    about the map: Catherby, Ardougne and Rimmington are ship endpoints too.
    """
    crossings = yaml.safe_load(
        (ROOT / "curated" / "crossings.yaml").read_text(encoding="utf-8"))["crossings"]
    islands = tuple(place.lower() for place in crossings)
    for section in GUIDE["sections"]:
        for found in section["steps"]:
            if not found.get("travel"):
                continue
            text = found["text"].lower()
            if any(word in text for word in (
                    "boat", "ship", "sail", "charter", "canoe", "minecart",
                    "mine cart", "carpet", "glider", "balloon", "quetzal",
                    "spirit tree", "fairy ring", "mushtree", "obelisk")):
                continue
            assert any(island in text for island in islands), found["text"]
            # And never a teleport: an island is not only reachable by boat.
            assert "tele" not in text, found["text"]


def test_the_transport_table_parses_completely():
    """Every row is accounted for: a route, a hub, or somewhere a hub reaches.

    Dropping the ones without a destination lost fairy rings, spirit trees and
    gliders entirely -- they have no destination column because you choose it in
    an interface after boarding.
    """
    table = json.loads((ROOT / "build" / "transports.json").read_text(encoding="utf-8"))
    assert len(table["routes"]) > 400
    assert len(table["hubs"]) > 300, "fairy rings and spirit trees live here"
    assert table["arrivals"], "the minecart stops"
    for route in table["routes"]:
        assert route["id"] > 0
        assert len(route["origin"]) == 3 and len(route["destination"]) == 3


def test_charters_travel_into_the_named_port_not_out_of_it():
    table = json.loads((ROOT / 'build/transports.json').read_text(encoding='utf-8'))
    for _, step in travels():
        travel = step['travel']
        if travel['kind'] != 'charter_ships':
            continue
        docks = {tuple(r['origin']) for r in table['routes']
                 if r['kind'] == 'charter_ships' and r['label'] == travel['place']}
        assert docks == {tuple(travel['destination'])}
        for d in travel['departures']:
            assert d['origin'] != travel['destination']


def test_every_departure_retains_its_own_source_id_and_action():
    table = json.loads((ROOT / 'build/transports.json').read_text(encoding='utf-8'))
    for _, step in travels():
        travel = step['travel']
        for d in travel['departures']:
            assert any(all(r[k] == d[k] for k in ('origin', 'id', 'action'))
                       and r['destination'] == travel['destination'] for r in table['routes']) or (
                           travel['kind'] == 'minecarts' and any(
                               r['kind'] == 'minecarts' and all(r[k] == d[k] for k in ('origin', 'id', 'action'))
                               for r in table['hubs']))


def test_network_stops_are_joined_without_a_route_edge():
    from pipeline.merge_curated import travel_for
    table = json.loads((ROOT / 'build/transports.json').read_text(encoding='utf-8'))
    for place in {r['label'] for r in table['arrivals'] if r['kind'] == 'minecarts'}:
        travel = travel_for('Take minecart to ' + place, table, {})
        assert travel is not None, place
        assert travel['departures'], place
        assert all(d['id'] == 28835 for d in travel['departures'])
        destination_hubs = [r['origin'] for r in table['hubs']
                            if r['kind'] == 'minecarts' and r['label'] == place]
        assert all(d['origin'] not in destination_hubs for d in travel['departures'])


def test_bank29_both_compound_journeys_have_boarding_guidance():
    steps = {s['id']: s for section in GUIDE['sections'] for s in section['steps']}
    assert steps['da29187ebe']['travel']['destination'] == [1670, 3833, 0]
    assert steps['121cd58f0b']['travel']['destination'] == [1761, 3710, 0]


def test_unknown_or_ambiguous_network_stop_is_unresolved():
    from pipeline.merge_curated import travel_for
    table = {'hubs': [{'kind': 'minecarts', 'label': 'Town', 'origin': [1, 2, 0],
                      'id': 1, 'action': 'Travel'}],
             'arrivals': [{'kind': 'minecarts', 'label': 'Town', 'destination': p}
                          for p in ([3, 4, 0], [5, 6, 0])]}
    assert travel_for('Take minecart to Town', table, {}) is None
    assert travel_for('Take minecart to Townish', table, {}) is None


def test_equal_distance_destinations_fail_closed():
    from pipeline.merge_curated import travel_for
    routes = [{'kind': 'boats', 'label': 'Aaa, Bbb', 'id': 1, 'action': 'Travel',
               'origin': [10, 10, 0], 'destination': p} for p in ([0, 0, 0], [2, 0, 0])]
    assert travel_for('Take boat to Bbb', {'routes': routes}, {'Bbb': {'points': [[1, 0, 0]]}}) is None

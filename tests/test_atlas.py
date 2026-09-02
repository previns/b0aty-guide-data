"""The Quest Helper join.

The pipeline forbids resolving by similarity, and Quest Helper's coordinates
are usually reached by matching its prose descriptions -- which is exactly the
banned thing, and why build_qh_hints.py output goes to a human instead.

These tests pin the property that makes this join different: it compares
numbers, never names.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import merge_curated  # noqa: E402

ATLAS = {
    "npc": {
        "3211": {"points": [[3243, 3206, 0]], "ambiguous": False},
        "120": {"points": [[3086, 3257, 0], [3086, 3258, 0]], "ambiguous": True},
    },
    "object": {},
    "collections": {"PICKAXES": [1265, 1267]},
}


def test_a_single_coordinate_joins_on_the_id():
    points, ambiguous = merge_curated.atlas_points(ATLAS, "npc", [3211])
    assert points == [[3243, 3206, 0]]
    assert not ambiguous


def test_several_coordinates_are_all_kept_and_flagged():
    """Picking one would be a guess; the ambiguity is the honest answer."""
    points, ambiguous = merge_curated.atlas_points(ATLAS, "npc", [120])
    assert len(points) == 2
    assert ambiguous


def test_an_id_quest_helper_never_visits_yields_nothing():
    points, ambiguous = merge_curated.atlas_points(ATLAS, "npc", [999999])
    assert points == []
    assert not ambiguous


def test_the_wrong_kind_does_not_cross_match():
    """An NPC id must never pick up an object's coordinates."""
    points, _ = merge_curated.atlas_points(ATLAS, "object", [3211])
    assert points == []


def test_a_target_with_no_ids_cannot_be_joined():
    """Inferred targets carry no ids by construction, so they get no points.

    This is the safety property: a name the grammar guessed can never acquire
    a coordinate, because the join has nothing to key on.
    """
    points, _ = merge_curated.atlas_points(ATLAS, "npc", [])
    assert points == []


def test_a_missing_atlas_is_not_an_error():
    empty = {"npc": {}, "object": {}, "collections": {}}
    assert merge_curated.atlas_points(empty, "npc", [3211]) == ([], False)


# --- curated item collections ----------------------------------------------

def test_an_unknown_collection_constant_is_rejected():
    """A typo must fail the build, not quietly drop a category.

    "Pickaxe" appears 33 times. A misspelt constant would resolve none of them
    and report nothing -- the same silent under-reporting as the resolver bugs.
    """
    problems = merge_curated.check_collections(
        {"Pickaxe": "PICKAXESS"}, {"PICKAXES": [1265]}, {})
    assert problems
    assert "PICKAXESS" in problems[0]


def test_valid_collections_pass():
    assert merge_curated.check_collections(
        {"Pickaxe": "PICKAXES"}, {"PICKAXES": [1265]}, {}) == []


def test_a_list_of_collections_merges_their_ids():
    """"Teleport Runes" is law plus the four elements, and no single Quest
    Helper collection covers that."""
    ids = merge_curated.collection_members(
        ["AIR_RUNE", "FIRE_RUNE"], {"AIR_RUNE": [556, 4695], "FIRE_RUNE": [554, 4694]}, {})
    assert ids == [556, 4695, 554, 4694]


def test_a_list_entry_may_name_a_wiki_entity():
    """Quest Helper has no law rune collection, so the entity supplies it."""
    ids = merge_curated.collection_members(
        ["Law Runes", "AIR_RUNE"], {"AIR_RUNE": [556]}, {"Law Runes": {"ids": [563]}})
    assert ids == [563, 556]


def test_a_duplicate_id_across_collections_appears_once():
    # A dust rune is in both AIR_RUNE and EARTH_RUNE.
    ids = merge_curated.collection_members(
        ["AIR_RUNE", "EARTH_RUNE"], {"AIR_RUNE": [556, 4696], "EARTH_RUNE": [557, 4696]}, {})
    assert ids == [556, 4696, 557]


def test_an_unknown_name_in_a_list_fails_the_whole_row():
    """Half a category is worse than none: the bank tag would look complete
    while missing the runes it forgot."""
    assert merge_curated.collection_members(
        ["AIR_RUNE", "NONESUCH"], {"AIR_RUNE": [556]}, {}) is None


def test_an_empty_row_is_rejected():
    assert merge_curated.collection_members([], {}, {}) is None


def test_the_shipped_collection_file_is_valid():
    """The real curated file, against the real atlas."""
    import json
    import yaml
    repo = Path(__file__).resolve().parent.parent
    atlas_path = repo / "build" / "atlas.json"
    entities_path = repo / "build" / "entities.json"
    if not atlas_path.exists() or not entities_path.exists():
        return  # build artifacts; nothing to check on a clean tree
    atlas = json.loads(atlas_path.read_text(encoding="utf-8"))
    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    mapping = yaml.safe_load(
        (repo / "curated" / "item_collections.yaml").read_text(encoding="utf-8")
    )["collections"]
    assert merge_curated.check_collections(mapping, atlas["collections"], entities) == []


# --- diary completion bits --------------------------------------------------

def test_a_stale_step_id_fails_the_build():
    """A reworded step must not carry its old auto-tick to whatever inherited
    the id. This is the row that would silently mark work done."""
    problems = merge_curated.check_diary(
        {"deadbeef01": {"varplayer": "LUMB_DRAY_ACHIEVEMENT_DIARY", "bit": 5}},
        {"LUMB_DRAY_ACHIEVEMENT_DIARY": 1194},
        {"1111111111"})
    assert problems and "wiki text moved" in problems[0]


def test_an_unknown_varplayer_fails_the_build():
    problems = merge_curated.check_diary(
        {"1111111111": {"varplayer": "NOT_A_REAL_DIARY", "bit": 5}},
        {"LUMB_DRAY_ACHIEVEMENT_DIARY": 1194},
        {"1111111111"})
    assert problems and "unknown VarPlayer" in problems[0]


def test_an_out_of_range_bit_fails_the_build():
    for bit in (-1, 32, "five", None):
        problems = merge_curated.check_diary(
            {"1111111111": {"varplayer": "D", "bit": bit}}, {"D": 1}, {"1111111111"})
        assert problems, f"bit {bit!r} should be rejected"


def test_a_valid_row_passes():
    assert merge_curated.check_diary(
        {"1111111111": {"varplayer": "D", "bit": 5}}, {"D": 1}, {"1111111111"}) == []


def test_the_shipped_diary_file_is_valid():
    import json
    import yaml
    repo = Path(__file__).resolve().parent.parent
    ids_path = repo / "build" / "ids.json"
    guide_path = repo / "dist" / "guide.json"
    if not ids_path.exists() or not guide_path.exists():
        return
    varplayers = json.loads(ids_path.read_text(encoding="utf-8"))["varplayer"]
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    step_ids = {s["id"] for sec in guide["sections"] for s in sec["steps"]}
    tasks = yaml.safe_load(
        (repo / "curated" / "diary_tasks.yaml").read_text(encoding="utf-8"))["tasks"]
    assert merge_curated.check_diary(tasks, varplayers, step_ids) == []

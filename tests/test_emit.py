"""Tests for the emitted contract and the progress-migration map.

Migrations are the one thing here that touches a player's saved data. A wrong
map silently un-ticks work someone actually did, so the rules are pinned.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.emit import build_migrations, content_hash, project  # noqa: E402
from pipeline.validate import coverage, invariants  # noqa: E402

GUIDE = REPO / "dist" / "guide.json"


def guide_doc(slug: str, steps: list[tuple[str, str]]) -> dict:
    return {
        "sections": [
            {
                "slug": slug,
                "steps": [{"id": sid, "text": text} for sid, text in steps],
            }
        ]
    }


# --- migrations --------------------------------------------------------------


def test_no_migrations_when_nothing_changed():
    doc = guide_doc("bank-1", [("aaaaaaaaaa", "Talk to Bob")])
    assert build_migrations(doc, doc) == {}


def test_reworded_step_migrates():
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Talk to Bob in Lumbridge")])
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Talk to Bob in Lumbridge castle")])
    assert build_migrations(before, after) == {"aaaaaaaaaa": "bbbbbbbbbb"}


def test_unrelated_replacement_does_not_migrate():
    """A deleted step and an unrelated new one must not be paired -- that would
    mark work complete that the player never did."""
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Talk to Bob in Lumbridge")])
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Mine 15 iron ore at the quarry")])
    assert build_migrations(before, after) == {}


def test_migration_never_crosses_sections():
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Talk to Bob in Lumbridge")])
    after = {
        "sections": [
            {"slug": "bank-1", "steps": []},
            {"slug": "bank-2", "steps": [{"id": "bbbbbbbbbb", "text": "Talk to Bob in Lumbridge"}]},
        ]
    }
    assert build_migrations(before, after) == {}


def test_each_new_step_is_claimed_once():
    """Two removed steps must not both migrate onto the same new step."""
    before = guide_doc(
        "bank-1",
        [("aaaaaaaaaa", "Collect 3x Logs here"), ("cccccccccc", "Collect 3x Logs here now")],
    )
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Collect 4x Logs here")])
    result = build_migrations(before, after)
    assert list(result.values()).count("bbbbbbbbbb") <= 1


def test_deleted_step_maps_nowhere():
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Talk to Bob")])
    after = guide_doc("bank-1", [])
    assert build_migrations(before, after) == {}


def test_first_build_has_no_migrations():
    assert build_migrations(None, guide_doc("bank-1", [("aaaaaaaaaa", "x")])) == {}


# --- content hash ------------------------------------------------------------


def test_content_hash_is_stable_and_order_independent():
    a = {"sections": [{"slug": "x"}], "episodes": []}
    b = {"episodes": [], "sections": [{"slug": "x"}]}
    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_with_content():
    a = {"sections": [{"slug": "x"}]}
    b = {"sections": [{"slug": "y"}]}
    assert content_hash(a) != content_hash(b)


# --- the shipped artifact ----------------------------------------------------

pytestmark_guide = pytest.mark.skipif(
    not GUIDE.exists(), reason="dist/guide.json not built yet"
)


@pytest.fixture(scope="module")
def guide() -> dict:
    if not GUIDE.exists():
        pytest.skip("dist/guide.json not built yet")
    return json.loads(GUIDE.read_text(encoding="utf-8"))


def test_shipped_guide_passes_its_own_invariants(guide):
    assert invariants(guide) == []


def test_generated_at_is_excluded_from_the_hash(guide):
    """A rebuild that changes nothing must not produce a new contentHash, or
    every daily CI run would open a pointless PR."""
    recomputed = content_hash(
        {k: v for k, v in guide.items() if k not in ("migrations", "contentHash", "generatedAt")}
    )
    assert recomputed == guide["contentHash"]


def test_every_target_has_a_name_and_confidence(guide):
    for section in guide["sections"]:
        for step in section["steps"]:
            target = step.get("target")
            if target:
                assert target["name"].strip()
                assert target["confidence"] in {
                    "linked", "wiki-exact", "wiki-redirect", "inferred", "manual"
                }


def test_ids_only_appear_with_wiki_backing(guide):
    """An `inferred` target is a name the grammar guessed and the wiki could not
    confirm. It must never carry IDs or coordinates presented as fact."""
    for section in guide["sections"]:
        for step in section["steps"]:
            target = step.get("target") or {}
            if target.get("confidence") == "inferred":
                assert not target.get("ids")
                assert not target.get("points")


def test_images_are_https(guide):
    for section in guide["sections"]:
        for url in section["imageUrls"]:
            assert url.startswith("https://")


def test_coverage_report_matches_the_guide(guide):
    report = coverage(guide)
    assert report["totalSteps"] == sum(len(s["steps"]) for s in guide["sections"])
    assert 0 <= report["pct"]["target"] <= 100


def test_project_drops_internal_build_fields():
    doc = {
        "episodes": [],
        "sections": [
            {
                "id": "aaaaaaaaaa", "slug": "s", "ordinal": 0, "title": "S",
                "bankNumber": None, "bankSuffix": None, "episodeOrdinal": None,
                "continuationOf": None, "imageUrls": [], "sourceLine": 42,
                "terminated": True, "bankComment": "Bank 1",
                "steps": [
                    {
                        "id": "bbbbbbbbbb", "ordinal": 0, "depth": 1, "kind": "step",
                        "raw": "Talk to Bob", "sourceLine": 43, "videoIds": [],
                        "confidence": "linked", "merged": {"dialogue": [[1]]},
                    }
                ],
            }
        ],
    }
    out = project(doc)
    section = out["sections"][0]
    assert "sourceLine" not in section and "bankComment" not in section
    step = section["steps"][0]
    assert step["text"] == "Talk to Bob"
    assert "raw" not in step and "sourceLine" not in step and "merged" not in step
    assert step["dialogue"] == [[1]]


# --- migration matching: the structural rules -------------------------------


def test_appended_clarification_migrates():
    """The commonest real edit. A flat 0.85 ratio missed this one at 0.82."""
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Collect the Empty Jug, Bowl & Knife in Lumbridge kitchen")])
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Collect the Empty Jug, Bowl & Knife in Lumbridge kitchen (updated by an editor)")])
    assert build_migrations(before, after) == {"aaaaaaaaaa": "bbbbbbbbbb"}


def test_trimmed_step_migrates():
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Head north to the bank and deposit everything you have")])
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Head north to the bank")])
    assert build_migrations(before, after) == {"aaaaaaaaaa": "bbbbbbbbbb"}


def test_short_prefix_does_not_migrate():
    """"Bank" is a prefix of half the guide. Containment needs real length."""
    before = guide_doc("bank-1", [("aaaaaaaaaa", "Bank")])
    after = guide_doc("bank-1", [("bbbbbbbbbb", "Bank at Draynor and deposit all of your logs")])
    assert build_migrations(before, after) == {}


def test_similar_but_distant_steps_do_not_migrate():
    """Two near-identical lines far apart in a section are separate steps, not a
    rewording -- position is what tells them apart."""
    before = {"sections": [{"slug": "bank-1", "steps": [
        {"id": "aaaaaaaaaa", "text": "Collect 3x Logs next to the stairs", "ordinal": 0},
    ]}]}
    after = {"sections": [{"slug": "bank-1", "steps": [
        {"id": "cccccccccc", "text": "Unrelated filler step one", "ordinal": 0},
        {"id": "dddddddddd", "text": "Unrelated filler step two", "ordinal": 1},
        {"id": "eeeeeeeeee", "text": "Unrelated filler step three", "ordinal": 2},
        {"id": "ffffffffff", "text": "Collect 4x Logs next to the stairs", "ordinal": 3},
    ]}]}
    assert build_migrations(before, after) == {}


def test_similar_and_adjacent_steps_do_migrate():
    before = {"sections": [{"slug": "bank-1", "steps": [
        {"id": "aaaaaaaaaa", "text": "Collect 3x Logs next to the stairs", "ordinal": 0},
    ]}]}
    after = {"sections": [{"slug": "bank-1", "steps": [
        {"id": "ffffffffff", "text": "Collect 4x Logs next to the stairs", "ordinal": 0},
    ]}]}
    assert build_migrations(before, after) == {"aaaaaaaaaa": "ffffffffff"}


# --- display text ------------------------------------------------------------


def test_display_text_resolves_link_markup():
    from pipeline.emit import display_text

    assert display_text("Talk to [[Father Aereck]] (3,1)") == "Talk to Father Aereck (3,1)"
    assert display_text("Talk to [[Veos (Port Sarim)|Veos]]") == "Talk to Veos"


def test_display_text_leaves_literal_brackets_alone():
    """`[Restless Ghost]` and `(3,1)` are literal text on the wiki page."""
    from pipeline.emit import display_text

    assert display_text("Pickpocket a man [Lumbridge Easy Diary]") == (
        "Pickpocket a man [Lumbridge Easy Diary]"
    )


def test_shipped_guide_has_no_wiki_markup(guide):
    for section in guide["sections"]:
        for step in section["steps"]:
            assert "[[" not in step["text"], step["text"]
            assert "]]" not in step["text"], step["text"]

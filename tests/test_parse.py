"""Regression tests for the wikitext parser.

Every test here corresponds to a row in docs/wikitext-traps.md. Each one is a
place where the obvious parser silently drops content instead of failing, which
is why they are pinned to a frozen fixture rather than the live page.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "v3_15325328.txt"

sys.path.insert(0, str(REPO))
from pipeline.parse import Parser, normalize_for_id, step_id  # noqa: E402


@pytest.fixture(scope="module")
def parsed() -> dict:
    return Parser(FIXTURE.read_text(encoding="utf-8")).parse()


def warnings_of(parsed: dict, code: str) -> list[dict]:
    return [w for w in parsed["warnings"] if w["code"] == code]


# --- structure ---------------------------------------------------------------


def test_every_checklist_becomes_a_section(parsed):
    """236 {{Checklist}} blocks in, 236 sections out. Nothing dropped."""
    raw = FIXTURE.read_text(encoding="utf-8")
    assert raw.count("{{Checklist") == 236
    assert len(parsed["sections"]) == 236


def test_all_23_episodes_are_found(parsed):
    assert [e["ordinal"] for e in parsed["episodes"]] == list(range(1, 24))


def test_every_section_belongs_to_an_episode(parsed):
    orphans = [s["title"] for s in parsed["sections"] if s["episodeOrdinal"] is None]
    assert orphans == []


def test_section_slugs_are_unique(parsed):
    slugs = [s["slug"] for s in parsed["sections"]]
    assert len(slugs) == len(set(slugs))


def test_sections_are_in_document_order(parsed):
    lines = [s["sourceLine"] for s in parsed["sections"]]
    assert lines == sorted(lines)


# --- trap 1: unterminated {{Checklist}} blocks -------------------------------


def test_unterminated_blocks_recover_and_warn(parsed):
    """Two blocks on the live page never close. Both must still produce a
    section with its steps intact, and must be reported, not swallowed."""
    warned = warnings_of(parsed, "unterminated_checklist")
    assert len(warned) == 2

    unterminated = [s for s in parsed["sections"] if not s["terminated"]]
    assert {s["title"] for s in unterminated} == {"Bank 30", "Bank 39A"}
    for section in unterminated:
        assert section["steps"], f"{section['title']} lost its steps"


def test_unterminated_block_does_not_swallow_the_next_section(parsed):
    titles = [s["title"] for s in parsed["sections"]]
    i = titles.index("Bank 30")
    assert titles[i : i + 3] == ["Bank 30", "Bank 30", "Bank 31"]
    j = titles.index("Bank 39A")
    assert titles[j : j + 3] == ["Bank 39A", "Bank 39B", "Bank 40"]


# --- trap 2: empty title= (continuation blocks) ------------------------------


def test_continuation_sections_inherit_the_previous_title(parsed):
    continuations = [s for s in parsed["sections"] if s["continuationOf"]]
    assert len(continuations) == 6
    by_id = {s["id"]: s for s in parsed["sections"]}
    for section in continuations:
        parent = by_id[section["continuationOf"]]
        assert section["title"] == parent["title"]
        assert section["bankNumber"] == parent["bankNumber"]
        assert section["slug"] != parent["slug"]


# --- trap 3: first step inline on the title line -----------------------------


def test_inline_first_step_is_not_lost(parsed):
    """`{{Checklist|title=Bank 28|* Withdraw: ...}}` puts step 1 on the opening
    line, where a startswith("*") line filter never sees it."""
    inline = [
        s
        for s in parsed["sections"]
        if s["steps"] and s["steps"][0]["sourceLine"] == s["sourceLine"]
    ]
    assert len(inline) == 5
    assert [s["title"] for s in inline] == [
        "Starting out",
        "Bank 28",
        "Bank 31",
        "Bank 132",
        "Bank 138",
    ]
    # "|*Starting Out" has no space after the bullet, and Bank 138 combines the
    # inline step with an empty title=. Both must still parse.
    assert inline[0]["steps"][0]["raw"] == "Starting Out"
    assert inline[-1]["continuationOf"] is not None


def test_hardcoded_bank_title_still_agrees_with_the_counter(parsed):
    """Bank 132 is written as a literal `title=Bank 132`, bypassing {{#expr}}.
    The simulated counter must land on the same number anyway."""
    section = next(s for s in parsed["sections"] if s["title"] == "Bank 132")
    assert section["bankNumber"] == 132


# --- trap 4: {{Var}} bank counter simulation ---------------------------------


def test_bank_numbers_agree_with_the_html_comment_oracle(parsed):
    """The page independently labels banks with <!-- Bank N -->. The simulated
    counter must agree with all 214 of them."""
    checked = [s for s in parsed["sections"] if s["bankComment"]]
    assert len(checked) == 214
    assert warnings_of(parsed, "bank_number_mismatch") == []


def test_banks_are_contiguous_from_one(parsed):
    """Banks 39, 105 and 164 exist only in A/B form -- there is no plain one --
    so contiguity holds over base numbers, not over unsuffixed sections."""
    numbers = [
        s["bankNumber"]
        for s in parsed["sections"]
        if s["bankNumber"] and not s["continuationOf"]
    ]
    assert numbers == sorted(numbers)
    assert sorted(set(numbers)) == list(range(1, max(numbers) + 1))
    assert max(numbers) == 211

    unsuffixed = {
        s["bankNumber"]
        for s in parsed["sections"]
        if s["bankNumber"] and not s["bankSuffix"] and not s["continuationOf"]
    }
    assert {39, 105, 164}.isdisjoint(unsuffixed)


def test_letter_suffixed_banks_are_preserved(parsed):
    suffixed = {
        f"{s['bankNumber']}{s['bankSuffix']}"
        for s in parsed["sections"]
        if s["bankSuffix"]
    }
    assert suffixed == {"39A", "39B", "105A", "105B", "164A", "164B"}


# --- trap 5: nested sub-steps ------------------------------------------------


def test_nesting_depth_is_preserved(parsed):
    depths = {st["depth"] for s in parsed["sections"] for st in s["steps"]}
    assert depths == {1, 2, 3}


# --- trap 6: images and videos attach to the right thing ---------------------


def test_every_extimage_attaches_to_the_following_section(parsed):
    raw = FIXTURE.read_text(encoding="utf-8")
    assert raw.count("{{Extimage") == 173
    assert sum(len(s["imageUrls"]) for s in parsed["sections"]) == 173


def test_videos_split_between_episodes_and_steps(parsed):
    raw = FIXTURE.read_text(encoding="utf-8")
    episode_videos = sum(len(e["videoIds"]) for e in parsed["episodes"])
    step_videos = sum(
        len(st["videoIds"]) for s in parsed["sections"] for st in s["steps"]
    )
    assert episode_videos == 23
    assert step_videos == 6
    assert episode_videos + step_videos == raw.count("{{Youtube")


def test_step_video_anchors_to_the_step_that_mentions_it(parsed):
    """A {{Youtube}} following a stray bullet must land on that bullet, not on
    whatever step happened to be parsed last."""
    anchored = [
        st
        for s in parsed["sections"]
        for st in s["steps"]
        if st["videoIds"]
    ]
    assert len(anchored) == 6
    for step in anchored:
        assert any(vid in step["raw"] for vid in step["videoIds"]), step["raw"]


# --- trap 7: stray bullets outside any block ---------------------------------


def test_stray_bullets_after_a_section_become_trailing_notes(parsed):
    notes = [
        st
        for s in parsed["sections"]
        for st in s["steps"]
        if st["kind"] == "trailing-note"
    ]
    assert len(notes) == 10


def test_intro_bullets_stay_in_the_preamble(parsed):
    """The six 'early GP' bullets precede every section and are guide prose,
    not steps."""
    bullets = [line for line in parsed["preamble"] if line.startswith("*")]
    assert len(bullets) == 6
    assert any("Agility Pyramid" in b for b in bullets)


def test_end_of_episode_markers_are_not_preamble(parsed):
    assert not any(line.lower().startswith("end of") for line in parsed["preamble"])


# --- step identity -----------------------------------------------------------


def test_ids_are_stable_across_runs():
    a = Parser(FIXTURE.read_text(encoding="utf-8")).parse()
    b = Parser(FIXTURE.read_text(encoding="utf-8")).parse()
    ids_a = [st["id"] for s in a["sections"] for st in s["steps"]]
    ids_b = [st["id"] for s in b["sections"] for st in s["steps"]]
    assert ids_a == ids_b


def test_step_ids_are_unique(parsed):
    ids = [st["id"] for s in parsed["sections"] for st in s["steps"]]
    assert len(ids) == len(set(ids)), "duplicate step ids -- collision suffix failed"


def test_id_ignores_link_markup_but_not_wording():
    """Adding a [[link]] around an existing name must not renumber progress;
    changing the words must."""
    assert step_id("bank-1", "Talk to [[Bob]]") == step_id("bank-1", "Talk to Bob")
    assert step_id("bank-1", "Talk to Bob") != step_id("bank-1", "Talk to Bobby")
    assert step_id("bank-1", "Talk to Bob") != step_id("bank-2", "Talk to Bob")


def test_normalize_strips_piped_links():
    assert normalize_for_id("Talk to [[Veos (Port Sarim)|Veos]] now") == "talk to veos now"


def test_ordinals_are_dense_and_ordered(parsed):
    for section in parsed["sections"]:
        assert [st["ordinal"] for st in section["steps"]] == list(
            range(len(section["steps"]))
        )


# --- text fidelity -----------------------------------------------------------


def test_step_text_keeps_wiki_link_markup(parsed):
    """annotate.py needs the [[...]] markup; parse must not strip it."""
    linked = [
        st for s in parsed["sections"] for st in s["steps"] if "[[" in st["raw"]
    ]
    assert len(linked) > 500


def test_no_step_text_is_empty_or_whitespace(parsed):
    for section in parsed["sections"]:
        for step in section["steps"]:
            assert step["raw"].strip() == step["raw"]
            assert step["raw"]


def test_cli_runs_clean_against_the_fixture(tmp_path):
    out = tmp_path / "parsed.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "pipeline" / "parse.py"),
            "--fixture",
            str(FIXTURE),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert len(doc["sections"]) == 236

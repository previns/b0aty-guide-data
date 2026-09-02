"""Regressions for the three resolution bugs found on 2026-08-31.

Each one under-reported rather than fabricating, which is why none of them
tripped a validation gate: the pipeline's guards are built to catch invented
data, and a silently dropped page looks exactly like a name the wiki does not
have. They were found by asking why a specific known-good item -- Tinderbox --
was marked missing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import resolve_wiki  # noqa: E402


def _page(title, wikitext):
    return {"title": title, "revisions": [{"slots": {"main": {"content": wikitext}}}]}


# --- bug 1: a redirect and its target in the same batch ---------------------

def test_redirect_collision_keeps_the_directly_requested_title():
    """The guide contains the typo "Tinerbox" and the correct "Tinderbox".

    The wiki redirects the first to the second, so one page comes back for two
    requested titles. Both must resolve.
    """
    query = {
        "redirects": [{"from": "Tinerbox", "to": "Tinderbox"}],
        "pages": [_page("Tinderbox", "{{Infobox Item\n|id = 590\n}}")],
    }
    found = resolve_wiki.resolve_chunk(["Tinderbox", "Tinerbox"], query)

    assert not found["Tinderbox"]["missing"], "the correct spelling must resolve"
    assert not found["Tinerbox"]["missing"], "the typo must resolve via the redirect"
    assert found["Tinderbox"]["viaRedirect"] is False
    assert found["Tinerbox"]["viaRedirect"] is True


def test_normalisation_and_redirect_apply_in_order():
    query = {
        "normalized": [{"from": "tinerbox", "to": "Tinerbox"}],
        "redirects": [{"from": "Tinerbox", "to": "Tinderbox"}],
        "pages": [_page("Tinderbox", "{{Infobox Item\n|id = 590\n}}")],
    }
    found = resolve_wiki.resolve_chunk(["tinerbox"], query)
    assert not found["tinerbox"]["missing"]
    assert found["tinerbox"]["title"] == "Tinderbox"


def test_a_title_the_wiki_lacks_is_still_missing():
    """The fix must not turn absent pages into resolutions."""
    query = {"pages": [{"title": "Nonesuch", "missing": True}]}
    found = resolve_wiki.resolve_chunk(["Nonesuch"], query)
    assert found["Nonesuch"]["missing"]


def test_a_title_absent_from_the_response_is_missing():
    found = resolve_wiki.resolve_chunk(["Unanswered"], {"pages": []})
    assert found["Unanswered"]["missing"]


# --- bug 2: positional {{Map}} coordinates ---------------------------------

def test_positional_map_coordinates_are_parsed():
    """{{Map|name=X|2930,10197|...}} is as common as the named form."""
    parsed = resolve_wiki.parse_page({
        "missing": False,
        "title": "Blast Furnace",
        "wikitext": "{{Infobox Activity\n|name = Blast Furnace\n}}\n"
                    "{{Map|name=Blast Furnace|2930,10197|mapID=10}}",
    })
    assert parsed is not None, "an activity page carrying a map must resolve"
    assert [2930, 10197, 0] in parsed["points"]


def test_named_map_coordinates_still_parse():
    parsed = resolve_wiki.parse_page({
        "missing": False,
        "title": "Somewhere",
        "wikitext": "{{Infobox Location\n}}\n{{Map|x = 3243|y = 3210}}",
    })
    assert [3243, 3210, 0] in parsed["points"]


# --- bug 3: infobox types that carry a location ----------------------------

def test_location_bearing_infoboxes_resolve_as_places():
    for box in ("Activity", "Shop", "Guild", "Dungeon"):
        parsed = resolve_wiki.parse_page({
            "missing": False,
            "title": box,
            "wikitext": f"{{{{Infobox {box}\n}}}}\n{{{{Map|1000,2000}}}}",
        })
        assert parsed is not None, f"Infobox {box} should resolve"
        assert parsed["kind"] == "place", f"Infobox {box} should be a place"


def test_a_place_never_carries_ids_that_could_be_highlighted():
    """Widening the accepted infoboxes must not widen what gets outlined."""
    parsed = resolve_wiki.parse_page({
        "missing": False,
        "title": "Blast Furnace",
        "wikitext": "{{Infobox Activity\n}}\n{{Map|2930,10197}}",
    })
    assert parsed["kind"] == "place"
    assert parsed["ids"] == [], "a place must not supply highlight ids"


def test_an_unknown_infobox_is_still_rejected():
    parsed = resolve_wiki.parse_page({
        "missing": False,
        "title": "Music",
        "wikitext": "{{Infobox Music\n}}\n{{Map|1000,2000}}",
    })
    assert parsed is None


# --- bug 4: cache keys collided on case-insensitive filesystems ------------

def test_titles_differing_only_in_case_get_different_cache_files():
    """MediaWiki treats "Small Fishing Net" and "Small fishing net" as
    different pages, and only the second exists.

    Sanitising the title alone gave file names differing only in case, which
    are the *same file* on Windows and macOS -- so whichever variant was
    fetched first decided the answer for the other, and 161 titles were
    recorded as having no wiki page. Every resolution here is silently wrong
    rather than merely missing, which is why it is worth a test.
    """
    from pathlib import Path as _Path
    a = resolve_wiki.cache_slot(_Path("cache"), "Small Fishing Net")
    b = resolve_wiki.cache_slot(_Path("cache"), "Small fishing net")
    assert a != b
    assert a.name.lower() != b.name.lower(), "collides on a case-insensitive disk"


def test_a_cache_slot_is_stable_for_the_same_title():
    from pathlib import Path as _Path
    first = resolve_wiki.cache_slot(_Path("cache"), "Tinderbox")
    second = resolve_wiki.cache_slot(_Path("cache"), "Tinderbox")
    assert first == second


def test_a_cache_slot_survives_punctuation_and_length():
    from pathlib import Path as _Path
    slot = resolve_wiki.cache_slot(_Path("cache"), "Ali's/Big|Name?" + "x" * 300)
    assert len(slot.name) < 130
    assert all(ch.isalnum() or ch in "_.-" for ch in slot.name)


# --- the sentence-case variant ---------------------------------------------

def test_sentence_case_is_tried():
    """The guide title-cases constantly; the wiki almost never does."""
    variants = resolve_wiki.title_variants("Small Fishing Net")
    assert "Small fishing net" in variants


def test_the_original_spelling_is_tried_first():
    variants = resolve_wiki.title_variants("Cup of Tea")
    assert variants[0] == "Cup of Tea"


def test_a_single_word_gains_no_case_variant():
    assert resolve_wiki.title_variants("Tinderbox") == ["Tinderbox"]


# --- guide screenshots ------------------------------------------------------

def test_an_image_on_another_host_fails_validation():
    """The links come from a page anyone can edit, so the build checks them."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    import validate

    problems = validate.image_problems({
        "sections": [{"title": "Bank 1", "imageUrls": ["https://evil.example/x.png"]}],
        "imageHashes": {},
    })
    assert problems and "unexpected host" in problems[0]


def test_an_image_with_no_hash_fails_validation():
    """The plugin refuses an unhashed image, so this would be a silently blank
    panel rather than a loud failure."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    import validate

    problems = validate.image_problems({
        "sections": [{"title": "Bank 1", "imageUrls": ["https://i.ibb.co/a/b.png"]}],
        "imageHashes": {},
    })
    assert problems and "no recorded hash" in problems[0]


def test_a_malformed_hash_fails_validation():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    import validate

    problems = validate.image_problems({
        "sections": [{"title": "Bank 1", "imageUrls": ["https://i.ibb.co/a/b.png"]}],
        "imageHashes": {"https://i.ibb.co/a/b.png": "tooshort"},
    })
    assert problems and "malformed" in problems[0]


def test_a_properly_hashed_image_passes():
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
    import validate

    assert validate.image_problems({
        "sections": [{"title": "Bank 1", "imageUrls": ["https://i.ibb.co/a/b.png"]}],
        "imageHashes": {"https://i.ibb.co/a/b.png": "a" * 64},
    }) == []

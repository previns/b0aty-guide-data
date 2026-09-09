"""How current the vendored Quest Helper is.

It went thirteen months stale without anyone noticing, and everything this
pipeline extracts comes from it. What that cost, concretely: the current
Quest Helper repairs the dwarf cannon with six `WidgetStep`s that highlight the
tool and the part, and writes most of its conditions through a `VarbitBuilder`
and named expressions. None of those idioms existed in the old copy, so the
extractor had never been taught to read them -- and the guide's author was
looking at a plugin doing things ours could not, with no way to tell that the
source we compare against was not the source they were running.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

QH = (Path(__file__).resolve().parent.parent.parent / "B0aty Guide"
      / "quest-helper-master" / "src" / "main" / "java" / "com" / "questhelper")


def test_the_vendored_copy_is_present():
    assert QH.is_dir(), f"no quest-helper source at {QH}"


def test_it_is_recent_enough_to_trust():
    """A year-old copy is a year of quests and idioms this cannot see.

    Checked by the newest source file's timestamp rather than by a version
    string, because the vendored copy is a zip extract with no git metadata.
    """
    newest = max(f.stat().st_mtime for f in QH.rglob("*.java"))
    age_days = (date.today() - date.fromtimestamp(newest)).days
    assert age_days < 400, (
        f"the vendored quest-helper is {age_days} days old. Re-download it "
        "before trusting any comparison against it: "
        "https://github.com/Zoinkwiz/quest-helper/archive/refs/heads/master.zip")


def test_the_idioms_this_pipeline_reads_are_still_in_use():
    """Each of these was found only after the copy was refreshed.

    If one disappears upstream the extractor keeps working; if one appears that
    is not listed here, nobody finds out until a player reports a quest going
    quiet. This at least pins what is known to be read.
    """
    source = " ".join(f.read_text(encoding="utf-8", errors="ignore")
                       for f in QH.rglob("*.java"))
    for idiom, what in (
        ("new WidgetStep(", "highlights part of an interface"),
        ("WidgetPresenceRequirement", "is that interface open"),
        ("new VarbitBuilder(", "fluent varbit comparisons"),
        ("puzzleWrapStep", "a puzzle wrapped around a step"),
        ("addWidgetHighlight", "marks part of an interface"),
        ("new NpcCondition(", "is that npc here"),
        ("new ObjectCondition(", "has that object appeared"),
        ("ItemOnTileRequirement", "is that item on the floor"),
    ):
        assert idiom in source, f"{idiom} ({what}) is gone from quest-helper"

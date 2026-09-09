"""Tests that read the vendored Quest Helper source, and where it isn't.

The pipeline extracts everything it knows about quests from a checkout of
quest-helper that sits *beside* this repository rather than inside it, at
``../B0aty Guide/quest-helper-master``. That is deliberate: refreshing it
rewrites guidance across the whole guide, so it is a reviewed act rather than a
dependency that drifts on its own. ``test_vendored_source.py`` exists to fail
when it goes stale, and it once went thirteen months stale unnoticed.

A GitHub runner checks out this repository alone, so that directory is simply
not there, and every test reading it failed. Seven of them, every night, which
is most of what the daily "sync failed" mail was reporting once the build itself
got far enough to run tests at all.

Failing is the wrong answer: those tests are not broken, they are inapplicable.
Passing quietly would be worse -- it would claim coverage that never ran. So
they are skipped, and pytest reports them as skipped, which is the truth.

Skipped by what the test itself reads, not by a list of file names. A list goes
stale the first time somebody adds a test and does not know to update it, and
the failure mode is a red build at 05:20 with no obvious cause.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VENDORED = REPO.parent / "B0aty Guide" / "quest-helper-master"

# How a test says it needs the vendored source: build_quest_steps.DEFAULT_SOURCE,
# a path written out, or a module-level QH constant it walks.
MARKERS = ("DEFAULT_SOURCE", "quest-helper-master", "QH /", "QH.", "QH)")

REASON = ("needs the vendored quest-helper source at "
          f"{VENDORED}, which only exists on a development machine")


def pytest_collection_modifyitems(config, items):
    if VENDORED.is_dir():
        return

    skip = pytest.mark.skip(reason=REASON)
    for item in items:
        function = getattr(item, "function", None)
        if function is None:
            continue
        try:
            source = inspect.getsource(function)
        except (OSError, TypeError):
            continue
        if any(marker in source for marker in MARKERS):
            item.add_marker(skip)

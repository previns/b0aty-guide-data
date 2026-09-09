"""The daily wiki sync builds what it says it builds.

Every run of this workflow failed, from the first, on a missing
`build/runelite/Quest.java`. The file is an input to `merge_curated`, lives
under a gitignored directory, and is downloaded by nothing -- so it existed on
a development machine and nowhere else. Nobody noticed for six days because the
mail said only "sync failed".

The repair was to pin the inputs a runner cannot produce. The repair that keeps
it repaired is here: a stage added later must be *reachable*, and this fails
when it is not, at the moment it is written rather than at 05:20 the next
morning.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "sync.yml"
PIPELINE = REPO / "pipeline"

sys.path.insert(0, str(PIPELINE))
import pin_reference  # noqa: E402

# `default=REPO / "build" / "thing.json"`, allowing the line break black would
# put in the middle of it.
RE_BUILD_ARG = re.compile(
    r'add_argument\(\s*"--([a-z-]+)"\s*,\s*type=Path\s*,\s*'
    r'default=REPO\s*/\s*"build"\s*/\s*"([a-z_]+\.json)"', re.S)
RE_STAGE = re.compile(r"^\s*python pipeline/([a-z_]+)\.py", re.M)


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def steps_named(fragment: str) -> list[dict]:
    return [s for s in workflow()["jobs"]["sync"]["steps"]
            if fragment in (s.get("name") or "")]


def stages_the_workflow_runs() -> list[str]:
    out: list[str] = []
    for step in workflow()["jobs"]["sync"]["steps"]:
        for stage in RE_STAGE.findall(step.get("run") or ""):
            out.append(stage)
    return out


def arguments(stage: str) -> tuple[set[str], set[str]]:
    """(what it writes, what it reads) as build/ file names.

    A stage can write more than one artifact and name only one of them --out:
    `annotate` also writes build/coverage.json through --coverage, and
    `resolve_wiki` writes build/unresolved.json through --unresolved. So a
    path is an output when the source actually writes to it, not when the flag
    happens to be spelled "out".
    """
    source = (PIPELINE / f"{stage}.py").read_text(encoding="utf-8")
    writes, reads = set(), set()
    for flag, name in RE_BUILD_ARG.findall(source):
        attribute = flag.replace("-", "_")
        written = re.search(r"args\.%s\.write" % re.escape(attribute), source)
        (writes if flag == "out" or written else reads).add(name)
    return writes, reads


def test_every_build_input_is_either_produced_here_or_pinned():
    run = stages_the_workflow_runs()
    produced = set()
    for stage in run:
        produced |= arguments(stage)[0]

    pinned = set(pin_reference.COMPRESSED)

    unreachable = {}
    for stage in run:
        for name in arguments(stage)[1]:
            if name not in produced and name not in pinned:
                unreachable.setdefault(name, []).append(stage)

    assert not unreachable, (
        "the sync reads build/ files nothing gives it: "
        + "; ".join(f"{name} (read by {', '.join(who)})"
                    for name, who in sorted(unreachable.items()))
        + ". Either run the stage that writes it, or add it to "
          "pin_reference.COMPRESSED and re-pack.")


def test_the_pinned_files_are_committed_and_readable():
    """A pin that is not on disk is a green test and a red workflow."""
    for name in pin_reference.COMPRESSED:
        packed = pin_reference.PINNED / (name + ".gz")
        assert packed.exists(), f"missing pinned/{name}.gz -- run --pack"
        assert packed.stat().st_size > 0
    for name in pin_reference.VERBATIM:
        packed = pin_reference.PINNED / name
        assert packed.exists(), f"missing pinned/{name} -- run --pack"


def test_quest_java_is_pinned_because_nothing_downloads_it():
    """The original failure, named. build_locations fetches the seven worldmap
    files and not this one, so only pinning puts it on a runner."""
    assert "runelite/Quest.java" in pin_reference.VERBATIM
    locations = (PIPELINE / "build_locations.py").read_text(encoding="utf-8")
    assert "Quest" not in re.search(r"SOURCES = \{(.*?)\}", locations, re.S).group(1)


def test_the_pull_request_targets_a_branch_that_exists():
    """It said `base: main` for six days. The repository only has master, so
    even a green build could not have opened the pull request."""
    opener = [s for s in workflow()["jobs"]["sync"]["steps"]
              if "create-pull-request" in (s.get("uses") or "")]
    assert len(opener) == 1
    assert opener[0]["with"]["base"] == "master"


def test_the_sync_never_moves_the_quest_helper_data():
    """A wiki sync must change only what the wiki changed. If pinned/ were
    committed by the workflow, a quest-helper upgrade could ride along inside a
    routine pull request, which is what its review exists to catch."""
    opener = [s for s in workflow()["jobs"]["sync"]["steps"]
              if "create-pull-request" in (s.get("uses") or "")][0]
    assert "pinned" not in opener["with"]["add-paths"]


def test_the_reference_data_is_unpacked_before_anything_reads_it():
    names = [s.get("name") or "" for s in workflow()["jobs"]["sync"]["steps"]]
    assert "Unpack pinned reference data" in names
    assert names.index("Unpack pinned reference data") < names.index("Build")

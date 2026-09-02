"""Stage 3f: Quest Helper's step list per quest, keyed by quest progress.

Writes build/quest_steps.json. This is what lets the guide show what to do next
inside a quest it only partly completes.

Why the guide needs it
----------------------
The route does "macro questing": it advances a quest a step or two while
passing through, rather than doing it in one sitting. So a step reads "Start X
Marks the Spot on Veos" and the player is expected to have Quest Helper open
alongside. Quest Helper stores exactly what is needed:

    QUEST_X_MARKS_THE_SPOT(VarbitID.CLUEQUEST)          <- progress lives here
    steps.put(0, speakVeosLumbridge)                    <- what to do at 0
    speakVeosLumbridge = new NpcStep(this, NpcID.VEOS_VISIBLE,
        new WorldPoint(3228, 3242, 0), "Speak to Veos ...")

Read the varbit, look up the value, and you have the instruction and its
target. The progress value is game state, so this is as provable as the
achievement-diary bits.

What does not survive extraction
--------------------------------
Two thirds of Quest Helper's slots are ConditionalStep, which chooses a branch
from zone, item and varbit requirements at runtime. Reproducing that means
porting their condition engine, which would dwarf this plugin and is not what
Plugin Hub review should be asked to read.

So a conditional contributes its *default* branch, flagged `conditional` with
its branch count. The default is the right instruction when you arrive at a
step and can be stale once you are partway through it, and 1,337 of them have
two or more branches. The plugin must present these as "Quest Helper's step",
never as certainty.

Quest Helper is BSD 2-Clause (see NOTICE.md). Unlike every other extraction in
this pipeline, this one takes their *prose*, not only ids and coordinates.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"

WP = r"new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
RE_PUT = re.compile(r"steps\.put\(\s*(\d+)\s*,\s*(\w+)\s*\)")
RE_PUT_ALIAS = re.compile(r"steps\.put\(\s*(\d+)\s*,\s*steps\.get\(\s*(\d+)\s*\)\s*\)")
RE_NPC = re.compile(
    r"(\w+)\s*=\s*new\s+NpcStep\(\s*this\s*,\s*NpcID\.(\w+)\s*,\s*" + WP
    + r'\s*,\s*"([^"]{3,400})"', re.S)
RE_OBJ = re.compile(
    r"(\w+)\s*=\s*new\s+ObjectStep\(\s*this\s*,\s*ObjectID\.(\w+)\s*,\s*" + WP
    + r'\s*,\s*"([^"]{3,400})"', re.S)
RE_DETAILED = re.compile(
    r"(\w+)\s*=\s*new\s+DetailedQuestStep\(\s*this\s*,\s*" + WP
    + r'\s*,\s*"([^"]{3,400})"', re.S)
RE_CONDITIONAL = re.compile(r"(\w+)\s*=\s*new\s+ConditionalStep\(\s*this\s*,\s*(\w+)")
RE_ADD_STEP = re.compile(r"(\w+)\.addStep\(")
# QUEST_X_MARKS_THE_SPOT(VarbitID.CLUEQUEST) / (VarPlayerID.FOO)
RE_QUEST_VAR = re.compile(r"^\s*(QUEST_\w+)\(\s*(Varbit|VarPlayer)ID\.(\w+)", re.M)
# X_MARKS_THE_SPOT(new XMarksTheSpot(), ... QuestVarbits.QUEST_X_MARKS_THE_SPOT
#
# Line-scoped on purpose. With re.DOTALL the lazy .*? runs past the end of a row
# that has no QuestVarbits on it and swallows the next few rows, which silently
# dropped a third of the quests -- X Marks the Spot among them.
RE_QUEST_ROW = re.compile(
    r"^\s*\w+\(\s*new\s+(\w+)\(\)\s*,[^\n]*?QuestVarbits\.(QUEST_\w+)", re.M)


def quest_vars(root: Path, ids: dict) -> dict[str, dict]:
    """QuestVarbits constant -> {kind, id, constant}."""
    path = root / "com/questhelper/questinfo/QuestVarbits.java"
    if not path.is_file():
        return {}
    out = {}
    for name, kind, constant in RE_QUEST_VAR.findall(path.read_text(encoding="utf-8")):
        table = ids["varbit"] if kind == "Varbit" else ids["varplayer"]
        if constant in table:
            out[name] = {"kind": kind.lower(), "id": table[constant], "constant": constant}
    return out


def helper_to_var(root: Path) -> dict[str, str]:
    """Quest helper class name -> its QuestVarbits constant."""
    path = root / "com/questhelper/questinfo/QuestHelperQuest.java"
    if not path.is_file():
        return {}
    return dict(RE_QUEST_ROW.findall(path.read_text(encoding="utf-8")))


def steps_in(text: str) -> dict[int, dict]:
    """Progress value -> the instruction at that value."""
    concrete: dict[str, dict] = {}
    for var, npc, x, y, z, desc in RE_NPC.findall(text):
        concrete[var] = {"kind": "npc", "constant": npc,
                         "point": [int(x), int(y), int(z)], "text": desc.strip()}
    for var, obj, x, y, z, desc in RE_OBJ.findall(text):
        concrete[var] = {"kind": "object", "constant": obj,
                         "point": [int(x), int(y), int(z)], "text": desc.strip()}
    for var, x, y, z, desc in RE_DETAILED.findall(text):
        concrete[var] = {"kind": "walk", "constant": None,
                         "point": [int(x), int(y), int(z)], "text": desc.strip()}

    defaults = dict(RE_CONDITIONAL.findall(text))
    branches: dict[str, int] = {}
    for var in RE_ADD_STEP.findall(text):
        branches[var] = branches.get(var, 0) + 1

    out: dict[int, dict] = {}
    for raw_value, var in RE_PUT.findall(text):
        value = int(raw_value)
        entry = concrete.get(var)
        conditional = False
        if entry is None and var in defaults:
            entry = concrete.get(defaults[var])
            conditional = True
        if entry is None:
            continue
        record = dict(entry)
        if conditional:
            record["conditional"] = True
            record["branches"] = branches.get(var, 0)
        out[value] = record

    # steps.put(1, steps.get(0)) -- the same instruction under another value.
    for value, source in {int(a): int(b) for a, b in RE_PUT_ALIAS.findall(text)}.items():
        if source in out and value not in out:
            out[value] = dict(out[source])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--ids", type=Path, default=REPO / "build" / "ids.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "quest_steps.json")
    args = ap.parse_args()

    root = args.source / "src" / "main" / "java"
    if not root.is_dir():
        print(f"no quest-helper source at {root}; writing an empty table")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"quests": {}}), encoding="utf-8")
        return 0

    ids = json.loads(args.ids.read_text(encoding="utf-8"))
    variables = quest_vars(root, ids)
    class_to_var = helper_to_var(root)

    quests: dict[str, dict] = {}
    conditional_slots = 0
    for directory in sorted((root / "com/questhelper/helpers/quests").iterdir()):
        if not directory.is_dir():
            continue
        files = list(directory.glob("*.java"))
        text = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
        steps = steps_in(text)
        if not steps:
            continue
        # The helper class that declares loadSteps is the quest's entry point.
        variable = None
        for path in files:
            var_name = class_to_var.get(path.stem)
            if var_name and var_name in variables:
                variable = variables[var_name]
                break
        if variable is None:
            continue
        conditional_slots += sum(1 for s in steps.values() if s.get("conditional"))
        quests[directory.name] = {
            "var": variable,
            "steps": {str(k): v for k, v in sorted(steps.items())},
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"source": "quest-helper (BSD 2-Clause)", "quests": quests}, indent=1),
        encoding="utf-8")

    total = sum(len(q["steps"]) for q in quests.values())
    print(f"quests            {len(quests):5}")
    print(f"step slots        {total:5}")
    print(f"  from a default  {conditional_slots:5}  (conditional; branch not evaluated)")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

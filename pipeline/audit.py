"""Check every assumption the plugin makes against the guide it is given.

    python pipeline/audit.py            # dist/guide.json
    python pipeline/audit.py --samples 8

`validate.py` answers "is this file well-formed and has coverage slipped".
This answers a different question: **where does the data say something the
plugin will act on and be wrong about**. Every check below exists because the
plugin has a mechanism that trusts that field, and the failures are the ones
that are invisible from inside the client -- a step that silently never ticks,
a highlight on a thing in another city, an instruction belonging to a quest the
player has not started.

Findings are grouped. A count of zero is worth as much as a count of ten: it is
the evidence that a class of bug is actually gone, rather than not looked for.

Nothing here is fixed automatically. A finding is either a rule to change in the
pipeline or a row for curated/, and both are decisions.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The guide's own habit: a bracket that names the reason for a step, not its
# subject. Mirrors merge_curated.RE_FETCHING.
RE_FETCHING = re.compile(
    r"^\s*(?:take|collect|buy|purchase|withdraw|bank|deposit|loot|grab|keep"
    r"|fill|pick(?!pocket))\b", re.I)

UNDERGROUND_Y = 6400


class Findings:
    """Named buckets of offending steps, reported with a sample of each."""

    def __init__(self, samples: int):
        self.samples = samples
        self.groups: dict[str, list[str]] = collections.OrderedDict()
        self.checked: dict[str, int] = collections.OrderedDict()

    def check(self, name: str, population: int) -> None:
        """Record that a class was looked at, and how many could have failed."""
        self.checked[name] = population
        self.groups.setdefault(name, [])

    def fail(self, name: str, detail: str) -> None:
        self.groups.setdefault(name, []).append(detail)

    def report(self) -> int:
        bad = 0
        for name, hits in self.groups.items():
            population = self.checked.get(name)
            scope = f" of {population}" if population is not None else ""
            if not hits:
                print(f"  ok    {name}  (0{scope})")
                continue
            bad += len(hits)
            print(f"  FAIL  {name}  ({len(hits)}{scope})")
            for detail in hits[:self.samples]:
                print(f"          {detail}")
            if len(hits) > self.samples:
                print(f"          ... and {len(hits) - self.samples} more")
        return bad


def point_ok(raw) -> bool:
    return (isinstance(raw, list) and len(raw) >= 3
            and all(isinstance(v, int) for v in raw[:3]))


def every_instruction(guide: dict):
    """Each shipped instruction and where it came from, branches included."""
    def walk(owner, key, record):
        yield owner, key, record
        for branch in record.get("whenIn", ()):
            yield from walk(owner, key, branch)

    for name, helper in guide.get("questHelpers", {}).items():
        for value, record in helper.get("steps", {}).items():
            yield from walk(name, value, record)
    for bit, record in guide.get("diaryTasks", {}).items():
        yield from walk("diary", bit, record)


def milestone_condition_ok(condition):
    """The renderer's deliberately smaller completion-condition contract."""
    if not isinstance(condition, dict) or len(condition) != 1:
        return False
    for op in ("all", "any"):
        if op in condition:
            parts = condition[op]
            return isinstance(parts, list) and bool(parts) and all(milestone_condition_ok(p) for p in parts)
    var = condition.get("var")
    if not isinstance(var, dict) or not set(var) <= {"kind", "id", "value", "op", "bit", "set"}:
        return False
    if var.get("kind") not in ("varbit", "varplayer") or type(var.get("id")) is not int or var["id"] < 0:
        return False
    if "bit" in var:
        return (type(var["bit"]) is int and 0 <= var["bit"] <= 31
                and "value" not in var and "op" not in var
                and ("set" not in var or type(var["set"]) is bool))
    return (type(var.get("value")) is int and "set" not in var
            and var.get("op", "==") in ("==", "!=", ">", ">=", "<", "<="))


def steps_of(guide: dict):
    for section in guide["sections"]:
        for step in section["steps"]:
            if step.get("kind") == "step":
                yield section, step


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--guide", type=Path, default=REPO / "dist" / "guide.json")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    guide = json.loads(args.guide.read_text(encoding="utf-8"))
    steps = list(steps_of(guide))
    helpers = guide.get("questHelpers", {})
    tasks = guide.get("diaryTasks", {})
    found = Findings(args.samples)

    def where(section, step) -> str:
        return f"[{section['title']}] {step['text'][:64]}"

    # --- the file refers to itself consistently ---------------------------
    print("references")
    found.check("every step id is unique", len(steps))
    seen_ids: dict[str, str] = {}
    for section, step in steps:
        if step["id"] in seen_ids:
            found.fail("every step id is unique",
                       f"{step['id']} also on {seen_ids[step['id']]}")
        seen_ids[step["id"]] = where(section, step)

    for field, table, label in (("questHelper", helpers, "quest helper"),
                                ("questContext", helpers, "carried quest"),
                                ("diaryTask", tasks, "diary task")):
        population = sum(1 for _, s in steps if s.get(field))
        found.check(f"every {label} key is shipped", population)
        for section, step in steps:
            key = step.get(field)
            if key and key not in table:
                found.fail(f"every {label} key is shipped",
                           f"{key} missing -- {where(section, step)}")

    found.check("every migration lands on a real step", len(guide.get("migrations", {})))
    for old, new in guide.get("migrations", {}).items():
        if new not in seen_ids:
            found.fail("every migration lands on a real step", f"{old} -> {new}")

    # --- coordinates and ids are the shapes the plugin unpacks ------------
    print("\nshapes")
    targets = [(sec, st) for sec, st in steps if st.get("target")]
    found.check("every target point is three numbers", len(targets))
    found.check("a target with ids names its kind", len(targets))
    for section, step in targets:
        target = step["target"]
        for raw in target.get("points", []):
            if not point_ok(raw):
                found.fail("every target point is three numbers",
                           f"{raw} -- {where(section, step)}")
        if target.get("ids") and not target.get("kind"):
            found.fail("a target with ids names its kind", where(section, step))

    instructions = list(every_instruction(guide))
    found.check("every instruction gives the player something", len(instructions))
    found.check("every instruction point is three numbers", len(instructions))
    found.check("an icon is a real item id", len(instructions))
    found.check("a branch condition can be answered", len(instructions))
    found.check("an interface mark names an interface", len(instructions))
    found.check("an interface mark carries only what the plugin reads", len(instructions))
    for owner, key, record in instructions:
        tag = f"{owner}@{key}"
        if not (record.get("text") or record.get("point") or record.get("ids")):
            found.fail("every instruction gives the player something", tag)
        if record.get("point") is not None and not point_ok(record["point"]):
            found.fail("every instruction point is three numbers",
                       f"{tag} {record['point']}")
        if "icon" in record and not isinstance(record["icon"], int):
            found.fail("an icon is a real item id", f"{tag} {record['icon']!r}")
        when = record.get("when")
        for mark in record.get("widgets") or []:
            # Interface zero is a real interface, so a mark that lost its id
            # would ring something arbitrary rather than nothing.
            if not mark.get("interface"):
                found.fail("an interface mark names an interface", f"{tag} {mark}")
            if not set(mark) <= {"interface", "child", "children", "item",
                                 "model", "says", "named"}:
                found.fail("an interface mark carries only what the plugin reads",
                           f"{tag} {mark}")
        if when is not None and not condition_ok(when):
            found.fail("a branch condition can be answered", f"{tag} {when}")

    # --- the rules the plugin acts on -------------------------------------
    print("\nrules")
    goals = [(sec, s) for sec, s in steps if any(k in s for k in (
        "questStopItems", "questStopValue", "questStopCondition", "questStopUnresolved"))]
    found.check("explicit quest goals have one supported completion signal", len(goals))
    for section, step in goals:
        signals = [k for k in ("questStopItems", "questStopValue", "questStopCondition", "questStopUnresolved") if step.get(k)]
        helper = helpers.get(step.get("questHelper"), {})
        valid = (len(signals) == 1 and step.get("questStep") and helper
                 and not any(k in step for k in ("questDoneAt", "questDoneAtPanel", "questCompletes", "questStartOnly")))
        if "questStopValue" in step:
            valid = valid and type(step["questStopValue"]) is int and 0 < step["questStopValue"] <= helper.get("lastValue", 0)
        if "questStopCondition" in step:
            valid = valid and milestone_condition_ok(step["questStopCondition"])
        if not valid:
            found.fail("explicit quest goals have one supported completion signal", where(section, step))
    quest_steps = [(sec, st) for sec, st in steps if st.get("questStep")]
    found.check("a step doing a quest is not fetching for one", len(quest_steps))
    found.check("a step doing a quest names only that quest", len(quest_steps))
    for section, step in quest_steps:
        if RE_FETCHING.match(step["text"]):
            found.fail("a step doing a quest is not fetching for one",
                       where(section, step))
        if sum(1 for t in step.get("tags", []) if t.get("quest")) > 1:
            found.fail("a step doing a quest names only that quest",
                       where(section, step))

    bounded = [(sec, st) for sec, st in steps if st.get("questDoneAt") is not None]
    found.check("a boundary is inside its quest", len(bounded))
    found.check("a boundary belongs to a step doing that quest", len(bounded))
    for section, step in bounded:
        helper = helpers.get(step.get("questHelper") or "")
        if helper is None:
            found.fail("a boundary belongs to a step doing that quest",
                       where(section, step))
            continue
        if not step.get("questStep"):
            found.fail("a boundary belongs to a step doing that quest",
                       where(section, step))
        if step["questDoneAt"] > helper.get("lastValue", 0):
            found.fail("a boundary is inside its quest",
                       f"{step['questDoneAt']} > {helper.get('lastValue')} -- "
                       + where(section, step))

    order: dict[str, int] = {}
    found.check("boundaries never go backwards", len(bounded))
    for section, step in steps:
        key, at = step.get("questHelper"), step.get("questDoneAt")
        if key is None or at is None:
            continue
        if key in order and at < order[key]:
            found.fail("boundaries never go backwards",
                       f"{key} {order[key]} then {at} -- " + where(section, step))
        order[key] = at

    carried = [(sec, st) for sec, st in steps if st.get("questContext")]
    advisory = [(sec, st) for sec, st in steps if st.get("advice")]
    found.check("advice never drives a quest", len(advisory))
    for section, step in advisory:
        if step.get("questStep"):
            found.fail("advice never drives a quest", where(section, step))

    found.check("a carried quest is not also the step's own", len(carried))
    for section, step in carried:
        if step.get("questStep"):
            found.fail("a carried quest is not also the step's own",
                       where(section, step))

    # --- completion signals ------------------------------------------------
    print("\ncompletion")
    diary = [(sec, st) for sec, st in steps
             if (st.get("completion") or {}).get("bit") is not None]
    found.check("a diary bit is one of the 32", len(diary))
    found.check("a diary step's task key matches its bit", len(diary))
    for section, step in diary:
        done = step["completion"]
        if not 0 <= done["bit"] <= 31:
            found.fail("a diary bit is one of the 32",
                       f"bit {done['bit']} -- " + where(section, step))
        key = step.get("diaryTask")
        if key and key != f"{done['varplayer']}:{done['bit']}":
            found.fail("a diary step's task key matches its bit",
                       f"{key} vs {done['varplayer']}:{done['bit']}")

    acquires = [(sec, st) for sec, st in steps if st.get("acquires")]
    found.check("a step that ticks on holding names what to hold", len(acquires))
    for section, step in acquires:
        if not step.get("items") or any(not i.get("ids") for i in step["items"]):
            found.fail("a step that ticks on holding names what to hold",
                       where(section, step))

    arrives = [(sec, st) for sec, st in steps if st.get("arrivesAt")]
    found.check("a step that ticks on arriving has somewhere to arrive", len(arrives))
    for section, step in arrives:
        points = (step.get("destination") or {}).get("points") or []
        points += (step.get("target") or {}).get("points") or []
        if not points:
            found.fail("a step that ticks on arriving has somewhere to arrive",
                       where(section, step))

    # --- things that will silently point at nothing ------------------------
    print("\nguidance")
    sellers = [(sec, st) for sec, st in steps if st.get("sellers")]
    found.check("every shopkeeper offered can be outlined", len(sellers))
    for section, step in sellers:
        for seller in step["sellers"]:
            if not seller.get("ids"):
                found.fail("every shopkeeper offered can be outlined",
                           f"{seller.get('name')} -- " + where(section, step))

    tele = [(sec, st) for sec, st in steps if st.get("teleport")]
    found.check("a teleport that is an item says which item", len(tele))
    for section, step in tele:
        if not step["teleport"].get("ids") and step["teleport"].get("collection"):
            found.fail("a teleport that is an item says which item",
                       where(section, step))

    upper = [(sec, st) for sec, st in steps
             if any(p[2] > 0 or p[1] >= UNDERGROUND_Y
                    for p in ((st.get("target") or {}).get("points") or [])
                    if point_ok(p))]
    guessed = [(sec, st) for sec, st in upper
               if not st.get("approach")
               and not any(p[2] == 0 and p[1] < UNDERGROUND_Y
                           for p in ((st.get("destination") or {}).get("points") or [])
                           if point_ok(p))]
    print(f"  note  a target on another level: {len(upper)} steps, "
          f"{len(upper) - len(guessed)} answered by a known way up or a ground "
          f"destination, {len(guessed)} left to the nearest-staircase guess")

    inferred = [(sec, st) for sec, st in steps
                if (st.get("target") or {}).get("confidence") == "inferred"]
    print(f"  note  targets matched by name at runtime: {len(inferred)} "
          f"(no ids; wrong ones match nothing rather than the wrong thing)")

    unresolved = sum(1 for _, st in steps for i in st.get("items", [])
                     if not i.get("ids"))
    print(f"  note  item entries with no id: {unresolved}")

    # What is left blank, once the lines that are meant to be blank are taken
    # out. This is the number worth watching: a step the guide wrote as advice
    # needs no guidance, and counting it as a gap hid the real ones.
    advice = [st for _, st in steps if st.get("advice")]
    def bare(step):
        target = step.get("target") or {}
        return not (target.get("ids") or target.get("name") or step.get("items")
                    or step.get("questHelper") or step.get("diaryTask")
                    or step.get("teleport") or step.get("completion")
                    or step.get("banking") or step.get("dialogue")
                    or (step.get("destination") or {}).get("points"))
    blank = [st for _, st in steps if bare(st)]
    gaps = [st for st in blank if not st.get("advice")]
    print(f"  note  steps the guide writes as advice: {len(advice)} "
          f"({sum(1 for st in advice if bare(st))} of them carrying nothing, correctly)")
    print(f"  note  steps carrying nothing that are not advice: {len(gaps)} "
          f"-- these are the real gaps")

    # --- fields that only mean something with their companion ---------------
    print("\ncompanions")
    found.check("spread only where there is a point to spread from", len(instructions))
    found.check("a dialogue option has words on it", len(instructions))
    found.check("a zone box is the right way round", len(instructions))
    for owner, key, record in instructions:
        tag = f"{owner}@{key}"
        if record.get("spread") and not record.get("point"):
            found.fail("spread only where there is a point to spread from", tag)
        for said in record.get("dialogue", []):
            if not said.strip():
                found.fail("a dialogue option has words on it", tag)
        for box in (record.get("when") or {}).get("zone", []):
            if len(box) >= 6 and (box[0] > box[3] or box[1] > box[4] or box[2] > box[5]):
                found.fail("a zone box is the right way round", f"{tag} {box}")

    withdraws = [(sec, st) for sec, st in steps if st.get("withdraw")]
    found.check("a withdraw step says what to withdraw", len(withdraws))
    for section, step in withdraws:
        if not step.get("items"):
            found.fail("a withdraw step says what to withdraw", where(section, step))

    counted = [(sec, st) for sec, st in steps for i in st.get("items", [])
               if i.get("count") is not None]
    found.check("an item count is a real quantity", len(counted))
    for section, step in steps:
        for item in step.get("items", []):
            if item.get("count") is not None and item["count"] < 1:
                found.fail("an item count is a real quantity",
                           f"{item['name']} x{item['count']} -- " + where(section, step))

    # A carried quest has exactly two honest origins: a parent step above it
    # doing that quest, or a "Start X ... Complete X" span it sits inside. This
    # used to say "nested", which was the only origin at the time; a step in a
    # span is a plain sibling, and stating the rule as nesting would have meant
    # deleting the check rather than restating it.
    found.check("a carried quest comes from a parent or a span", len(carried))
    for section, step in carried:
        quest = step["questContext"]
        if step.get("depth", 1) > 1 and any(
                above.get("questStep") and above.get("questHelper") == quest
                for above in section["steps"]
                if above["ordinal"] < step["ordinal"]
                and above.get("depth", 1) < step.get("depth", 1)):
            continue
        doing = [s for s in section["steps"]
                 if s.get("questStep") and s.get("questHelper") == quest]
        inside = (len(doing) >= 2
                  and doing[0]["ordinal"] < step["ordinal"] < doing[-1]["ordinal"])
        if not inside:
            found.fail("a carried quest comes from a parent or a span",
                       where(section, step))

    # A handover names a step of Quest Helper's own list, so it has to be one
    # that exists -- a position past the end is never reached and the guide step
    # hangs there for ever.
    handovers = [(sec, st) for sec, st in steps
                 if st.get("questDoneAtPanel") is not None]
    found.check("a handover points at a real quest helper step", len(handovers))
    found.check("a handover is a position the plugin can observe", len(handovers))
    found.check("a handover is not on the step that completes the quest", len(handovers))
    for section, step in handovers:
        helper = guide["questHelpers"].get(step.get("questHelper")) or {}
        panels = helper.get("panelCount") or 0
        if not 0 < step["questDoneAtPanel"] < panels:
            found.fail("a handover points at a real quest helper step",
                       where(section, step))
        if step.get("questCompletes"):
            found.fail("a handover is not on the step that completes the quest",
                       where(section, step))
        # The plugin meets a hand-over by comparing it against the panel of the
        # instruction being shown. A position no instruction carries can never
        # be reached, and the step would wait for ever.
        seen = {candidate.get("panel")
                for record in (helper.get("steps") or {}).values()
                for candidate in [record] + (record.get("whenIn") or [])}
        if step["questDoneAtPanel"] not in seen:
            found.fail("a handover is a position the plugin can observe",
                       where(section, step))

    # Nothing in a span may be advice: it has nothing to guide to, and pointing
    # Quest Helper at it is how a line about max hits started driving a quest.
    found.check("a carried quest is never on advice", len(carried))
    for section, step in carried:
        if step.get("advice"):
            found.fail("a carried quest is never on advice", where(section, step))

    # Not a failure: a shopkeeper with no wiki coordinate is still outlined the
    # moment they load, which is the part that matters in the room. Only the
    # walk to a shop in another city is lost.
    unplaced = sum(1 for _, st in sellers for s in st["sellers"]
                   if not any(point_ok(p) for p in s.get("points", [])))
    print(f"  note  shopkeepers offered with no coordinate: {unplaced} "
          f"(outlined on arrival, but not walked to)")

    found.check("shopkeepers are only offered when nobody was named", len(sellers))
    for section, step in sellers:
        if (step.get("target") or {}).get("kind") == "npc":
            found.fail("shopkeepers are only offered when nobody was named",
                       where(section, step))

    found.check("a teleport names its method", len(tele))
    for section, step in tele:
        if not (step["teleport"].get("via") or "").strip():
            found.fail("a teleport names its method", where(section, step))

    named_targets = [(sec, st) for sec, st in steps
                     if (st.get("target") or {}).get("confidence") == "inferred"]
    found.check("a name-matched target has a name to match", len(named_targets))
    for section, step in named_targets:
        target = step["target"]
        if not (target.get("names") or [target.get("name")])[0]:
            found.fail("a name-matched target has a name to match",
                       where(section, step))

    # --- text the player will read -----------------------------------------
    print("\ntext")
    LEFTOVERS = ('{{', '[[', '}}', '" +', '\\n', '<br')
    found.check("no step text carries wiki markup", len(steps))
    for section, step in steps:
        for mark in LEFTOVERS:
            if mark in step["text"]:
                found.fail("no step text carries wiki markup",
                           f"{mark!r} -- " + where(section, step))
                break

    found.check("no instruction carries source markup", len(instructions))
    for owner, key, record in instructions:
        said = record.get("text") or ""
        for mark in LEFTOVERS:
            if mark in said:
                found.fail("no instruction carries source markup",
                           f"{owner}@{key} {mark!r} {said[:40]}")
                break

    # --- the quest timeline reads forwards ---------------------------------
    print("\ntimeline")
    last_for: dict[str, tuple] = {}
    for section, step in steps:
        key = step.get("questHelper")
        if key and step.get("questStep"):
            last_for[key] = (section, step)
    completes = [(sec, st) for sec, st in steps if st.get("questCompletes")]
    found.check("only the guide's last step for a quest ends it", len(completes))
    for section, step in completes:
        key = step.get("questHelper")
        if key not in last_for or last_for[key][1]["id"] != step["id"]:
            found.fail("only the guide's last step for a quest ends it",
                       where(section, step))

    found.check("a step never both ends a quest and stops partway", len(completes))
    for section, step in completes:
        if step.get("questDoneAt") is not None:
            found.fail("a step never both ends a quest and stops partway",
                       where(section, step))

    print()
    bad = found.report()
    print()
    print(f"steps {len(steps)}, instructions {len(instructions)}, "
          f"quest helpers {len(helpers)}, diary tasks {len(tasks)}")
    print("audit clean" if bad == 0 else f"{bad} findings")
    return 1 if bad else 0


def condition_ok(when: dict) -> bool:
    """Whether a branch condition is one the plugin can actually evaluate."""
    if "open" in when:
        # "Is that interface on screen" -- a widget lookup, and the thing that
        # makes a puzzle inside a menu answerable at all.
        return isinstance(when["open"], int)
    if "here" in when:
        # "Is that thing in the scene" -- answered by the same walk the tracker
        # already does. Ids only: a constant that did not resolve leaves the
        # condition unanswerable, which is what this check is for.
        found = when["here"]
        return (found.get("kind") in ("npc", "object", "groundItem")
                and bool(found.get("ids")))
    if "not" in when:
        return condition_ok(when["not"])
    for joiner in ("all", "any"):
        if joiner in when:
            return bool(when[joiner]) and all(condition_ok(p) for p in when[joiner])
    if "item" in when:
        return bool(when["item"].get("ids"))
    if "zone" in when:
        return bool(when["zone"]) and all(
            isinstance(box, list) and len(box) >= 6 for box in when["zone"])
    if "var" in when:
        # A var comparison the plugin evaluates: either a value with an
        # operator, or a bit position with the state it should be in. Anything
        # else is a shape this does not read, and shipping it would have the
        # plugin quietly answering "false" to a branch that holds.
        var = when["var"]
        if var.get("kind") not in ("varbit", "varplayer") or var.get("id") is None:
            return False
        if var.get("bit") is not None:
            return isinstance(var.get("set"), bool)
        return var.get("value") is not None and var.get("op") in (
            "==", "!=", "<", "<=", ">", ">=")
    return False


if __name__ == "__main__":
    raise SystemExit(main())

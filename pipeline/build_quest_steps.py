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
step and can be stale once you are partway through it, and most of them have
two or more branches. The plugin must present these as "Quest Helper's step",
never as certainty.

Eleven conditionals default to a stand-in their own class replaces at runtime
-- an empty step, "Unknown state.", or Pirate's Treasure asking you to open the
quest journal. Those fall back to the *last* branch added, because a
ConditionalStep returns the first branch whose conditions hold and Quest Helper
writes them most-advanced first.

How the source is read
----------------------
Constructor calls, parsed with a bracket reader rather than one regex per
constructor shape. Matching shapes was the first attempt and it resolved 76% of
the step slots; it knew `new NpcStep(this, NpcID.X, new WorldPoint(...),
"text")` and nothing else, so the 141 NpcSteps and 97 ObjectSteps that name no
coordinate, the 605 DetailedQuestSteps that are pure prose, and every
ConditionalStep whose default was itself a ConditionalStep all came out empty.
Gertrude's Cat shipped one step of five, and "continue Gertrude's Cat" pointed
at nothing.

Reading it properly is 96% of the slots, and three separate things had to be
true for that:

  * arguments split at the *top level*. `new ObjectStep(this, ObjectID.X,
    point, req)` has no description of its own, and "the first string anywhere
    inside" lifts the name out of the nested `new ItemRequirement("Coins", ...)`
    and shows it as the instruction.
  * delegation followed. A step naming neither a thing nor a place passes the
    question to the step handed to it -- through conditional chains, through
    `steps.put(4, findFluffsKitten())` into the method, and through
    `new RumSmugglingStep(this)` into the class's own `super(questHelper, ...)`.
  * one table per registered helper, not per folder. Three folders hold more
    than one; Recipe for Disaster holds ten, and reading their steps.put calls
    together merged ten unrelated tables under one set of progress values.
    That shipped -- value 80 pointed at a chompy bird instead of Murphy.

Quests are keyed by their QuestHelperQuest enum name, with the RuneLite Quest
constant and the folder as aliases. The folder was the key until then, and a
folder is neither one quest nor named after one: eleven quests the route tags
-- Underground Pass, Tribal Totem, Romeo & Juliet -- were dropped for no better
reason than a different spelling.

Quest Helper is BSD 2-Clause (see NOTICE.md). Unlike every other extraction in
this pipeline, this one takes their *prose*, not only ids and coordinates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO.parent / "B0aty Guide" / "quest-helper-master"
# ---------------------------------------------------------------------------
# Reading Quest Helper's step declarations
#
# Quest Helper writes its steps as ordinary Java constructor calls, so this
# reads them the way a compiler would rather than pattern-matching one
# constructor shape at a time. Matching shapes is what shipped first and it
# resolved 76% of the step slots: it knew `new NpcStep(this, NpcID.X,
# new WorldPoint(...), "text")` and nothing else, so the 141 NpcSteps and 97
# ObjectSteps that name no coordinate, the 605 DetailedQuestSteps that are pure
# prose, and every ConditionalStep whose default was itself a ConditionalStep
# all came out empty. Gertrude's Cat shipped one step of five, which is why
# "continue Gertrude's Cat" pointed at nothing.
#
# Arguments are split at the top level only. That matters: `new ObjectStep(this,
# ObjectID.X, point, req)` has no description of its own, and taking "the first
# string anywhere inside" would lift the name out of the nested
# `new ItemRequirement("Coins", ...)` and present it as the instruction.
# ---------------------------------------------------------------------------

RE_WP = re.compile(r"^new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)")
RE_ID_CONST = re.compile(r"\b(NpcID|ObjectID|NullObjectID|QHObjectID)\.([A-Z0-9_]+)")
RE_CLASS = re.compile(r"\bclass\s+(\w+)\s+extends\s+(\w+)")
# A step class imported from another quest's package.
RE_QUEST_IMPORT = re.compile(
    r"import\s+com\.questhelper\.helpers\.quests\.(\w+)\.(\w+)\s*;")
RE_ASSIGNED_TO = re.compile(r"(\w+)\s*=\s*$")
RE_NEW = re.compile(r"\bnew\s+([A-Z]\w*)\s*\(")
RE_SUPER = re.compile(r"\bsuper\s*\(")
# private QuestStep getTalkToGertrude() { ... return talkToGertrude; }
RE_RETURN = re.compile(r"\breturn\s+([^;]+);")
# steps.put(0, x); steps.put(0, x = build()); steps.put(0, build());
# RuneLite's Quest name -> the Quest Helper folder for the same sub-quest.
RFD_FOLDERS = {
    "Recipe for Disaster - Another Cook's Quest": "recipefordisasterstart",
    "Recipe for Disaster - Mountain Dwarf": "recipefordisasterdwarf",
    "Recipe for Disaster - Wartface & Bentnoze": "recipefordisasterwartfaceandbentnoze",
    "Recipe for Disaster - King Awowogei": "recipefordisastermonkeyambassador",
    "Recipe for Disaster - Culinaromancer": "recipefordisasterfinale",
}
RE_COMPLEX_STATE = re.compile("extends[ ]+ComplexStateQuestHelper")
RE_PUT = re.compile(r"steps\.put\(\s*(\d+)\s*,\s*([^;]+?)\s*\)\s*;")
# Three quests build the map instead, as a chain of .put off an ImmutableMap
# builder rather than a named variable. Underground Pass is one, and it
# registers eleven steps that way.
RE_BUILDER = "ImmutableMap.Builder<Integer, QuestStep>"
RE_BUILDER_PUT = re.compile(r"\.put\(\s*(\d+)\s*,\s*([^;()]+?)\s*\)")
RE_PUT_ALIAS = re.compile(r"steps\.put\(\s*(\d+)\s*,\s*steps\.get\(\s*(\d+)\s*\)\s*\)")

# Types whose constructor says everything there is to know. Anything else may
# delegate to a step handed to it, which is how ConditionalStep and every
# hand-written subclass names its default branch.
LEAF_TYPES = frozenset({
    "NpcStep", "ObjectStep", "DetailedQuestStep", "ItemStep", "DigStep",
    "WidgetStep", "EmoteStep", "NpcEmoteStep", "ObjectEmoteStep",
    "NpcFollowerStep", "WidgetDetailsStep",
})

# Long enough for the longest instruction Quest Helper writes, short enough
# that a malformed capture cannot put a page of source on the overlay.
MAX_TEXT = 400

# Built rather than typed: this file is edited by scripts often enough that a
# literal backslash in a non-raw string has been mangled into a control
# character more than once.
BACKSLASH = chr(92)


def _skip_quoted(src: str, i: int) -> int:
    """Index just past the string or char literal starting at i."""
    quote = src[i]
    i += 1
    while i < len(src):
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == quote:
            return i + 1
        i += 1
    return i


def strip_comments(src: str) -> str:
    """Java source with comments blanked and string literals untouched.

    Needed before any bracket counting. Quest Helper annotates ids inline --
    `ObjectID.GIANTS_FOUNDRY_CRUCIBLE_MULTI /* Crucible (empty */` -- and that
    unbalanced paren inside a comment would otherwise swallow the rest of the
    file. Newlines are kept so line numbers still mean something.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = _skip_quoted(src, i)
            out.append(src[i:j])
            i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * src.count("\n", i, j))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def read_args(src: str, opening: int) -> list[str]:
    """The top-level arguments of the call whose '(' sits at `opening`.

    Nested calls, arrays and generics stay inside a single argument, so an
    argument is either something this constructor was given or nothing.
    """
    depth = 0
    start = opening + 1
    args: list[str] = []
    i, n = opening, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            i = _skip_quoted(src, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append(src[start:i])
                return [a.strip() for a in args]
        elif c == "," and depth == 1:
            args.append(src[start:i])
            start = i + 1
        i += 1
    return []


# private static final int VARBIT_MARLEY_LINE = 1234;  /  int SOME_VAR = 5;
RE_INT_CONSTANT = re.compile(
    r"\b(?:static\s+)?(?:final\s+)?(?:static\s+)?(?:final\s+)?int\s+"
    r"(\w+)\s*=\s*(-?\d+)\s*;")


def int_constants(text: str) -> dict[str, int]:
    """The file's own named numbers.

    Quest Helper often gives a varbit a name at the top of the quest --
    `VARBIT_MARLEY_LINE = 1234` -- rather than writing `VarbitID.SOMETHING`.
    Reading only the shared id classes left two hundred and twenty varbit
    conditions unresolved, and a branch with an unresolved condition is dropped
    whole.
    """
    return {name: int(value) for name, value in RE_INT_CONSTANT.findall(text)}


def declarations(text: str) -> dict[str, tuple[str, list[str]]]:
    """Every `name = new Type(args)` in the source, by name.

    Each `class X extends Y` is registered under its own name as well, standing
    for the `super(questHelper, ...)` call it makes, so `new RumSmugglingStep(
    this)` reaches the step that class hands to its parent. Fifty of Priest in
    Peril's slots are a subclass of exactly that shape.
    """
    out: dict[str, tuple[str, list[str]]] = {}
    for match in RE_NEW.finditer(text):
        before = RE_ASSIGNED_TO.search(text[max(0, match.start() - 120):match.start()])
        if before:
            out[before.group(1)] = (match.group(1), read_args(text, match.end() - 1))

    for name, value in int_constants(text).items():
        out.setdefault(name, (INT_CONSTANT, [str(value)]))

    # `pw = fixCannon.puzzleWrapStepWithDefaultText("...")` -- pw is fixCannon
    # wrapped, and the wrapper carries none of the branches. Reading it as its
    # own step lost every branch of the puzzle it wraps.
    for name, wrapped in RE_PUZZLE_WRAP.findall(text):
        out.setdefault(name, (ALIAS, [wrapped]))

    # `blueSheepBurned = blueSheepState.eq(6)`, `bonesNearby = or(a, b, c)` --
    # a requirement given a name without a `new` anywhere in sight. Quest Helper
    # writes most of its conditions this way now, and a name with no declaration
    # is a condition that cannot be read, which drops the branch it guards.
    # Recorded as the expression itself; requirement_of reads it when asked.
    for name, expression in RE_NAMED_EXPRESSION.findall(text):
        if name not in out:
            out[name] = (EXPRESSION, [expression.strip()])

    # Each super(questHelper, ...) belongs to the class it is written inside,
    # which is the nearest one declared above it. `text` is every file in the
    # quest's folder joined together, so handing every super() call to every
    # class -- and letting setdefault give them all the first one -- crossed
    # sibling solvers over: A Kingdom Divided declares StonePuzzleStep and
    # StatuePuzzle side by side, and both resolved to "Solve the statue
    # puzzle." It stayed invisible while PuzzleWrapperStep's own sentence
    # overwrote the result.
    declared = [(m.start(), m.group(1), m.group(2)) for m in RE_CLASS.finditer(text)]
    found: dict[str, list[list[str]]] = {}
    for match in RE_SUPER.finditer(text):
        args = read_args(text, match.end() - 1)
        if not args or args[0] != "questHelper":
            continue
        enclosing = None
        for start, name, parent in declared:
            if start > match.start():
                break
            enclosing = (name, parent)
        if enclosing:
            out.setdefault(enclosing[0], (enclosing[1], args))
            found.setdefault(enclosing[0], []).append(args)

    # A solver whose only sentence belongs to the step class nested inside it.
    # Scrambled's EggSolver says nothing itself: its instruction -- "Rotate the
    # piece until you're prompted to move it" -- is on the private EggPieceStep
    # it builds, which nothing else can name. Taking it is only safe for a
    # class that has none of its own, and only from a class written inside its
    # braces, so the two never compete.
    for start, name, parent in declared:
        if name in out:
            continue
        body = _class_body(text, start)
        if body is None:
            continue
        inside = [(at, other) for at, other, _ in declared
                  if body[0] < at < body[1] and other in found]
        if len(inside) != 1:
            continue
        out[name] = (parent, found[inside[0][1]][0])
    return out


def _class_body(text: str, start: int) -> tuple[int, int] | None:
    """The span between a class declaration's own braces, or nothing.

    Counted rather than guessed: a nested class is inside these, a sibling
    declared after them is not, and that is the whole difference between a
    solver's own instruction and the next class's.
    """
    opened = text.find("{", start)
    if opened == -1:
        return None
    depth = 0
    for at in range(opened, len(text)):
        if text[at] == "{":
            depth += 1
        elif text[at] == "}":
            depth -= 1
            if depth == 0:
                return (opened, at)
    return None


def _first_text(args: list[str]) -> str | None:
    """The first argument that is a plain string literal, unescaped.

    A literal only: `originalTextStart + bossName + originalTextEnd` is built at
    runtime and there is no honest way to render it here.
    """
    for arg in args:
        body = joined_literals(arg)
        if body is not None and len(body) >= 3:
            return body[:MAX_TEXT]
    return None


def joined_literals(arg: str) -> str | None:
    """`"Speak to Marley in the Edgeville" + " Ruins."` read as one sentence.

    Quest Helper wraps its longer instructions across lines with `+`, and taking
    everything between the first quote and the last swallowed the operator and
    the indentation with it. 453 instructions carried that, and the overlay
    showed the raw Java.

    Stops at the first term that is not a literal: `text + bossName + more`
    is assembled at runtime, and half a sentence is worse than none.
    """
    arg = arg.strip()
    if not arg.startswith('"'):
        return None

    parts = []
    i = 0
    while i < len(arg) and arg[i] == '"':
        end = _skip_quoted(arg, i)
        parts.append(arg[i + 1:end - 1])
        rest = arg[end:].lstrip()
        if not rest:
            i = len(arg)
            break
        if not rest[0] == "+":
            return None
        i = end + arg[end:].index("+") + 1
        while i < len(arg) and arg[i].isspace():
            i += 1

    if arg[i:].strip():
        return None
    return unescape("".join(parts))


def unescape(body: str) -> str:
    """A Java string literal's contents as the sentence it stands for.

    `setText` wraps its lines with an escape rather than a `+`, so a text taken
    straight from one arrived with a literal backslash-n in the middle of it and
    the overlay showed it.
    """
    body = body.replace(BACKSLASH + "n", " ").replace(BACKSLASH + '"', '"')
    return " ".join(body.split())


def _first_point(args: list[str], decls: dict | None = None) -> list[int] | None:
    """The first argument that <em>is</em> a WorldPoint.

    Not one that merely contains one: a Zone is two of them and means an area
    the player might be in, not a place to walk to.

    Quest Helper usually writes the coordinate inline, and 8,599 steps do. 27 in
    four quests name it first and pass the name:

        WorldPoint tomasPoint = new WorldPoint(1796, 3781, 0);
        talkToLawry = new NpcStep(this, NpcID.PISCQUEST_OFFICIAL_VISIBLE,
            tomasPoint, "Speak to Tomas Lawry in Port Piscarilius.");

    Reading only the inline form left those steps with an npc id and nowhere to
    walk, so nothing was routed to and the only thing the plugin could still
    mark was the letter in the inventory -- which is what the author saw.

    Resolved through the declarations, and only when the named thing really is a
    WorldPoint: a Zone declared the same way is still an area, not a destination.
    """
    for arg in args:
        found = RE_WP.match(arg)
        if found:
            return [int(found.group(1)), int(found.group(2)), int(found.group(3))]

    for arg in args:
        declared = (decls or {}).get(arg.strip())
        if not declared or declared[0] != "WorldPoint" or len(declared[1]) < 3:
            continue
        try:
            return [int(v) for v in declared[1][:3]]
        except (TypeError, ValueError):
            continue
    return None


def _first_id(args: list[str]) -> tuple[str, str] | None:
    for arg in args:
        found = RE_ID_CONST.search(arg)
        if found:
            return found.group(1), found.group(2)
    return None


RE_ITEM_DECL = re.compile(r"\bnew\s+ItemRequirement\s*\(")
RE_QUANTITY = re.compile(r"^-?\d+$")


def item_declarations(text: str) -> dict[str, dict]:
    """Variable -> the item requirement it holds.

    Quest Helper declares these as fields and then hands them to the steps that
    need them:

        seasonedSardine = new ItemRequirement("Seasoned Sardine", ItemID.SEASONED_SARDINE);
        coins = new ItemRequirement("Coins", ItemCollections.COINS, 100);

    Read with the same bracket reader as the steps, so a nested call in the
    name or a `.isNotConsumed()` on the end changes nothing.
    """
    out: dict[str, dict] = {}
    for match in RE_ITEM_DECL.finditer(text):
        before = RE_ASSIGNED_TO.search(text[max(0, match.start() - 120):match.start()])
        if not before:
            continue
        record = _item_from(read_args(text, match.end() - 1))
        if record is not None:
            out[before.group(1)] = record
    for match in re.finditer(r"\b(\w+)\.addAlternates\s*\(", text):
        item = out.get(match[1])
        args = read_args(text, match.end() - 1)
        if item is not None and all(re.fullmatch(r"ItemID\.\w+", arg.strip()) for arg in args):
            item.setdefault("alternates", []).extend(arg.strip()[7:] for arg in args)
    for name, enabled in re.findall(r"\b(\w+)\.setHighlightInInventory\(\s*(true|false)\s*\)", text):
        if name in out:
            out[name]["highlight"] = enabled == "true"
    return out


def _item_from(args: list[str]) -> dict | None:
    """One `new ItemRequirement(...)` argument list as {name, constant, count}.

    `new ItemRequirement("Coins", -1, -1)` is a placeholder for something the
    quest cannot name yet; it carries no id and is dropped rather than shipped
    as an item nobody can hold.
    """
    if len(args) < 2 or not (args[0].startswith('"') and args[0].endswith('"')):
        return None
    name = args[0][1:-1].strip()
    source = args[1]
    count = 1
    if len(args) >= 3 and RE_QUANTITY.match(args[2]):
        count = int(args[2])
    record: dict = {"name": name, "count": max(1, count)}
    if source.startswith("ItemID."):
        record["constant"] = source[len("ItemID."):].split(")")[0].strip()
    elif source.startswith("ItemCollections."):
        record["collection"] = source[len("ItemCollections."):].split(")")[0].strip()
    else:
        return None
    return record


def cyclic_widget_puzzles(text: str, ids: dict) -> list[dict]:
    """Read QH's independent cyclic-dial solver, not arbitrary puzzle code.

    The exact shortest-direction expression and submit guard are required.
    A changed algorithm is unsupported, never approximated as this one. IDs,
    targets and cycle length all come from source, not from the quest name.
    """
    text = strip_comments(text)
    compact = re.sub(r"\s+", "", text)
    direction = re.search(r"Math\.floorMod\(currentPos-target,(\d+)\)<Math\.floorMod\(target-currentPos,\1\)\?arrowLeftId:arrowRightId", compact)
    if not direction or 'if(currentPos!=target)returnid;return0;' not in compact:
        return []
    guard = re.search(r"if\((highlightButtons\.get\(\d+\)(?:\+highlightButtons\.get\(\d+\))*)==0\)\{highlightButtons\.put\(\d+,COMPLETE\);\}", compact)
    if not guard:
        return []
    numbers = int_constants(text)
    for name, expression in re.findall(r"\bint\s+(\w+)\s*=\s*(InterfaceID\.\w+\.\w+)\s*;", text):
        numbers[name] = _widget_number(expression, ids.get('interface', {}), {})
    calls = re.findall(r"highlightButtons\.replace\((\d+),matchStateToSolution\(VarbitID\.(\w+),(\w+),(\w+),(\w+)\)\);", compact)
    slots = [int(n) for n in re.findall(r'get\((\d+)\)', guard[1])]
    if not 2 <= len(calls) <= 8 or [int(c[0]) for c in calls] != slots or len(set(slots)) != len(slots):
        return []
    size = int(direction[1])
    submit = numbers.get('COMPLETE')
    if not submit or not 2 <= size <= 128:
        return []
    cycles = []
    for _, var, target, right, left in calls:
        values = [ids.get('varbit', {}).get(var), numbers.get(target), numbers.get(left), numbers.get(right)]
        if any(v is None for v in values) or not 1 <= values[1] <= size or min(values[2:]) <= 0:
            return []
        cycles.append(dict(zip(('varbit', 'target', 'left', 'right'), values), size=size))
    return [{'cycles': cycles, 'submit': submit}]


def combination_lock(text: str, ids: dict) -> dict | None:
    """QH's ChestCodeStep, read exactly or not at all.

    A row of dials, each showing one letter of a code. The solver reads each
    dial's current value out of a client int, works out whether up or down is
    the shorter way round, and draws that arrow with the number of clicks on
    it. What the player sees in Quest Helper is five highlighted arrows and
    five numbers; what they saw here was nothing, because none of this is data
    in the constructor -- it is an algorithm, and the constructor only says
    which letters to stop on.

    Recognised by its own arithmetic, not by the quest it appears in: the
    shortest-direction expression, the distance expression, and the arrow
    numbering. A changed algorithm is unsupported rather than approximated,
    because a puzzle solved the wrong way is worse than one left alone.

    Returns the parts that are the same at every call site. The letters
    themselves are arguments, and are read from the call.
    """
    compact = re.sub(r"\s+", "", strip_comments(text))
    direction = re.search(
        r"Math" + re.escape(".") + r"floorMod" + re.escape("(")
        + r"currentValue-target,SIZE_OF_LOOP" + re.escape(")")
        + r"<Math" + re.escape(".") + r"floorMod" + re.escape("(")
        + r"target-currentValue,SIZE_OF_LOOP" + re.escape(")")
        + r"" + re.escape("?") + r"arrowDownId:arrowUpId", compact)
    distance = ("returnMath.min(Math.floorMod(currentValue-target,SIZE_OF_LOOP),"
                "Math.floorMod(target-currentValue,SIZE_OF_LOOP));")
    if not direction or distance not in compact:
        return None
    if "if(currentValue!=target)returnid;return0;" not in compact:
        return None

    numbers = int_constants(text)
    start = numbers.get("START_DOWN_ARROW")
    interval = numbers.get("ARROW_INTERVAL")
    if start is None or interval is None or not 1 <= interval <= 32:
        return None
    # The up arrow is the one after the down arrow, and the solver says so.
    if "intarrowUPID=START_DOWN_ARROW+1+(ARROW_INTERVAL*i);" not in compact:
        return None
    if "intarrowDownID=START_DOWN_ARROW+(ARROW_INTERVAL*i);" not in compact:
        return None

    # Whitespace is already gone, so each of these reads as one run of
    # characters and needs no escaping beyond the literal punctuation.
    varc = re.search("START_VARCLIENTINT_POS=VarClientID[.]([A-Za-z0-9_]+);", compact)
    lock = re.search("client[.]getWidget[(]InterfaceID[.]([A-Za-z0-9_]+[.][A-Za-z0-9_]+)[)]"
                     ";if[(]widget!=null[)][{]Widgetarrow=widget[.]getChild", compact)
    confirm = re.search("client[.]getWidget[(]InterfaceID[.]([A-Za-z0-9_]+[.][A-Za-z0-9_]+)[)]"
                        ";if[(]widget!=null[)][{]graphics", compact)
    if not (varc and lock and confirm):
        return None
    base = (ids.get("varclient") or {}).get(varc.group(1))
    table = ids.get("interface") or {}
    parent = table.get(lock.group(1))
    submit = table.get(confirm.group(1))
    if base is None or parent is None or submit is None:
        return None
    found = {"varc": base, "parent": parent, "submit": submit,
             "down": start, "up": start + 1, "interval": interval}
    # The sentence the class hands its parent, and the parameters it builds it
    # out of. "Open the " + objectName + " using the code " + answer + "." is
    # not a literal, so it was refused and the step fell back to the wrapper's
    # "Work out how to open the chest". Rendering it needs the call site, which
    # is where the letters live too.
    plain = strip_comments(text)
    signature = re.search("public" + " ([A-Za-z0-9_]+)"
                          + r"\s*\(([^)]*)\)\s*\{\s*super\s*\(", plain)
    if signature:
        names = []
        for part in signature.group(2).split(","):
            words = part.replace("...", " ").split()
            if len(words) >= 2:
                names.append(words[-1])
        arguments = read_args(plain, plain.index("super", signature.end() - 8) + 5)
        if names and names[0].lower().endswith("helper") and len(arguments) >= 2:
            found["params"] = names[1:]
            found["template"] = arguments[1]
    return found


def combination_locks(text: str, ids: dict) -> dict[str, dict]:
    """Class name -> its lock, for every solver of this shape in the folder.

    Read one class at a time. A quest can hold several locks with different
    codes -- The Blood Moon Rises has four -- so the answer belongs to the step
    that opens that lock, never to the quest.
    """
    out: dict[str, dict] = {}
    for match in RE_CLASS.finditer(text):
        body = _class_body(text, match.start())
        if body is None:
            continue
        found = combination_lock(text[match.start():body[1] + 1], ids)
        if found is not None:
            out[match.group(1)] = found
    return out


def _combination_step(args: list[str], lock: dict) -> dict | None:
    """One `new ChestCodeStep(this, "chest", "NALIA", 10, 3, 3, 4, 4, 9)`.

    The class says how a combination lock is solved; this call says which
    letters to stop on. Both are needed and neither is enough on its own.
    """
    given = [a.strip() for a in args if a.strip() != "getQuestHelper()"]
    numbers = [int(a) for a in given if re.fullmatch("-?[0-9]+", a)]
    if len(numbers) < 3:
        # No targets. The Heart of Darkness reads its code off a book while the
        # player is standing there, so there is nothing here to solve with.
        return None
    size, targets = numbers[0], numbers[1:]
    if not 2 <= size <= 128 or not 2 <= len(targets) <= 8:
        return None
    if any(not 0 <= target < size for target in targets):
        return None
    cycles = [{"varc": lock["varc"] + i, "target": target,
               "down": lock["down"] + lock["interval"] * i,
               "up": lock["up"] + lock["interval"] * i}
              for i, target in enumerate(targets)]
    return {"kind": "walk", "constant": None, "point": None,
            "text": _rendered(lock, given) or "",
            "combinationLocks": [{"parent": lock["parent"], "submit": lock["submit"],
                                  "size": size, "cycles": cycles}]}


def _rendered(lock: dict, args: list[str]) -> str | None:
    """The class's own sentence, with this call's arguments put into it.

    Not a guess: parameters are bound in the order Java binds them, and a term
    that does not resolve to a literal abandons the whole sentence rather than
    rendering half of one.
    """
    params, template = lock.get("params"), lock.get("template")
    if not params or not template:
        return None
    bound = dict(zip(params, args))
    said = []
    for part in template.split("+"):
        part = part.strip()
        literal = _verbatim(part)
        if literal is None:
            literal = _verbatim(bound.get(part, ""))
        if literal is None:
            return None
        said.append(literal)
    return "".join(said).strip() or None


def _verbatim(arg: str) -> str | None:
    """A Java string literal, exactly as written.

    _first_text trims and refuses short ones, which is right for an
    instruction and wrong for a fragment of one: "Open the " loses the space
    that separates it from the next word, and "." disappears entirely.
    """
    arg = (arg or "").strip()
    if len(arg) < 2 or not arg.startswith(chr(34)) or not arg.endswith(chr(34)):
        return None
    slash, quote = chr(92), chr(34)
    body = arg[1:-1]
    if quote in body.replace(slash + quote, ""):
        return None
    return body.replace(slash + quote, quote).replace(slash + slash, slash)


def item_alternatives(text: str, ids: dict) -> dict[str, dict]:
    """Explicit QH substitutes, scoped to this quest and joined by numeric ID."""
    text = strip_comments(text)
    declared = item_declarations(text)
    found = {}
    conflicts = set()
    for match in re.finditer(r"\b(\w+)\.addAlternates\s*\(", text):
        item = declared.get(match[1], {})
        primary = ids.get(item.get("constant"))
        args = read_args(text, match.end() - 1)
        if primary is None or not args or any(not re.fullmatch(r"ItemID\.\w+", a.strip()) for a in args):
            continue
        others = [ids.get(a.strip().split(".")[1]) for a in args]
        if any(n is None for n in others):
            continue
        notes = re.findall(r"\(can be ([^()]+)\)", item.get("name", ""), re.I)
        if not notes:
            continue
        values = {"ids": sorted(set([primary, *others])), "notes": notes}
        key = str(primary)
        if key in found and found[key] != values:
            conflicts.add(key)
        found[key] = values
    return {k: v for k, v in found.items() if k not in conflicts}


def step_items(args: list[str], declared: dict[str, dict]) -> list[dict]:
    """The item requirements handed to one step, in the order it names them.

    This is the difference between "what the quest needs" and "what this step
    needs". Quest Helper rings the second in your inventory, and until now the
    build only had the first -- so a player mid-quest was shown the whole
    shopping list or nothing at all.

    An argument that is not a declared requirement is skipped in silence:
    conditions, zones and sub-steps travel in the same argument list, and
    guessing at them would ring items the step never asked for.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for arg in args:
        record = None
        if re.fullmatch(r"\w+", arg):
            record = declared.get(arg)
        else:
            highlighted = re.fullmatch(r"(\w+)\.highlighted\(\)", arg.strip())
            if highlighted and highlighted[1] in declared:
                record = dict(declared[highlighted[1]], highlight=True)
            found = RE_ITEM_DECL.match(arg)
            if found:
                record = _item_from(read_args(arg, found.end() - 1))
        if record is None or record["name"] in seen:
            continue
        seen.add(record["name"])
        out.append(dict(record))
    return out

RE_ZONE_POINT = re.compile(r"^new\s+WorldPoint\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)")
RE_ZONE_REGION = re.compile(r"^-?\d+$")

# net.runelite.api.Constants.REGION_SIZE, which is what Zone(regionID) adds.
REGION_SIZE = 64


def zone_box(args: list[str]) -> list[int] | None:
    """A `new Zone(...)` argument list as [minX, minY, minPlane, maxX, maxY, maxPlane].

    Quest Helper's Zone has four constructors and this reads three of them --
    two corners, one corner, and a region id -- exactly as Zone does, including
    that a region covers planes 0 to 2 unless one is named. The fourth takes
    `regionPoint(...)` helpers whose arithmetic lives in the quest's own class,
    and those are skipped rather than approximated.
    """
    points = [RE_ZONE_POINT.fullmatch(a.strip()) for a in args]
    corners = [p for p in points if p]
    if len(args) in (1, 2) and len(corners) == len(args):
        xs = [int(p.group(1)) for p in corners]
        ys = [int(p.group(2)) for p in corners]
        zs = [int(p.group(3)) for p in corners]
        return [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]

    if len(args) in (1, 2) and all(RE_ZONE_REGION.fullmatch(a.strip()) for a in args):
        region = int(args[0])
        min_x = ((region >> 8) & 0xFF) << 6
        min_y = (region & 0xFF) << 6
        plane_low, plane_high = 0, 2
        if len(args) > 1 and RE_ZONE_REGION.match(args[1]):
            plane_low = plane_high = int(args[1])
        return [min_x, min_y, plane_low,
                min_x + REGION_SIZE, min_y + REGION_SIZE, plane_high]
    return None


def zones_of(name: str, decls: dict) -> list[list[int]] | None:
    """The boxes a ZoneRequirement covers, or None when it is not one.

    None and an empty list mean different things: not a zone requirement at all
    against a zone requirement whose zones could not be read. Only the first is
    safe to keep looking at.
    """
    entry = decls.get(name)
    if entry is None or entry[0] != "ZoneRequirement":
        return None

    boxes: list[list[int]] = []
    for arg in entry[1]:
        if arg.startswith('"'):
            # ZoneRequirement("in the tower", zone) -- the label, not a zone.
            continue
        inner = decls.get(arg)
        if inner is not None and inner[0] == "Zone":
            box = zone_box(inner[1])
            if box is None:
                return []
            boxes.append(box)
            continue
        found = re.match(r"new\s+Zone\s*\(", arg)
        if found:
            box = zone_box(read_args(arg, found.end() - 1))
            if box is None:
                return []
            boxes.append(box)
            continue
        return []
    return boxes

RE_ADD_DIALOG = re.compile(r"(\w+)\.addDialogSteps?\s*\(")
RE_ADD_DIALOG_CHANGE = re.compile(r"(\w+)\.addDialogChange\s*\(")
# Also the cast form, `((ObjectStep) findDaconiaStone).addAlternateObjects(...)`.
# quest-helper casts whenever the field is declared as a plain QuestStep, and it
# does so 254 times out of 482 -- so reading only the bare form threw away more
# than half of every step's alternate ids, across 61 quests. The Grand Tree has
# two roots to search and only one of them was ever outlined.
RE_ADD_ALTERNATE = re.compile(
    r"(\w+)\s*\)?\s*\.addAlternate(?:Npcs|Objects)\s*\(")
RE_BARE_ID = re.compile(r"^(?:NpcID|ObjectID|NullObjectID|QHObjectID)\.([A-Z0-9_]+)$")


# goThroughRoom6.addTileMarker(new WorldPoint(3162, 4600, 1), SpriteID.X)
# dropPetRock.addTileMarkers(new WorldPoint(...), new WorldPoint(...))
RE_ADD_TILE_MARKER = re.compile(r"(\w+)\.addTileMarkers?\(")


def route_steps(text: str) -> dict[str, bool]:
    return {m[1]: True for m in re.finditer(r"\b(\w+)\s*\)*\s*\.setLinePoints\s*\(", text)}


def line_points(text: str) -> dict[str, list]:
    """Keep literal, unambiguous QH routes, including explicit segment breaks."""
    text = strip_comments(text)
    assignments = {}
    for match in re.finditer(r"\b(\w+)\s*=(?!=)\s*([^;]+);", text):
        assignments.setdefault(match[1], []).append(match[2].strip())

    def literal(expr, seen=frozenset()):
        expr = expr.strip()
        if re.fullmatch(r"\w+", expr):
            values = assignments.get(expr, [])
            mutates = re.search(r"\b" + re.escape(expr) + r"\.(?:add|addAll|remove|clear|set|sort)\s*\(", text)
            if len(values) != 1 or expr in seen or mutates:
                return None
            return literal(values[0], seen | {expr})
        wrapper = re.fullmatch(r"new\s+ArrayList\s*<>\s*\((.*)\)", expr, re.S)
        if wrapper:
            return literal(wrapper[1], seen)
        reverse = re.fullmatch(r"Lists\.reverse\s*\((.*)\)", expr, re.S)
        if reverse:
            points = literal(reverse[1], seen)
            return list(reversed(points)) if points else None
        match = re.fullmatch(r"(?:Arrays\.asList|List\.of)\s*(\(.*\))", expr, re.S)
        if not match:
            return None
        points = []
        for arg in read_args(match[1], 0):
            if arg.strip() == "null":
                points.append(None)
                continue
            point = re.fullmatch(r"new\s+WorldPoint\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*([0-3])\s*\)", arg.strip())
            if not point:
                return None
            points.append([int(n) for n in point.groups()])
        return points if sum(point is not None for point in points) >= 2 else None

    out = {}
    for match in re.finditer(r"\b(\w+)\s*\)*\s*\.setLinePoints\s*\(", text):
        args = read_args(text, match.end() - 1)
        points = literal(args[0]) if len(args) == 1 else None
        out.setdefault(match[1], []).append(points)
    # Multiple state-dependent routes require execution, not a first-match guess.
    return {name: values[0] for name, values in out.items()
            if values[0] and all(value == values[0] for value in values)}


def tile_markers(text: str) -> dict[str, list[list[int]]]:
    """Variable -> the tiles quest-helper marks on the floor for that step.

    A safespot to stand on, the square to drop the pet rock, the three tiles
    that are safe in Tarn's lair. Seventy-three of them across nineteen files,
    and they are the only thing on screen for a step whose instruction is
    "stand here" -- there is no npc and no scenery to outline, so without them
    the guide draws a line to a room and then says nothing.

    Only the coordinates. The sprite quest-helper puts on the tile is its own
    icon set, which this plugin does not ship.
    """
    out: dict[str, list[list[int]]] = {}
    for match in RE_ADD_TILE_MARKER.finditer(text):
        name = match.group(1)
        for arg in read_args(text, match.end() - 1):
            found = re.match(r"new\s+WorldPoint\s*\(", arg.strip())
            if not found:
                continue
            numbers = []
            for part in read_args(arg.strip(), found.end() - 1):
                part = part.strip()
                if not re.fullmatch(r"-?\d+", part):
                    numbers = []
                    break
                numbers.append(int(part))
            if len(numbers) == 3:
                out.setdefault(name, [])
                if numbers not in out[name]:
                    out[name].append(numbers)
    return out


# allSteps.add(new PanelDetails("Killing sheep", Arrays.asList(enterEnclosure,
#     pickupCattleprod, prodSheep1, ...), plagueJacket))
RE_PANEL = re.compile(r"new\s+PanelDetails\s*\(")
RE_STEP_LIST = re.compile(
    r"(?:Arrays\.asList|Collections\.singletonList|List\.of)\s*\(")


def panel_order(text: str) -> dict[str, int]:
    """Variable -> where that step comes in the quest, in quest-helper's order.

    `getPanels()` is the quest author's own chronological listing -- the sidebar
    the player reads down. Nothing else in the file says what order the steps
    happen in: the progress value is too coarse (Sheep Herder has three values
    for a dozen actions) and a ConditionalStep's branches are ordered
    most-specific-first, which is not the same as first-to-last.

    This is what lets the build answer "where in the quest is the guide asking
    me to stop". "Continue Sheep Herder until all 4 Sheep bones are burnt" is
    everything up to and including `useBonesOnIncinerator`, and the step after
    it, `talkToHalgriveToFinish`, is where the guide's next step picks up.
    """
    order: dict[str, int] = {}
    for panel in RE_PANEL.finditer(text):
        for arg in read_args(text, panel.end() - 1):
            listed = RE_STEP_LIST.search(arg)
            if not listed:
                continue
            for name in read_args(arg, listed.end() - 1):
                name = name.strip()
                if re.fullmatch(r"\w+", name) and name not in order:
                    order[name] = len(order)
            break
    return order


# useToolkit.addWidgetHighlight(new WidgetHighlight(849, 36));
# talkToX.addWidgetHighlight(WidgetHighlight.createMultiskillByName("Snake"));
# The plain call takes a WidgetHighlight; the two longer names take the same
# arguments the constructor would and build one themselves.
RE_PUZZLE_WRAP = re.compile(
    r"(\w+)\s*=\s*(\w+)\s*\.puzzleWrapStep\w*\s*\(")

RE_WIDGET_STEP = re.compile(r"(\w+)\s*=[^;]{0,80}?new\s+WidgetStep\s*\(")
RE_ADD_WIDGET = re.compile(
    r"(\w+)\.addWidgetHighlight(WithItemIdRequirement|WithTextRequirement)?\(")
# teomatWidget = new WidgetHighlight(...);  -- the whole right-hand side is
# captured, so a trailing .withModelRequirement(...) comes with it.
RE_WIDGET_NAMED = re.compile(r"(\w+)\s*=\s*(new\s+WidgetHighlight\s*)\(")
RE_WIDGET_NEW = re.compile(r"^new\s+WidgetHighlight\s*\(")
RE_WITH_MODEL = re.compile(r"\.withModelRequirement\(\s*(\w+)\s*\)")
RE_WIDGET_FACTORY = re.compile(
    r"^WidgetHighlight\.(createMultiskillByName|createMultiskillByItemId"
    r"|createShopItemHighlight)\s*\(")


def _merged_widgets(text: str, ids: dict) -> dict[str, list[dict]]:
    """Both ways quest-helper marks part of an interface, by step variable."""
    out: dict[str, list[dict]] = {}
    for source in (widget_highlights(text, ids), widget_steps(text, ids)):
        for name, marks in source.items():
            for mark in marks:
                if mark not in out.setdefault(name, []):
                    out[name].append(mark)
    return out


def widget_steps(text: str, ids: dict) -> dict[str, list[dict]]:
    """Variable -> the interface parts a WidgetStep points at.

    Quest Helper's own way of guiding a puzzle that happens inside a menu:
    `new WidgetStep(this, "Click the pliers and use it on the safety switch",
    InterfaceID.McannonInterface.MCANNON_TOOL2)` outlines that component. It is
    what a player sees when repairing the dwarf cannon, and there are 154 of
    them across twenty quests -- Dwarf Cannon, Sea Slug, Tower of Life, and the
    rest of the ones that hand you an interface and expect you to know which
    part to click.

    The same shape as a WidgetHighlight, so the plugin draws it with the same
    overlay: an interface id, optionally a child inside it.
    """
    table = ids.get("interface") or {}
    out: dict[str, list[dict]] = {}
    for match in RE_WIDGET_STEP.finditer(text):
        args = read_args(text, match.end() - 1)
        numbers = []
        for arg in args:
            arg = arg.strip()
            if arg in ("this", "questHelper") or arg.startswith('"'):
                continue
            found = re.match(r"new\s+WidgetDetails\s*\(", arg)
            if found:
                for part in read_args(arg, found.end() - 1):
                    number = _widget_number(part, table, {})
                    if number is None:
                        numbers = []
                        break
                    numbers.append(number)
                break
            number = _widget_number(arg, table, {})
            if number is None:
                continue
            numbers.append(number)
        if not numbers:
            continue
        if len(numbers) == 1:
            record = {"interface": numbers[0]}
        else:
            record = {"interface": (numbers[0] << 16) | numbers[1]}
            if len(numbers) >= 3 and numbers[2] >= 0:
                record["child"] = numbers[2]
        out.setdefault(match.group(1), []).append(record)
    return out


def widget_highlights(text: str, ids: dict) -> dict[str, list[dict]]:
    """Variable -> the parts of an interface quest-helper marks for that step.

    While a menu is open there is nothing in the world to outline, so a widget
    highlight is the whole of the guidance: which tool to click on the cannon,
    which line of the multi-skill menu to pick, which slot of the shop to buy.

    Its own model, kept whole: an interface to look in, optionally one child
    inside it, whether to search the children, and up to four filters -- an item
    id, a model id, some text the widget must contain, a name it must contain.
    The plugin applies them in the same order quest-helper does.

    A name this cannot resolve to a number produces nothing for that highlight,
    rather than a highlight pointing at interface zero.
    """
    table = ids.get("interface") or {}
    items = ids.get("item") or {}

    # A highlight given a name first: `teomatWidget = new WidgetHighlight(...)`
    # and then `talkToX.addWidgetHighlight(teomatWidget)`. Thirteen of the
    # thirty are written that way, and reading only the inline form left every
    # one of them unmarked.
    held: dict[str, str] = {}
    for match in RE_WIDGET_NAMED.finditer(text):
        opening = text.index("(", match.end() - 1)
        held[match.group(1)] = text[match.start(2):_closes(text, opening) + 1]

    out: dict[str, list[dict]] = {}
    for match in RE_ADD_WIDGET.finditer(text):
        args = read_args(text, match.end() - 1)
        if match.group(2):
            # (groupID, childID, itemID or text, checkChildren) -- the same
            # arguments the four-argument constructor takes.
            record = _widget_highlight(
                "new WidgetHighlight(" + ", ".join(args) + ")", table, items)
            if record is not None:
                out.setdefault(match.group(1), []).append(record)
            continue
        for arg in args:
            arg = arg.strip()
            record = _widget_highlight(held.get(arg, arg), table, items)
            if record is not None:
                out.setdefault(match.group(1), []).append(record)
    return out


def _closes(text: str, opening: int) -> int:
    """The index of the bracket that closes the one at `opening`."""
    depth = 0
    for i in range(opening, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(text) - 1


def _widget_highlight(arg: str, table: dict, items: dict) -> dict | None:
    """One `new WidgetHighlight(...)` or one of its three factories."""
    model = RE_WITH_MODEL.search(arg)
    extra_model = _widget_number(model.group(1), table, items) if model else None
    if model:
        arg = arg[:model.start()]

    factory = RE_WIDGET_FACTORY.match(arg)
    if factory:
        inner = read_args(arg, factory.end() - 1)
        if not inner:
            return None
        which = factory.group(1)
        if which == "createShopItemHighlight":
            where, filters = "Shopmain.ITEMS", {"item": _widget_number(inner[0], table, items)}
        elif which == "createMultiskillByItemId":
            where, filters = "Skillmulti.BOTTOM", {"item": _widget_number(inner[0], table, items)}
        else:
            where, filters = "Skillmulti.BOTTOM", {"named": _widget_text(inner[0])}
        number = table.get(where)
        value = next(iter(filters.values()))
        if number is None or value is None:
            return None
        record = {"interface": number, "children": True}
        record.update({k: v for k, v in filters.items() if v is not None})
        return record

    found = RE_WIDGET_NEW.match(arg)
    if not found:
        return None
    args = read_args(arg, found.end() - 1)
    numbers, words, flag = [], [], False
    for one in args:
        one = one.strip()
        if one in ("true", "false"):
            flag = flag or one == "true"
            continue
        said = _widget_text(one)
        if said is not None:
            words.append(said)
            continue
        number = _widget_number(one, table, items)
        if number is None:
            return None
        numbers.append(number)

    if not numbers:
        return None
    # One number is an interface; two are a group and a child, packed the way
    # quest-helper packs them; the third is a child of that child.
    if len(numbers) == 1:
        record = {"interface": numbers[0]}
    else:
        record = {"interface": (numbers[0] << 16) | numbers[1]}
        if len(numbers) >= 3:
            # The four-argument form is (group, child, itemId, checkChildren);
            # the three-argument one is (group, child, childChildId). Only the
            # first carries a boolean, which is what tells them apart.
            if flag:
                record["item"] = numbers[2]
            else:
                record["child"] = numbers[2]
    if flag:
        record["children"] = True
    if words:
        record["says"] = words[0][:MAX_TEXT]
    if extra_model is not None:
        record["model"] = extra_model
    return record


def _widget_number(arg: str, table: dict, items: dict) -> int | None:
    """A literal, an InterfaceID name, or an ItemID name."""
    arg = arg.strip()
    if re.fullmatch(r"-?\d+", arg):
        return int(arg)
    named = re.fullmatch(r"InterfaceID\.(\w+(?:\.\w+)?)", arg)
    if named:
        return table.get(named.group(1))
    item = re.fullmatch(r"ItemID\.(\w+)", arg)
    if item:
        return items.get(item.group(1))
    return None


def _widget_text(arg: str) -> str | None:
    body = joined_literals(arg.strip())
    return body if body else None


def dialogue_options(text: str) -> dict[str, list[str]]:
    """Variable -> the dialogue options Quest Helper says to pick.

    `talkToChildren.addDialogSteps("What will make you tell me?", "Okay then,
    I'll pay.")` -- the words on the option, not its position in the list.

    Quest Helper highlights whichever visible option matches, at any point in
    the conversation, and that is why it never loses its place. The guide writes
    the same instruction as bare numbers, "(2,2)", which has to be counted
    through a conversation that opens and closes between every question -- and
    counting is what produced a (1,2,1,1) step showing 1,1,1,1.

    A set, not a sequence: an option is right whenever it is on screen.
    """
    out: dict[str, list[str]] = {}
    for match in RE_ADD_DIALOG.finditer(text):
        said = []
        for arg in read_args(text, match.end() - 1):
            if arg.startswith('"') and arg.endswith('"') and len(arg) > 2:
                body = arg[1:-1].replace('\\"', '"').strip()
                if body:
                    said.append(body[:MAX_TEXT])
        for option in said:
            # Several calls accumulate onto one step, and a quest repeats an
            # option across steps.
            if option not in out.setdefault(match.group(1), []):
                out[match.group(1)].append(option)
    return out


def dialogue_rules(text: str) -> dict[str, list[dict]]:
    """Conditional menu choices: retain every source exclusion, never flatten."""
    out = {}
    for match in re.finditer(r'(\w+)\.addDialogStepWithExclusions?\s*\(', text):
        args = read_args(text, match.end() - 1)
        if len(args) < 2 or any(not re.fullmatch(r'"(?:\\.|[^"\\])*"', a.strip()) for a in args):
            continue
        values = [a.strip()[1:-1].replace('\\"', '"') for a in args]
        if all(values):
            out.setdefault(match[1], []).append({'text': values[0], 'unless': values[1:]})
    return out


def dialogue_changes(text: str) -> dict[str, list[dict]]:
    """Variable -> the options quest-helper relabels, and what it says of them.

    `addDialogChange` renames an option in place to say what choosing it means:

        talkToClivet.addDialogChange("I'll help you.", "I'll help you. (side with Hazeel)");
        talkToClivet.addDialogChange("I won't help you.", "I won't help you. (side with Ceril)");

    Both are on screen at once and they take the quest in opposite directions,
    so the words alone cannot say which one a route wants. The note can. Read
    only `addDialogSteps` and the whole choice is invisible, which is what the
    guide's author reported: the route says to side with Hazeel and the plugin
    marked nothing at the one moment that decides it.

    The note is whatever the relabelling adds, so "I'll help you. (side with
    Hazeel)" against "I'll help you." leaves "side with Hazeel". A rename that
    does not extend the original is kept whole rather than guessed at.
    """
    out: dict[str, list[dict]] = {}
    for match in RE_ADD_DIALOG_CHANGE.finditer(text):
        args = [a.strip() for a in read_args(text, match.end() - 1)]
        said = []
        for arg in args:
            if arg.startswith('"') and arg.endswith('"') and len(arg) > 2:
                said.append(arg[1:-1].replace('\\"', '"').strip())
        if len(said) < 2 or not said[0]:
            continue
        option, renamed_to = said[0][:MAX_TEXT], said[1][:MAX_TEXT]
        note = renamed_to
        if renamed_to.startswith(option):
            note = renamed_to[len(option):].strip().strip("()").strip()
        if not note:
            continue
        entry = {"option": option, "note": note}
        if entry not in out.setdefault(match.group(1), []):
            out[match.group(1)].append(entry)
    return out


def alternate_ids(text: str) -> dict[str, list[str]]:
    """Variable -> the other ids that are also this step's target.

    "Talk to Shilop or Wilough" is one step with two npcs, and quest-helper says
    so with `addAlternateNpcs`. Reading only the constructor's id outlined one of
    them and left the player looking for the other. 468 steps say it.
    """
    out: dict[str, list[str]] = {}
    for match in RE_ADD_ALTERNATE.finditer(text):
        for arg in read_args(text, match.end() - 1):
            found = RE_BARE_ID.match(arg.strip())
            if found:
                out.setdefault(match.group(1), []).append(found.group(1))
    return out

RE_ADD_STEP_CALL = re.compile(r"(?:(\w+)\.)?addStep\s*\(")
# A DetailedOwnerStep does not call addStep. It drives itself from updateSteps()
# with `if (atValve1.check(client)) { startUpStep(turnValve1); }`, which is the
# same thing said another way: this requirement, then this step. 38 classes
# extend it and 62 branches are written like this, so reading only addStep left
# Hazeel Cult's five valves -- their order and which way each turns -- as one
# sentence saying "turn the valves".
#
# A negated guard is skipped by construction: `!solved1.check(client)` has no
# word character after the bracket. That is the wanted outcome rather than a
# limitation, because those are RuneliteRequirements backed by a widget listener
# this pipeline cannot read anyway.
RE_OWNED_BRANCH = re.compile(
    r"if\s*\(\s*(\w+)\s*\.check\s*\(\s*client\s*\)\s*\)\s*\{?\s*"
    r"startUpStep\s*\(\s*(\w+)\s*\)", re.S)


def _is_placeholder(record: dict | None) -> bool:
    """Whether a resolved default says nothing a player could act on.

    Eleven of Quest Helper's conditionals default to a stand-in -- an empty
    step, "Unknown state.", or Pirate's Treasure asking you to open the quest
    journal so its own class can work out where you are. The class then picks a
    branch at runtime, which is exactly the part this pipeline does not
    reproduce, so taking the default at face value puts a sentence about a
    journal on screen in place of the quest.
    """
    if record is None:
        return False
    text = record.get("text") or ""
    if record.get("point") or record.get("constant"):
        return False
    lowered = text.lower()
    return (not text or lowered.startswith("unknown state")
            or "journal to sync" in lowered)


def call_end(text: str, opening: int) -> int:
    """Position after a balanced call, skipping literals rather than their ')'s."""
    depth, cursor = 0, opening
    while cursor < len(text):
        char = text[cursor]
        if char in "\"'":
            cursor = _skip_quoted(text, cursor)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return len(text)


def fluent_step_owners(text: str) -> dict[int, str]:
    """Associate fluent addStep calls with their actual receiver.

    ConditionalStep.addStep returns this. An anonymous '.addStep' is not a
    call on the enclosing quest class: Biohazard lost nearly all its branches
    through that mistaken attribution despite having readable requirements.
    Only walk the known constructor / addStep chain, never another factory.
    """
    owners = {}

    def following(cursor, owner):
        while cursor < len(text):
            match = re.match(r"\s*\.\s*(addStep)\s*\(", text[cursor:])
            if not match:
                break
            owners[cursor + match.start(1)] = owner
            cursor = call_end(text, cursor + match.end() - 1)

    for match in RE_NEW.finditer(text):
        if match.group(1) != "ConditionalStep":
            continue
        assigned = RE_ASSIGNED_TO.search(text[max(0, match.start() - 120):match.start()])
        if assigned:
            following(call_end(text, match.end() - 1), assigned.group(1))
    for match in RE_ADD_STEP_CALL.finditer(text):
        if match.group(1):
            following(call_end(text, match.end() - 1), match.group(1))
    return owners


def add_steps(text: str) -> dict[str, list[str]]:
    """Owner -> the (condition, step) pairs added to it, in declaration order.

    `this.addStep(...)` is attributed to the class it sits in, which is how
    every hand-written ConditionalStep subclass adds its branches.

    Order matters. A ConditionalStep returns the first branch whose conditions
    hold, so Quest Helper writes them most-advanced first and the last one is
    the state a player entering the step is in.
    """
    classes = [(m.start(), m.group(1)) for m in RE_CLASS.finditer(text)]

    def enclosing(at: int) -> str | None:
        names = [name for start, name in classes if start < at]
        return names[-1] if names else None

    found: list[tuple[int, str, tuple[str, str]]] = []
    fluent = fluent_step_owners(text)
    for match in RE_ADD_STEP_CALL.finditer(text):
        owner = match.group(1) or fluent.get(match.start())
        if owner is None and text[:match.start()].rstrip().endswith("."):
            # An unknown fluent receiver is unresolved, never the quest itself.
            continue
        if owner in (None, "this"):
            owner = enclosing(match.start())
            if owner is None:
                continue
        args = read_args(text, match.end() - 1)
        if len(args) == 2 or (len(args) == 3 and args[2] in ("true", "false")):
            # The third argument is isLockable, not a step.
            found.append((match.start(), owner, (args[0], args[1])))
        elif len(args) == 1:
            found.append((match.start(), owner, ("", args[-1])))

    # The owner-step idiom, attributed to the class it is written in.
    for match in RE_OWNED_BRANCH.finditer(text):
        owner = enclosing(match.start())
        if owner is None:
            continue
        found.append((match.start(), owner, (match.group(1), match.group(2))))

    # Both idioms in the order they are written, because a conditional returns
    # the first branch that holds and the order is the meaning.
    out: dict[str, list[tuple[str, str]]] = {}
    for _, owner, pair in sorted(found, key=lambda row: row[0]):
        out.setdefault(owner, []).append(pair)
    return out

def _is_a_step(arg: str, decls: dict) -> bool:
    """Whether an argument is one of quest-helper's steps rather than a value.

    By type name: everything it calls a step ends in "Step", and the handful
    that do not are listed. A requirement, a zone or a coordinate is not one,
    and must never be mistaken for the sentence to show the player.
    """
    arg = arg.strip()
    found = RE_NEW.match(arg)
    kind = found.group(1) if found else (decls.get(arg) or ("",))[0]
    return kind in LEAF_TYPES or kind.endswith("Step")


def build(name: str, decls: dict, branches: dict, seen: frozenset,
          wants: dict | None = None, drawn: dict | None = None) -> dict | None:
    """What a declared step amounts to, following delegation.

    A step naming neither a thing nor a place passes the question on to the step
    it was handed: `new ConditionalStep(this, climbLadder, "...")` is answered by
    the ladder. Prose set at the outer level wins, because that is the sentence
    Quest Helper puts in its sidebar.

    `seen` stops a cycle. A step that reaches itself would otherwise recurse
    until the interpreter gave up, and one quest doing that would fail the whole
    build rather than lose one instruction.
    """
    if name in seen or name not in decls:
        return None
    seen = seen | {name}
    declared_type, args = decls[name]
    if declared_type == EXPRESSION:
        # The name stands for an expression rather than a constructor. It may be
        # a condition, which requirement_of reads, or a step -- a call to one of
        # quest-helper's builder methods. Try it as a step; nothing is lost if it
        # is neither.
        expression = args[0]
        # `theCat = getGertrudesCat(milkHighlighted)` -- a call to one of the
        # quest's own builder methods. follow_methods has already worked out
        # what that method returns, so the call is followed by its name; the
        # arguments only decide which items it highlights, not which step it is.
        call = RE_METHOD_CALL.match(expression)
        if call and call.group(1) in decls:
            expression = call.group(1)
        built = _delegate(expression, decls, branches, seen, wants, drawn)
        if built is not None:
            extras = _extras(name, drawn)
            if extras:
                built = dict(built)
                built.update(extras)
        return built
    if declared_type == ALIAS:
        aliased = build(args[0], decls, branches, seen, wants, drawn)
        extras = _extras(name, drawn)
        if aliased is not None and extras:
            aliased = dict(aliased)
            aliased.update(extras)
        return aliased
    rest = [a for a in args if a not in ("this", "questHelper")]

    # A combination lock. The class holds the algorithm and this call holds the
    # code, so the step is built here rather than delegated: delegating reached
    # the class, whose sentence is assembled at runtime out of these very
    # arguments, and came back with the word "chest".
    lock = ((drawn or {}).get("locks") or {}).get(declared_type)
    if lock is not None:
        made = _combination_step(rest, lock)
        if made is not None:
            made.update(_extras(name, drawn))
            return made

    text = _first_text(rest)
    # PuzzleWrapperStep(this, solvingStep, hiddenText, ...) carries two
    # sentences. PuzzleWrapperStep.java sets `this.text = hiddenStep.getText()`
    # and keeps the real one as `solvingStep`, switching between them on Quest
    # Helper's "Show Puzzle Solutions" config: hiddenText is what a player sees
    # with solutions turned OFF. "Work out how to open the chest in Marcellus'
    # house" is that sentence; "Search the chest... The code is 'NALIA'" is the
    # step behind it.
    #
    # Taking the string argument meant the wrapper's own sentence overwrote the
    # step it wraps, so 48 puzzles across 21 quests shipped the version that
    # withholds the answer and none shipped the answer. Children of the Sun said
    # "Mark the suspect guards" nine times without ever saying which guards.
    #
    # A guide is the solutions-on case by definition, so the wrapper's sentence
    # is demoted to a fallback and the step it wraps speaks for itself.
    hidden = None
    if declared_type == "PuzzleWrapperStep":
        # Only an argument that is a string in its own right. _first_text also
        # finds literals nested inside another constructor, and the wrapped
        # step is usually written inline: `new ChestCodeStep(this, "chest",
        # "NALIA", 10, ...)` handed back the word "chest", which then reached
        # the overlay as the instruction for opening the chest.
        for arg in rest:
            stripped = arg.strip()
            if stripped.startswith(chr(34)) and stripped.endswith(chr(34)):
                said = _first_text([stripped])
                if said:
                    hidden = said
                    break
        text = None
        # The wrapped step, resolved as the class it is rather than the call
        # that made it. A solver written inline -- `new ChestCodeStep(this,
        # "chest", "NALIA", 10, ...)` -- builds its sentence at runtime out of
        # those arguments, so reading the call hands back a parameter: the word
        # "chest" arrived as the instruction for opening the chest. The class's
        # own super() sentence is the instruction; its arguments are not.
        for arg in rest:
            stripped = arg.strip()
            if not _is_a_step(stripped, decls):
                continue
            built = RE_NEW.match(stripped)
            locks = (drawn or {}).get("locks") or {}
            if built and built.group(1) in decls and built.group(1) not in locks:
                inner = _delegate(built.group(1), decls, branches, seen, wants, drawn)
            else:
                # A lock is the exception: its sentence and its solution are
                # both built out of the call's own arguments, so the call is
                # what has to be read.
                inner = _delegate(stripped, decls, branches, seen, wants, drawn)
            if inner and (inner.get("text") or "").strip():
                text = inner["text"]
                break
    point = _first_point(rest, decls)
    named = _first_id(rest)

    mine = step_items(rest, wants or {})
    extras = _extras(name, drawn)

    # A wrapper whose arguments are themselves steps: PuzzleWrapperStep hands
    # the same object two ObjectSteps, one with the puzzle's instructions and
    # one without. The id and the coordinate are found by looking inside the
    # argument, and the sentence was not -- so Dwarf Cannon's toolkit step
    # arrived with the cannon to click, the toolkit to use on it, and no words:
    # "use the right tool on the spring, the middle tool on the Safety switch,
    # and the left tool on the gear" is the entire point of that step, and it is
    # the kind of thing Quest Helper says during an interface where there is
    # nothing in the world to outline.
    if not text and declared_type != "PuzzleWrapperStep":
        # A wrapper has already resolved its own, by class rather than by call.
        for arg in rest:
            # Only from an argument that is itself a step. A requirement carries
            # a name -- `new ItemRequirement("Coins", ItemID.COINS)` -- and
            # reading that as the instruction is the exact mistake the top-level
            # argument split exists to prevent.
            if not _is_a_step(arg, decls):
                continue
            inner = _delegate(arg, decls, branches, seen, wants, drawn)
            if inner is None:
                # An inline `new StonePuzzleStep(this)`. Its words are in that
                # class's own `super(questHelper, "...")`, not in this
                # constructor, and the argument is not a declared name, so
                # delegation by name finds nothing and the search falls through
                # to whatever else is in scope -- which put A Kingdom Divided's
                # statue puzzle on its wall panel. Resolve the class itself.
                built = RE_NEW.match(arg.strip())
                if built:
                    inner = _delegate(built.group(1), decls, branches, seen,
                                      wants, drawn)
            if inner and (inner.get("text") or "").strip():
                text = inner["text"]
                break

    # Nothing readable behind the wrapper -- a solver class with its words in
    # its own source, not in the constructor. Its sentence is better than none.
    if not text and hidden:
        text = hidden

    if named is not None or point is not None:
        kind = "walk"
        if named is not None:
            kind = "npc" if named[0] == "NpcID" else "object"
        record = {"kind": kind, "constant": named[1] if named else None,
                  "point": point, "text": text or ""}
        # `new NpcStep(this, NpcID.KITTENS_MEW, point, "...", true)` -- the bare
        # boolean is quest-helper's allowMultipleHighlights (showAllInArea on an
        # ObjectStep), and it means every one of them counts. The kitten could
        # be in any of the crates, and marking only the nearest is no help at
        # all.
        if point is not None and declared_type in ("NpcStep", "ObjectStep")                 and "true" in rest:
            record["spread"] = True
        if mine:
            record["items"] = mine
        record.update(extras)
        return record

    if declared_type not in LEAF_TYPES:
        # The type itself first. `new RumSmugglingStep(this)` takes no
        # arguments at all -- the step it stands for is the one that class
        # hands to its parent, and Pirate's Treasure spends its whole middle
        # inside it.
        for arg in [declared_type] + rest:
            inner = _delegate(arg, decls, branches, seen, wants, drawn)
            if inner is None:
                continue
            if _is_placeholder(inner):
                added = branches.get(name) or branches.get(declared_type) or []
                for _, branch in reversed(added):
                    instead = _delegate(branch, decls, branches, seen, wants, drawn)
                    if instead is not None and not _is_placeholder(instead):
                        inner = instead
                        break
            record = dict(inner)
            # A ConditionalStep with nothing added to it is a wrapper, not a
            # choice: there is one branch and it is the one being returned.
            # Flagging those "(varies)" dimmed a third of the diary tasks for
            # an uncertainty that does not exist.
            count = max(len(branches.get(name, ())), len(branches.get(declared_type, ())))
            if count or inner.get("conditional"):
                record["conditional"] = True
                record["branches"] = max(count, inner.get("branches", 0))
            if text:
                record["text"] = text
            if mine:
                # A conditional names the items for the whole choice; the
                # branch names its own. Both are wanted, outer first.
                have = {i["name"] for i in mine}
                record["items"] = mine + [i for i in record.get("items", ())
                                          if i["name"] not in have]
            record.update(extras)
            here = when_in(name, decls, branches, seen, wants, drawn)
            if not here:
                here = when_in(declared_type, decls, branches, seen, wants, drawn)
            if here:
                # A branch often has no words of its own -- Quest Helper puts
                # the sentence on the choice and lets the branch carry the npc.
                for branch in here:
                    if not branch.get("text"):
                        branch["text"] = record.get("text", "")
                # Added to the default's own branches, never in place of them.
                # `new ConditionalStep(this, hazeelSteps)` takes a conditional as
                # its default, and quest-helper checks this step's branches
                # first, then falls through to that default -- which then checks
                # its own fourteen. Overwriting them threw the whole Hazeel Cult
                # scroll chain away, so "Return to Alomone with the scroll" was
                # answered with the crate-and-key line that is only the default's
                # default. Outer first, because that is the order it is asked in.
                inherited = list(record.get("whenIn", ()))
                record["whenIn"] = here + inherited
                if inherited:
                    record["conditional"] = True
                    record["branches"] = len(here) + len(inherited)
            return record

    if text:
        # Prose and nothing else. Quest Helper shows plenty of these -- "Use your
        # Doogle Leaves on the Sardine" names no coordinate because there is
        # nowhere to go -- and saying that beats repeating the step before it.
        record = {"kind": "walk", "constant": None, "point": None, "text": text}
        if mine:
            record["items"] = mine
        record.update(extras)
        return record

    # A conditional whose default is nothing -- `super(questHelper, null,
    # requirements)` -- but which has branches of its own. Recruitment Drive
    # writes MissCheeversStep that way: the entire vial challenge lives in its
    # addStep chain, and returning nothing here dropped all three of its
    # instructions. There is no default to describe, but the branches are the
    # step, and they are what the player needs.
    here = when_in(name, decls, branches, seen, wants, drawn)
    if not here:
        here = when_in(declared_type, decls, branches, seen, wants, drawn)
    if here:
        record = {"kind": "walk", "constant": None, "point": None,
                  "text": text or "", "conditional": True,
                  "branches": len(here), "whenIn": here}
        if mine:
            record["items"] = mine
        record.update(extras)
        return record
    return None


def requirement_of(name: str, decls: dict, wants: dict,
                   seen: frozenset = frozenset()) -> dict | None:
    """A branch's condition, if it is one the plugin can answer exactly.

    Quest Helper's ConditionalStep returns the first branch whose requirements
    hold, and reproducing its whole requirement engine is not something this
    plugin is going to carry. But three of its requirements are lookups, not
    logic:

    * a zone is a box, and the player is inside it or not
    * an item requirement is "do you hold N of these ids", which the inventory
      already answers for the bank ring and the auto-tick
    * `Conditions(a, b)` of those is both of them

    Between them they cover the pattern that matters most here. Gertrude's Cat
    at progress 4 is three branches -- hold the kitten and be upstairs, hold the
    kitten, be upstairs -- and shipping only the zone one left the guide saying
    "search the crates" after the player had the kitten in hand.

    Returns None for anything else, and None is load-bearing: a branch whose
    condition cannot be read is not shipped, and nothing below it may be called
    certain.
    """
    if name in seen or len(seen) > 12:
        return None
    seen = seen | {name}

    # A requirement with a widening call on the end of it. "blanket" and
    # "blanket.alsoCheckBank(questBank)" are the same requirement asked two
    # ways, and refusing the second dropped every branch that used it -- which
    # in Monk's Friend is both of the branches that notice you already have the
    # blanket, so the guide went on saying "pick up the Child's blanket" to a
    # player holding it.
    #
    # Answered narrowly on purpose: this looks in the inventory and worn
    # equipment, where Quest Helper would also accept the bank. A branch that
    # holds for them and not for us falls through to the next one, which is the
    # cheap direction to be wrong in.
    # `and(a, b)`, `or(a, b)`, `not(a)`, `nor(a, b)` -- quest-helper's
    # LogicHelper, which is `new Conditions(LogicType.X, ...)` written shorter.
    # Six hundred and ninety-four branch conditions are one of these.
    logic = RE_LOGIC_HELPER.match(name.strip())
    if logic:
        inner = read_args(name.strip(), logic.end() - 1)
        joined = LOGIC_HELPERS[logic.group(1).lower()]
        parts = []
        for arg in inner:
            nested = requirement_of(arg.strip(), decls, wants, seen - {name})
            if nested is None:
                return None
            parts.append(nested)
        if not parts:
            return None
        body = parts[0] if len(parts) == 1 else {joined[0]: parts}
        return {"not": body} if joined[1] else body

    # `blueSheepState.eq(3)` -- quest-helper's VarbitBuilder, a fluent way to
    # write a varbit comparison. It is new since the copy this pipeline was
    # first written against, and not reading it cost Sheep Herder every branch
    # that notices a sheep has been dealt with.
    built = RE_VAR_BUILDER.match(name.strip())
    if built:
        holder = decls.get(built.group(1))
        if holder is not None and holder[0] == "VarbitBuilder" and holder[1]:
            number = _number(holder[1][0].strip(), decls)
            value = _number(built.group(3).strip(), decls)
            if number is not None and value is not None:
                return {"var": {"kind": "varbit", "id": number, "value": value,
                                "op": BUILDER_OPS[built.group(2)]}}
        return None

    chained = RE_ALSO_CHECK_BANK.match(name.strip())
    if chained:
        base = requirement_of(chained.group(1), decls, wants, seen - {name})
        if base is not None and "item" in base and ".alsoCheckBank(" in name:
            return {"item": dict(base["item"], bank=True)}
        return base
    if name in wants:
        return {"item": dict(wants[name])}

    quantity = re.fullmatch(r"(\w+)\.quantity\s*\(\s*([^()]+)\s*\)", name.strip())
    if quantity:
        count = _number(quantity.group(2).strip(), decls)
        base = requirement_of(quantity.group(1), decls, wants, seen)
        # ItemRequirement.quantity returns a copy. Do not alter its shared
        # declaration or guess a dynamic quantity / grouped requirement.
        if count is None or count <= 0 or base is None or set(base) != {"item"}:
            return None
        return {"item": {**base["item"], "count": count}}

    entry = decls.get(name)
    if entry is not None and entry[0] == EXPRESSION:
        # A name standing for an expression. Read the expression instead, with
        # this name retired from `seen` so a self-reference still terminates.
        return requirement_of(entry[1][0], decls, wants, seen)

    if entry is None:
        found = RE_NEW.match(name.strip())
        if not found:
            return None
        entry = (found.group(1), read_args(name, found.end() - 1))

    kind, args = entry
    if kind == "RuneliteRequirement":
        if len(args) not in (3, 4):
            return None
        key = _widget_text(args[1])
        expected = "true"
        condition_arg = args[2]
        if len(args) == 4 and _widget_text(args[2]) is not None:
            expected = _widget_text(args[2])
            condition_arg = args[3]
        nested = requirement_of(condition_arg, decls, wants, seen)
        if not key or nested is None:
            return None
        return {"memory": {"key": key, "value": expected, "when": nested}}

    if kind == "DialogRequirement":
        talker = None
        active = False
        texts = args
        if len(args) >= 3 and args[2].strip() in ("true", "false"):
            talker = "@player" if args[0].strip().endswith(".getPlayerName()") else _widget_text(args[0])
            if talker is None and args[0].strip() != "null": return None
            active, texts = args[2].strip() == "true", [args[1]]
        elif len(args) >= 3 and args[1].strip() in ("true", "false"):
            talker = _widget_text(args[0])
            if talker is None and args[0].strip() != "null": return None
            active, texts = args[1].strip() == "true", args[2:]
        words = [_widget_text(arg) for arg in texts]
        if not words or not all(words): return None
        found = {"text": words, "active": active}
        if talker is not None: found["speaker"] = talker
        return {"dialog": found}

    if kind == "Conditions" and args and args[0].strip() in ("true", "false"):
        body = requirement_of("new Conditions(" + ",".join(args[1:]) + ")", decls, wants, seen)
        if body is None or args[0].strip() == "false": return body
        key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
        return {"once": {"key": key, "when": body}}

    if kind == "ZoneRequirement":
        boxes = zones_of(name, decls) if name in decls else None
        if boxes is None:
            boxes = _zone_args(args, decls)
        return {"zone": boxes} if boxes else None

    if kind in ("VarbitRequirement", "VarplayerRequirement"):
        return _var_requirement(kind, args, decls)

    if kind in ("NpcCondition", "NpcRequirement", "ObjectCondition",
                "ItemOnTileRequirement"):
        return _scene_requirement(kind, args, decls, wants)

    if kind == "WidgetPresenceRequirement":
        # "Is that interface on screen." The whole of quest-helper's dwarf
        # cannon puzzle turns on this plus five varbits, and every branch of it
        # was dropped for want of this one shape.
        numbers = []
        for arg in args:
            number = _widget_number(arg.strip(), VAR_IDS.get("interface") or {}, {})
            if number is None:
                return None
            numbers.append(number)
        # The three-argument constructor tests a particular child of the
        # widget, not its parent. Dropping that argument makes a different
        # condition. Only -1 explicitly means the parent in QH's getWidget.
        if len(numbers) == 3 and numbers[2] == -1:
            numbers.pop()
        if len(numbers) not in (1, 2):
            return None
        packed = (numbers[0] if len(numbers) == 1
                  else (numbers[0] << 16) | numbers[1])
        return {"open": packed}

    if kind == "WidgetTextRequirement":
        # "Is that interface showing these words." Quest Helper guards every
        # one of its interface solvers with this -- the chest in the Ribbiting
        # Tale and in the Heart of Darkness are both
        # WidgetTextRequirement(809, 5, 9, "Confirm") -- and refusing the shape
        # dropped the branch holding the answer. 352 conditions are this.
        #
        # Its constructors are a packed component or a group and child, then
        # optionally a third int naming a child of that child, then one or more
        # strings. A bare `true`/`false` before the strings is checkChildren,
        # which widens the search to the widget's static children.
        numbers: list[int] = []
        texts: list[str] = []
        children = False
        for arg in args:
            arg = arg.strip()
            if arg in ("true", "false"):
                children = arg == "true"
                continue
            said = _widget_text(arg)
            if said is not None:
                texts.append(said)
                continue
            if texts:
                # An int after the strings is not part of this shape.
                return None
            number = _widget_number(arg, VAR_IDS.get("interface") or {}, {})
            if number is None:
                return None
            numbers.append(number)
        if not texts or len(numbers) not in (1, 2, 3):
            return None
        if len(numbers) == 1:
            group, child = numbers[0] >> 16, numbers[0] & 0xFFFF
        else:
            group, child = numbers[0], numbers[1]
        found = {"group": group, "child": child, "text": texts}
        # Only a third int means a child of the child; -1 is QH's "the parent".
        if len(numbers) == 3 and numbers[2] != -1:
            found["index"] = numbers[2]
        if children:
            found["children"] = True
        return {"widget": found}

    if kind in ("ItemRequirement", "ItemRequirements", "Conditions"):
        # LogicType.OR makes the list a choice rather than a conjunction.
        # Skipping the marker and joining with "all" quietly turned every one of
        # them into an AND, which is a stricter condition than Quest Helper's
        # and so a branch that should have been taken was not.
        joiner = "all"
        for arg in args:
            if arg.strip().startswith("LogicType."):
                which = arg.strip()[len("LogicType."):].strip().rstrip(")").upper()
                if which.startswith("OR"):
                    joiner = "any"
                elif which.startswith("NOR"):
                    joiner = "not any"
                elif which.startswith("NAND"):
                    joiner = "not all"
                elif not which.startswith("AND"):
                    # XOR and anything new: not answered rather than guessed.
                    return None
        parts = []
        for arg in args:
            arg = arg.strip()
            if not arg or arg.startswith('"') or arg.startswith("LogicType."):
                continue
            if kind == "ItemRequirement":
                item = _item_from(args)
                return {"item": item} if item else None
            inner = wants.get(arg)
            if inner is not None:
                parts.append({"item": dict(inner)})
                continue
            nested = requirement_of(arg, decls, wants, seen)
            if nested is None:
                return None
            parts.append(nested)
        if not parts:
            return None
        if joiner.startswith("not "):
            inner = joiner[4:]
            body = parts[0] if len(parts) == 1 else {inner: parts}
            return {"not": body}
        return parts[0] if len(parts) == 1 else {joiner: parts}

    return None


# "blanket.alsoCheckBank(questBank)" is the requirement "blanket", asked in a
# way that also counts the bank.
# LogicHelper's five: the joiner to use, and whether the whole thing is negated.
LOGIC_HELPERS = {
    "and": ("all", False),
    "or": ("any", False),
    "not": ("any", True),
    "nor": ("any", True),
    "nand": ("all", True),
}
RE_LOGIC_HELPER = re.compile(r"^(and|or|not|nor|nand)\s*\(")

# `blueSheepState.eq(3)`, `.ge(1)` -- VarbitBuilder's comparisons.
BUILDER_OPS = {"eq": "==", "ge": ">=", "gt": ">", "le": "<=", "lt": "<",
               "ne": "!="}
# `name = <expression>;` on one line, where the expression is a call rather
# than a constructor. Deliberately not multi-line: a wrapped expression is
# usually a step being assembled, and reading those here confuses the two.
RE_METHOD_CALL = re.compile(r"^(\w+)\s*\(")

RE_NAMED_EXPRESSION = re.compile(
    r"^\s*(?:\w+\s+)?(\w+)\s*=\s*((?!new\s)[\w.]+\([^;]*\))\s*;\s*$",
    re.M)

RE_VAR_BUILDER = re.compile(
    r"^(\w+)\.(eq|ge|gt|le|lt|ne)\s*\(\s*([^)]+?)\s*\)$")

RE_ALSO_CHECK_BANK = re.compile(
    r"^(\w+)\.(?:alsoCheckBank|isNotConsumed|highlighted|named)\([^)]*\)$")

# Operation.GREATER_EQUAL -> ">=", and the rest of quest-helper's comparisons.
OPERATIONS = {
    "GREATER": ">", "LESS": "<", "LESS_EQUAL": "<=",
    "EQUAL": "==", "GREATER_EQUAL": ">=", "NOT_EQUAL": "!=",
}


SCENE_KINDS = {
    "NpcCondition": "npc",
    "NpcRequirement": "npc",
    "ObjectCondition": "object",
    "ItemOnTileRequirement": "groundItem",
}


def _scene_requirement(kind: str, args: list[str], decls: dict,
                       wants: dict) -> dict | None:
    """"Is that thing here?" -- a look at the loaded scene, not logic.

    Quest Helper asks it constantly: is the npc standing there yet, has the
    object appeared, is the item on the floor. A hundred and eighty branch
    conditions in the quests this guide runs are one of these, and every one was
    dropped -- along with the branch it guarded, which is usually the branch
    that notices the player has done the thing.

    It needs nothing this plugin does not already do: the scene tracker walks
    npcs and objects every tick and the ground-item tracker walks tiles. The
    only new part is asking on behalf of a condition rather than a step.

    A point or a zone narrows it where quest-helper gives one. Ids that cannot
    be resolved make the whole condition unreadable, as everywhere else.
    """
    numbers: list[str] = []
    box = None
    for arg in args:
        arg = arg.strip()
        if not arg or arg.startswith('"'):
            continue
        point = _point_args(arg, decls)
        if point is not None:
            box = point
            continue
        held = wants.get(arg)
        if held is not None and held.get("constant"):
            numbers.append(held["constant"])
            continue
        inner = decls.get(arg)
        if inner is not None and inner[0] == "ItemRequirement":
            item = _item_from(inner[1])
            if item and item.get("constant"):
                numbers.append(item["constant"])
                continue
            return None
        named = re.match(r"(?:Npc|Object|Item)ID\.(\w+)$", arg)
        if named:
            numbers.append(named.group(1))
            continue
        if re.fullmatch(r"-?\d+", arg):
            numbers.append(arg)
            continue
        return None

    if not numbers:
        return None
    found = {"kind": SCENE_KINDS[kind], "constants": numbers}
    if box:
        found["zone"] = box
    return {"here": found}


def _point_args(arg: str, decls: dict) -> list[list[int]] | None:
    """A WorldPoint or a Zone written inline or named, as one box."""
    inner = decls.get(arg)
    if inner is not None and inner[0] == "Zone":
        one = zone_box(inner[1])
        return [one] if one else None
    found = re.match(r"new\s+(Zone|WorldPoint)\s*\(", arg)
    if not found:
        return None
    read = read_args(arg, found.end() - 1)
    if found.group(1) == "Zone":
        one = zone_box(read)
        return [one] if one else None
    numbers = [int(x) for x in read if re.fullmatch(r"-?\d+", x.strip())]
    if len(numbers) != 3:
        return None
    return [[numbers[0], numbers[1], numbers[2], numbers[0], numbers[1], numbers[2]]]


def _var_requirement(kind: str, args: list[str], decls: dict | None = None) -> dict | None:
    """A varbit or VarPlayer comparison, which is a lookup and not logic.

    Two thousand three hundred branch conditions are one of these, by far the
    largest thing standing between this and Quest Helper's own choice of step --
    more than zones and items put together. And it needs none of the condition
    engine that is deliberately not ported: the value is an array read the
    client already does for the quest's own progress.

    Every constructor quest-helper offers is listed, and anything not on the
    list is refused rather than guessed. The bit form is separate because
    "is bit 3 of this VarPlayer set" is a different question from "does this
    equal 3", and reading one as the other is silently wrong.
    """
    numbers = []
    operation = None
    boolean = None
    for arg in args:
        arg = arg.strip()
        if arg.startswith("Operation."):
            operation = OPERATIONS.get(arg[len("Operation."):].strip().rstrip(")"))
            if operation is None:
                return None
            continue
        if arg in ("true", "false"):
            boolean = arg == "true"
            continue
        if arg.startswith('"') or arg == "questBank":
            continue
        number = _number(arg, decls)
        if number is None:
            return None
        numbers.append(number)

    which = "varbit" if kind == "VarbitRequirement" else "varplayer"
    if boolean is not None:
        # (id, bitIsSet, bitPosition)
        if len(numbers) != 2:
            return None
        return {"var": {"kind": which, "id": numbers[0],
                        "bit": numbers[1], "set": boolean}}
    if len(numbers) != 2:
        # Three numbers is the bit-shift form, which is not answered here.
        return None
    return {"var": {"kind": which, "id": numbers[0],
                    "value": numbers[1], "op": operation or "=="}}


def _number(arg: str, decls: dict | None = None) -> int | None:
    """A literal, or a VarbitID/VarPlayerID constant resolved from the index."""
    arg = arg.strip()
    if re.fullmatch(r"-?\d+", arg):
        return int(arg)
    local = (decls or {}).get(arg)
    if local and local[0] == INT_CONSTANT:
        return int(local[1][0])
    named = re.fullmatch(r"(?:Varbit|VarPlayer)ID\.(\w+)", arg)
    if named and VAR_IDS:
        for table in ("varbit", "varplayer"):
            number = VAR_IDS.get(table, {}).get(named.group(1))
            if number is not None:
                return number
    return None


# Filled in by main() so _number can resolve constants without threading the
# index through every requirement call.
VAR_IDS: dict = {}


def _zone_args(args: list[str], decls: dict) -> list[list[int]]:
    """The boxes named directly in a ZoneRequirement's argument list."""
    boxes = []
    for arg in args:
        if arg.startswith('"'):
            continue
        inner = decls.get(arg)
        if inner is not None and inner[0] == "Zone":
            box = zone_box(inner[1])
            if box is None:
                return []
            boxes.append(box)
            continue
        found = re.match(r"new\s+Zone\s*\(", arg)
        if found:
            box = zone_box(read_args(arg, found.end() - 1))
            if box is None:
                return []
            boxes.append(box)
            continue
        return []
    return boxes


def resolved_item_ids(item, ids, collections):
    constant = item.pop("constant", None)
    collection = item.pop("collection", None)
    alternates = item.pop("alternates", [])
    names = ([constant] if constant else []) + alternates
    if names:
        found = [ids.get("item", {}).get(name) for name in names]
        if any(number is None for number in found): return []
        return list(dict.fromkeys(found))
    return list(collections.get(collection) or ()) if collection else list(item.get("ids") or ())


def resolve_requirement(condition: dict, ids: dict, collections: dict) -> bool:
    """Turn an item condition's constant into ids. False if it will not."""
    if "item" in condition:
        item = condition["item"]
        numbers = resolved_item_ids(item, ids, collections)
        if not numbers:
            return False
        item["ids"] = numbers
        return True
    if "dialog" in condition:
        return True
    for key in ("memory", "once"):
        if key in condition:
            return resolve_requirement(condition[key]["when"], ids, collections)
    if "open" in condition or "widget" in condition:
        # Nothing to resolve: both are interface coordinates already, with no
        # constant to look up. Omitting "widget" here dropped every branch its
        # condition guarded even after the condition itself became readable.
        return True
    if "here" in condition:
        found = condition["here"]
        table = {"npc": "npc", "object": "object", "groundItem": "item"}[found["kind"]]
        numbers = []
        for constant in found.pop("constants"):
            number = (int(constant) if constant.lstrip("-").isdigit()
                      else ids.get(table, {}).get(constant))
            if number is not None and number not in numbers:
                numbers.append(number)
        if not numbers:
            return False
        found["ids"] = numbers
        return True
    if "not" in condition:
        return resolve_requirement(condition["not"], ids, collections)
    for joiner in ("all", "any"):
        if joiner in condition:
            return all(resolve_requirement(part, ids, collections)
                       for part in condition[joiner])
    return "zone" in condition or "var" in condition

def when_in(name: str, decls: dict, branches: dict, seen: frozenset,
            wants: dict | None, drawn: dict | None) -> list[dict]:
    """The branches of a conditional that turn on where the player is standing.

    A ConditionalStep returns the first branch whose conditions hold, and a
    third of all branch conditions in quest-helper are a bare ZoneRequirement --
    "are you upstairs in the Lumberyard yet". That is a box on the map, so it
    can be answered exactly, with none of the condition engine this pipeline
    refuses to port. It is also the pattern that matters most here: the
    downstairs branch says climb the ladder, the upstairs branch says use the
    bucket of milk on the cat, and taking the default meant the guide never
    stopped pointing at the ladder.

    Emitted in declaration order, so the plugin takes the first zone the player
    is inside -- the same rule, applied to the branches it can read.

    `certain` marks a branch as decided rather than guessed. It holds only while
    every branch above it is also a bare zone: an earlier branch whose condition
    cannot be read here might have been the one Quest Helper picked, and a zone
    match below it proves nothing about that.
    """
    out: list[dict] = []
    certain = True
    for condition, step in branches.get(name, ()):
        when = requirement_of(condition.strip(), decls, wants or {})
        if when is None:
            # A condition this cannot answer. Nothing below it may be called
            # decided either: quest-helper takes the first branch that holds,
            # and this might have been it.
            certain = False
            continue
        record = _delegate(step, decls, branches, seen, wants, drawn)
        if record is None:
            certain = False
            continue
        branch = dict(record)
        branch.pop("conditional", None)
        branch.pop("branches", None)
        branch["when"] = when
        if not certain:
            branch["conditional"] = True
        out.append(branch)
    return out


def _extras(name: str, drawn: dict | None) -> dict:
    """The per-step things quest-helper attaches after the constructor.

    `theCat.addIcon(...)`, `talkToChildren.addDialogSteps(...)`,
    `talkToChildren.addAlternateNpcs(...)` -- all keyed by the step's variable,
    and all invisible to anything reading only the `new` expression.
    """
    if not drawn:
        return {}
    out = {}
    panel = drawn.get("panel", {}).get(name)
    if panel is not None:
        out["panel"] = panel
    for field in ("icon", "dialogue", "dialogueRules", "choices", "alternates", "tiles", "linePoints", "questRoute", "widgets"):
        value = drawn.get(field, {}).get(name)
        if value:
            out[field] = value
    said = drawn.get("said", {}).get(name)
    if said:
        out["text"] = said
    return out


def _delegate(arg: str, decls: dict, branches: dict, seen: frozenset,
              wants: dict | None = None, drawn: dict | None = None) -> dict | None:
    """Resolve one constructor argument as the step it stands for, or None."""
    if re.fullmatch(r"\w+", arg):
        return build(arg, decls, branches, seen, wants, drawn)
    found = RE_NEW.match(arg)
    if not found:
        return None
    # An anonymous inner step: give it a name that cannot collide with a Java
    # identifier so the cycle guard still holds.
    anonymous = "\x00" + str(len(seen))
    nested = dict(decls)
    nested[anonymous] = (found.group(1), read_args(arg, found.end() - 1))
    return build(anonymous, nested, branches, seen, wants, drawn)


RE_METHOD = re.compile(r"\b(\w+)\s*\([^;{}()]*\)\s*\{")
RE_CALL_ASSIGNMENT = re.compile(r"(\w+)\s*=\s*(\w+)\s*\(")
RE_ADD_ICON = re.compile(r"(\w+)\.addIcon\(\s*ItemID\.([A-Z0-9_]+)\s*\)")
# `giveKittenToFluffy.setText("Return the kitten to Gertrude's cat.")` --
# quest-helper reuses a step and renames it for the branch it appears in, and
# the constructor's own sentence is then the wrong one to show.
RE_SET_TEXT = re.compile(r'(\w+)\.setText\(\s*"([^"]{3,400})"\s*\)')
# Marks a variable that stands for another. The space makes it something no
# Java type can be called, so it can never collide with a declared type.
# A space, so it can never collide with a Java type name.
INT_CONSTANT = "a number"

# A name that stands for an expression rather than a constructor. A space, so
# it can never collide with a Java type.
EXPRESSION = "expression for"

ALIAS = "alias for"
# Java constructs that also read as `name(...) {`.
JAVA_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "synchronized", "do", "else",
    "try", "return", "new",
})


def method_returns(text: str) -> dict[str, str]:
    """Method name -> the expression it returns.

    `steps.put(4, findFluffsKitten())` registers a step with no name at the call
    site at all, and `gertrudesCat = getGertrudesCat(milkHighlighted)` builds one
    inside a method that takes arguments. Either way the step is somewhere else,
    under another name or under none.

    The last `return` in the body wins: quest-helper's builders end with the
    step they assembled, and anything before that is a guard.
    """
    out: dict[str, str] = {}
    for match in RE_METHOD.finditer(text):
        if match.group(1) in JAVA_KEYWORDS:
            continue
        opening = text.index("{", match.end() - 1)
        depth = 0
        i = opening
        while i < len(text):
            if text[i] in "\"'":
                i = _skip_quoted(text, i)
                continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        returned = RE_RETURN.findall(text[opening:i])
        if returned:
            out[match.group(1)] = returned[-1].strip()
    return out


def follow_methods(text: str, decls: dict, methods: dict) -> None:
    """Give `x = someMethod(...)` the declaration of what that method returns.

    Quest Helper builds a step in a helper method and assigns it to a field, so
    the field has no `new` of its own. Without this the field resolves to
    nothing -- which is how Gertrude's Cat lost the branch that says to use the
    bucket of milk on the cat, and with it the ladder, the icon and the item.
    """
    # Each builder method stands for whatever it returns, so a call to it can be
    # followed by name -- whether the step is assigned to a field first or
    # registered straight from the call.
    for called, returned in methods.items():
        # An EXPRESSION entry is only a note that the name stands for something;
        # a followed method says what. The note must not block the answer.
        if called in decls and decls[called][0] != EXPRESSION:
            continue
        returned = returned.strip()
        if re.fullmatch(r"\w+", returned):
            decls[called] = (ALIAS, [returned])
            continue
        found = RE_NEW.match(returned)
        if found:
            decls[called] = (found.group(1), read_args(returned, found.end() - 1))

    for match in RE_CALL_ASSIGNMENT.finditer(text):
        variable, called = match.group(1), match.group(2)
        if variable in decls or called in JAVA_KEYWORDS:
            continue
        if called in methods:
            # An alias, not a copy. Copying the declaration resolves the step
            # and loses its name, and a conditional's branches are looked up by
            # name -- which is how the branch that says to use the bucket of
            # milk on the cat went missing while the step itself resolved fine.
            decls[variable] = (ALIAS, [called])


def icon_constants(text: str) -> dict[str, str]:
    """Variable -> the ItemID constant quest-helper draws on top of it.

    `gertrudesCat.addIcon(ItemID.BUCKET_MILK)` is how Quest Helper says "use
    this item on that thing": the sprite goes over the npc and the item is
    highlighted in the inventory. It says it 918 times, and it is the clearest
    instruction the plugin gives -- a picture of what to click with, drawn on
    what to click it on.
    """
    return dict((variable, constant)
                for variable, constant in RE_ADD_ICON.findall(text))


def renamed(text: str) -> dict[str, str]:
    """Variable -> the sentence quest-helper gave it after building it."""
    return dict((variable, unescape(said)[:MAX_TEXT])
                for variable, said in RE_SET_TEXT.findall(text))


def _names_in(expression: str, methods: dict[str, str]) -> list[str]:
    """The step names a `steps.put` expression could mean, best first."""
    names: list[str] = []
    direct = re.match(r"^(\w+)\s*(?:=|$)", expression.strip())
    if direct:
        names.append(direct.group(1))
    # A step held by another object: ".put(0, startingOff.talkToKingBolren)".
    # The Path of Glouphrie keeps every step in a section class and lists them
    # this way, and taking only a bare name dropped all twenty-five.
    field = re.match(r"^\w+(?:\.\w+)+$", expression.strip())
    if field:
        names.append(expression.strip().rsplit(".", 1)[1])
    for call in re.findall(r"\b(\w+)\s*\(", expression):
        returned = methods.get(call)
        if returned:
            names.append(returned)
    return names


def follow_conditional_copies(text: str, decls: dict, branches: dict, drawn: dict) -> None:
    """ConditionalStep.copy clones default/text/conditions, not an alias.

    Capture conditions at the copy site: copying a source's final branch list
    leaks subsequent mutations into the copy. This lost complete progress slots
    in At First Light and Perilous Moons. Unknown receiver types stay unresolved.
    """
    inherited = {}
    own = {name: list(parts) for name, parts in branches.items()}

    def combine(parts):
        result = []
        positions = {}
        for condition, step in parts:
            # QH stores conditions in a LinkedHashMap. Reusing the same named
            # Requirement replaces its value in place; a freshly constructed
            # and(...) expression is a different object, not the same key.
            key = condition.strip()
            if re.fullmatch(r"\w+", key) and key in positions:
                result[positions[key]] = (condition, step)
            else:
                if re.fullmatch(r"\w+", key):
                    positions[key] = len(result)
                result.append((condition, step))
        return result

    for match in re.finditer(r"\b(\w+)\s*=\s*(\w+)\s*\.\s*copy\s*\(\s*\)\s*;", text):
        target, source = match.groups()
        if target == source or decls.get(source, (None,))[0] != "ConditionalStep":
            continue
        decls[target] = ("ConditionalStep", list(decls[source][1]))
        before = text[:match.start()]
        inherited[target] = combine(inherited.get(source, []) + add_steps(before).get(source, []))
        branches[target] = combine(inherited[target] + own.get(target, []))
        # Only setText is copied by ConditionalStep.copy (not icons/widgets).
        source_text = renamed(before).get(source, drawn.get("copiedText", {}).get(source))
        if source_text is not None:
            drawn.setdefault("copiedText", {})[target] = source_text
            drawn["said"].setdefault(target, source_text)


def steps_in(text: str, registers: str | None = None) -> dict[int, dict]:
    """Progress value -> the instruction at that value.

    `text` is every file in the quest's folder, because a step is often
    declared in a sibling class. `registers` is the one helper that calls
    steps.put, and defaults to the same thing.

    The two are separate because three folders hold more than one registered
    helper -- Recipe for Disaster holds ten -- and reading their steps.put calls
    together merged ten unrelated tables under one set of progress values. That
    shipped: Recipe for Disaster's value 80 pointed at a chompy bird.
    """
    text = strip_comments(text)
    decls = declarations(text)
    methods = method_returns(text)
    follow_methods(text, decls, methods)
    wants = item_declarations(text)
    drawn = {"icon": icon_constants(text), "dialogue": dialogue_options(text),
             "dialogueRules": dialogue_rules(text), "choices": dialogue_changes(text),
             "alternates": alternate_ids(text), "said": renamed(text),
             "tiles": tile_markers(text), "linePoints": line_points(text), "questRoute": route_steps(text), "panel": panel_order(text),
             "widgets": _merged_widgets(text, VAR_IDS),
             "locks": combination_locks(text, VAR_IDS)}
    registers = text if registers is None else strip_comments(registers)

    branches = add_steps(text)
    follow_conditional_copies(text, decls, branches, drawn)

    out: dict[int, dict] = {}
    puts = RE_PUT.findall(registers)
    if RE_BUILDER in registers:
        puts = puts + RE_BUILDER_PUT.findall(registers)
    for raw_value, expression in puts:
        for candidate in _names_in(expression, methods):
            record = build(candidate, decls, branches, frozenset(), wants, drawn)
            if record is not None:
                out[int(raw_value)] = record
                break

    # steps.put(1, steps.get(0)) -- the same instruction under another value.
    for value, source in {int(a): int(b) for a, b in RE_PUT_ALIAS.findall(registers)}.items():
        if source in out and value not in out:
            out[value] = dict(out[source])

    # A ComplexStateQuestHelper fills no steps.put table. It hands back the
    # whole quest from loadStep() as one ConditionalStep whose branches turn on
    # varbits, items and zones -- the shape everything above already reads. It
    # was simply never asked for, so Elemental Workshop I and Alfred Grimhand's
    # Barcrawl extracted nothing at all and the guide said "Complete Elemental
    # Workshop I" with no guidance behind it. One slot, at 0: the plugin looks
    # up the nearest slot at or below the quest's progress, so it answers at
    # every stage, and the branches inside it do the choosing.
    if not out and RE_COMPLEX_STATE.search(registers):
        root = methods.get("loadStep")
        for candidate in (_names_in(root, methods) if root else ()):
            record = build(candidate, decls, branches, frozenset(), wants, drawn)
            if record is not None:
                out[0] = record
                break
    return out

# QUEST_X_MARKS_THE_SPOT(VarbitID.CLUEQUEST) / (VarPlayerID.FOO)
RE_QUEST_VAR = re.compile(r"^\s*(QUEST_\w+)\(\s*(Varbit|VarPlayer)ID\.(\w+)", re.M)

# QuestVarPlayer rows carry the id inline: QUEST_COOKS_ASSISTANT(29).
RE_QUEST_VARPLAYER = re.compile(r"^\s*(QUEST_\w+)\(\s*(\d+)\s*\)", re.M)


def quest_vars(root: Path, ids: dict) -> dict[str, dict]:
    """Quest progress constant -> {kind, id, constant}, from both tables.

    QuestVarbits names a RuneLite constant, which has to be looked up in the id
    index. QuestVarPlayer carries the number inline. Reading only the first
    lost every quest that predates varbit-based progress.
    """
    out: dict[str, dict] = {}

    varbits = root / "com/questhelper/questinfo/QuestVarbits.java"
    if varbits.is_file():
        for name, kind, constant in RE_QUEST_VAR.findall(
                varbits.read_text(encoding="utf-8")):
            table = ids["varbit"] if kind == "Varbit" else ids["varplayer"]
            if constant in table:
                out[name] = {"kind": kind.lower(), "id": table[constant],
                             "constant": constant}

    varplayers = root / "com/questhelper/questinfo/QuestVarPlayer.java"
    if varplayers.is_file():
        for name, number in RE_QUEST_VARPLAYER.findall(
                varplayers.read_text(encoding="utf-8")):
            # The id is the number itself, so there is nothing to look up and
            # nothing that can fail to resolve.
            out.setdefault(name, {"kind": "varplayer", "id": int(number),
                                  "constant": name})

    return out

# new ItemRequirement("Raw rat meat", ItemID.RAW_RAT_MEAT)
RE_ITEM_REQUIREMENT = re.compile(
    r'new\s+ItemRequirement\(\s*"([^"]{2,40})"\s*,\s*ItemID\.([A-Z0-9_]+)')


def item_requirements(text: str, ids: dict) -> list[dict]:
    """The items a quest's helper says you need, as {name, id}.

    Quest Helper declares these as fields -- `new ItemRequirement("Raw rat
    meat", ItemID.RAW_RAT_MEAT)` -- so the name and the number sit side by side
    and every one of them resolves. Per quest rather than per step: which
    requirement belongs to which step is expressed in conditions this pipeline
    does not evaluate, and claiming otherwise would put the wrong items in
    front of a player mid-quest.
    """
    out: dict[str, int] = {}
    for name, constant in RE_ITEM_REQUIREMENT.findall(text):
        number = ids.get(constant)
        if number is not None:
            out.setdefault(name, number)
    return [{"name": n, "id": i} for n, i in sorted(out.items())]


def every(steps: dict):
    """Each instruction and each of its zone branches.

    A branch is an instruction in its own right -- its own npc, coordinate,
    items and icon -- so everything that resolves a constant has to reach it.
    Missing this shipped branches whose ids were still Quest Helper's constant
    names, which the plugin cannot look up.
    """
    for record in steps.values():
        yield from _with_branches(record)


def _with_branches(record: dict):
    """One instruction and every branch beneath it, however deep.

    A branch can be a conditional in its own right. Yielding only one level
    left forty-one icons still carrying quest-helper's constant name instead of
    a number, and the plugin refused the whole file over it.
    """
    yield record
    for branch in record.get("whenIn", ()):
        yield from _with_branches(branch)


def resolve_conditions(steps: dict, ids: dict, collections: dict) -> int:
    """Resolve the item ids inside branch conditions, dropping what will not.

    A condition that cannot be evaluated is worse than no branch at all: it
    would answer "no" for ever and the branch would never be chosen.
    """
    kept = 0
    for record in every(steps):
        surviving = []
        for branch in record.get("whenIn", ()):
            if resolve_requirement(branch.get("when") or {}, ids, collections):
                surviving.append(branch)
                kept += 1
        if surviving:
            record["whenIn"] = surviving
        else:
            record.pop("whenIn", None)
    return kept


def resolve_icons(steps: dict, ids: dict) -> int:
    """Turn each icon's ItemID constant into the number the plugin draws.

    An icon that will not resolve is dropped: half an instruction -- "use
    something on this" -- is worse than the sentence on its own.
    """
    resolved = 0
    for record in every(steps):
        constant = record.pop("icon", None)
        if constant is None:
            continue
        number = ids.get("item", {}).get(constant)
        if number is not None:
            record["icon"] = number
            resolved += 1
    return resolved


def resolve_step_items(steps: dict, ids: dict, collections: dict) -> int:
    """Turn each step's item requirements into ids, and drop what will not.

    A requirement naming an ItemCollections constant carries every member, best
    tier first, exactly as the guide's own category words do -- "Pickaxe" is any
    pickaxe. One that resolves to nothing is removed rather than shipped empty:
    an item with no id cannot be ringed, and listing it would put a line in
    front of the player that never clears.
    """
    resolved = 0
    for record in every(steps):
        kept = []
        for item in record.get("items", ()):
            numbers = resolved_item_ids(item, ids, collections)
            if not numbers:
                continue
            item["ids"] = numbers
            kept.append(item)
            resolved += 1
        if kept:
            record["items"] = kept
        else:
            record.pop("items", None)
    return resolved


def resolve_ids(steps: dict, ids: dict) -> int:
    """Turn each instruction's constant into the numbers the plugin can match.

    The plugin cannot resolve a constant name at runtime -- Plugin Hub forbids
    reflection -- so the numbers have to travel in the data, exactly as they do
    for diary bits. An instruction whose constant is not in RuneLite's own id
    classes keeps its coordinate and simply carries no ids: it can still be
    pathed to and marked on the map, just not outlined.
    """
    resolved = 0
    for record in every(steps):
        constant = record.get("constant")
        if not constant:
            continue
        group = "npc" if record.get("kind") == "npc" else "object"
        number = ids.get(group, {}).get(constant)
        if number is None:
            continue
        # The alternates are the same step's other faces: "Talk to Shilop or
        # Wilough" is one instruction with two npcs, and outlining only the
        # first left the player looking for a second that was never marked.
        numbers = [number]
        for other in record.pop("alternates", ()):
            also = ids.get(group, {}).get(other)
            if also is not None and also not in numbers:
                numbers.append(also)
        record["ids"] = numbers
        resolved += 1
    return resolved


RE_ROW_START = re.compile(r"^\t([A-Z][A-Z0-9_]*)\(\s*new\s+(\w+)\(\)", re.M)
RE_ROW_QUEST = re.compile(r"\bQuest\.([A-Z][A-Z0-9_]*)")
RE_ROW_VAR = re.compile(r"\bQuest(?:Varbits|VarPlayer)\.(QUEST_\w+)")


def reachable_ids(name: str, decls: dict, branches: dict, wants: dict,
                  drawn: dict, ids: dict) -> set[int]:
    """Every npc and object id a step could name, down every branch.

    Wider than what is shipped, and for a different purpose. The shipped
    instruction takes one branch, because showing the player two places at once
    is worse than showing one; this is asking "does this quest, at this progress
    value, involve that thing at all" -- and for that, every branch counts.

    It is what lets a guide step be placed on the quest's timeline: "Talk to
    Shilop to continue Gertrudes Cat" names npc 3501, quest-helper names 3501 at
    progress 1, so that step is progress 1. An exact id against quest-helper's
    own table, not a similarity.
    """
    found: set[int] = set()
    seen: set[str] = set()
    stack = [name]
    while stack:
        current = stack.pop()
        if current in seen or len(seen) > 200:
            continue
        seen.add(current)

        record = build(current, decls, branches, frozenset(), wants, drawn)
        if record is not None and record.get("constant"):
            group = "npc" if record.get("kind") == "npc" else "object"
            for constant in [record["constant"]] + list(record.get("alternates", ())):
                number = ids.get(group, {}).get(constant)
                if number is not None:
                    found.add(number)

        for _, step in branches.get(current, ()):
            stack.append(step.strip())
        declared = decls.get(current)
        if declared:
            stack.extend(a for a in declared[1] if re.fullmatch(r"\w+", a))
    return found


def panel_anchor_index(text: str, ids: dict) -> dict[str, list[int]]:
    """Game id -> the positions in quest-helper's own step list that name it.

    The same idea as :func:`anchor_index`, against a far finer ruler. A quest's
    progress value moves a handful of times; its sidebar has an entry for every
    action, and the guide writes its steps at that granularity -- "continue
    until you get the samples" is a point the value cannot express and the
    sidebar can.

    Built from the panels, so a step quest-helper does not list is not placed.
    """
    text = strip_comments(text)
    decls = declarations(text)
    methods = method_returns(text)
    follow_methods(text, decls, methods)
    branches = add_steps(text)
    wants = item_declarations(text)
    drawn = {"icon": icon_constants(text), "dialogue": dialogue_options(text),
             "dialogueRules": dialogue_rules(text), "choices": dialogue_changes(text),
             "alternates": alternate_ids(text), "said": renamed(text),
             "tiles": tile_markers(text), "linePoints": line_points(text), "questRoute": route_steps(text), "panel": panel_order(text),
             "widgets": _merged_widgets(text, VAR_IDS)}

    out: dict[str, list[int]] = {}
    for name, position in panel_order(text).items():
        for number in reachable_ids(name, decls, branches, wants, drawn, ids):
            where = out.setdefault(str(number), [])
            if position not in where:
                where.append(position)
    for where in out.values():
        where.sort()
    return out


def anchor_index(text: str, registers: str, ids: dict) -> dict[str, list[int]]:
    """Game id -> the progress values that id appears at, as strings for JSON.

    Read once per quest and used only to place the guide's steps against it.
    """
    text = strip_comments(text)
    registers = strip_comments(registers)
    decls = declarations(text)
    methods = method_returns(text)
    follow_methods(text, decls, methods)
    branches = add_steps(text)
    wants = item_declarations(text)
    drawn = {"icon": icon_constants(text), "dialogue": dialogue_options(text),
             "dialogueRules": dialogue_rules(text), "choices": dialogue_changes(text),
             "alternates": alternate_ids(text), "said": renamed(text),
             "tiles": tile_markers(text), "linePoints": line_points(text), "questRoute": route_steps(text), "panel": panel_order(text),
             "widgets": _merged_widgets(text, VAR_IDS)}

    puts = RE_PUT.findall(registers)
    if RE_BUILDER in registers:
        puts = puts + RE_BUILDER_PUT.findall(registers)

    out: dict[str, list[int]] = {}
    for raw_value, expression in puts:
        value = int(raw_value)
        for candidate in _names_in(expression, methods):
            for number in reachable_ids(candidate, decls, branches, wants, drawn, ids):
                where = out.setdefault(str(number), [])
                if value not in where:
                    where.append(value)
            break
    for where in out.values():
        where.sort()
    return out

def registered_helpers(root: Path) -> list[dict]:
    """One entry per quest Quest Helper registers, in enum order.

    Each row of QuestHelperQuest names the helper class, the RuneLite quest it
    is for, and where its progress lives:

        DRAGON_SLAYER_I(new DragonSlayer(), Quest.DRAGON_SLAYER_I,
            QuestVarPlayer.QUEST_DRAGON_SLAYER_I, ...)

    Read per row rather than per folder. The folder was the key until now, and
    a folder is neither one quest nor named after one: `dragonslayer` holds
    Dragon Slayer I, and eleven quests the route tags -- Underground Pass,
    Tribal Totem, Romeo & Juliet -- were dropped for no better reason than the
    folder being spelled differently from the quest.
    """
    path = root / "com/questhelper/questinfo/QuestHelperQuest.java"
    return helper_rows(path.read_text(encoding="utf-8")) if path.is_file() else []


def helper_rows(text: str) -> list[dict]:
    """The rows of QuestHelperQuest, read one at a time.

    Each row runs to the start of the next, never to the next match: the regex
    this replaced used a lazy match across newlines, so a row naming no
    progress variable ran on into the rows below it and took a third of the
    quests with it.
    """
    rows: list[dict] = []
    starts = list(RE_ROW_START.finditer(text))
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        body = text[match.start():end]
        var = RE_ROW_VAR.search(body)
        if var is None:
            # A helper with no progress variable cannot be looked up by value,
            # so there is nothing this pipeline can do with it.
            continue
        quest = RE_ROW_QUEST.search(body)
        rows.append({
            "constant": match.group(1),
            "helper": match.group(2),
            "quest": quest.group(1) if quest else None,
            "var": var.group(1),
        })
    return rows


def keys_for(row: dict, folder: str) -> list[str]:
    """The names this quest should answer to, most specific first.

    The route writes quest names as the wiki does, and three spellings have to
    meet: Quest Helper's own enum, RuneLite's Quest constant, and the folder.
    "Desert Treasure I" is DESERT_TREASURE in one and DESERT_TREASURE_I in the
    other, and "Romeo & Juliet" only ever matches ROMEO__JULIET.
    """
    names = [row["constant"]]
    if row["quest"]:
        names.append(row["quest"])
    seen: list[str] = []
    for name in names:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key and key not in seen:
            seen.append(key)
    if folder not in seen:
        seen.append(folder)
    return seen


RE_DIARY_BIT = re.compile(
    r"(\w+)\s*=\s*new\s+VarplayerRequirement\(\s*VarPlayerID\.(\w+)\s*,"
    r"\s*(?:false|true)\s*,\s*(\d+)")


def diary_tasks(root: Path, ids: dict, collections_by_name: dict) -> dict[str, dict]:
    """Diary task bit -> what Quest Helper says to do for it.

    Diary helpers are shaped differently from quests. There is no progress value
    to key on -- a diary varbit is done or not done -- so instead each task is
    an `addStep` whose condition is the task's own bit:

        notGotHaircut = new VarplayerRequirement(VarPlayerID.FALADOR_ACHIEVEMENT_DIARY, false, 3);
        doEasy.addStep(notGotHaircut, gotHaircutTask);
        getHaircut = new NpcStep(this, NpcID.HAIRDRESSER, new WorldPoint(2945, 3380, 0), ...);

    That bit is the same number `build_diary_tasks.py` already writes into each
    step's `completion`, read from the same VarPlayerID constants. So the join is
    two integers matching two integers -- no names, nothing to get wrong -- and
    it reaches 217 of the guide's 218 diary steps.

    Keyed "<varplayer>:<bit>" because JSON has no tuples.
    """
    out: dict[str, dict] = {}
    diaries = root / "com/questhelper/helpers/achievementdiaries"
    if not diaries.is_dir():
        return out

    for folder in sorted(p for p in diaries.iterdir() if p.is_dir()):
        text = strip_comments("\n".join(
            f.read_text(encoding="utf-8", errors="replace") for f in folder.glob("*.java")))
        decls = declarations(text)
        methods = method_returns(text)
        follow_methods(text, decls, methods)
        wants = item_declarations(text)
        drawn = icon_constants(text)
        branches = add_steps(text)

        bits: dict[str, str] = {}
        for variable, constant, bit in RE_DIARY_BIT.findall(text):
            number = ids["varplayer"].get(constant)
            if number is not None:
                bits[variable] = f"{number}:{bit}"

        for pairs in branches.values():
            for condition, step in pairs:
                key = bits.get(condition.strip())
                if key is None or key in out:
                    # Not a plain task bit -- a combined condition, or a step
                    # already claimed by an earlier difficulty. Both are left
                    # alone rather than guessed at.
                    continue
                record = build(step.strip(), decls, branches, frozenset(), wants, drawn)
                if record is not None:
                    out[key] = record

    resolve_ids(out, ids)
    resolve_step_items(out, ids, collections_by_name)
    resolve_icons(out, ids)
    # And the branch conditions, which the quest side does and this did not --
    # twelve diary branches shipped carrying a constant name the plugin cannot
    # look up, so they could never be true and never be chosen.
    resolve_conditions(out, ids, collections_by_name)
    return out

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--ids", type=Path, default=REPO / "build" / "ids.json")
    ap.add_argument("--atlas", type=Path, default=REPO / "build" / "atlas.json")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "quest_steps.json")
    args = ap.parse_args()

    root = args.source / "src" / "main" / "java"
    if not root.is_dir():
        print(f"no quest-helper source at {root}; writing an empty table")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"quests": {}}), encoding="utf-8")
        return 0

    ids = json.loads(args.ids.read_text(encoding="utf-8"))
    VAR_IDS.update(ids)
    variables = quest_vars(root, ids)
    # Quest Helper's own item categories, extracted by build_atlas.
    collections = json.loads(args.atlas.read_text(encoding="utf-8")).get(
        "collections", {}) if args.atlas.exists() else {}

    # Helper class name -> its folder and the folder's whole source. A step is
    # often declared in a sibling class, so declarations are read across the
    # folder even though steps.put is read from one file.
    folders: dict[str, tuple[str, str, Path]] = {}
    # Every folder under helpers, not only helpers/quests. Quest Helper files
    # miniquests separately, and Skippy and the Mogres and Vale Totems are two
    # the route tags -- looking in one folder lost both.
    seen: set[Path] = set()
    for source in sorted((root / "com/questhelper/helpers").rglob("*.java")):
        if source.parent in seen:
            continue
        seen.add(source.parent)
        files = sorted(source.parent.glob("*.java"))
        # And everything in its subfolders. The Path of Glouphrie declares
        # every step in sections/StartingOff.java and its siblings and only
        # lists them in the main class -- ".put(0, startingOff.talkToKingBolren)"
        # -- so reading one level found the table and none of its steps, and
        # the quest extracted nothing.
        nested = sorted(f for f in source.parent.rglob("*.java") if f.parent != source.parent)
        text = chr(10).join(f.read_text(encoding="utf-8", errors="replace") for f in files + nested)
        # A solver borrowed from another quest. The Ribbiting Tale and The
        # Final Dawn both open their chest with Desert Treasure II's
        # ChestCodeStep, and The Heart of Darkness uses Secrets of the
        # North's arrow chest. Reading one folder leaves that class
        # undeclared, so the step falls back to the first string in the
        # constructor: the branch holding the answer arrived saying "chest".
        for match in RE_QUEST_IMPORT.finditer(text):
            package, class_name = match.groups()
            if package == source.parent.name:
                continue
            borrowed = source.parent.parent / package / (class_name + ".java")
            if borrowed.is_file():
                text += chr(10) + borrowed.read_text(encoding="utf-8", errors="replace")
        for path in files:
            folders[path.stem] = (source.parent.name, text, path)

    quests: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    conditional_slots = 0
    resolved_ids = 0
    named_ids = 0
    required_items = 0
    step_item_ids = 0
    icons = 0
    zone_branches = 0
    spoken = 0
    alternates = 0
    for row in registered_helpers(root):
        variable = variables.get(row["var"])
        found = folders.get(row["helper"])
        if variable is None or found is None:
            continue
        folder, text, path = found
        own = path.read_text(encoding="utf-8", errors="replace")
        steps = steps_in(text, own)
        if not steps:
            continue

        conditional_slots += sum(1 for s in steps.values() if s.get("conditional"))
        resolved_ids += resolve_ids(steps, ids)
        step_item_ids += resolve_step_items(steps, ids, collections)
        icons += resolve_icons(steps, ids)
        zone_branches += resolve_conditions(steps, ids, collections)
        # Scope solver metadata to this helper's source folder. Every selected
        # branch keeps it: a text/listener condition may be unsupported, but
        # the actual visible puzzle controls are sufficient to show its hint.
        puzzles = []
        for puzzle_source in sorted(path.parent.glob('*.java')):
            puzzles.extend(cyclic_widget_puzzles(puzzle_source.read_text(encoding='utf-8'), ids))
        if puzzles:
            for instruction in every(steps):
                instruction['widgetPuzzles'] = puzzles
        named_ids += sum(1 for s in steps.values() if s.get("constant"))
        spoken += sum(len(s.get("dialogue", ())) for s in every(steps))
        alternates += sum(max(0, len(s.get("ids", ())) - 1) for s in every(steps))
        # From the helper's own file. Reading the folder gave Recipe for
        # Disaster's ten sub-quests each other's shopping lists.
        wanted = item_requirements(own, ids["item"])
        required_items += len(wanted)

        names = keys_for(row, folder)
        key = names[0]
        quests[key] = {
            "var": variable,
            "items": wanted,
            "itemAlternatives": item_alternatives(own, ids["item"]),
            # Where each thing this quest names sits on its own timeline, so a
            # guide step that names the same thing can be placed against it.
            "anchors": anchor_index(text, own, ids),
            # The highest value Quest Helper describes. Past it the quest is
            # over, and the plugin has to stop answering -- a floor lookup
            # otherwise returns "talk to X to complete the quest" forever,
            # long after the player did.
            "lastValue": max(steps),
            # How many steps quest-helper's own sidebar lists, so the last of
            # them can be named without the plugin having to scan for it. That
            # last step is where a guide step reading "continue X until Y" gives
            # way to the one reading "complete X".
            "panelCount": len(panel_order(text)),
            # Which of those steps name which game entity, so a guide step can
            # be placed on the quest's own timeline rather than only on its
            # progress value.
            "panelAnchors": panel_anchor_index(text, ids),
            "steps": {str(k): v for k, v in sorted(steps.items())},
        }
        for name in names[1:]:
            # First registration wins, so a sub-quest never takes the name of
            # the quest it belongs to: "recipefordisaster" is RFD - Start,
            # which is where a player told to start it should be sent.
            aliases.setdefault(name, key)

    # RuneLite and Quest Helper name the Recipe for Disaster sub-quests
    # differently, and the guide reaches a quest through RuneLite's name.
    # Three of the eight happened to squash to the same folder; these five did
    # not, so "Complete Dwarf RFD" linked to nothing. Only where the folder was
    # actually extracted -- an alias to nothing would hide that it is missing.
    for runelite, folder in RFD_FOLDERS.items():
        if folder in quests:
            aliases.setdefault(re.sub(r"[^a-z0-9]", "", runelite.lower()), folder)

    aliases = {name: key for name, key in aliases.items() if name not in quests}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tasks = diary_tasks(root, ids, collections)

    args.out.write_text(
        json.dumps({"source": "quest-helper (BSD 2-Clause)",
                    "aliases": aliases, "quests": quests, "tasks": tasks}, indent=1),
        encoding="utf-8")

    total = sum(len(q["steps"]) for q in quests.values())
    print(f"quests            {len(quests):5}")
    print(f"  also known as   {len(aliases):5}  (alternate spellings)")
    print(f"step slots        {total:5}")
    print(f"  from a default  {conditional_slots:5}  (conditional; branch not evaluated)")
    print(f"  naming a thing  {named_ids:5}")
    print(f"  with game ids   {resolved_ids:5}  (the rest keep only a coordinate)")
    print(f"quest items      {required_items:5}  (what each quest says to bring)")
    print(f"step items       {step_item_ids:5}  (what one step of it needs, in hand)")
    print(f"branches read    {zone_branches:5}  (a zone, an item held, or both)")
    print(f"item icons       {icons:5}  (drawn on the thing to use it on)")
    print(f"dialogue options {spoken:5}  (the words on them, not their number)")
    print(f"extra ids        {alternates:5}  (the same step's other npcs and objects)")
    print(f"diary tasks      {len(tasks):5}  (joined on the task's own bit)")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

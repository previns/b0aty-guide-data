"""Quest Helper's per-quest step list.

The extraction that lets the guide show what to do next inside a quest it only
partly completes. Pinned because two of its failures are silent: a regex that
runs past a line boundary drops whole quests, and a conditional step that loses
its flag would be presented as certainty.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_quest_steps as bqs  # noqa: E402

_rows = bqs.helper_rows

SOURCE = '''
	steps.put(0, speakVeosLumbridge);
	steps.put(1, steps.get(0));
	steps.put(2, digOutsideBob);
	speakVeosLumbridge = new NpcStep(this, NpcID.VEOS_VISIBLE, new WorldPoint(3228, 3242, 0),
		"Talk to Veos in The Sheared Ram pub.");
	digOutsideBob = new ConditionalStep(this, walkToBob);
	digOutsideBob.addStep(inArea, digHere);
	digOutsideBob.addStep(hasSpade, digThere);
	walkToBob = new DetailedQuestStep(this, new WorldPoint(3230, 3203, 0), "Walk to Bob's.");
'''


def test_a_direct_step_carries_its_target_and_text():
    steps = bqs.steps_in(SOURCE)
    assert steps[0]["kind"] == "npc"
    assert steps[0]["constant"] == "VEOS_VISIBLE"
    assert steps[0]["point"] == [3228, 3242, 0]
    assert steps[0]["text"].startswith("Talk to Veos")
    assert "conditional" not in steps[0]


def test_an_aliased_slot_repeats_the_instruction():
    """steps.put(1, steps.get(0)) is the same instruction under another value."""
    steps = bqs.steps_in(SOURCE)
    assert steps[1]["text"] == steps[0]["text"]


def test_a_conditional_step_is_flagged_with_its_branch_count():
    """Unflagged, the default branch would be shown as though it were certain."""
    steps = bqs.steps_in(SOURCE)
    assert steps[2]["conditional"] is True
    assert steps[2]["branches"] == 2
    # It still carries the default's instruction, which is the useful part.
    assert steps[2]["text"].startswith("Walk to Bob")


def test_a_slot_with_no_extractable_instruction_is_omitted():
    """Better a gap than a step with no target -- DigStep and the puzzle
    wrappers have no coordinates to give."""
    steps = bqs.steps_in("steps.put(4, digSomething);\n")
    assert steps == {}


def test_a_row_without_a_progress_variable_does_not_swallow_the_next():
    """A row is read to the start of the next row, not to the next match.

    The regex this replaced used a lazy `.*?` across newlines, so a row naming
    no QuestVarbits ran on into the rows below it and silently dropped a third
    of the quests -- X Marks the Spot among them.
    """
    text = (
        "\tNO_VARBIT_QUEST(new SomeQuest(), Quest.SOMETHING, QuestDetails.Type.F2P),\n"
        "\tX_MARKS_THE_SPOT(new XMarksTheSpot(), Quest.X_MARKS_THE_SPOT,"
        " QuestVarbits.QUEST_X_MARKS_THE_SPOT, QuestDetails.Type.F2P),\n"
    )
    rows = _rows(text)
    assert [r["constant"] for r in rows] == ["X_MARKS_THE_SPOT"]
    assert rows[0]["helper"] == "XMarksTheSpot"
    assert rows[0]["var"] == "QUEST_X_MARKS_THE_SPOT"


def test_a_quest_answers_to_every_spelling_of_its_name():
    """The wiki, Quest Helper's enum and RuneLite's Quest constant disagree.

    "Desert Treasure I" is DESERT_TREASURE in one table and DESERT_TREASURE_I
    in the other. Eleven quests the route tags were dropped over spellings like
    that, so both names -- and the folder -- have to lead to the same steps.
    """
    row = {"constant": "DESERT_TREASURE", "quest": "DESERT_TREASURE_I"}
    assert bqs.keys_for(row, "deserttreasure") == ["deserttreasure", "deserttreasurei"]

    row = {"constant": "ROMEO__JULIET", "quest": "ROMEO__JULIET"}
    assert bqs.keys_for(row, "romeoandjuliet") == ["romeojuliet", "romeoandjuliet"]


def test_a_step_with_prose_and_no_coordinate_is_kept():
    """Six hundred of Quest Helper's steps are prose alone.

    "Use your Doogle Leaves on the Sardine" names no coordinate because there
    is nowhere to go. Requiring a WorldPoint dropped all of them, which is how
    Gertrude's Cat came to ship one step out of five.
    """
    steps = bqs.steps_in(
        'steps.put(1, useLeaves);\n'
        'useLeaves = new DetailedQuestStep(this, "Use your Doogle Leaves on the Sardine.",'
        ' doogleLeaves, sardine);\n'
    )
    assert steps[1]["text"] == "Use your Doogle Leaves on the Sardine."
    assert steps[1]["point"] is None


def test_a_wrapped_step_lends_its_words():
    """PuzzleWrapperStep hands the same object two steps, one with the detail.

    Dwarf Cannon's toolkit step arrived with the cannon to click, the toolkit to
    use on it, and no words at all -- and the words are the step: "use the right
    tool on the spring, the middle tool on the Safety switch, and the left tool
    on the gear". The id and the coordinate were being read out of the nested
    step and the sentence was not.
    """
    steps = bqs.steps_in(
        'steps.put(0, useToolkit); '
        'useToolkit = new PuzzleWrapperStep(this,'
        ' new ObjectStep(this, ObjectID.DOOR, new WorldPoint(1, 2, 0),'
        ' "Use the right tool on the spring."),'
        ' new ObjectStep(this, ObjectID.DOOR, new WorldPoint(1, 2, 0), "Use it.")); '
    )
    assert steps[0]["text"] == "Use the right tool on the spring."
    assert steps[0]["constant"] == "DOOR", "and still knows what to click"


def test_a_nested_string_is_never_read_as_the_instruction():
    """Arguments are split at the top level for exactly this reason.

    An ObjectStep with no description of its own would otherwise borrow the
    name out of a nested requirement and show "Coins" as the instruction.
    """
    steps = bqs.steps_in(
        'steps.put(0, openDoor);\n'
        'openDoor = new ObjectStep(this, ObjectID.DOOR, new WorldPoint(1, 2, 0),'
        ' new ItemRequirement("Coins", ItemID.COINS));\n'
    )
    assert steps[0]["text"] == ""
    assert steps[0]["constant"] == "DOOR"


def test_a_conditional_chain_resolves_to_the_step_at_the_end_of_it():
    """A default that is itself a conditional was three hundred lost slots."""
    steps = bqs.steps_in(
        'steps.put(0, outer);\n'
        'outer = new ConditionalStep(this, inner, "Get the milk.");\n'
        'inner = new ConditionalStep(this, climbLadder);\n'
        'climbLadder = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(3, 4, 0),'
        ' "Climb the ladder.");\n'
    )
    assert steps[0]["constant"] == "LADDER"
    assert steps[0]["point"] == [3, 4, 0]
    # The outer sentence is the one Quest Helper puts in its sidebar.
    assert steps[0]["text"] == "Get the milk."
    # Nothing was added to either conditional, so there was never a choice to
    # get wrong. Flagging these "(varies)" dimmed a third of the diary tasks for
    # an uncertainty that does not exist.
    assert "conditional" not in steps[0]


def test_a_conditional_with_branches_is_flagged_as_a_guess():
    steps = bqs.steps_in(
        'steps.put(0, outer);\n'
        'outer = new ConditionalStep(this, climbLadder, "Get the milk.");\n'
        'outer.addStep(hasSomething, otherStep);\n'
        'otherStep = new NpcStep(this, NpcID.HANS, new WorldPoint(1, 1, 0), "Talk.");\n'
        'climbLadder = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(3, 4, 0),'
        ' "Climb the ladder.");\n'
    )
    assert steps[0]["conditional"] is True
    assert steps[0]["branches"] == 1


def test_a_step_built_inside_a_method_is_followed_to_its_return():
    """`steps.put(4, findFluffsKitten())` names nothing at the call site."""
    steps = bqs.steps_in(
        'steps.put(4, findFluffsKitten());\n'
        'steps.put(5, finish = returnToGertrude());\n'
        'private QuestStep findFluffsKitten()\n'
        '{\n'
        '\tsearchCrates = new NpcStep(this, NpcID.KITTENS_MEW, new WorldPoint(3306, 3505, 0),'
        ' "Search the crates.");\n'
        '\treturn searchCrates;\n'
        '}\n'
        'private NpcStep returnToGertrude()\n'
        '{\n'
        '\tbackToGertrude = new NpcStep(this, NpcID.GERTRUDE, new WorldPoint(3148, 3413, 0),'
        ' "Return to Gertrude.");\n'
        '\treturn backToGertrude;\n'
        '}\n'
    )
    assert steps[4]["constant"] == "KITTENS_MEW"
    assert steps[5]["constant"] == "GERTRUDE"


def test_a_placeholder_default_falls_back_to_the_last_branch():
    """Eleven conditionals default to a stand-in their own class replaces.

    Pirate's Treasure defaults to a sentence about opening the quest journal.
    Branches are written most-advanced first, so the last one is the state a
    player entering the step is in.
    """
    steps = bqs.steps_in(
        'steps.put(1, smuggleRum);\n'
        'smuggleRum = new RumSmugglingStep(this);\n'
        'class RumSmugglingStep extends ConditionalStep\n'
        '{\n'
        '\tRumSmugglingStep(QuestHelper questHelper)\n'
        '\t{\n'
        '\t\tsuper(questHelper, new DetailedQuestStep(questHelper,'
        ' "Please open the Quest Journal to sync the current quest state."));\n'
        '\t}\n'
        '\tvoid setup()\n'
        '\t{\n'
        '\t\tthis.addStep(hasRum, bringRumBack);\n'
        '\t\tthis.addStep(nothing, goToKaramja);\n'
        '\t}\n'
        '}\n'
        'bringRumBack = new NpcStep(this, NpcID.FRANK, new WorldPoint(1, 1, 0), "Bring it back.");\n'
        'goToKaramja = new NpcStep(this, NpcID.SEAMAN, new WorldPoint(2, 2, 0), "Sail to Karamja.");\n'
    )
    assert steps[1]["constant"] == "SEAMAN"
    assert steps[1]["conditional"] is True


def test_a_comment_holding_an_unbalanced_paren_does_not_swallow_the_file():
    """Quest Helper annotates ids inline: `ObjectID.X /* Crucible (empty */`."""
    steps = bqs.steps_in(
        'steps.put(0, useCrucible);\n'
        'useCrucible = new ObjectStep(this, ObjectID.CRUCIBLE /* Crucible (empty */,'
        ' new WorldPoint(5, 6, 0), "Use the crucible.");\n'
        'steps.put(1, after);\n'
        'after = new NpcStep(this, NpcID.SMITH, new WorldPoint(7, 8, 0), "Talk to the smith.");\n'
    )
    assert steps[0]["constant"] == "CRUCIBLE"
    assert steps[1]["constant"] == "SMITH"


def test_a_folder_holding_two_helpers_keeps_their_tables_apart():
    """Recipe for Disaster's folder holds ten registered helpers.

    Reading their steps.put calls together merged ten unrelated tables under
    one set of progress values, and that shipped: value 80 pointed at a chompy
    bird instead of Murphy.
    """
    shared = (
        'pete = new NpcStep(this, NpcID.MURPHY, new WorldPoint(1, 1, 0), "Talk to Murphy.");\n'
        'dave = new NpcStep(this, NpcID.EVIL_DAVE, new WorldPoint(2, 2, 0), "Talk to Dave.");\n'
        'steps.put(80, pete);\n'
        'steps.put(80, dave);\n'
    )
    only_pete = 'steps.put(80, pete);\n'
    assert bqs.steps_in(shared, only_pete)[80]["constant"] == "MURPHY"


def test_a_step_that_reaches_itself_does_not_hang_the_build():
    """One quest looping would otherwise fail the whole refresh."""
    steps = bqs.steps_in(
        'steps.put(0, a);\n'
        'a = new ConditionalStep(this, b);\n'
        'b = new ConditionalStep(this, a);\n'
    )
    assert steps == {}


def test_the_shipped_table_has_x_marks_the_spot():
    import json
    path = Path(__file__).resolve().parent.parent / "build" / "quest_steps.json"
    if not path.exists():
        return
    quests = json.loads(path.read_text(encoding="utf-8"))["quests"]
    quest = quests.get("xmarksthespot")
    assert quest is not None, "X Marks the Spot should extract"
    assert quest["var"]["kind"] == "varbit"
    assert quest["steps"]["0"]["constant"] == "VEOS_VISIBLE"


def test_a_step_carries_the_items_it_was_handed():
    """Quest Helper gives its requirements to the step that needs them.

    Reading only the per-quest list showed a player halfway through a quest the
    whole shopping list or nothing at all, while Quest Helper was ringing the
    two things the step in front of them actually wanted.
    """
    steps = bqs.steps_in(
        'steps.put(0, useLeaves);\n'
        'sardine = new ItemRequirement("Raw Sardine", ItemID.RAW_SARDINE);\n'
        'doogleLeaves = new ItemRequirement("Doogle Leaves", ItemID.DOOGLELEAVES);\n'
        'coins = new ItemRequirement("Coins", ItemCollections.COINS, 100);\n'
        'useLeaves = new DetailedQuestStep(this, "Use the leaves on the sardine.",'
        ' sardine, doogleLeaves, coins);\n'
    )
    names = [item["name"] for item in steps[0]["items"]]
    assert names == ["Raw Sardine", "Doogle Leaves", "Coins"]
    assert steps[0]["items"][2]["count"] == 100
    assert steps[0]["items"][2]["collection"] == "COINS"


def test_a_requirement_with_no_id_is_not_shipped():
    """`new ItemRequirement("Coins", -1, -1)` stands in for something the quest
    cannot name yet. An item with no id cannot be ringed, and listing it puts a
    line in front of the player that never clears."""
    steps = bqs.steps_in(
        'steps.put(0, talk);\n'
        'mystery = new ItemRequirement("Something", -1, -1);\n'
        'rope = new ItemRequirement("Rope", ItemID.ROPE);\n'
        'talk = new NpcStep(this, NpcID.HANS, new WorldPoint(1, 2, 0), "Talk.",'
        ' mystery, rope);\n'
    )
    assert [i["name"] for i in steps[0]["items"]] == ["Rope"]
    bqs.resolve_step_items(steps, {"item": {"ROPE": 954}}, {})
    assert steps[0]["items"] == [{"name": "Rope", "count": 1, "ids": [954]}]


def test_a_nested_requirement_is_not_read_as_the_steps_own():
    """Arguments are read at the top level, so a requirement built inside
    another constructor belongs to that one and not to the step."""
    steps = bqs.steps_in(
        'steps.put(0, open);\n'
        'open = new ObjectStep(this, ObjectID.DOOR, new WorldPoint(1, 2, 0), "Open it.",'
        ' new ItemRequirements(LogicType.AND, "", new ItemRequirement("Key", ItemID.KEY)));\n'
    )
    assert "items" not in steps[0]


def test_a_conditional_lists_its_own_items_before_its_branch_s():
    """The choice names what the whole step needs; the branch names its own."""
    steps = bqs.steps_in(
        'steps.put(2, giveMilk);\n'
        'sardine = new ItemRequirement("Seasoned Sardine", ItemID.SEASONED_SARDINE);\n'
        'milk = new ItemRequirement("Bucket of milk", ItemID.BUCKET_MILK);\n'
        'climbLadder = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(3, 4, 0),'
        ' "Climb the ladder.", milk);\n'
        'giveMilk = new ConditionalStep(this, climbLadder, "Use the milk on the cat.",'
        ' sardine);\n'
    )
    assert [i["name"] for i in steps[2]["items"]] == ["Seasoned Sardine", "Bucket of milk"]


def test_a_zone_branch_is_read_and_the_default_is_kept():
    """A third of quest-helper's branch conditions are a bare zone.

    A zone is a box on the map, so the branch can be chosen exactly without any
    of the condition engine this pipeline refuses to port. Gertrude's Cat is the
    shape of it: downstairs climb the ladder, upstairs use the milk on the cat.
    """
    steps = bqs.steps_in(
        'steps.put(2, giveMilkToCat);\n'
        'zone = new Zone(new WorldPoint(3306, 3507, 1), new WorldPoint(3312, 3513, 2));\n'
        'upstairs = new ZoneRequirement(zone);\n'
        'climbLadder = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(3310, 3509, 0),'
        ' "Climb the ladder.");\n'
        'theCat = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(3308, 3511, 1), "");\n'
        'giveMilkToCat = new ConditionalStep(this, climbLadder, "Use the milk on the cat.");\n'
        'giveMilkToCat.addStep(upstairs, theCat);\n'
    )
    assert steps[2]["constant"] == "LADDER"
    branch = steps[2]["whenIn"][0]
    assert branch["constant"] == "GERTRUDESCAT"
    assert branch["when"] == {"zone": [[3306, 3507, 1, 3312, 3513, 2]]}
    # A branch with no words of its own borrows the choice's sentence.
    assert branch["text"] == "Use the milk on the cat."
    # Its zone was matched, so it is not a guess.
    assert "conditional" not in branch


def test_a_zone_below_an_unreadable_condition_stays_a_guess():
    """A ConditionalStep returns the first branch whose conditions hold.

    An earlier branch this pipeline cannot evaluate might have been the one
    Quest Helper picked, so a zone match beneath it proves nothing.
    """
    steps = bqs.steps_in(
        'steps.put(0, choice);\n'
        'zone = new Zone(new WorldPoint(1, 1, 0), new WorldPoint(9, 9, 0));\n'
        'inside = new ZoneRequirement(zone);\n'
        'fallback = new NpcStep(this, NpcID.HANS, new WorldPoint(5, 5, 0), "Fall back.");\n'
        'first = new NpcStep(this, NpcID.COOK, new WorldPoint(6, 6, 0), "First.");\n'
        'second = new NpcStep(this, NpcID.DUKE, new WorldPoint(7, 7, 0), "Second.");\n'
        'choice = new ConditionalStep(this, fallback);\n'
        'choice.addStep(hasSomething, first);\n'
        'choice.addStep(inside, second);\n'
    )
    branch = steps[0]["whenIn"][0]
    assert branch["constant"] == "DUKE"
    assert branch["conditional"] is True


def test_a_branch_can_turn_on_an_item_being_held():
    """"Do you have the kitten" is a lookup, not logic, and the inventory
    already answers it for the bank ring and the auto-tick."""
    steps = bqs.steps_in(
        'steps.put(4, findKitten);\n'
        'hasKitten = new ItemRequirement("Fluffs kitten", ItemID.GERTRUDEKITTENS);\n'
        'searchCrates = new NpcStep(this, NpcID.KITTENS_MEW, new WorldPoint(1, 1, 0),'
        ' "Search the crates.");\n'
        'giveToFluffy = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(2, 2, 1),'
        ' "Return the kitten.");\n'
        'findKitten = new ConditionalStep(this, searchCrates);\n'
        'findKitten.addStep(hasKitten, giveToFluffy);\n'
    )
    assert steps[4]["constant"] == "KITTENS_MEW"
    branch = steps[4]["whenIn"][0]
    assert branch["constant"] == "GERTRUDESCAT"
    assert branch["when"]["item"]["name"] == "Fluffs kitten"


def test_a_branch_can_need_the_item_and_the_place_together():
    steps = bqs.steps_in(
        'steps.put(4, findKitten);\n'
        'zone = new Zone(new WorldPoint(1, 1, 1), new WorldPoint(9, 9, 1));\n'
        'upstairs = new ZoneRequirement(zone);\n'
        'hasKitten = new ItemRequirement("Kitten", ItemID.GERTRUDEKITTENS);\n'
        'both = new Conditions(hasKitten, upstairs);\n'
        'searchCrates = new NpcStep(this, NpcID.KITTENS_MEW, new WorldPoint(1, 1, 0), "Search.");\n'
        'giveToFluffy = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(2, 2, 1), "Return it.");\n'
        'findKitten = new ConditionalStep(this, searchCrates);\n'
        'findKitten.addStep(both, giveToFluffy);\n'
    )
    when = steps[4]["whenIn"][0]["when"]
    assert set(when) == {"all"}
    assert len(when["all"]) == 2


def test_a_condition_that_cannot_be_read_ships_no_branch():
    """A branch whose condition would always answer "no" is worse than none: it
    can never be chosen, and it hides that the default is a guess."""
    steps = bqs.steps_in(
        'steps.put(0, choice);\n'
        'fallback = new NpcStep(this, NpcID.HANS, new WorldPoint(1, 1, 0), "Wait.");\n'
        'other = new NpcStep(this, NpcID.COOK, new WorldPoint(2, 2, 0), "Cook.");\n'
        'choice = new ConditionalStep(this, fallback);\n'
        'choice.addStep(new SkillRequirement(Skill.MAGIC, 50), other);\n'
    )
    assert "whenIn" not in steps[0]
    assert steps[0]["conditional"] is True


def test_a_step_that_says_they_all_count_is_marked():
    """`new NpcStep(..., point, "...", true)` is allowMultipleHighlights. The
    kitten could be in any of the Lumberyard crates, and marking the nearest
    crate is no help at all."""
    steps = bqs.steps_in(
        'steps.put(4, searchCrates);\n'
        'searchCrates = new NpcStep(this, NpcID.KITTENS_MEW, new WorldPoint(3306, 3505, 0),'
        ' "Search for a kitten in the crates.", true);\n'
    )
    assert steps[4]["spread"] is True

    ladder = bqs.steps_in(
        'steps.put(2, climb);\n'
        'climb = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(3310, 3509, 0),'
        ' "Climb the ladder.");\n'
    )
    assert "spread" not in ladder[2]


def test_a_renamed_step_shows_its_new_words():
    """quest-helper reuses a step and renames it for the branch it appears in,
    and the constructor's own sentence is then the wrong one to show."""
    steps = bqs.steps_in(
        'steps.put(0, theCat);\n'
        'theCat = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(1, 1, 1), "Talk to it.");\n'
        'theCat.setText("Return the kitten to Gertrudes cat.");\n'
    )
    assert steps[0]["text"] == "Return the kitten to Gertrudes cat."


def test_a_region_zone_covers_that_region():
    """`new Zone(regionID)` is the whole region on planes 0 to 2, which is what
    quest-helper's Zone computes from the id."""
    # 12850 is 0x3232, so both halves are 50 and both bases are 50 << 6.
    assert bqs.zone_box(["12850"]) == [3200, 3200, 0, 3264, 3264, 2]
    assert bqs.zone_box(["12850", "1"]) == [3200, 3200, 1, 3264, 3264, 1]


def test_a_zone_built_from_helpers_is_refused_rather_than_guessed():
    """`new Zone(regionPoint(34, 17), regionPoint(39, 25))` does arithmetic in
    the quest's own class. Approximating it would put a branch in front of the
    player in the wrong place."""
    assert bqs.zone_box(["regionPoint(34, 17)", "regionPoint(39, 25)"]) is None


def test_an_icon_names_the_item_to_use_on_the_target():
    """`addIcon` is quest-helper saying "use this on that" -- the sprite goes on
    the npc and the item lights up in the inventory."""
    steps = bqs.steps_in(
        'steps.put(0, theCat);\n'
        'theCat = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(1, 2, 1), "Use it.");\n'
        'theCat.addIcon(ItemID.BUCKET_MILK);\n'
    )
    assert steps[0]["icon"] == "BUCKET_MILK"
    assert bqs.resolve_icons(steps, {"item": {"BUCKET_MILK": 1927}}) == 1
    assert steps[0]["icon"] == 1927


def test_an_unresolved_icon_is_dropped():
    """Half an instruction -- "use something on this" -- is worse than the
    sentence on its own."""
    steps = bqs.steps_in(
        'steps.put(0, theCat);\n'
        'theCat = new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(1, 2, 1), "Use it.");\n'
        'theCat.addIcon(ItemID.NOT_A_REAL_ITEM);\n'
    )
    assert bqs.resolve_icons(steps, {"item": {}}) == 0
    assert "icon" not in steps[0]


def test_a_step_built_by_a_method_taking_arguments_is_followed():
    """`gertrudesCat = getGertrudesCat(milkHighlighted)` builds the step inside a
    method, so the field has no `new` of its own. Following only zero-argument
    methods lost the branch that says to use the milk on the cat."""
    steps = bqs.steps_in(
        'steps.put(0, theCat);\n'
        'theCat = getGertrudesCat(milkHighlighted);\n'
        'private NpcStep getGertrudesCat(ItemRequirement... requirement)\n'
        '{\n'
        '\treturn new NpcStep(this, NpcID.GERTRUDESCAT, new WorldPoint(3308, 3511, 1), "");\n'
        '}\n'
    )
    assert steps[0]["constant"] == "GERTRUDESCAT"
    assert steps[0]["point"] == [3308, 3511, 1]

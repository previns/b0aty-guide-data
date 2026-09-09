"""A ConditionalStep handed another ConditionalStep as its default.

Hazeel Cult writes exactly this:

    var hazeelSteps = new ConditionalStep(this, enterKitchenAfterButler);
    hazeelSteps.addStep(and(inCultRoom, hadScroll), giveAlomoneScroll);
    ... fourteen arms in all ...

    var step6 = new ConditionalStep(this, hazeelSteps);
    step6.addStep(sidedWithCeril, cerilSteps);
    steps.put(6, step6);

The outer step's branches used to be written *over* the default's rather than
added to them, so all fourteen arms were thrown away and the whole quest slot
answered with `enterKitchenAfterButler` -- whose text is "Search a crate in the
Carnillean's basement kitchen for a key". The guide author reported precisely
that: at "Return to Alomone with the scroll" the plugin sent them to a crate.

quest-helper checks the outer branches first and only then falls through to the
default, which checks its own, so the outer ones come first here.
"""
from pipeline import build_quest_steps as q


SETUP = '''
crate = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(1, 2, 0), "Search a crate for a key");
scroll = new NpcStep(this, NpcID.ONE, new WorldPoint(1, 2, 0), "Return to Alomone with the scroll");
valves = new ObjectStep(this, ObjectID.GATE, new WorldPoint(3, 4, 0), "Turn the valves");
armour = new NpcStep(this, NpcID.TWO, new WorldPoint(3, 4, 0), "Bring the armour to Ceril");
hasScroll = new VarbitRequirement(10, 1);
sidedWithCeril = new VarbitRequirement(11, 1);
inCultRoom = new VarbitRequirement(12, 1);
inner = new ConditionalStep(this, crate);
inner.addStep(hasScroll, scroll);
ceril = new ConditionalStep(this, valves);
ceril.addStep(inCultRoom, armour);
'''


def texts(record):
    return [b["text"] for b in record.get("whenIn", [])]


def test_a_nested_default_keeps_its_own_branches():
    result = q.steps_in(SETUP + '''
outer = new ConditionalStep(this, inner);
outer.addStep(sidedWithCeril, ceril);
steps.put(6, outer);
''')
    step = result[6]
    # The default of the default is still what the slot falls back to.
    assert step["text"] == "Search a crate for a key"

    got = texts(step)
    assert "Turn the valves" in got, "the outer step's own branch"
    assert "Return to Alomone with the scroll" in got, "the nested default's branch"
    # Asked in the order quest-helper asks them.
    assert got.index("Turn the valves") < got.index("Return to Alomone with the scroll")
    assert step["branches"] == len(got)


def test_a_nested_default_without_outer_branches_is_unchanged():
    """The path that already worked must keep working."""
    result = q.steps_in(SETUP + '''
outer = new ConditionalStep(this, inner);
steps.put(7, outer);
''')
    assert result[7]["text"] == "Search a crate for a key"
    assert texts(result[7]) == ["Return to Alomone with the scroll"]

"""DetailedOwnerStep drives itself, and says so in a different dialect.

Most of quest-helper writes a choice as `conditional.addStep(cond, step)`. A
`DetailedOwnerStep` subclass instead overrides `updateSteps()` and writes:

    if (atValve1.check(client))
    {
        startUpStep(turnValve1);
    }

which is the same sentence. Reading only addStep left Hazeel Cult's five valves
-- their order, and which way each one turns -- as the single line "Turn the
valves near the cave to direct the underground water", and the guide author
reported exactly that.

38 classes extend DetailedOwnerStep and 42 branches are written this way.
"""
from pipeline import build_quest_steps as q


SETUP = '''
valve1 = new Zone(new WorldPoint(2560, 3245, 0), new WorldPoint(2565, 3251, 0));
valve2 = new Zone(new WorldPoint(2567, 3262, 0), new WorldPoint(2575, 3264, 0));
atValve1 = new ZoneRequirement(valve1);
atValve2 = new ZoneRequirement(valve2);
turnValve1 = new ObjectStep(getQuestHelper(), ObjectID.SEWERVALVE1, new WorldPoint(2562, 3247, 0), "Turn the valve west of the Clocktower to the right.");
turnValve2 = new ObjectStep(getQuestHelper(), ObjectID.SEWERVALVE2, new WorldPoint(2572, 3263, 0), "Turn the valve east of the Clocktower to the left.");
'''


def test_the_owner_step_idiom_is_read_as_a_branch():
    branches = q.add_steps('''
public class Valves extends DetailedOwnerStep
{
	protected void updateSteps()
	{
		if (!solved1.check(client))
		{
			if (atValve1.check(client))
			{
				startUpStep(turnValve1);
			}
		}
		else if (atValve2.check(client))
		{
			startUpStep(turnValve2);
		}
	}
}
''')
    assert branches["Valves"] == [("atValve1", "turnValve1"), ("atValve2", "turnValve2")]


def test_a_negated_guard_is_not_read_as_a_branch():
    """`!solved1.check(client)` is a RuneliteRequirement behind a widget
    listener. Reading it as a branch would promise a choice we cannot make."""
    branches = q.add_steps('''
public class Valves extends DetailedOwnerStep
{
	protected void updateSteps()
	{
		if (!solved1.check(client))
		{
			startUpStep(turnValve1);
		}
	}
}
''')
    assert branches.get("Valves") is None


def test_addStep_and_the_owner_idiom_keep_source_order():
    """A conditional returns the first branch that holds, so order is meaning."""
    branches = q.add_steps('''
public class Mixed extends DetailedOwnerStep
{
	void build()
	{
		this.addStep(condA, stepA);
		if (condB.check(client))
		{
			startUpStep(stepB);
		}
		this.addStep(condC, stepC);
	}
}
''')
    assert branches["Mixed"] == [("condA", "stepA"), ("condB", "stepB"), ("condC", "stepC")]

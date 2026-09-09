"""The source's copy semantics, including independent ordered branches."""
from pipeline import build_quest_steps as q


SETUP = '''
fallback = new ObjectStep(this, ObjectID.LADDER, new WorldPoint(1, 2, 0), "Downstairs");
first = new NpcStep(this, NpcID.ONE, new WorldPoint(1, 2, 0), "First");
second = new NpcStep(this, NpcID.TWO, new WorldPoint(1, 2, 0), "Second");
conditionA = new VarbitRequirement(10, 1);
conditionB = new VarbitRequirement(11, 1);
base = new ConditionalStep(this, fallback);
'''


def texts(record):
    return [b["text"] for b in record.get("whenIn", [])]


def test_copied_default_and_added_branch_are_both_retained():
    result = q.steps_in(SETUP + '''
clone = base.copy();
clone.addStep(conditionA, first);
steps.put(1, clone);
steps.put(2, base);
''')
    assert result[1]["text"] == "Downstairs"
    assert texts(result[1]) == ["First"]
    assert texts(result[2]) == []


def test_copy_snapshots_inherited_conditions_before_later_source_mutations():
    result = q.steps_in(SETUP + '''
base.addStep(conditionA, first);
clone = base.copy();
base.addStep(conditionB, second);
steps.put(1, clone);
steps.put(2, base);
''')
    assert texts(result[1]) == ["First"]
    assert texts(result[2]) == ["First", "Second"]


def test_copies_of_copies_inherit_conditions_without_sharing_mutations():
    result = q.steps_in(SETUP + '''
base.addStep(conditionA, first);
clone = base.copy();
clone.addStep(conditionB, second);
third = clone.copy();
clone.addStep(conditionA, second);
steps.put(1, third);
steps.put(2, clone);
''')
    assert texts(result[1]) == ["First", "Second"]
    assert texts(result[2]) == ["Second", "Second"]


def test_unknown_copy_is_not_guessed_as_a_step():
    assert q.steps_in(SETUP + 'clone = unknown.copy(); steps.put(1, clone);') == {}


def test_at_first_light_pre_fox_slots_are_all_extracted(monkeypatch):
    import json
    from pathlib import Path
    ids = json.loads((q.REPO / "build/ids.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(q, "VAR_IDS", {"varbit": ids["varbit"], "varplayer": ids["varplayer"], "interface": ids["interface"]})
    source = Path(q.DEFAULT_SOURCE) / "src/main/java/com/questhelper/helpers/quests/atfirstlight/AtFirstLight.java"
    result = q.steps_in(source.read_text(encoding="utf-8"))
    assert {0, 1, 2, 3, 4} <= result.keys()
    assert any("Verity" in text for text in texts(result[1]))
    assert any("Wolf" in text for text in texts(result[2]))
    assert len(result[3]["whenIn"]) == 5

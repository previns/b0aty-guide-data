import json
from pathlib import Path
from pipeline.annotate import annotate_step
from pipeline.merge_curated import is_preparation, attach_quest_side_tasks


def test_timed_pickup_is_supplies_not_the_tagged_quest():
    text = 'When you go talk to Anita, take 2 Swamp toads [Tai Bwo Wannai Trio]'
    assert is_preparation(text, 1)
    assert annotate_step(text)['items'] == [{'name': 'Swamp toads', 'count': 2}]


def test_explicit_during_quest_links_to_previous_anchor_only():
    anchor = {'id': 'a', 'raw': 'Continue Quest', 'merged': {'questStep': True}}
    task = {'id': 'b', 'raw': 'During the quest, collect a cowhide', 'merged': {}}
    unrelated = {'id': 'c', 'raw': 'When the tree grows, cut it', 'merged': {}}
    assert attach_quest_side_tasks({'sections': [{'steps': [anchor, task, unrelated]}]}) == 1
    assert task['merged']['questSideTaskOf'] == 'a'
    assert 'questSideTaskOf' not in unrelated['merged']


def test_bank25_reminders_have_verified_stages_and_supplies():
    g = json.loads((Path(__file__).resolve().parents[1] / 'dist/guide.json').read_text(encoding='utf-8'))
    steps = {s['id']: s for sec in g['sections'] for s in sec['steps']}
    for key, stage in [('57ebcf3e91', 80), ('30f3fe36a6', 100), ('4d95617033', 110)]:
        assert steps[key]['questSideTaskFrom'] == stage
        assert steps[steps[key]['questSideTaskOf']]['questHelper'] == 'thegrandtree'
    assert not steps['30f3fe36a6'].get('questStep')
    assert steps['30f3fe36a6']['items'][0]['count'] == 2
    assert steps['30f3fe36a6']['items'][0]['ids'] == [2150]
    for section in g['sections']:
        previous = set()
        for step in section['steps']:
            anchor = step.get('questSideTaskOf')
            if anchor:
                assert anchor in previous
                assert steps[anchor].get('questStep')
                assert step.get('questSideTaskFrom', 0) >= 0
            previous.add(step['id'])

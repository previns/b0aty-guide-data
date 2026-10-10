"""Arrival must use a resolved final destination and must never skip a second task."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline'))
from merge_curated import arrival_point


def destination(name='Lumbridge', points=None, **extras):
    return {'destination': {'name': name, 'points': points or [[3222, 3218, 0]], **extras}}


@pytest.mark.parametrize('raw', ['Teleport to Lumbridge', 'Home teleport to [[Lumbridge]]',
                                 'Head to Lumbridge', 'Return to Lumbridge'])
def test_pure_travel(raw):
    assert arrival_point(raw, destination()) == [3222, 3218, 0]


@pytest.mark.parametrize('raw', ['Teleport to Lumbridge & talk to Bob',
    'Teleport to Lumbridge [Lumbridge Medium Diary]', 'Head to Lumbridge and buy an axe',
    'Return to Ardougne & complete Plague City', 'Head to Lumbridge; search the crate',
    'Head to Lumbridge to continue a quest', 'Teleport to Lumbridge if needed'])
def test_compound_or_conditional_steps_stay_manual(raw):
    assert arrival_point(raw, destination()) is None


@pytest.mark.parametrize('key', ['completion', 'questStep', 'advice'])
def test_other_completion_requirements_win(key):
    assert arrival_point('Head to Lumbridge', {**destination(), key: True}) is None


def test_resolved_destination_wins_over_upstairs_wiki_marker():
    merged = destination('Grand Tree', [[2465, 3495, 0]])
    merged['target'] = {'points': [[2466, 3492, 1]]}
    assert arrival_point('Head to the Grand Tree', merged) == [2465, 3495, 0]


def test_ambiguous_destination_cannot_fall_back_to_an_arbitrary_target():
    merged = destination(points=[[1, 2, 0], [3, 4, 0]], ambiguous=True)
    merged['target'] = {'points': [[1, 2, 0]], 'kind': 'place', 'confidence': 'wiki-exact'}
    assert arrival_point('Head to Lumbridge', merged) is None


def test_ship_arrival_wins_over_boarding_npc_and_destination_marker():
    merged = destination('Entrana')
    merged['travel'] = {'destination': [2834, 3331, 1]}
    assert arrival_point('Head to Entrana', merged) == [2834, 3331, 1]


def test_shipped_guide_uses_the_final_arrival_contract():
    guide = json.loads((ROOT / 'dist/guide.json').read_text(encoding='utf-8'))
    steps = [s for section in guide['sections'] for s in section['steps']]
    for step in steps:
        if step['text'] in ('Teleport to Lumbridge', 'Home teleport to Lumbridge'):
            assert step['arrivesAt'] == [3222, 3218, 0]
        if step['text'] == 'Head to the Grand Tree':
            assert step['arrivesAt'] == [2465, 3495, 0]
        if step.get('arrivesAt'):
            assert not step.get('completion')
            assert not step.get('questStep')

import json
import pytest
from pathlib import Path

from pipeline import build_quest_steps as q


def test_source_cyclic_solver_is_extracted_without_quest_constants_in_renderer():
    source = Path(q.DEFAULT_SOURCE) / 'src/main/java/com/questhelper/helpers/quests/tribaltotem/PuzzleStep.java'
    if not source.exists():
        pytest.skip('Local Quest Helper source is not installed')
    ids = json.loads((q.REPO / 'build/ids.json').read_text(encoding='utf-8'))
    text = source.read_text(encoding='utf-8')
    puzzles = q.cyclic_widget_puzzles(text, ids)
    assert len(puzzles) == 1
    puzzle = puzzles[0]
    assert [c['target'] for c in puzzle['cycles']] == [11, 21, 18, 20]
    assert [c['varbit'] for c in puzzle['cycles']] == [14807, 14808, 14809, 14810]
    assert puzzle['submit'] == 24182843
    assert all(c['size'] == 26 for c in puzzle['cycles'])
    assert not q.cyclic_widget_puzzles(text.replace('arrowLeftId : arrowRightId', 'arrowRightId : arrowLeftId'), ids)
    assert not q.cyclic_widget_puzzles(text, {'interface': {}, 'varbit': ids['varbit']})
    assert not q.cyclic_widget_puzzles(text, {'interface': ids['interface'], 'varbit': {}})
    assert not q.cyclic_widget_puzzles(text.replace('== 0)', '== 1)'), ids)


def test_every_tribal_totem_branch_keeps_the_visible_interface_solver():
    guide = json.loads((q.REPO / 'dist/guide.json').read_text(encoding='utf-8'))
    nodes = list(q.every(guide['questHelpers']['tribaltotem']['steps']))
    assert nodes
    for node in nodes:
        assert len(node['widgetPuzzles']) == 1
        assert [c['target'] for c in node['widgetPuzzles'][0]['cycles']] == [11, 21, 18, 20]


def test_all_emitted_puzzles_have_complete_safe_control_contracts():
    guide = json.loads((q.REPO / 'dist/guide.json').read_text(encoding='utf-8'))
    owners = set()
    for key, helper in guide['questHelpers'].items():
        for node in q.every(helper['steps']):
            for puzzle in node.get('widgetPuzzles', []):
                owners.add(key)
                assert puzzle['submit'] > 0
                assert 2 <= len(puzzle['cycles']) <= 8
                controls = [puzzle['submit']]
                for cycle in puzzle['cycles']:
                    assert cycle['varbit'] >= 0
                    assert 2 <= cycle['size'] <= 128
                    assert 1 <= cycle['target'] <= cycle['size']
                    assert cycle['left'] > 0 and cycle['right'] > 0
                    controls.extend([cycle['left'], cycle['right']])
                assert len(controls) == len(set(controls))
    assert owners == {'tribaltotem'}

"""Every shipped node is checked, with negative controls against silent loss."""
import copy
import gzip
import json
from pathlib import Path

from pipeline.audit_regressions import inventory

ROOT = Path(__file__).resolve().parents[1]


def artifacts():
    guide = json.loads((ROOT / 'dist/guide.json').read_text(encoding='utf-8'))
    annotations = json.loads((ROOT / 'build/annotated.json').read_text(encoding='utf-8'))
    with gzip.open(ROOT / 'pinned/quest_steps.json.gz', 'rt', encoding='utf-8') as stream:
        reference = json.load(stream)
    return guide, annotations, reference


def test_every_shipped_helper_and_diary_branch_survives_merge_and_emit():
    result = inventory(*artifacts())
    assert not result['issues'], result['issues']
    assert result['steps'] == 2925
    # 13970 until the Lily Pad Labour Dispute alias, 2026-09-11. That step
    # named a quest we held sixteen Quest Helper steps for and linked to none
    # of them; linking it shipped those instructions, hence +18.
    #
    # 13988 -> 14113 the same day, reading Quest Helper's puzzle solutions:
    # PuzzleWrapperStep's own sentence is the one shown with solutions turned
    # OFF, sibling classes in a quest folder crossed their super() text over,
    # a conditional with a null default dropped every branch it had, and
    # WidgetTextRequirement -- which guards every interface solver -- could
    # not be read at all.
    #
    # 14113 -> 14573 on 2026-10-07: Quest Helper's stateful conditions became
    # readable -- RuneliteRequirement, DialogRequirement and Conditions(true,
    # ...) -- so 460 branches that turned on them stopped being dropped.
    # Murder Mystery's whole investigation was among them: nine branches, of
    # which the shipped guide carried none.
    #
    # 14573 -> 14816 the same day: quests Quest Helper drives from one root
    # step (ComplexStateQuestHelper -- Elemental Workshop I, the Barcrawl)
    # were read through loadStep(), Recipe for Disaster's subquests were
    # matched to their folders, and steps declared in a quest's subfolders or
    # reached through a dotted field (Path of Glouphrie) became visible.
    assert result['instructions'] == 14816


def test_inventory_detects_lost_nested_branches_not_just_total_counts():
    guide, annotations, reference = artifacts()
    damaged = copy.deepcopy(guide)
    node = next(n for h in damaged['questHelpers'].values() for n in h['steps'].values() if n.get('whenIn'))
    node['whenIn'][0]['text'] = 'wrong instruction with the same node count'
    assert inventory(damaged, annotations, reference)['issues']


def test_inventory_rejects_advice_as_item_completion_proof():
    guide, annotations, reference = artifacts()
    node = next(s for sec in guide['sections'] for s in sec['steps'] if s.get('advice'))
    node['acquires'] = True
    assert any('advice auto-completes' in s for s in inventory(guide, annotations, reference)['issues'])


def test_inventory_amount_is_never_mistaken_for_one_item():
    import re
    guide, _, _ = artifacts()
    for section in guide['sections']:
        for step in section['steps']:
            if re.search(r'\binventor(?:y|ies)\s+(?:of|with)\b', step['text'], re.I):
                assert not step.get('acquires'), step


def test_curated_overrides_cannot_silently_replace_duplicate_keys():
    import yaml

    def check(node):
        if isinstance(node, yaml.MappingNode):
            keys = [k.value for k, _ in node.value]
            assert len(keys) == len(set(keys)), f'duplicate YAML keys: {keys}'
            for _, value in node.value:
                check(value)
        elif isinstance(node, yaml.SequenceNode):
            for value in node.value:
                check(value)

    check(yaml.compose((ROOT / 'curated/overrides.yaml').read_text(encoding='utf-8')))


def test_inventory_interaction_metadata_survives_stage_join_exactly():
    from pipeline.audit import every_instruction
    guide, _, _ = artifacts()
    actions = json.loads((ROOT / 'build/inventory_actions.json').read_text(encoding='utf-8'))
    found = 0
    from pipeline.merge_curated import own_item_operands
    for _, _, node in every_instruction(guide):
        # The stage's table where it has an answer for this sentence; otherwise
        # the step's own required items that the sentence says to use -- "put
        # the skull back" on the coffin step, which the table never sees because
        # its verb is not the first word. Exact either way.
        expected = (actions['questActions'].get(node.get('text'))
                    or own_item_operands(node.get('text') or '', node.get('items') or []))
        assert node.get('inventoryHighlightIds', []) == (expected or [])
        found += bool(expected)
    assert found > 0
    for section in guide['sections']:
        for step in section['steps']:
            assert step.get('inventoryAction') == actions['actions'].get(step['id'])

"""Whole-guide inventory for previously reported bug classes, not a live-playthrough claim.

Run after emit. Lists every affected step, not just the original reproduction.
The existing audit checks runtime contracts; this checks retention across stages
and records the populations exercised by the Java regression suite.
"""
import collections
import copy
import gzip
import json
from pathlib import Path

from pipeline.audit import every_instruction
from pipeline.merge_curated import choose_sides

ROOT = Path(__file__).resolve().parents[1]


def inventory(guide, annotated, reference):
    steps = [s for sec in guide['sections'] for s in sec['steps']]
    nodes = list(every_instruction(guide))
    groups = collections.defaultdict(list)
    issues = []
    annotations = {s['id']: s.get('annotation', {})
                   for sec in annotated['sections'] for s in sec['steps']}
    for step in steps:
        target = step.get('target') or {}
        flags = {
            'named_target_priority': bool(target.get('ids')) and not step.get('questFollow'),
            'quest_only_navigation': bool(step.get('questStep') or step.get('questContext')) and not target,
            'bounded_quest_follow': step.get('questFollow'),
            'known_staircase': step.get('approach'),
            'shop_purchase': annotations.get(step['id'], {}).get('buys'),
            'ground_spawns': step.get('spawns'),
            'item_completion': step.get('acquires'),
            'inventory_interaction': step.get('inventoryAction'),
            'manual_compound_completion': step.get('completionManual'),
            'diary_completion': step.get('diaryTask'),
            'manual_quest_goal': step.get('questStopUnresolved'),
            'quest_panel_handover': step.get('questDoneAtPanel') is not None,
        }
        for name, applies in flags.items():
            if applies:
                groups[name].append({'id': step['id'], 'text': step['text']})
        if step.get('advice') and step.get('acquires'):
            issues.append(f"advice auto-completes on items: {step['id']}")
        if step.get('acquires') and any(i.get('count', 1) <= 0 or not i.get('ids') for i in step.get('items', [])):
            issues.append(f"incomplete acquisition requirement: {step['id']}")

    # Merge may promote source-labelled dialogue choices. Everything else in
    # every retained instruction, including nested defaults, widgets and vars,
    # must survive intact. Comparing counts alone would miss swapped nodes.
    # inventoryHighlightIds is added by the separate interaction stage; its
    # exact emitted values are checked against that artifact in regression tests.
    expected_helpers = copy.deepcopy(reference['quests'])
    choose_sides({'sections': [{'steps': [{'merged': s} for s in steps]}],
                  'questHelpers': expected_helpers})

    def runtime_fields(value):
        if isinstance(value, dict):
            return {k: runtime_fields(v) for k, v in value.items()
                    if k not in ('itemAlternatives', 'inventoryHighlightIds')}
        if isinstance(value, list):
            return [runtime_fields(v) for v in value]
        return value

    for key, helper in guide['questHelpers'].items():
        if runtime_fields(helper) != runtime_fields(expected_helpers.get(key)):
            issues.append(f"extracted helper changed or lost fields during merge/emit: {key}")
    for key, task in guide.get('diaryTasks', {}).items():
        if runtime_fields(task) != runtime_fields(reference['tasks'].get(key)):
            issues.append(f"extracted diary instruction changed during merge/emit: {key}")

    for owner, value, node in nodes:
        for field in ('widgets', 'widgetPuzzles', 'icon', 'choices', 'whenIn', 'conditional', 'tiles', 'inventoryHighlightIds'):
            if field in node and node[field] is not None:
                groups['instruction_' + field].append(f'{owner}@{value}')
    unresolved = collections.Counter(i['name'] for s in steps for i in s.get('items', []) if not i.get('ids'))
    return {'contentHash': guide['contentHash'], 'sections': len(guide['sections']),
            'steps': len(steps), 'instructions': len(nodes),
            'widgetMarks': sum(len(n.get('widgets', [])) for _, _, n in nodes),
            'counts': {k: len(v) for k, v in groups.items()},
            'instances': dict(groups), 'unresolvedItems': unresolved.most_common(), 'issues': issues}


def main():
    guide = json.loads((ROOT / 'dist/guide.json').read_text(encoding='utf-8'))
    annotated = json.loads((ROOT / 'build/annotated.json').read_text(encoding='utf-8'))
    with gzip.open(ROOT / 'pinned/quest_steps.json.gz', 'rt', encoding='utf-8') as stream:
        reference = json.load(stream)
    result = inventory(guide, annotated, reference)
    bundled = ROOT.parent / 'b0aty-guide-plugin/src/main/resources/com/b0atyguide/guide.json'
    if bundled.exists():
        other = json.loads(bundled.read_text(encoding='utf-8'))
        if {k: v for k, v in guide.items() if k != 'generatedAt'} != {
                k: v for k, v in other.items() if k != 'generatedAt'}:
            result['issues'].append('bundled guide differs from emitted data')
    out = ROOT / 'build/guide-regression-audit.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('instances', 'unresolvedItems')}, indent=2))
    print('Top unresolved item names:', result['unresolvedItems'][:10])
    print('Full instance inventory:', out)
    return bool(result['issues'])


if __name__ == '__main__':
    raise SystemExit(main())

"""Resolve explicit inventory interactions; recipes come from cited source data.

Side input to merge_curated. Never modifies guide text or human overrides.
Unknown action operands and recipes are reported, never fuzzy-matched.
"""
import collections
import hashlib
import json
import random
import re
from pathlib import Path
try:
    from .annotate import strip_links
except ImportError:
    from annotate import strip_links

ROOT = Path(__file__).resolve().parents[1]
DIRECT = re.compile(r"^\s*(use|read|eat|drink|rub|wear|wield|equip|fill|empty|bury|clean|open|light)\s+", re.I)
MAKE = re.compile(r"^\s*(?:make|mix|create)\s+(?:(\d+)\s*x?\s+)?(.+?)[.!]?\s*$", re.I)


def normalized(name):
    return ' '.join(name.casefold().split())


def exact_item(name, entities):
    matches = {tuple(sorted(set(v.get('ids', [])))) for k, v in entities.items()
               if normalized(k) == normalized(name) and v.get('kind') == 'item' and v.get('ids')}
    # Duplicate cached spellings of the SAME entity are not competing entities.
    return list(next(iter(matches))) if len(matches) == 1 else []


def action_for(raw, entities, recipes):
    text = strip_links(raw).strip()
    made = MAKE.fullmatch(text)
    if made:
        candidates = [r for r in recipes if normalized(r['product']) == normalized(made[2])]
        if len(candidates) == 1:
            recipe = candidates[0]
            consumed = []
            for need in recipe['consumed']:
                choices = [exact_item(n, entities) for n in need['names']]
                if not all(choices):
                    return None, 'unresolved recipe ingredient'
                consumed.append({'ids': sorted({i for ids in choices for i in ids}), 'count': need['count']})
            produced = exact_item(recipe['product'], entities)
            if not produced:
                return None, 'unresolved recipe product'
            return {'kind': 'recipe', 'source': recipe['source'], 'count': int(made[1] or 1),
                    'highlightIds': sorted({i for n in consumed for i in n['ids']}),
                    'consumed': consumed,
                    'produced': {'ids': produced, 'count': recipe['produced']['count']}}, None
        return None, 'recipe is not verified'
    direct = DIRECT.match(text)
    if not direct:
        return None, None
    # Filled water containers are the result of filling, not its operands.
    # Combat/currency uses also do not instruct an inventory interaction.
    if direct[1].lower() == 'fill' and re.search(r'\bof water\b', text, re.I):
        return None, 'fill input state needs source verification'
    if direct[1].lower() == 'use' and re.search(r'\b(?:to kill|for golems|per inv|to enter)\b', text, re.I):
        return None, 'use describes combat, currency, or supplies'
    # The action's operands, not every item mentioned later in the sentence.
    tail = re.split(r"[.;\[\(]|\s+(?:and|then|to|for|at|from|in)\s+|\s*&\s*", text[direct.end():], maxsplit=1, flags=re.I)[0]
    operands = re.split(r"\s+(?:on|with)\s+", tail, maxsplit=1, flags=re.I) if direct[1].lower() == 'use' else [tail]
    ids, missing = set(), []
    for operand in operands:
        name = re.sub(r"^(?:the|a|an|your)\s+", '', operand.strip(), flags=re.I)
        name = re.sub(r"^\d+\s*x?\s+", '', name)
        found = exact_item(name, entities)
        ids.update(found)
        if not found:
            missing.append(name)
    if ids:
        reason = 'unresolved operand(s): ' + ', '.join(missing) if missing else None
        return {'kind': 'interact', 'highlightIds': sorted(ids)}, reason
    return None, 'inventory operand not resolved exactly'


def texts_in(value):
    """Instruction prose from pinned Quest Helper data, including nested branches."""
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            yield value['text']
        for child in value.values():
            yield from texts_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts_in(child)


def main():
    doc = json.loads((ROOT / 'build/annotated.json').read_text(encoding='utf-8'))
    entities = json.loads((ROOT / 'build/entities.json').read_text(encoding='utf-8'))
    recipes = json.loads((ROOT / 'data/inventory_recipes.json').read_text(encoding='utf-8'))['recipes']
    actions, unresolved, samples = {}, [], []
    steps = [s for section in doc['sections'] for s in section['steps']]
    for step in steps:
        action, reason = action_for(step['raw'], entities, recipes)
        if action:
            actions[step['id']] = action
        if reason:
            unresolved.append({'id': step['id'], 'raw': step['raw'], 'reason': reason})
        samples.append({'raw': step['raw'], 'action': action})
    quest_source = ROOT / 'build/quest_steps.json'
    quest_texts = sorted(set(texts_in(json.loads(quest_source.read_text(encoding='utf-8')))))
    quest_actions, quest_unresolved = {}, []
    for raw in quest_texts:
        action, reason = action_for(raw, entities, recipes)
        if action:
            quest_actions[raw] = action['highlightIds']
        if reason:
            quest_unresolved.append({'raw': raw, 'reason': reason})
    report = {'questTextsIn': len(quest_texts), 'questInteractionsOut': len(quest_actions),
              'questUnresolved': quest_unresolved, 'stepsIn': len(steps), 'actionsOut': len(actions),
              'byKind': dict(collections.Counter(a['kind'] for a in actions.values())),
              'unresolved': unresolved, 'sample': random.Random(7).sample(samples, 5)}
    (ROOT / 'build/inventory_actions.json').write_text(json.dumps({'sourceHash': hashlib.sha256((ROOT / 'build/annotated.json').read_bytes()).hexdigest(), 'questSourceHash': hashlib.sha256(quest_source.read_bytes()).hexdigest(), 'questActions': quest_actions, 'actions': actions}, indent=2), encoding='utf-8')
    (ROOT / 'build/inventory-actions-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('unresolved', 'questUnresolved')}, indent=2))
    print('Unresolved by reason:', collections.Counter(r['reason'] for r in unresolved))
    print('Top unresolved raw instructions:', collections.Counter(r['raw'] for r in unresolved).most_common(10))


if __name__ == '__main__':
    main()

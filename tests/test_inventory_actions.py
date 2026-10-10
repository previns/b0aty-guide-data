import json
from pathlib import Path

import pytest
from pipeline.build_inventory_actions import action_for, exact_item
from pipeline.merge_curated import acquisition_blocker
from pipeline.validate import INVENTORY_ACTION
import jsonschema

RECIPES = json.loads((Path(__file__).parents[1] / 'data/inventory_recipes.json').read_text())['recipes']
ENTITIES = {name: {'kind': 'item', 'ids': [id]} for name, id in [
    ('Clay', 434), ('Soft Clay', 1761), ('Jug of Water', 1937),
    ('Bucket of Water', 1929), ('Bowl of Water', 1921), ('Vial of Water', 227),
    ('Feather', 314), ('Enchanted scroll', 21259)]}


def test_soft_clay_highlights_only_consumed_inputs():
    action, reason = action_for('Make Soft Clay', ENTITIES, RECIPES)
    assert reason is None
    assert action['produced'] == {'ids': [1761], 'count': 1}
    assert action['highlightIds'] == [227, 434, 1921, 1929, 1937]
    jsonschema.validate(action, INVENTORY_ACTION)


def test_explicit_recipe_quantity():
    action, _ = action_for('Make 2x Soft Clay.', ENTITIES, RECIPES)
    assert action['count'] == 2


@pytest.mark.parametrize('raw', ['Mine 4 Clay and make Soft Clay',
    'Fill the buckets and make 2x Soft Clay. Refill the Buckets',
    'Withdraw: Soft Clay', 'Keep Soft Clay for later'])
def test_compound_and_supply_steps_do_not_become_recipes(raw):
    action, _ = action_for(raw, ENTITIES, RECIPES)
    assert not action or action['kind'] != 'recipe'


def test_use_highlights_both_exact_operands():
    action, reason = action_for('Use your Feather on the Enchanted scroll in your inventory', ENTITIES, RECIPES)
    assert action['highlightIds'] == [314, 21259]
    assert reason is None


def test_ambiguous_and_unresolved_entities_never_match():
    ambiguous = dict(ENTITIES, clay={'kind': 'item', 'ids': [999]})
    assert exact_item('Clay', ambiguous) == []
    assert action_for('Make Soft Clay', ambiguous, RECIPES)[0] is None
    assert action_for('Make fake Soft Clay', ENTITIES, RECIPES)[0] is None
    assert exact_item('Some Clay', ENTITIES) == []


@pytest.mark.parametrize('raw', ['Buy Desert Robes & wear them',
    'Collect 11 Logs & make 10 Planks', 'Mine 4 Clay and make Soft Clay',
    'Buy 5 Jugs of wine, hop and buy 10 total', 'Withdraw: 36 noted lockpicks', 'Mine 5 clay while yoinking the bird feather',
    'Loot 3 Logs. Drop these', 'Collect trading sticks as you need roughly 1,300'])
def test_ownership_cannot_complete_compound_or_ambiguous_amounts(raw):
    assert acquisition_blocker(raw, {'items': [{'ids': [1], 'count': 1}]})


def test_simple_pickup_and_capacity_note_are_still_supported():
    assert acquisition_blocker('Take 2 Clay', {'items': [{'ids': [434], 'count': 2}]}) is None
    assert acquisition_blocker('Withdraw: Clay (1 Inventory Slot)', {'items': [{'ids': [434]}]}) is None


def test_overlapping_requirements_cannot_count_same_stack_twice():
    assert acquisition_blocker('Withdraw: tools', {'items': [{'ids': [1, 2]}, {'ids': [2]}]})


def test_recipe_schema_rejects_missing_inputs_and_invalid_count():
    action, _ = action_for('Make Soft Clay', ENTITIES, RECIPES)
    action['count'] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(action, INVENTORY_ACTION)
    del action['count']
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(action, INVENTORY_ACTION)


def test_full_water_container_is_not_a_fill_operand():
    action, reason = action_for('Fill a bucket of Water at the Well', ENTITIES, RECIPES)
    assert action is None
    assert reason


def test_currency_use_is_not_an_inventory_click():
    entities = {'ectotokens': {'kind': 'item', 'ids': [4278]}}
    assert action_for('Use 2 ectotokens to enter Port Phasmatys', entities, RECIPES)[0] is None


def test_partial_interaction_reports_unresolved_operand():
    action, reason = action_for('Use unknown dye on Clay', ENTITIES, RECIPES)
    assert action['highlightIds'] == [434]
    assert 'unknown dye' in reason


def test_quest_interactions_join_only_prose_not_widget_text_lists():
    from pipeline.merge_curated import attach_inventory_interactions
    value = {'text': 'Use Clay on water', 'whenIn': [{'text': 'Pickpocket for a key', 'icon': 1}],
             'when': {'widget': {'text': ['Use Clay on water']}}}
    attach_inventory_interactions(value, {'Use Clay on water': [434]})
    assert value['inventoryHighlightIds'] == [434]
    assert 'inventoryHighlightIds' not in value['whenIn'][0]
    assert 'inventoryHighlightIds' not in value['when']['widget']

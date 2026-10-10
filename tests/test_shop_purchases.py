from pipeline.annotate import annotate_step, split_item_list
from pipeline.build_quest_steps import item_alternatives
import json
from pathlib import Path


def test_lowercase_goods_keep_quantity():
    items = annotate_step('Buy 10x Pineapple, 2x orange, 3x Lemon')['items']
    assert items[1] == {'name': 'orange', 'count': 2}


def test_thousands_and_parenthetical_costs_are_not_item_separators():
    assert split_item_list('1,200 Nature Runes, 500 Law Runes') == [
        {'name': 'Nature Runes', 'count': 1200}, {'name': 'Law Runes', 'count': 500}]
    assert split_item_list('Chaos Runes (29,000 per Onyx), Chisel') == [
        {'name': 'Chaos Runes'}, {'name': 'Chisel'}]


def test_minimum_quantity_plus_is_not_an_item_separator():
    assert annotate_step('Buy 100+ Cosmic Runes + 20 Law Runes')['items'] == [
        {'name': 'Cosmic Runes', 'count': 100}, {'name': 'Law Runes', 'count': 20}]


def test_lowercase_items_survive_collecting_and_mining_too():
    assert annotate_step('Collect 2x redberries')['items'] == [{'name': 'redberries', 'count': 2}]
    assert annotate_step('Mine 10x clay')['items'] == [{'name': 'clay', 'count': 10}]


def test_articles_do_not_eat_the_start_of_item_names():
    assert annotate_step('Collect Ashes')['items'] == [{'name': 'Ashes'}]
    assert annotate_step('Collect all Ashes')['items'] == [{'name': 'Ashes'}]
    assert annotate_step('Take an egg')['items'] == [{'name': 'egg'}]


def test_only_explicit_resolved_substitutes_are_exported():
    source = '''food = new ItemRequirement("Food (can be Other food)", ItemID.FOOD);
food.addAlternates(ItemID.OTHER);'''
    assert item_alternatives(source, {'FOOD': 1, 'OTHER': 2}) == {
        '1': {'ids': [1, 2], 'notes': ['Other food']}}
    assert item_alternatives(source, {'FOOD': 1}) == {}
    assert item_alternatives(source.replace(' (can be Other food)', ''), {'FOOD': 1, 'OTHER': 2}) == {}


def test_conflicting_substitutes_fail_closed():
    source = '''a = new ItemRequirement("Food (can be Other)", ItemID.FOOD);
b = new ItemRequirement("Food (can be Other)", ItemID.FOOD);
a.addAlternates(ItemID.OTHER);
b.addAlternates(ItemID.THIRD);'''
    assert item_alternatives(source, {'FOOD': 1, 'OTHER': 2, 'THIRD': 3}) == {}


def test_generated_bank20_shop_goods():
    guide = json.loads((Path(__file__).resolve().parents[1] / 'dist/guide.json').read_text(encoding='utf-8'))
    steps = {s['id']: s for section in guide['sections'] for s in section['steps']}
    assert set(steps['2307ddc79b']['items'][0]['ids']) == {2217, 2243, 9538}
    assert {'name': 'orange', 'ids': [2108], 'count': 2} in steps['2788d49340']['items']


def test_authorised_contextual_items_do_not_use_other_items_with_similar_names():
    guide = json.loads((Path(__file__).resolve().parents[1] / 'dist/guide.json').read_text(encoding='utf-8'))
    steps = {s['id']: s for section in guide['sections'] for s in section['steps']}
    assert steps['54e5f491c0']['items'] == [{'name': 'bananas', 'ids': [1963], 'count': 10}]
    assert steps['1f9257ad78']['items'] == [{'name': 'rum', 'ids': [431]}]
    assert {i['name']: i['ids'] for i in steps['260e82444c']['items']} == {
        'Raw Bear Meat': [2136], 'Bones': [526], 'fur': [948]}

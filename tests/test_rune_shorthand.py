from pipeline.annotate import split_item_list
import json
from pathlib import Path


def test_bank24_independent_rune_quantities():
    assert split_item_list('Mind/6xAir/6xEarth/All Water Runes') == [
        {'name': 'Mind Runes'}, {'name': 'Air Runes', 'count': 6},
        {'name': 'Earth Runes', 'count': 6}, {'name': 'Water Runes'}]


def test_shared_rune_suffix_and_explicit_individual_counts():
    assert split_item_list('2xLaw/3xFire/Air Runes') == [
        {'name': 'Law Runes', 'count': 2}, {'name': 'Fire Runes', 'count': 3},
        {'name': 'Air Runes'}]


def test_unknown_rune_shorthand_is_not_guessed():
    assert split_item_list('Mystery/All Water Runes') != [
        {'name': 'Mystery Runes'}, {'name': 'Water Runes'}]


def test_bank24_emitted_tags_and_all_quantity_stays_manual():
    guide = json.loads((Path(__file__).resolve().parents[1] / 'dist/guide.json').read_text(encoding='utf-8'))
    step = next(s for sec in guide['sections'] for s in sec['steps'] if s['id'] == 'd7670bdda2')
    items = {i['name']: i for i in step['items']}
    assert items['Mind Runes']['ids'] == [558]
    assert items['Air Runes']['ids'] == [556] and items['Air Runes']['count'] == 6
    assert items['Earth Runes']['ids'] == [557] and items['Earth Runes']['count'] == 6
    assert items['Water Runes']['ids'] == [555]
    assert not step.get('acquires')

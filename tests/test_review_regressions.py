import pytest

from pipeline import build_quest_steps as q
from pipeline.refresh import STAGES


@pytest.mark.parametrize('args', [
    ['new WorldPoint(1, 2, 0)', 'unresolvedCorner'],
    ['new WorldPoint(1, 2, 0).changed()'],
    ['12345', 'unknownPlane'],
    ['12345', '0', 'extra'],
])
def test_zone_does_not_drop_unreadable_constructor_arguments(args):
    assert q.zone_box(args) is None


def test_known_zone_constructors_still_match_source():
    assert q.zone_box(['new WorldPoint(1, 2, 0)', 'new WorldPoint(3, 4, 1)']) == [1, 2, 0, 3, 4, 1]
    assert q.zone_box(['12345', '1']) == [3072, 3648, 1, 3136, 3712, 1]


def test_widget_child_is_not_mistaken_for_parent_presence():
    assert q.requirement_of('new WidgetPresenceRequirement(10, 2, 3)', {}, {}) is None
    assert q.requirement_of('new WidgetPresenceRequirement(10, 2, -1)', {}, {}) == {'open': (10 << 16) | 2}
    assert q.requirement_of('new WidgetPresenceRequirement(10, 2)', {}, {}) == {'open': (10 << 16) | 2}


def test_full_refresh_includes_spawn_source_before_merging():
    names = [name for name, _, _ in STAGES]
    assert names.index('fetch_item_spawns') < names.index('merge_curated')
    assert next(network for name, network, _ in STAGES if name == 'fetch_item_spawns')
    assert 'fetch_item_spawns' not in [name for name, network, _ in STAGES if not network]

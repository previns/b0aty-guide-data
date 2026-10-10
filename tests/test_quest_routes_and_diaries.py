from pathlib import Path
import json
from pipeline.build_quest_steps import line_points
from pipeline.build_diary_tasks import whole_diary
from pipeline.annotate import split_item_list


def test_literal_route_keeps_order_and_repeated_points():
    source = "p = List.of(new WorldPoint(1, 2, 0), new WorldPoint(3, 4, 0), new WorldPoint(1, 2, 0)); step.setLinePoints(p);"
    assert line_points(source) == {"step": [[1, 2, 0], [3, 4, 0], [1, 2, 0]]}


def test_dynamic_or_reassigned_routes_stay_unresolved():
    source = "p = List.of(new WorldPoint(1, 2, 0), new WorldPoint(3, 4, 0)); p = other; step.setLinePoints(p);"
    assert line_points(source) == {}
    assert line_points("step.setLinePoints(List.of(new WorldPoint(x, 2, 0), new WorldPoint(3, 4, 0)));") == {}


def test_cast_and_inline_route():
    assert line_points("((NpcStep) (step)).setLinePoints(Arrays.asList(new WorldPoint(1, 2, 0), new WorldPoint(3, 4, 0)));") == {"step": [[1, 2, 0], [3, 4, 0]]}


def test_whole_diary_does_not_complete_individual_or_compound_tasks():
    row = {"varbit": 4503, "varbitValue": 1, "varbitName": "FALADOR_EASY_REWARD", "title": "Falador Easy Diary"}
    signals = {"Falador Easy Diary": row}
    assert whole_diary("Complete Falador Easy Diary [Lamp on Herblore]", signals)["varbit"] == 4503
    assert whole_diary("Complete the Falador Easy Diary", signals)["varbit"] == 4503
    assert whole_diary("Complete a lap [Falador Easy Diary]", signals) is None
    assert whole_diary("Complete Falador Easy Diary and use the lamp", signals) is None
    assert whole_diary("Complete Unknown Easy Diary", signals) is None


def test_dragonhide_shared_prefix_is_scoped_and_keeps_counts():
    assert split_item_list("Green D hide Chaps, 2x Vambs & Coif") == [
        {"name": "green d'hide chaps"}, {"name": "green d'hide vambraces", "count": 2}, {"name": "Coif"}]
    assert split_item_list("Green D hide Chaps, Coif, Vambs")[-1] == {"name": "Vambs"}


def test_published_lost_tribe_route_is_preserved():
    guide = json.loads((Path(__file__).resolve().parents[1] / "dist/guide.json").read_text(encoding="utf-8"))
    def leaves(value):
        if isinstance(value, dict):
            yield value
            for child in value.values(): yield from leaves(child)
        elif isinstance(value, list):
            for child in value: yield from leaves(child)
    routes = [s["linePoints"] for s in leaves(guide["questHelpers"]["thelosttribe"]) if "Travel through the tunnels." in str(s.get("text", "")) and "linePoints" in s]
    assert routes and all(len(route) == 36 for route in routes)
    assert routes[0][0] == [3222, 9618, 0]
    assert routes[0][-1] == [3317, 9612, 0]


def test_static_reverse_routes_and_null_segments_are_preserved():
    source = "path = Arrays.asList(new WorldPoint(1, 2, 0), null, new WorldPoint(3, 4, 0)); step.setLinePoints(Lists.reverse(path));"
    assert line_points(source) == {"step": [[3, 4, 0], None, [1, 2, 0]]}
    assert line_points(source + " path.add(new WorldPoint(5,6,0));") == {}

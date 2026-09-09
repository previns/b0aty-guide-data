"""Which dialogue option a route takes, where quest-helper labels them.

Hazeel Cult puts "I'll help you." and "I won't help you." in the same menu and
they take the quest in opposite directions. quest-helper says which is which by
relabelling them with `addDialogChange`; the guide says which it wants in its
own bracket, "Start Hazeel Cult [Side with Hazeel]".
"""
from pipeline import build_quest_steps as q
from pipeline import merge_curated as m


def test_the_relabelled_option_and_its_note_are_read():
    got = q.dialogue_changes('''
talkToClivet.addDialogChange("I'll help you.", "I'll help you. (side with Hazeel)");
talkToClivet.addDialogChange("I won't help you.", "I won't help you. (side with Ceril)");
''')
    assert got["talkToClivet"] == [
        {"option": "I'll help you.", "note": "side with Hazeel"},
        {"option": "I won't help you.", "note": "side with Ceril"},
    ]


def test_a_rename_that_does_not_extend_the_original_is_kept_whole():
    """Better a note that reads oddly than one guessed at by cutting."""
    got = q.dialogue_changes('talk.addDialogChange("Yes.", "Agree to help");')
    assert got["talk"] == [{"option": "Yes.", "note": "Agree to help"}]


def _doc(tag, notes):
    return {
        "sections": [{"steps": [{"merged": {
            "questHelper": "q", "tags": [{"tag": tag}]}}]}],
        "questHelpers": {"q": {"steps": {"0": {
            "text": "Talk to them.",
            "dialogue": ["Hello."],
            "choices": [{"option": o, "note": n} for o, n in notes],
        }}}},
    }


def test_the_side_the_guide_names_is_added_to_the_highlighted_options():
    doc = _doc("Side with Hazeel", [
        ("I'll help you.", "side with Hazeel"),
        ("I won't help you.", "side with Ceril"),
    ])
    assert m.choose_sides(doc) == 1
    said = doc["questHelpers"]["q"]["steps"]["0"]["dialogue"]
    assert said == ["Hello.", "I'll help you."]


def test_a_tag_naming_no_side_marks_nothing():
    doc = _doc("Recipe for Disaster", [
        ("I'll help you.", "side with Hazeel"),
        ("I won't help you.", "side with Ceril"),
    ])
    assert m.choose_sides(doc) == 0
    assert doc["questHelpers"]["q"]["steps"]["0"]["dialogue"] == ["Hello."]


def test_a_route_that_names_both_sides_is_a_contradiction_not_a_vote():
    doc = _doc("Side with Hazeel", [
        ("I'll help you.", "side with Hazeel"),
        ("I won't help you.", "side with Ceril"),
    ])
    # A second step on the same quest asking for the other side.
    doc["sections"][0]["steps"].append({"merged": {
        "questHelper": "q", "tags": [{"tag": "Side with Ceril"}]}})
    assert m.choose_sides(doc) == 0
    assert doc["questHelpers"]["q"]["steps"]["0"]["dialogue"] == ["Hello."]

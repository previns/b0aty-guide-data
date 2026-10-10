"""The other things a step also points at.

quest-helper says "this step targets these as well" two ways:

    talkToChildren.addAlternateNpcs(NpcID.WILOUGH);
    ((ObjectStep) findDaconiaStone).addAlternateObjects(ObjectID.LARGEROOT2_GNOME);

It casts whenever the field is declared as a plain QuestStep, and it does so 254
times out of 482. Reading only the bare form dropped more than half of every
step's alternate ids across 61 quests -- Desert Treasure II lost 20, Rag and
Bone Man 19, Shades of Mort'ton 16.

The Grand Tree is the one the author noticed: there are two roots to search
under the tree and only one of them was ever outlined.
"""
from pipeline import build_quest_steps as q


def test_the_bare_form_is_read():
    got = q.alternate_ids('talkToChildren.addAlternateNpcs(NpcID.WILOUGH);')
    assert got == {"talkToChildren": ["WILOUGH"]}


def test_the_cast_form_is_read():
    got = q.alternate_ids(
        '((ObjectStep) findDaconiaStone).addAlternateObjects(ObjectID.LARGEROOT2_GNOME);')
    assert got == {"findDaconiaStone": ["LARGEROOT2_GNOME"]}


def test_both_forms_land_on_the_same_step():
    got = q.alternate_ids(
        'findGloughJournal.addAlternateObjects(ObjectID.A);\n'
        '((ObjectStep) findGloughJournal).addAlternateObjects(ObjectID.B);\n')
    assert got["findGloughJournal"] == ["A", "B"]


def test_the_grand_tree_ships_both_roots():
    """End to end, in the file the plugin loads."""
    import io, json
    from pathlib import Path
    guide = json.loads(
        (Path(__file__).resolve().parent.parent.parent / "b0aty-guide-plugin"
         / "src" / "main" / "resources" / "com" / "b0atyguide" / "guide.json"
         ).read_text(encoding="utf-8"))

    def walk(node):
        yield node
        for branch in node.get("whenIn") or []:
            yield from walk(branch)

    roots = [n for slot in guide["questHelpers"]["thegrandtree"]["steps"].values()
             for n in walk(slot)
             if "Search the roots" in (n.get("text") or "")]
    assert roots, "the roots step should ship"
    for node in roots:
        assert node.get("ids") == [1985, 1986], node.get("ids")

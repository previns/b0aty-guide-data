import json
from pathlib import Path
from pipeline.build_quest_steps import dialogue_rules, every


def test_exclusions_are_not_unconditional_answers():
    assert dialogue_rules('s.addDialogStepWithExclusions("None.", "A.", "B.");') == {
        's': [{'text': 'None.', 'unless': ['A.', 'B.']}]}
    assert dialogue_rules('s.addDialogStepWithExclusion("Next", "Answer");') == {
        's': [{'text': 'Next', 'unless': ['Answer']}]}
    assert dialogue_rules('s.addDialogStepWithExclusions("None.", unknown);') == {}


def test_grand_tree_return_to_king_retains_conditional_fallback():
    guide = json.loads((Path(__file__).resolve().parents[1] / 'dist/guide.json').read_text(encoding='utf-8'))
    nodes = list(every(guide['questHelpers']['thegrandtree']['steps']))
    node = next(n for n in nodes if 'I think so!' in n.get('dialogue', []))
    assert node['dialogueRules'] == [{'text': 'None of the above.', 'unless': [
        "A man came to me with the King's seal.", 'I gave the man Daconia rocks.']}]
    assert 'None of the above.' not in node['dialogue']

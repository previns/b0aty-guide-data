"""Preserve receiver, branch order and item quantities; never widen unknowns."""
import json
from pathlib import Path

import pytest

from pipeline import build_quest_steps as q


def test_constructor_chain_belongs_to_the_variable_not_enclosing_class():
    text = '''class Example extends BasicQuestHelper {
      var route = new ConditionalStep(this, fallback)
        .addStep(and(first, second), stepOne)
        .addStep(third, stepTwo, false);
      route.addStep(fourth, stepThree).addStep(fifth, stepFour);
      this.addStep(sixth, stepFive);
    }'''
    assert q.add_steps(text) == {
        "route": [("and(first, second)", "stepOne"), ("third", "stepTwo"),
                  ("fourth", "stepThree"), ("fifth", "stepFour")],
        "Example": [("sixth", "stepFive")],
    }


def test_unknown_factory_chain_does_not_leak_into_enclosing_class():
    assert q.add_steps('class Example { var route = unknown().addStep(a, b); }') == {}


def test_fluent_chains_stop_at_statement_boundaries_and_skip_quoted_parentheses():
    assert q.add_steps('''class Example {
      a = new ConditionalStep(this, fallback, "a ) .addStep").addStep(x, one);
      b = new ConditionalStep(this, fallback).addStep(y, two);
    }''') == {"a": [("x", "one")], "b": [("y", "two")]}


def test_lockability_argument_is_not_mistaken_for_the_step():
    assert q.add_steps('route.addStep(a, target, true);') == {"route": [("a", "target")]}
    assert q.add_steps('route.addStep(a, target, unknown);') == {}


@pytest.mark.parametrize("expression,count", [("coins.quantity(3)", 3), ("coins.quantity(NEEDED)", 4)])
def test_quantity_copies_a_resolved_item_requirement(expression, count):
    decls = {"coins": ("ItemRequirement", ['"Coins"', "ItemID.COINS", "1"]),
             "NEEDED": (q.INT_CONSTANT, ["4"])}
    actual = q.requirement_of(expression, decls, {})
    assert actual == {"item": {"name": "Coins", "constant": "COINS", "count": count}}
    assert q.requirement_of("coins", decls, {})["item"]["count"] == 1


@pytest.mark.parametrize("quantity", ["0", "-1", "unknown", "needed()"])
def test_unknown_or_nonpositive_quantity_is_not_turned_into_one(quantity):
    decls = {"coins": ("ItemRequirement", ['"Coins"', "ItemID.COINS"])}
    assert q.requirement_of(f"coins.quantity({quantity})", decls, {}) is None


def test_biohazard_chemicals_were_readable_but_attached_to_the_wrong_owner():
    path = Path(q.DEFAULT_SOURCE) / "src/main/java/com/questhelper/helpers/quests/biohazard/Biohazard.java"
    text = q.strip_comments(path.read_text(encoding="utf-8"))
    decls, wants = q.declarations(text), q.item_declarations(text)
    condition = q.requirement_of("hasChemicals", decls, wants)
    assert {p["item"]["constant"] for p in condition["any"]} == {
        "ETHENEA", "LIQUID_HONEY", "SULPHURIC_BROLINE"}
    branches = q.add_steps(text)
    assert ("hasChemicals", "giveChemicals") in branches["smuggleInChemicals"]
    assert "Biohazard" not in branches
    assert len(branches["returnToElenaWithDistillator"]) == 8

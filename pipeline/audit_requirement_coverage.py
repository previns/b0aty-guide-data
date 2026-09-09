"""Measure source branch predicates, separately from shipped/reachable nodes.

No weakened AND/OR conditions: supported means the complete predicate resolves.
Unsupported leaves are counted once per blocked branch, not as partial credit.
"""
import collections
import json
import re
from pathlib import Path

from pipeline import build_quest_steps as q

ROOT = Path(__file__).resolve().parents[1]


def main():
    ids = json.loads((ROOT / "build/ids.json").read_text(encoding="utf-8"))
    atlas = json.loads((ROOT / "build/atlas.json").read_text(encoding="utf-8"))
    q.VAR_IDS.update(ids)
    source_root = Path(q.DEFAULT_SOURCE) / "src/main/java/com/questhelper/helpers"
    totals = collections.Counter()
    blockers = collections.Counter()
    examples = {}
    folders = []
    original = q.requirement_of
    failures = []
    without_quantity = False

    def traced(name, decls, wants, seen=frozenset()):
        if without_quantity and re.fullmatch(r"\w+\.quantity\s*\([^()]+\)", name.strip()):
            result = None
        else:
            result = original(name, decls, wants, seen)
        if result is None:
            failures.append(name)
        return result

    q.requirement_of = traced
    try:
        for folder in sorted({p.parent for p in source_root.rglob("*.java")}):
            text = q.strip_comments("\n".join(p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.java"))))
            decls, wants = q.declarations(text), q.item_declarations(text)
            q.follow_methods(text, decls, q.method_returns(text))
            stats = collections.Counter()
            for owner, branches in q.add_steps(text).items():
                for condition, target in branches:
                    if not condition:
                        continue
                    stats["sourceBranchPredicates"] += 1
                    without_quantity = True
                    before = traced(condition, decls, wants)
                    if before is not None and q.resolve_requirement(before, ids, atlas.get("collections", {})):
                        stats["supportedWithoutQuantity"] += 1
                    without_quantity = False
                    failures.clear()
                    after = traced(condition, decls, wants)
                    if after is not None and q.resolve_requirement(after, ids, atlas.get("collections", {})):
                        stats["supported"] += 1
                        continue
                    leaf = failures[0] if failures else "unresolved IDs"
                    kind = decls.get(leaf, ("expression",))[0]
                    if leaf in ("true", "false"):
                        kind = "remembered Conditions boolean (stateful)"
                    elif kind in (q.EXPRESSION, "expression"):
                        expression = decls.get(leaf, (None, [leaf]))[1][0]
                        method = re.search(r"\.([A-Za-z]+)\s*\(", expression)
                        kind = "method: " + method[1] if method else "unresolved expression/name"
                    blockers[kind] += 1
                    examples.setdefault(kind, [])
                    if len(examples[kind]) < 4:
                        examples[kind].append({"folder": str(folder.relative_to(source_root)),
                                               "owner": owner, "condition": condition,
                                               "blockedAt": leaf, "target": target})
            if stats:
                totals.update(stats)
                folders.append({"folder": str(folder.relative_to(source_root)), **stats})
    finally:
        q.requirement_of = original
    report = {"scope": "Written source branch predicates across helper folders, not reachable shipped coverage",
              "totals": dict(totals), "blockers": dict(blockers.most_common()),
              "examples": examples, "folders": folders}
    path = ROOT / "build/requirement-coverage.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["scope"])
    print(json.dumps(report["totals"]))
    print("Unsupported complete predicates by first blocking leaf:")
    for kind, count in blockers.most_common(12):
        print(f"{count:5} {kind}")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
